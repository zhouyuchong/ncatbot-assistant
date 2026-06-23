import asyncio
import tempfile
from pathlib import Path
from unittest import IsolatedAsyncioTestCase, main

import tests.bootstrap  # noqa: F401
from ncatbot_assistant.drive_bot.intents import ScopeType, TaskStatus, TaskType
from ncatbot_assistant.drive_bot.jobs.queue import TaskQueueWorker
from ncatbot_assistant.drive_bot.storage import TaskStore


class DriveBotQueueTest(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.store = TaskStore(Path(self.tmpdir.name) / "tasks.sqlite3")
        self.store.initialize()
        self.notifications = []

    async def asyncTearDown(self):
        self.tmpdir.cleanup()

    async def test_run_once_marks_task_succeeded_and_notifies(self):
        task = self.store.enqueue(TaskType.DAILY, ScopeType.PRIVATE, None, "u1", "每日新闻", {}, 30)

        async def handle_daily(claimed):
            self.assertEqual(claimed.id, task.id)
            return {"message": "done"}

        async def notify(done_task):
            self.notifications.append(done_task)

        worker = TaskQueueWorker(
            store=self.store,
            handlers={TaskType.DAILY: handle_daily},
            notify=notify,
            idle_seconds=0.01,
        )

        processed = await worker.run_once()

        self.assertTrue(processed)
        self.assertEqual(self.store.get(task.id).status, TaskStatus.SUCCEEDED)
        self.assertEqual(self.store.get(task.id).result, {"message": "done"})
        self.assertEqual(self.notifications[0].id, task.id)

    async def test_run_once_marks_task_failed_and_notifies(self):
        task = self.store.enqueue(TaskType.SETU, ScopeType.PRIVATE, None, "u1", "/setu", {}, 30)

        async def fail_handler(_task):
            raise RuntimeError("network failed")

        async def notify(done_task):
            self.notifications.append(done_task)

        worker = TaskQueueWorker(
            store=self.store,
            handlers={TaskType.SETU: fail_handler},
            notify=notify,
            idle_seconds=0.01,
        )

        processed = await worker.run_once()

        self.assertTrue(processed)
        self.assertEqual(self.store.get(task.id).status, TaskStatus.FAILED)
        self.assertEqual(self.store.get(task.id).error, "network failed")
        self.assertEqual(self.notifications[0].id, task.id)

    async def test_run_once_returns_false_when_queue_is_empty(self):
        async def notify(_task):
            raise AssertionError("should not notify")

        worker = TaskQueueWorker(self.store, {}, notify, idle_seconds=0.01)

        self.assertFalse(await worker.run_once())

    async def test_notify_error_does_not_fail_processed_task(self):
        task = self.store.enqueue(TaskType.DAILY, ScopeType.PRIVATE, None, "u1", "每日新闻", {}, 30)

        async def handle_daily(_task):
            return {"message": "done"}

        async def notify(_task):
            raise RuntimeError("event is gone")

        worker = TaskQueueWorker(
            store=self.store,
            handlers={TaskType.DAILY: handle_daily},
            notify=notify,
            idle_seconds=0.01,
        )

        processed = await worker.run_once()

        self.assertTrue(processed)
        self.assertEqual(self.store.get(task.id).status, TaskStatus.SUCCEEDED)


if __name__ == "__main__":
    main()
