"""Single-request LLM decisions, preserving structured tool calls."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments_json: str


@dataclass(frozen=True)
class LlmDecision:
    text: str = ''
    tool_calls: tuple[ToolCall, ...] = ()


def failure_details(error: Exception) -> tuple[str, int | None, str]:
    """Expose useful categories without logging provider bodies or user messages."""
    status = getattr(error, 'status_code', None)
    if type(status) is not int:
        status = None
    if 'reasoning_content' in str(error).lower():
        reason = 'reasoning_history_required'
    elif isinstance(error, TimeoutError):
        reason = 'timeout'
    elif status in (401, 403):
        reason = 'authentication'
    elif status == 429:
        reason = 'rate_limit'
    elif status == 400:
        reason = 'invalid_request'
    elif status is not None and status >= 500:
        reason = 'upstream_error'
    elif isinstance(error, ValueError) and str(error) == 'Empty model response':
        reason = 'empty_response'
    else:
        reason = 'unknown'
    return type(error).__name__, status, reason


async def complete_once(messages: list[dict[str, str]], config: dict,
                        tools: list[dict]) -> LlmDecision:
    import asyncio
    import litellm

    model = config['model']
    if '/' not in model:
        model = f'openai/{model}'
    timeout = config.get('timeout_seconds', 30)
    token_limit = config.get('short_conversation_max_tokens') or config.get('max_tokens', 800)
    request_options = {}
    model_name = model.rsplit('/', 1)[-1]
    if model_name.startswith('deepseek-v4-') or model_name in {'deepseek-flash', 'deepseek-pro'}:
        # V4 defaults to thinking and requires reasoning_content on every assistant
        # history entry when tools are present. This one-shot router stores bounded
        # program summaries, so use non-thinking mode rather than replay reasoning.
        request_options['extra_body'] = {'thinking': {'type': 'disabled'}}
    response = await asyncio.wait_for(litellm.acompletion(
        model=model, messages=messages, api_key=config.get('api_key'),
        base_url=config.get('base_url'), temperature=float(config.get('temperature', .7)),
        max_tokens=int(token_limit), tools=tools, tool_choice='auto',
        timeout=timeout, max_retries=0, num_retries=0,
        **request_options,
    ), timeout=timeout)
    logger = config.get('logger')
    usage = getattr(response, 'usage', None)
    if not response.choices:
        raise ValueError('Empty model response')
    message = response.choices[0].message
    calls = tuple(ToolCall(call.function.name, call.function.arguments)
                  for call in (message.tool_calls or []))
    if logger:
        logger.info('LLM tool decision: llm_requests=1 tool_calls=%s prompt_tokens=%s completion_tokens=%s',
                    len(calls), getattr(usage, 'prompt_tokens', None), getattr(usage, 'completion_tokens', None))
    text = message.content or ''
    if not isinstance(text, str) or (not text.strip() and not calls):
        raise ValueError('Empty model response')
    return LlmDecision(text=text.strip(), tool_calls=calls)
