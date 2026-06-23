from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from ncatbot_assistant.drive_bot.intents import TaskRecord, TaskType
from ncatbot_assistant.drive_bot.storage import TaskStore


TaskHandler = Callable[[TaskRecord], Awaitable[dict]]
TaskNotifier = Callable[[TaskRecord], Awaitable[None]]


class TaskQueueWorker:
    def __init__(
        self,
        store: TaskStore,
        handlers: dict[TaskType, TaskHandler],
        notify: TaskNotifier,
        idle_seconds: float = 1.0,
    ):
        self.store = store
        self.handlers = handlers
        self.notify = notify
        self.idle_seconds = idle_seconds
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stopping.clear()
            self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        self._stopping.set()
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass

    async def run_once(self) -> bool:
        task = self.store.claim_next()
        if task is None:
            return False

        try:
            handler = self.handlers[task.task_type]
            result = await handler(task)
            self.store.mark_succeeded(task.id, result)
        except Exception as exc:
            self.store.mark_failed(task.id, str(exc))

        try:
            await self.notify(self.store.get(task.id))
        except Exception:
            pass
        return True

    async def _run_loop(self) -> None:
        while not self._stopping.is_set():
            processed = await self.run_once()
            if not processed:
                await asyncio.sleep(self.idle_seconds)
