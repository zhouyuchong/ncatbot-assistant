import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock
import tests.bootstrap
from ncatbot_assistant.drive_bot.tools import execute_tool, ToolExecutionContext, tool_schemas
from ncatbot_assistant.drive_bot.llm_client import ToolCall
from ncatbot_assistant.drive_bot.conversation_state import TaskConversationStateStore
from ncatbot_assistant.drive_bot.llm_context import ConversationKey
from ncatbot_assistant.drive_bot.storage import TaskStore
from ncatbot_assistant.drive_bot.intents import TaskType, ScopeType, TaskStatus
from ncatbot_assistant.drive_bot.services.jm import JmSearchItem


class ToolTest(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = TaskStore(Path(self.temp.name) / 'tasks.sqlite3')
        self.store.initialize()
        self.key = ConversationKey.group('g1', 'u1')
        self.state = TaskConversationStateStore()
        self.search = AsyncMock(return_value=[JmSearchItem(123, 'A'), JmSearchItem(456, 'B')])
        def enqueue(intent):
            return self.store.enqueue(intent.task_type, intent.scope_type, intent.group_id, intent.user_id,
                                      intent.raw_message, intent.payload, 10)
        self.context = ToolExecutionContext(self.key, self.state, self.store, self.search, enqueue, Mock())

    async def call(self, name, args):
        return await execute_tool(ToolCall(name, json.dumps(args)), self.context)

    async def test_search_then_selection_creates_correct_task(self):
        result = await self.call('jm_search', {'keywords': '原神'})
        self.assertIn('2. [456]', result.reply_text)
        result = await self.call('jm_download', {'result_index': 2})
        self.assertIn('#1', result.reply_text)
        self.assertEqual(self.store.get(1).payload, {'album_id': 456})
        self.assertEqual(self.state.get(self.key).last_download_task_id, 1)

    async def test_missing_and_invalid_selection_never_enqueues(self):
        for args in [{'result_index': 2}, {}, {'album_id': 1, 'result_index': 1},
                     {'album_id': True}, {'album_id': -1}, {'album_id': '123'},
                     {'album_id': 1, 'user_id': 'someone'}]:
            with self.subTest(args=args):
                await self.call('jm_download', args)
                self.assertIsNone(self.store.claim_next())
        await self.call('jm_search', {'keywords': '原神'})
        await self.call('jm_download', {'result_index': 3})
        self.assertIsNone(self.store.claim_next())

    async def test_missing_keywords_sets_pending_and_rejects_long_input(self):
        result = await self.call('jm_search', {})
        self.assertIn('关键词', result.reply_text)
        self.assertEqual(self.state.get(self.key).pending_action.missing_field, 'keywords')
        await self.call('jm_search', {'keywords': 'a' * 201})
        self.search.assert_not_awaited()

    async def test_new_empty_or_failed_search_clears_previous_results(self):
        for response in [[], RuntimeError('network')]:
            await self.call('jm_search', {'keywords': '旧'})
            if isinstance(response, Exception):
                self.search.side_effect = response
            else:
                self.search.return_value = response
            await self.call('jm_search', {'keywords': '新'})
            self.assertEqual(self.state.get(self.key).search_results, [])
            await self.call('jm_download', {'result_index': 1})
            self.assertIsNone(self.store.claim_next())
            self.search.side_effect = None
            self.search.return_value = [JmSearchItem(123, 'A')]

    async def test_bad_json_unknown_tools_and_unknown_arguments(self):
        for call in [ToolCall('delete', '{}'), ToolCall('jm_download', '{'),
                     ToolCall('jm_download', '[]'), ToolCall('jm_search', '{"user_id":"x"}')]:
            await execute_tool(call, self.context)
        self.assertIsNone(self.store.claim_next())
        self.search.assert_not_awaited()
        self.assertEqual({s['function']['name'] for s in tool_schemas()},
                         {'jm_search', 'jm_download', 'task_status', 'daily_news', 'anime_news'})

    async def test_news_tools_enqueue_empty_payload_and_track_latest_task(self):
        await self.call('jm_download', {'album_id': 123})
        await self.call('jm_search', {})
        for name, task_type in [('daily_news', TaskType.DAILY), ('anime_news', TaskType.ANIME_NEWS)]:
            with self.subTest(tool=name):
                reply = await self.call(name, {})
                state = self.state.get(self.key)
                self.assertIsNotNone(state.last_task_id)
                task = self.store.get(state.last_task_id)
                self.assertEqual(task.task_type, task_type)
                self.assertEqual(task.payload, {})
                self.assertEqual((task.group_id, task.user_id), ('g1', 'u1'))
                self.assertIsNone(state.pending_action)
                self.assertEqual(state.last_download_task_id, 1)
                self.assertIn(f'#{task.id}', reply.reply_text)
                self.assertIn(f'#{task.id}', (await self.call('task_status', {})).reply_text)
        self.search.assert_not_awaited()

    async def test_news_tools_reject_unknown_arguments(self):
        for name in ['daily_news', 'anime_news']:
            for args in [{'topic': 'AI'}, {'user_id': 'other'}, {'date': 'yesterday'}]:
                await self.call(name, args)
                self.assertIsNone(self.store.claim_next())
        schemas = {s['function']['name']: s['function']['parameters'] for s in tool_schemas()}
        for name in ['daily_news', 'anime_news']:
            self.assertEqual(schemas[name]['properties'], {})
            self.assertFalse(schemas[name]['additionalProperties'])

    async def test_oversized_ids_are_rejected_before_storage(self):
        for name, args in [('task_status', {'task_id': 9223372036854775808}),
                           ('jm_download', {'album_id': 9223372036854775808})]:
            result = await self.call(name, args)
            self.assertTrue(result.reply_text)
        self.assertIsNone(self.store.claim_next())

    async def test_new_operation_clears_pending_search(self):
        await self.call('jm_download', {'album_id': 123})
        await self.call('jm_search', {})
        await self.call('task_status', {})
        self.assertIsNone(self.state.get(self.key).pending_action)

    async def test_status_uses_live_database_and_checks_owner(self):
        await self.call('jm_download', {'album_id': 123})
        self.assertIn('排队', (await self.call('task_status', {})).reply_text)
        self.store.claim_next()
        self.assertIn('运行', (await self.call('task_status', {})).reply_text)
        self.store.mark_succeeded(1, {})
        self.assertIn('成功', (await self.call('task_status', {})).reply_text)
        self.store.mark_failed(1, 'network')
        self.assertIn('失败', (await self.call('task_status', {})).reply_text)
        other = self.store.enqueue(TaskType.JM_DOWNLOAD, ScopeType.GROUP, 'g1', 'u2', '', {}, 1)
        self.assertNotIn('排队', (await self.call('task_status', {'task_id': other.id})).reply_text)
        self.state.clear(self.key)
        self.assertIn('编号', (await self.call('task_status', {})).reply_text)
        self.assertIn('失败', (await self.call('task_status', {'task_id': 1})).reply_text)
