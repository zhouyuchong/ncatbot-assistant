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


async def complete_once(messages: list[dict[str, str]], config: dict,
                        tools: list[dict]) -> LlmDecision:
    import asyncio
    import litellm

    model = config['model']
    if '/' not in model:
        model = f'openai/{model}'
    timeout = config.get('timeout_seconds', 30)
    token_limit = config.get('short_conversation_max_tokens') or config.get('max_tokens', 800)
    response = await asyncio.wait_for(litellm.acompletion(
        model=model, messages=messages, api_key=config.get('api_key'),
        base_url=config.get('base_url'), temperature=float(config.get('temperature', .7)),
        max_tokens=int(token_limit), tools=tools, tool_choice='auto',
        timeout=timeout, max_retries=0, num_retries=0,
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
