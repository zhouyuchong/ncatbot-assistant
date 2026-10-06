from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
import tests.bootstrap
from ncatbot_assistant.drive_bot.storage import TaskStore
from ncatbot_assistant.drive_bot.intents import ScopeType, TaskType
from ncatbot_assistant.drive_bot.llm_context import ConversationKey


class ScopedTaskTest(TestCase):
    def test_task_lookup_is_scoped_and_survives_reopen(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / 'tasks.sqlite3'
            store = TaskStore(path)
            store.initialize()
            task = store.enqueue(TaskType.JM_DOWNLOAD, ScopeType.GROUP, 'g1', 'u1', '/jm 12', {'album_id': 12}, 10)
            reopened = TaskStore(path)
            self.assertEqual(reopened.get_for_conversation(task.id, ConversationKey.group('g1', 'u1')).id, task.id)
            for key in [ConversationKey.group('g1', 'u2'), ConversationKey.group('g2', 'u1'), ConversationKey.private('u1')]:
                self.assertIsNone(reopened.get_for_conversation(task.id, key))
            self.assertIsNone(reopened.get_for_conversation(999, ConversationKey.group('g1', 'u1')))
