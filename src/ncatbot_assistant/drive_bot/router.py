from __future__ import annotations

import re
from collections.abc import Callable

from .constants import JM_MATCH, SETU_PATTERN
from .intents import (
    ImmediateResponse,
    LlmFallbackIntent,
    QueuedTaskIntent,
    ScopeType,
    ShowUserProfileIntent,
    TaskType,
)
from .usage import DRIVE_BOT_USAGE, is_usage_question


def route_message(
    message: str,
    scope_type: ScopeType,
    user_id: str,
    group_id: str | None = None,
    jm_search_func: Callable[[list[str]], str] | None = None,
):
    text = message.strip()

    if is_usage_question(text):
        return ImmediateResponse(DRIVE_BOT_USAGE)

    if re.fullmatch(r"/showUserProfile", text, flags=re.IGNORECASE):
        return ShowUserProfileIntent()

    jm_match = re.search(JM_MATCH, text)
    if jm_match:
        after_jm = jm_match.group(1).strip()
        if re.fullmatch(r"\d+", after_jm):
            return QueuedTaskIntent(
                task_type=TaskType.JM_DOWNLOAD,
                scope_type=scope_type,
                group_id=group_id,
                user_id=user_id,
                raw_message=message,
                payload={"album_id": int(after_jm)},
            )

        tags = after_jm.split()
        if jm_search_func is None:
            return ImmediateResponse("JM 搜索暂时不可用")
        return ImmediateResponse(jm_search_func(tags))

    setu_match = re.search(SETU_PATTERN, text)
    if setu_match:
        raw_tags = setu_match.group(1)
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

    if "每日新闻" in text:
        return QueuedTaskIntent(
            task_type=TaskType.DAILY,
            scope_type=scope_type,
            group_id=group_id,
            user_id=user_id,
            raw_message=message,
            payload={},
        )

    if re.fullmatch(r"/dailyai", text, flags=re.IGNORECASE) or "每日ai" in text.lower():
        return QueuedTaskIntent(
            task_type=TaskType.DAILY_AI,
            scope_type=scope_type,
            group_id=group_id,
            user_id=user_id,
            raw_message=message,
            payload={},
        )

    if "动漫新闻" in text:
        return QueuedTaskIntent(
            task_type=TaskType.ANIME_NEWS,
            scope_type=scope_type,
            group_id=group_id,
            user_id=user_id,
            raw_message=message,
            payload={},
        )

    return LlmFallbackIntent(prompt=text)
