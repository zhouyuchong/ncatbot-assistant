import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock
import tests.bootstrap
from ncatbot_assistant.drive_bot.conversation import ConversationRuntime, handle_conversation_message
from ncatbot_assistant.drive_bot.conversation_state import TaskConversationStateStore
from ncatbot_assistant.drive_bot.llm_context import ConversationKey, ShortTermConversationMemory
from ncatbot_assistant.drive_bot.llm_client import ToolCall, LlmDecision
from ncatbot_assistant.drive_bot.tools import ToolExecutionContext
from ncatbot_assistant.drive_bot.storage import TaskStore
from ncatbot_assistant.drive_bot.services.jm import JmSearchItem
from ncatbot_assistant.drive_bot.jobs.queue import TaskQueueWorker
from ncatbot_assistant.drive_bot.intents import TaskType


def decision(name, **args):
    return LlmDecision(tool_calls=(ToolCall(name, json.dumps(args)),))


class ConversationTest(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = TaskStore(Path(self.temp.name) / 'tasks.sqlite3')
        self.store.initialize()
        self.now = 0
        self.states = TaskConversationStateStore(clock=lambda: self.now)
        self.key = ConversationKey.group('g1', 'u1')
        self.memory = ShortTermConversationMemory()
        self.search = AsyncMock(return_value=[JmSearchItem(123, 'A'), JmSearchItem(456, 'B')])
        self.complete = AsyncMock()
        self.legacy = AsyncMock(return_value='legacy reply')
        self.record = Mock()
        self.sequence = 0
        def enqueue(intent):
            return self.store.enqueue(intent.task_type, intent.scope_type, intent.group_id, intent.user_id,
                                      intent.raw_message, intent.payload, 10)
        self.context = ToolExecutionContext(self.key, self.states, self.store, self.search, enqueue, Mock())
        self.runtime = ConversationRuntime(self.context, self.memory, self.complete,
                                          [{'role': 'system', 'content': '角色'}], self.legacy,
                                          lambda: 'profile', self.record)

    async def send(self, text, value=None, message_id=None):
        self.sequence += 1
        self.complete.return_value = value or LlmDecision(text='聊天')
        return await handle_conversation_message(text, self.key, message_id or str(self.sequence), self.runtime)

    async def test_command_search_then_natural_selection_and_status(self):
        await self.send('/jm 原神')
        self.complete.assert_not_awaited()
        text = await self.send('下载第二个', decision('jm_download', result_index=2))
        self.assertIn('#1', text)
        self.assertEqual(self.store.get(1).payload, {'album_id': 456})
        self.assertEqual(self.complete.await_count, 1)
        await self.send('下好了吗', decision('task_status'))
        self.assertEqual(self.complete.await_count, 2)
        self.store.mark_succeeded(1, {})
        self.assertIn('成功', await self.send('/task 1'))
        self.assertEqual(self.complete.await_count, 2)
        history = self.memory.recent_messages(self.key)
        self.assertTrue(any('456' in m['content'] for m in history))
        self.assertTrue(any('#1' in m['content'] for m in history))

    async def test_natural_search_download_and_worker_complete(self):
        await self.send('搜原神', decision('jm_search', keywords='原神'))
        await self.send('下载第二个', decision('jm_download', result_index=2))
        worker = TaskQueueWorker(self.store, {TaskType.JM_DOWNLOAD: AsyncMock(return_value={'files': 1})}, AsyncMock())
        await worker.run_once()
        self.assertIn('成功', await self.send('完成了吗', decision('task_status')))
        self.assertEqual(self.complete.await_count, 3)

    async def test_pending_followup_topic_change_and_llm_failure(self):
        await self.send('帮我找', decision('jm_search'))
        self.assertIsNotNone(self.states.get(self.key).pending_action)
        await self.send('原神', decision('jm_search', keywords='原神'))
        messages = self.complete.call_args.args[0]
        self.assertTrue(any('keywords' in m['content'] for m in messages))
        self.assertIsNone(self.states.get(self.key).pending_action)
        await self.send('搜索', decision('jm_search'))
        self.complete.side_effect = RuntimeError('secret-api-key')
        self.assertNotIn('secret-api-key', await self.send('原神'))
        self.assertIsNotNone(self.states.get(self.key).pending_action)
        self.complete.side_effect = None
        await self.send('不搜了，聊点别的', LlmDecision(text='好的'))
        self.assertIsNone(self.states.get(self.key).pending_action)
        await self.send('搜索', decision('jm_search'))
        await self.send('/help')
        self.assertIsNone(self.states.get(self.key).pending_action)

    async def test_discussion_multiple_calls_and_untrusted_model_text(self):
        await self.send('下载功能有点慢', LlmDecision(text='可以看看排队情况'))
        self.assertIsNone(self.store.claim_next())
        call = ToolCall('jm_download', '{"album_id":123}')
        reply = await self.send('下载', LlmDecision(text='已经成功', tool_calls=(call, call)))
        self.assertNotIn('已经成功', reply)
        self.assertIsNone(self.store.claim_next())
        reply = await self.send('下载123', LlmDecision(text='下载成功', tool_calls=(call,)))
        self.assertNotIn('下载成功', reply)
        self.assertIn('队列', reply)

    async def test_duplicate_delivery_creates_only_one_task(self):
        await self.send('/jm 123', message_id='dup')
        self.assertIsNone(await self.send('/jm 123', message_id='dup'))
        self.assertEqual(self.store.claim_next().id, 1)
        self.assertIsNone(self.store.claim_next())
        self.assertEqual(self.record.call_count, 1)

    async def test_expiry_reboot_and_summary_limits(self):
        self.search.return_value = [JmSearchItem(i + 1, '标题' * 1000) for i in range(10)]
        await self.send('/jm 关键词')
        await self.send('下载第二个', decision('jm_download', result_index=2))
        messages = self.complete.call_args.args[0]
        summary = [m['content'] for m in messages if '当前办事状态' in m['content']][0]
        self.assertLessEqual(len(summary), 1500)
        self.assertTrue(all(len(m['content']) <= 500 for m in self.memory.recent_messages(self.key) if m['role'] == 'assistant'))
        self.now = 900
        await self.send('下载第二个', decision('jm_download', result_index=2))
        self.assertEqual(self.store.claim_next().id, 1)
        self.assertIsNone(self.store.claim_next())
        self.states.clear(self.key)
        self.assertIn('编号', await self.send('/task'))
        self.assertIn('运行', await self.send('/task 1'))

    async def test_tools_disabled_still_supports_commands(self):
        self.runtime.complete = None
        self.assertEqual(await self.send('你好'), 'legacy reply')
        self.complete.assert_not_awaited()
        await self.send('/jm 123')
        self.assertIn('排队', await self.send('/task'))
        self.assertEqual(self.legacy.await_count, 1)

    async def test_concurrent_same_conversation_and_independent_other_user(self):
        started = asyncio.Event()
        release = asyncio.Event()
        async def search(keywords):
            started.set()
            await release.wait()
            return [JmSearchItem(777, 'A')]
        self.context.search = search
        first = asyncio.create_task(self.send('/jm 关键词'))
        await started.wait()
        self.complete.return_value = decision('jm_download', result_index=1)
        second = asyncio.create_task(handle_conversation_message('下载第一个', self.key, 'next', self.runtime))
        await asyncio.sleep(0)
        self.assertFalse(second.done())
        other_key = ConversationKey.group('g1', 'u2')
        other_context = ToolExecutionContext(other_key, self.states, self.store, self.search, self.context.enqueue, Mock())
        other_runtime = ConversationRuntime(other_context, self.memory, self.complete, [], self.legacy, lambda: '', Mock())
        self.assertIn('指南', await handle_conversation_message('/help', other_key, 'other', other_runtime))
        release.set()
        await asyncio.gather(first, second)
        self.assertEqual(self.store.get(1).payload, {'album_id': 777})
