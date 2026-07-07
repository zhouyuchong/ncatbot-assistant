from __future__ import annotations

import datetime
from pathlib import Path
from collections.abc import Callable, Awaitable
from typing import Any


async def generate_daily_ai_summary(
    project_config: dict[str, Any],
    chat_text_func: Callable[[list[dict[str, str]]], Awaitable[str]],
) -> str:
    task_config = project_config.get("tasks") or {}
    if not isinstance(task_config, dict):
        task_config = {}

    daily_ai_config = task_config.get("daily_ai") or {}
    if not isinstance(daily_ai_config, dict):
        daily_ai_config = {}

    base_path = daily_ai_config.get("base_path")
    if not base_path:
        raise ValueError("配置文件中未配置 tasks.daily_ai.base_path")

    yesterday_str = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y%m%d")
    folder_path = Path(base_path) / yesterday_str

    if not folder_path.exists() or not folder_path.is_dir():
        raise FileNotFoundError(f"找不到昨天的目录: {folder_path}")

    md_contents = []
    for file in folder_path.glob("*.md"):
        try:
            md_contents.append(file.read_text(encoding="utf-8"))
        except Exception:
            continue

    if not md_contents:
        raise FileNotFoundError(f"目录 {folder_path} 中没有找到 md 文件")

    all_text = "\n\n".join(md_contents)
    today_display = datetime.datetime.now().strftime("%Y年%m月%d日")
    prompt = f"请总结以下AI论文和信息，输出一篇关于今天的（{today_display}）每日的AI技术看点：\n\n{all_text}"

    messages = [{"role": "user", "content": prompt}]
    return await chat_text_func(messages)
