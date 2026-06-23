from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from .intents import ScopeType, TaskRecord, TaskStatus, TaskType


class TaskStore:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    scope_type TEXT NOT NULL,
                    group_id TEXT,
                    user_id TEXT NOT NULL,
                    raw_message TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    result_json TEXT,
                    error TEXT,
                    estimated_seconds INTEGER NOT NULL,
                    created_at REAL NOT NULL,
                    started_at REAL,
                    finished_at REAL
                )
                """
            )

    def enqueue(
        self,
        task_type: TaskType,
        scope_type: ScopeType,
        group_id: str | None,
        user_id: str,
        raw_message: str,
        payload: dict[str, Any],
        estimated_seconds: int,
    ) -> TaskRecord:
        now = time.time()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO tasks (
                    task_type, status, scope_type, group_id, user_id, raw_message,
                    payload_json, estimated_seconds, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_type.value,
                    TaskStatus.QUEUED.value,
                    scope_type.value,
                    group_id,
                    user_id,
                    raw_message,
                    json.dumps(payload, ensure_ascii=False),
                    int(estimated_seconds),
                    now,
                ),
            )
            task_id = int(cursor.lastrowid)
        return self.get(task_id)

    def get(self, task_id: int) -> TaskRecord:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            raise KeyError(f"task {task_id} not found")
        return self._row_to_task(row)

    def claim_next(self) -> TaskRecord | None:
        now = time.time()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM tasks
                WHERE status = ?
                ORDER BY created_at, id
                LIMIT 1
                """,
                (TaskStatus.QUEUED.value,),
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                "UPDATE tasks SET status = ?, started_at = ? WHERE id = ?",
                (TaskStatus.RUNNING.value, now, row["id"]),
            )
            task_id = int(row["id"])
        return self.get(task_id)

    def mark_succeeded(self, task_id: int, result: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE tasks
                SET status = ?, result_json = ?, error = NULL, finished_at = ?
                WHERE id = ?
                """,
                (
                    TaskStatus.SUCCEEDED.value,
                    json.dumps(result, ensure_ascii=False),
                    time.time(),
                    task_id,
                ),
            )

    def mark_failed(self, task_id: int, error: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE tasks
                SET status = ?, error = ?, finished_at = ?
                WHERE id = ?
                """,
                (TaskStatus.FAILED.value, error, time.time(), task_id),
            )

    def recover_running_tasks(self) -> int:
        error = "任务因进程重启中断，已标记失败"
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE tasks
                SET status = ?, error = ?, finished_at = ?
                WHERE status = ?
                """,
                (
                    TaskStatus.FAILED.value,
                    error,
                    time.time(),
                    TaskStatus.RUNNING.value,
                ),
            )
            return int(cursor.rowcount)

    def queue_position(self, task_id: int) -> int:
        task = self.get(task_id)
        if task.status != TaskStatus.QUEUED:
            return 0
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS count FROM tasks
                WHERE status = ?
                  AND (created_at < ? OR (created_at = ? AND id <= ?))
                """,
                (TaskStatus.QUEUED.value, task.created_at, task.created_at, task.id),
            ).fetchone()
        return int(row["count"])

    def estimated_wait_seconds(self, task_id: int) -> int:
        task = self.get(task_id)
        if task.status != TaskStatus.QUEUED:
            return 0
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(estimated_seconds), 0) AS seconds FROM tasks
                WHERE status IN (?, ?)
                  AND id != ?
                  AND (
                    status = ?
                    OR created_at < ?
                    OR (created_at = ? AND id < ?)
                  )
                """,
                (
                    TaskStatus.QUEUED.value,
                    TaskStatus.RUNNING.value,
                    task.id,
                    TaskStatus.RUNNING.value,
                    task.created_at,
                    task.created_at,
                    task.id,
                ),
            ).fetchone()
        return int(row["seconds"])

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _row_to_task(self, row: sqlite3.Row) -> TaskRecord:
        result = json.loads(row["result_json"]) if row["result_json"] else None
        return TaskRecord(
            id=int(row["id"]),
            task_type=TaskType(row["task_type"]),
            status=TaskStatus(row["status"]),
            scope_type=ScopeType(row["scope_type"]),
            group_id=row["group_id"],
            user_id=row["user_id"],
            raw_message=row["raw_message"],
            payload=json.loads(row["payload_json"]),
            result=result,
            error=row["error"],
            estimated_seconds=int(row["estimated_seconds"]),
            created_at=float(row["created_at"]),
            started_at=row["started_at"],
            finished_at=row["finished_at"],
        )
