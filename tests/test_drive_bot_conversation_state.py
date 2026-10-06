import asyncio
from dataclasses import replace
from unittest import TestCase, IsolatedAsyncioTestCase
import tests.bootstrap
from ncatbot_assistant.drive_bot import conversation_state as cs
from ncatbot_assistant.drive_bot.llm_context import ConversationKey
from ncatbot_assistant.drive_bot.services.jm import JmSearchItem


class StateTest(TestCase):
    def setUp(self):
        self.now = 0
        self.store = cs.TaskConversationStateStore(clock=lambda: self.now)
        self.key = ConversationKey.group('g1', 'u1')

    def test_isolation_and_copy(self):
        state = self.store.get(self.key)
        state.search_results.append(JmSearchItem(12, 'title'))
        self.store.update(self.key, state)
        state.search_results.clear()
        self.assertEqual(len(self.store.get(self.key).search_results), 1)
        for key in [ConversationKey.group('g1', 'u2'), ConversationKey.group('g2', 'u1'), ConversationKey.private('u1')]:
            self.assertEqual(self.store.get(key).search_results, [])

    def test_expiry_and_capacity(self):
        state = self.store.get(self.key)
        state.last_download_task_id = 42
        self.store.update(self.key, state)
        self.now = 899
        self.assertEqual(self.store.get(self.key).last_download_task_id, 42)
        self.now = 900
        self.assertIsNone(self.store.get(self.key).last_download_task_id)
        self.store.update(self.key, state)
        for i in range(1000):
            self.now += 1
            key = ConversationKey.private(str(i))
            self.store.update(key, cs.TaskConversationState(last_download_task_id=i))
        self.assertIsNone(self.store.get(self.key).last_download_task_id)

    def test_message_dedup_expiry_capacity_and_scope(self):
        self.assertTrue(self.store.claim_message(self.key, '1'))
        self.assertFalse(self.store.claim_message(self.key, '1'))
        self.assertTrue(self.store.claim_message(ConversationKey.private('u2'), '1'))
        self.now = 900
        self.assertTrue(self.store.claim_message(self.key, '1'))
        for i in range(2000):
            self.store.claim_message(self.key, f'new-{i}')
        self.assertTrue(self.store.claim_message(self.key, '1'))


class StateLockTest(IsolatedAsyncioTestCase):
    async def test_serializes_same_key_and_releases_idle_locks(self):
        store = cs.TaskConversationStateStore()
        key = ConversationKey.private('u1')
        order = []
        async def work(n):
            async with store.lock(key):
                order.append(n)
                await asyncio.sleep(0)
                order.append(n)
        await asyncio.gather(work(1), work(2))
        self.assertEqual(order, [1, 1, 2, 2])
        self.assertEqual(len(store._locks), 0)
