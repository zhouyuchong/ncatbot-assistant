from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Awaitable, Callable
from typing import Any

from ncatbot_assistant.drive_bot.constants import CURRENTS_LATEST_NEWS_URL


async def generate_daily_news(
    project_config: dict[str, Any],
    chat_text_func: Callable[[list[dict[str, str]]], Awaitable[str]],
    logger=None,
    fetch_func: Callable[..., dict[str, Any] | Awaitable[dict[str, Any]]] | None = None,
) -> str:
    config = _daily_news_config(project_config)
    api_key = str(config.get("api_key") or "").strip()
    if not api_key:
        raise ValueError("配置文件中未配置 tasks.daily_news.api_key")

    language = str(config.get("language") or "en").strip() or "en"
    max_items = max(1, min(_parse_int(config.get("max_items"), 10), 10))
    fetch = fetch_func or fetch_latest_news
    payload = fetch(api_key=api_key, language=language)
    if inspect.isawaitable(payload):
        payload = await payload
    news = _normalize_news_payload(payload)[:max_items]

    messages = [{"role": "user", "content": _build_summary_prompt(news)}]
    try:
        return await chat_text_func(messages)
    except Exception as exc:
        if logger:
            logger.warning("每日新闻 LLM 摘要失败: %s", type(exc).__name__)
        return _build_fallback_digest(news)


async def fetch_latest_news(api_key: str, language: str) -> dict[str, Any]:
    return await asyncio.to_thread(fetch_latest_news_sync, api_key, language)


def fetch_latest_news_sync(
    api_key: str,
    language: str,
    timeout: int = 10,
) -> dict[str, Any]:
    import requests

    try:
        response = requests.get(
            CURRENTS_LATEST_NEWS_URL,
            params={"language": language, "apiKey": api_key},
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        raise RuntimeError("Currents 新闻接口请求失败") from exc

    if not isinstance(payload, dict):
        raise RuntimeError("Currents 新闻接口返回了无效 JSON 结构")
    return payload


def _daily_news_config(project_config: dict[str, Any]) -> dict[str, Any]:
    tasks = project_config.get("tasks") or {}
    if not isinstance(tasks, dict):
        return {}
    config = tasks.get("daily_news") or {}
    if not isinstance(config, dict):
        return {}
    return config


def _parse_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_news_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if payload.get("status") != "ok":
        raise RuntimeError("Currents 新闻接口返回失败状态")
    raw_news = payload.get("news")
    if not isinstance(raw_news, list):
        raise RuntimeError("Currents 新闻接口未返回有效新闻列表")

    normalized = []
    for item in raw_news:
        if not isinstance(item, dict):
            continue
        title = _clean_text(item.get("title"))
        url = _clean_text(item.get("url"))
        if not title or not url:
            continue
        categories = item.get("category")
        if not isinstance(categories, list):
            categories = []
        normalized.append(
            {
                "title": title,
                "description": _clean_text(item.get("description"))[:500],
                "url": url,
                "author": _clean_text(item.get("author")),
                "category": [
                    text for value in categories if (text := _clean_text(value))
                ],
                "published": _clean_text(item.get("published")),
            }
        )

    if not normalized:
        raise RuntimeError("Currents 新闻接口没有返回有效新闻")
    return normalized


def _clean_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())


def _build_summary_prompt(news: list[dict[str, Any]]) -> str:
    serialized = json.dumps(news, ensure_ascii=False, indent=2)
    return (
        "请根据下面的新闻数据生成适合 QQ 纯文本发送的每日新闻。\n"
        "要求：使用简体中文；先写一段综合摘要；再选出 5～10 条最值得关注且尽量覆盖不同类别的新闻；"
        "每条包含中文标题、简短说明和输入中的原文链接；不要编造输入之外的事实；不要使用表格。\n\n"
        f"新闻数据：\n{serialized}"
    )


def _build_fallback_digest(news: list[dict[str, Any]]) -> str:
    lines = ["今日新闻速览（AI 摘要暂不可用）"]
    for index, item in enumerate(news, start=1):
        lines.append(f"\n{index}. {item['title']}")
        if item["description"]:
            description = item["description"][:240]
            if len(item["description"]) > 240:
                description += "…"
            lines.append(description)
        lines.append(item["url"])
    return "\n".join(lines)
