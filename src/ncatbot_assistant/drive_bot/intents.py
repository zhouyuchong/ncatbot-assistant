from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ScopeType(str, Enum):
    GROUP = "group"
    PRIVATE = "private"


class TaskType(str, Enum):
    JM_DOWNLOAD = "jm_download"
    SETU = "setu"
    DAILY = "daily"
    DAILY_AI = "daily_ai"


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class ImmediateResponse:
    text: str


@dataclass(frozen=True)
class ShowUserProfileIntent:
    pass


@dataclass(frozen=True)
class QueuedTaskIntent:
    task_type: TaskType
    scope_type: ScopeType
    user_id: str
    raw_message: str
    payload: dict[str, Any]
    group_id: str | None = None


@dataclass(frozen=True)
class LlmFallbackIntent:
    prompt: str


@dataclass(frozen=True)
class TaskRecord:
    id: int
    task_type: TaskType
    status: TaskStatus
    scope_type: ScopeType
    user_id: str
    raw_message: str
    payload: dict[str, Any]
    estimated_seconds: int
    group_id: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: float | None = None
    started_at: float | None = None
    finished_at: float | None = None
