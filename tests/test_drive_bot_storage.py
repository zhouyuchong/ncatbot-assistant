import tempfile
from pathlib import Path
from unittest import TestCase, main

import tests.bootstrap  # noqa: F401
from ncatbot_assistant.drive_bot.estimator import format_duration, estimate_seconds
from ncatbot_assistant.drive_bot.intents import ScopeType, TaskStatus, TaskType
from ncatbot_assistant.drive_bot.storage import TaskStore


class DriveBotStorageTest(TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "tasks.sqlite3"
        self.store = TaskStore(self.db_path)
        self.store.initialize()

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_enqueue_persists_task_and_reports_queue_position(self):
        first = self.store.enqueue(
            task_type=TaskType.JM_DOWNLOAD,
            scope_type=ScopeType.GROUP,
            group_id="20002",
            user_id="10001",
            raw_message="/jm 1",
            payload={"album_id": 1},
            estimated_seconds=480,
        )
        second = self.store.enqueue(
            task_type=TaskType.SETU,
            scope_type=ScopeType.PRIVATE,
            group_id=None,
            user_id="10002",
            raw_message="/setu",
            payload={"tags": []},
            estimated_seconds=45,
        )

        self.assertEqual(self.store.queue_position(first.id), 1)
        self.assertEqual(self.store.queue_position(second.id), 2)
        self.assertEqual(self.store.estimated_wait_seconds(second.id), 480)
        self.assertEqual(self.store.get(first.id).payload, {"album_id": 1})

    def test_claim_next_uses_fifo_and_marks_running(self):
        first = self.store.enqueue(TaskType.DAILY, ScopeType.PRIVATE, None, "u1", "每日新闻", {}, 30)
        self.store.enqueue(TaskType.SETU, ScopeType.PRIVATE, None, "u2", "/setu", {"tags": []}, 45)

        claimed = self.store.claim_next()

        self.assertEqual(claimed.id, first.id)
        self.assertEqual(self.store.get(first.id).status, TaskStatus.RUNNING)

    def test_mark_succeeded_and_failed_store_results(self):
        succeeded = self.store.enqueue(TaskType.DAILY, ScopeType.PRIVATE, None, "u1", "每日新闻", {}, 30)
        failed = self.store.enqueue(TaskType.SETU, ScopeType.PRIVATE, None, "u2", "/setu", {"tags": []}, 45)
        self.store.claim_next()
        self.store.mark_succeeded(succeeded.id, {"uploaded_files": 1})
        self.store.claim_next()
        self.store.mark_failed(failed.id, "boom")

        self.assertEqual(self.store.get(succeeded.id).status, TaskStatus.SUCCEEDED)
        self.assertEqual(self.store.get(succeeded.id).result, {"uploaded_files": 1})
        self.assertEqual(self.store.get(failed.id).status, TaskStatus.FAILED)
        self.assertEqual(self.store.get(failed.id).error, "boom")

    def test_recover_running_tasks_marks_them_failed(self):
        task = self.store.enqueue(TaskType.DAILY, ScopeType.PRIVATE, None, "u1", "每日新闻", {}, 30)
        self.store.claim_next()

        recovered = self.store.recover_running_tasks()

        self.assertEqual(recovered, 1)
        self.assertEqual(self.store.get(task.id).status, TaskStatus.FAILED)
        self.assertIn("进程重启", self.store.get(task.id).error)

    def test_estimates_and_duration_format(self):
        self.assertEqual(estimate_seconds(TaskType.JM_DOWNLOAD), 480)
        self.assertEqual(format_duration(65), "1 分 5 秒")
        self.assertEqual(format_duration(30), "30 秒")


if __name__ == "__main__":
    main()
