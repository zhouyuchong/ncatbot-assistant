from __future__ import annotations

from dataclasses import dataclass

from .intents import TaskType


@dataclass(frozen=True)
class CommandSpec:
    name: str
    title: str
    usage: str
    description: str
    slash_aliases: tuple[str, ...]
    text_aliases: tuple[str, ...] = ()
    task_type: TaskType | None = None
    category: str = "other"


COMMAND_SPECS: tuple[CommandSpec, ...] = (
    CommandSpec(
        name="help",
        title="帮助",
        usage="/help",
        description="查看 Drive Bot 指南",
        slash_aliases=("/help",),
        text_aliases=("使用方法", "帮助", "help"),
        category="other",
    ),
    CommandSpec(
        name="jm",
        title="JM",
        usage="/jm <关键词|数字ID>",
        description="搜索 JMComic album；数字 ID 会进入下载队列并生成 PDF",
        slash_aliases=("/jm",),
        category="comic",
    ),
    CommandSpec(
        name="setu",
        title="涩图",
        usage="/setu [标签1] [标签2] [标签3]",
        description="按最多 3 个标签获取图片并上传",
        slash_aliases=("/setu",),
        task_type=TaskType.SETU,
        category="media",
    ),
    CommandSpec(
        name="news",
        title="每日新闻",
        usage="/news",
        description="获取 Currents 最新新闻，并生成中文摘要",
        slash_aliases=("/news", "/dailynews"),
        text_aliases=("每日新闻",),
        task_type=TaskType.DAILY,
        category="news",
    ),
    CommandSpec(
        name="dailyai",
        title="每日 AI 看点",
        usage="/dailyai",
        description="读取本地 Markdown 论文数据，生成今日 AI 技术看点",
        slash_aliases=("/dailyai",),
        text_aliases=("每日ai", "每日AI"),
        task_type=TaskType.DAILY_AI,
        category="news",
    ),
    CommandSpec(
        name="anime-news",
        title="动漫新闻",
        usage="/anime-news",
        description="读取已配置的动漫新闻文件并发送",
        slash_aliases=("/anime-news", "/animenews"),
        text_aliases=("动漫新闻",),
        task_type=TaskType.ANIME_NEWS,
        category="news",
    ),
    CommandSpec(
        name="profile",
        title="用户画像",
        usage="/profile",
        description="查看当前用户画像 prompt",
        slash_aliases=("/profile", "/showUserProfile"),
        category="other",
    ),
)


COMMANDS_BY_NAME = {spec.name: spec for spec in COMMAND_SPECS}


def command_spec(name: str) -> CommandSpec:
    return COMMANDS_BY_NAME[name]


def slash_aliases(name: str) -> tuple[str, ...]:
    return command_spec(name).slash_aliases


def text_aliases(name: str) -> tuple[str, ...]:
    return command_spec(name).text_aliases
