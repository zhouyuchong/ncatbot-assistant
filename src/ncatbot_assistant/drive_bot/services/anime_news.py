import os
from typing import Any

async def get_anime_news(project_config: dict[str, Any]) -> str:
    tasks_config = project_config.get("tasks", {})
    anime_news_config = tasks_config.get("anime_news", {})
    file_path = anime_news_config.get("file_path", "")
    
    if not file_path:
        raise RuntimeError("未配置动漫新闻文件路径 (tasks.anime_news.file_path)")
        
    if not os.path.exists(file_path):
        raise RuntimeError(f"找不到动漫新闻文件: {file_path}")
        
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return "动漫新闻文件内容为空。"
            return content
    except Exception as e:
        raise RuntimeError(f"读取动漫新闻文件失败: {e}")
