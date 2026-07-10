import asyncio
from typing import Any
import requests

BASE_URL = "https://anime-facts-rest-api.herokuapp.com/api/v1"

async def get_anime_list() -> str:
    return await asyncio.to_thread(_get_anime_list_sync)

def _get_anime_list_sync(timeout: int = 15) -> str:
    try:
        response = requests.get(BASE_URL, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        raise RuntimeError("获取动漫列表失败") from exc

    if not payload.get("success"):
        raise RuntimeError("获取动漫列表失败：接口返回错误")

    data = payload.get("data")
    if not isinstance(data, list) or not data:
        return "当前没有可用的动漫列表。"

    lines = ["支持查询的动漫列表："]
    for item in data:
        if isinstance(item, dict):
            name = item.get("anime_name")
            if name:
                lines.append(f"- {name}")
    
    lines.append("\n发送“动漫事实 <动漫名称>”查询详情。")
    return "\n".join(lines)


async def get_anime_facts(anime_name: str) -> str:
    return await asyncio.to_thread(_get_anime_facts_sync, anime_name)

def _get_anime_facts_sync(anime_name: str, timeout: int = 15) -> str:
    anime_name = anime_name.strip().lower()
    if not anime_name:
        raise ValueError("请输入动漫名称")

    try:
        response = requests.get(f"{BASE_URL}/{anime_name}", timeout=timeout)
        if response.status_code == 404:
             return f"未找到名为 {anime_name} 的动漫，请先发送“动漫列表”查看支持的动漫。"
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        raise RuntimeError(f"获取 {anime_name} 的事实失败") from exc

    if not payload.get("success"):
        raise RuntimeError(f"获取 {anime_name} 的事实失败：接口返回错误")

    data = payload.get("data")
    if not isinstance(data, list) or not data:
        return f"{anime_name} 暂无事实数据。"

    total = payload.get("total_facts", len(data))
    lines = [f"【{anime_name}】共有 {total} 条事实："]
    for item in data:
        if isinstance(item, dict):
            fact_id = item.get("fact_id")
            fact = item.get("fact")
            if fact:
                lines.append(f"{fact_id}. {fact}")
                
    return "\n".join(lines)
