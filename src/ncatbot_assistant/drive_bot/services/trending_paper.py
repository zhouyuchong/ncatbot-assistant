from __future__ import annotations

import datetime
import re
import sqlite3
from pathlib import Path
from collections.abc import Callable, Awaitable
from typing import Any

INVALID_FILENAME_CHARS = re.compile(r'[/\\:*?"<>|]+')
WHITESPACE = re.compile(r"\s+")

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
    md_contents = []
    
    for row in papers:
        title = row["title"]
        update_time_str = row["update_time"]
        
        try:
            date_part = update_time_str.split()[0]
            d = datetime.date.fromisoformat(date_part)
            year, week, _ = d.isocalendar()
            week_slug = f"{year}-W{week:02d}"
        except Exception:
            continue
            
        week_dir = base_dir / week_slug
        if not week_dir.exists():
            continue
            
        stem = safe_paper_filename(title, extension="")
        matched_file = None
        for file_path in week_dir.glob(f"{stem}*.md"):
            matched_file = file_path
            break
            
        if matched_file and matched_file.exists():
            try:
                md_contents.append(f"【{title}】\n" + matched_file.read_text(encoding="utf-8"))
            except Exception:
                continue

    if not md_contents:
        raise FileNotFoundError("没有找到任何热门论文的摘要文件，请确保 crawler 已经成功生成了摘要。")

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
