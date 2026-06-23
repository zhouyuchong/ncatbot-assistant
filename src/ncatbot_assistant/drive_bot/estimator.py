from __future__ import annotations

from .intents import TaskType


DEFAULT_ESTIMATES = {
    TaskType.JM_DOWNLOAD: 480,
    TaskType.SETU: 45,
    TaskType.DAILY: 30,
}


def estimate_seconds(task_type: TaskType, overrides: dict[str, int] | None = None) -> int:
    if overrides and task_type.value in overrides:
        return int(overrides[task_type.value])
    return DEFAULT_ESTIMATES[task_type]


def format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    minutes, rest = divmod(seconds, 60)
    if minutes and rest:
        return f"{minutes} 分 {rest} 秒"
    if minutes:
        return f"{minutes} 分钟"
    return f"{rest} 秒"
