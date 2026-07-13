from __future__ import annotations

import datetime
import re
import sqlite3
from pathlib import Path
from collections.abc import Callable, Awaitable
from typing import Any

import logging

INVALID_FILENAME_CHARS = re.compile(r'[/\\:*?"<>|]+')
WHITESPACE = re.compile(r"\s+")
LOGGER = logging.getLogger(__name__)

def safe_paper_filename(title: str, extension: str = ".md", max_stem_length: int = 180) -> str:
    stem = INVALID_FILENAME_CHARS.sub(" ", title)
    stem = WHITESPACE.sub(" ", stem).strip(" .")
    if not stem:
        stem = "paper"
    stem = stem[:max_stem_length].rstrip(" .")
    return f"{stem}{extension}"

async def generate_trending_paper_summary(
    project_config: dict[str, Any],
    chat_text_func: Callable[[list[dict[str, str]]], Awaitable[str]],
) -> str:
    task_config = project_config.get("tasks") or {}
    trending_config = task_config.get("trending_paper") or {}
    
    db_path = trending_config.get("db_path")
    if not db_path:
        db_path = "/Users/damonzzz/codes/damon/tech_crawler/data/papers/tech_crawler.db"
    
    base_path = trending_config.get("base_path")
    if not base_path:
        base_path = "/Users/damonzzz/codes/damon/tech_crawler/data/papers/trending"
        
    db_file = Path(db_path)
    if not db_file.exists():
        raise FileNotFoundError(f"找不到数据库文件: {db_file}")

    papers = []
    try:
        with sqlite3.connect(db_file) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT title, update_time FROM trending_papers ORDER BY hotness DESC, update_time DESC LIMIT 10"
            )
            papers = cursor.fetchall()
    except Exception as e:
        raise RuntimeError(f"查询数据库失败: {e}")

    if not papers:
        raise RuntimeError("数据库中没有找到热门论文")

    base_dir = Path(base_path)
    LOGGER.info(f"Trending papers base directory: {base_dir}")
    if not base_dir.exists():
        raise FileNotFoundError(f"找不到 base_path 目录: {base_dir}")
        
    md_contents = []
    
    for row in papers:
        title = row["title"]
        stem = safe_paper_filename(title, extension="")
        
        matched_file = None
        for file_path in base_dir.rglob("*.md"):
            if file_path.name.startswith(stem):
                matched_file = file_path
                break
            
        if matched_file and matched_file.exists():
            LOGGER.info(f"Found summary file for paper '{title}': {matched_file}")
            try:
                md_contents.append(f"【{title}】\n" + matched_file.read_text(encoding="utf-8"))
            except Exception as e:
                LOGGER.warning(f"Failed to read file {matched_file}: {e}")
                continue
        else:
            LOGGER.warning(f"Could not find summary file for paper '{title}' (stem: {stem})")

    if not md_contents:
        raise FileNotFoundError("没有找到任何热门论文的摘要文件，请确保 crawler 已经成功生成了摘要，检查日志以获取更多信息。")

    all_text = "\n\n".join(md_contents)
    
    project_dir = Path(__file__).resolve().parents[3]
    prompt_file = project_dir / "resources" / "skills" / "trending_paper_prompt.md"
    if prompt_file.exists():
        prompt_template = prompt_file.read_text(encoding="utf-8")
    else:
        prompt_template = "请总结以下近期热门的 AI 论文：\n\n{papers_text}"
        
    prompt = prompt_template.replace("{papers_text}", all_text)

    messages = [{"role": "user", "content": prompt}]
    return await chat_text_func(messages)
