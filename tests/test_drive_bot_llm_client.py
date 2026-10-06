import asyncio
import sys
import types
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, Mock, patch
import tests.bootstrap
from ncatbot_assistant.drive_bot import llm_client
from ncatbot_assistant.drive_bot.config import get_llm_tools_config


def response(text=None, calls=None, usage=None):
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(
        content=text, tool_calls=calls or []))], usage=usage)


def call(name='jm_download', args='{"album_id":123}'):
    return types.SimpleNamespace(id='call_1', type='function', function=types.SimpleNamespace(name=name, arguments=args))


class LlmClientTest(IsolatedAsyncioTestCase):
    async def complete(self, result=None, error=None, extra=None):
        api = AsyncMock(return_value=result, side_effect=error)
        config = dict(model='test', api_key='key', base_url='https://example.com', temperature=0.2,
                      max_tokens=800, short_conversation_max_tokens=321, timeout_seconds=30, logger=Mock())
        config.update(extra or {})
        with patch.dict(sys.modules, {'litellm': types.SimpleNamespace(acompletion=api)}):
            try:
                return await llm_client.complete_once([{'role': 'user', 'content': 'hello'}], config, [{'type': 'function'}]), api
            except Exception:
                self.assertEqual(api.await_count, 1)
                raise

    async def test_text_and_usage_and_request_budget(self):
        decision, api = await self.complete(response('hello', usage=types.SimpleNamespace(prompt_tokens=10, completion_tokens=2)))
        self.assertEqual(decision.text, 'hello')
        self.assertEqual(api.await_count, 1)
        args = api.call_args.kwargs
        self.assertEqual(args['model'], 'openai/test')
        self.assertEqual(args['max_tokens'], 321)
        self.assertEqual(args['max_retries'], 0)
        self.assertEqual(args['num_retries'], 0)
        self.assertEqual(args['timeout'], 30)
        self.assertEqual(args['tools'], [{'type': 'function'}])

    async def test_preserves_single_multiple_and_bad_json_for_validation(self):
        for calls in [[call()], [call(), call()], [call(args='{')]]:
            decision, api = await self.complete(response('not trusted', calls))
            self.assertEqual(len(decision.tool_calls), len(calls))
            self.assertEqual(decision.tool_calls[0].arguments_json, calls[0].function.arguments)
            self.assertEqual(api.await_count, 1)

    async def test_deepseek_v4_disables_thinking_for_summary_history(self):
        messages = [{'role': 'user', 'content': '搜索'},
                    {'role': 'assistant', 'content': '找到 10 个结果'},
                    {'role': 'user', 'content': '第九个'}]

        async def provider(**kwargs):
            # Model the documented DeepSeek thinking/tools history requirement.
            if kwargs.get('extra_body', {}).get('thinking', {}).get('type') != 'disabled':
                raise ValueError('reasoning_content must be passed back')
            return response(calls=[call(args='{"result_index":9}')])

        for model in ['deepseek-v4-flash', 'openai/deepseek-v4-pro',
                      'deepseek/deepseek-v4-flash', 'deepseek-flash', 'deepseek-pro']:
            api = AsyncMock(side_effect=provider)
            with patch.dict(sys.modules, {'litellm': types.SimpleNamespace(acompletion=api)}):
                result = await llm_client.complete_once(messages, {'model': model}, [{'type': 'function'}])
            self.assertEqual(result.tool_calls[0].arguments_json, '{"result_index":9}')
            self.assertEqual(api.await_count, 1)
            self.assertEqual(api.call_args.kwargs['messages'], messages)

    async def test_other_models_do_not_receive_deepseek_extension(self):
        for model in ['test', 'openai/gpt-4o', 'deepseek-chat', 'deepseek-reasoner']:
            _, api = await self.complete(response('ok'), extra={'model': model})
            self.assertNotIn('extra_body', api.call_args.kwargs)

    async def test_empty_and_errors_do_not_retry(self):
        with self.assertRaises(ValueError):
            await self.complete(response())
        with self.assertRaises(RuntimeError):
            await self.complete(error=RuntimeError('upstream'))

    async def test_logs_separate_request_and_tool_counts(self):
        for calls, expected_count in [([], 0), ([call(name='daily_news', args='{}')], 1)]:
            logger = Mock()
            await self.complete(response('ok', calls), extra={'logger': logger})
            args = logger.info.call_args.args
            rendered = args[0] % args[1:]
            self.assertIn('llm_requests=1', rendered)
            self.assertIn(f'tool_calls={expected_count}', rendered)
            self.assertNotIn('key', rendered)

    async def test_hard_timeout(self):
        async def hang(**kwargs):
            await asyncio.sleep(1)
        api = AsyncMock(side_effect=hang)
        with patch.dict(sys.modules, {'litellm': types.SimpleNamespace(acompletion=api)}):
            with self.assertRaises(TimeoutError):
                await llm_client.complete_once([], {'model': 'test', 'timeout_seconds': .01}, [])
        self.assertEqual(api.await_count, 1)


class FailureDetailsTest(TestCase):
    def test_safe_categories(self):
        for status, reason in [(400, 'invalid_request'), (401, 'authentication'),
                               (403, 'authentication'), (429, 'rate_limit'),
                               (503, 'upstream_error'), (None, 'unknown')]:
            error = RuntimeError('sk-secret; private request body')
            error.status_code = status
            self.assertEqual(llm_client.failure_details(error), ('RuntimeError', status, reason))
        self.assertEqual(llm_client.failure_details(TimeoutError())[2], 'timeout')
        self.assertEqual(llm_client.failure_details(ValueError('Empty model response'))[2], 'empty_response')
        error = RuntimeError('secret')
        error.status_code = 'private status'
        self.assertIsNone(llm_client.failure_details(error)[1])


class ToolConfigTest(TestCase):
    def test_defaults_and_disable_and_invalid_timeout(self):
        self.assertTrue(get_llm_tools_config({}).enabled)
        self.assertEqual(get_llm_tools_config({}).timeout_seconds, 30)
        self.assertFalse(get_llm_tools_config({'llm': {'tools': {'enabled': 'false'}}}).enabled)
        for timeout in [0, -1, 'bad', float('inf'), True]:
            self.assertEqual(get_llm_tools_config({'llm': {'tools': {'timeout_seconds': timeout}}}).timeout_seconds, 30)
