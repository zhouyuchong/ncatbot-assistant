"""Drive Bot usage text."""

from .commands import COMMAND_SPECS


USAGE_KEYWORDS = ("使用方法", "帮助", "help", "/help")


CATEGORY_TITLES = {
    "comic": "漫画",
    "news": "资讯与 AI",
    "media": "图片",
    "other": "其他",
}


def build_drive_bot_usage() -> str:
    lines = ["Drive Bot 指南 🚀", ""]
    for category, title in CATEGORY_TITLES.items():
        specs = [spec for spec in COMMAND_SPECS if spec.category == category]
        if not specs:
            continue
        lines.append(f"{title}:")
        for spec in specs:
            aliases = _format_aliases(spec.text_aliases)
            lines.append(f"- {spec.usage}: {spec.description}{aliases}")
        lines.append("")
    lines.append("未命中命令时，直接发送文字即可与我闲聊。")
    return "\n".join(lines).strip()


def _format_aliases(aliases: tuple[str, ...]) -> str:
    if not aliases:
        return ""
    return "；别名：" + "、".join(aliases)


DRIVE_BOT_USAGE = build_drive_bot_usage()


def is_usage_question(message: str) -> bool:
    normalized = message.strip().lower().strip("。.!！?？")
    return normalized in USAGE_KEYWORDS
