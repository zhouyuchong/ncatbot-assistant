from __future__ import annotations

import re

from .commands import slash_aliases, text_aliases
from .intents import (
    ImmediateResponse,
    JmSearchIntent,
    TaskStatusIntent,
    LlmFallbackIntent,
    QueuedTaskIntent,
    ScopeType,
    ShowUserProfileIntent,
    TaskType,
)
from .usage import DRIVE_BOT_USAGE, is_usage_question

TRAILING_PUNCTUATION = "。.!！?？"


def route_message(
    message: str,
    scope_type: ScopeType,
    user_id: str,
    group_id: str | None = None,
):
    text = message.strip()

    if is_usage_question(text):
        return ImmediateResponse(DRIVE_BOT_USAGE)

    if _matches_slash_command(text, "profile"):
        return ShowUserProfileIntent()

    task_match = _match_slash_with_args(text, "task", require_args=False)
    if task_match is not None:
        if not task_match.strip():
            return TaskStatusIntent()
        if re.fullmatch(r"[0-9]+", task_match.strip()) and int(task_match.strip()) > 0:
            return TaskStatusIntent(task_id=int(task_match.strip()))
        return ImmediateResponse("任务编号必须是正整数，例如 /task 42。")

    jm_match = _match_slash_with_args(text, "jm", require_args=True)
    if jm_match:
        after_jm = jm_match.strip()
        if re.fullmatch(r"\d+", after_jm):
            return QueuedTaskIntent(
                task_type=TaskType.JM_DOWNLOAD,
                scope_type=scope_type,
                group_id=group_id,
                user_id=user_id,
                raw_message=message,
                payload={"album_id": int(after_jm)},
            )

        return JmSearchIntent(keywords=after_jm)

    setu_match = _match_slash_with_args(text, "setu", require_args=False)
    if setu_match is not None:
        raw_tags = setu_match
        tags = raw_tags.strip().split() if raw_tags else []
        if len(tags) > 3:
            return ImmediateResponse("最多支持3个标签")
        return QueuedTaskIntent(
            task_type=TaskType.SETU,
            scope_type=scope_type,
            group_id=group_id,
            user_id=user_id,
            raw_message=message,
            payload={"tags": tags},
        )

    if _matches_simple_command(text, "news"):
        return QueuedTaskIntent(
            task_type=TaskType.DAILY,
            scope_type=scope_type,
            group_id=group_id,
            user_id=user_id,
            raw_message=message,
            payload={},
        )

    if _matches_simple_command(text, "dailyai"):
        return QueuedTaskIntent(
            task_type=TaskType.DAILY_AI,
            scope_type=scope_type,
            group_id=group_id,
            user_id=user_id,
            raw_message=message,
            payload={},
        )

    if _matches_simple_command(text, "anime-news"):
        return QueuedTaskIntent(
            task_type=TaskType.ANIME_NEWS,
            scope_type=scope_type,
            group_id=group_id,
            user_id=user_id,
            raw_message=message,
            payload={},
        )

    if _matches_simple_command(text, "trending"):
        return QueuedTaskIntent(
            task_type=TaskType.TRENDING_PAPER,
            scope_type=scope_type,
            group_id=group_id,
            user_id=user_id,
            raw_message=message,
            payload={},
        )

    return LlmFallbackIntent(prompt=text)


def _normalize_text_alias(message: str) -> str:
    return message.strip().strip(TRAILING_PUNCTUATION).lower()


def _matches_text_alias(message: str, command_name: str) -> bool:
    normalized = _normalize_text_alias(message)
    return normalized in {alias.lower() for alias in text_aliases(command_name)}


def _matches_slash_command(message: str, command_name: str) -> bool:
    normalized = message.strip().lower()
    return normalized in {alias.lower() for alias in slash_aliases(command_name)}


def _matches_simple_command(message: str, command_name: str) -> bool:
    return _matches_slash_command(message, command_name) or _matches_text_alias(message, command_name)


def _match_slash_with_args(message: str, command_name: str, *, require_args: bool) -> str | None:
    alternatives = [re.escape(alias) for alias in slash_aliases(command_name)]
    pattern = (
        rf"^(?:{'|'.join(alternatives)})\s+(.+)$"
        if require_args
        else rf"^(?:{'|'.join(alternatives)})(?:\s+(.+))?$"
    )
    match = re.fullmatch(pattern, message.strip(), flags=re.IGNORECASE)
    if not match:
        return None
    args = match.group(1) or ""
    return args
