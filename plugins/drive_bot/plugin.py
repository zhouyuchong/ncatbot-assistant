"""Drive group helper plugin.

Author: zhouyuchong
Date: 2026-06-22 13:01:18
Description:
LastEditors: zhouyuchong
LastEditTime: 2026-06-22 13:47:25
"""

import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from ncatbot.core import registrar
from ncatbot.event.qq import GroupMessageEvent, PrivateMessageEvent
from ncatbot.plugin import NcatBotPlugin

PROJECT_DIR = Path(__file__).resolve().parents[2]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from utils.msg_parser import message_parser  # noqa: E402

AI_FALLBACK_TRIGGER_TEXT = "无法理解喵"
AI_SYSTEM_PROMPT = (
    "你是一个接入 QQ 的轻量助手。请用简洁、自然的中文回复用户，"
    "不要假装自己能上传文件或执行插件命令。"
)
NEKO_SKILL_DIR = PROJECT_DIR / "skills" / "neko-on-everything"
NEKO_SKILL_FILES = (
    "SKILL.md",
    "references/persona.md",
    "references/avatars/code.md",
    "references/avatars/life.md",
    "references/avatars/math.md",
)


def _answer_files(answer: dict[str, Any]) -> list[dict[str, str]]:
    if "files" in answer:
        return list(answer["files"])
    return [{"file_name": answer["file_name"], "file_path": answer["file_path"]}]


def _delete_uploaded_file(file_path: str, logger) -> None:
    try:
        Path(file_path).unlink(missing_ok=True)
        logger.debug("已删除上传后的文件: %s", file_path)
    except Exception as exc:
        logger.warning("删除上传后的文件失败: %s", exc)


def _litellm_openai_model(model: str) -> str:
    if "/" in model:
        return model
    return f"openai/{model}"


def _env_or_config(env_name: str, config_value: Any) -> Any:
    value = os.getenv(env_name)
    if value is not None and value.strip():
        return value.strip()
    return config_value


@lru_cache(maxsize=1)
def _load_neko_skill_prompt() -> str:
    parts = []
    for relative_path in NEKO_SKILL_FILES:
        path = NEKO_SKILL_DIR / relative_path
        if path.exists():
            parts.append(path.read_text(encoding="utf-8").strip())
    if not parts:
        return ""
    return "\n\n".join(["Drive Bot roleplay skill:", *parts])


def _build_ai_system_prompt() -> str:
    skill_prompt = _load_neko_skill_prompt()
    if not skill_prompt:
        return AI_SYSTEM_PROMPT
    return f"{AI_SYSTEM_PROMPT}\n\n{skill_prompt}"


class DriveBotPlugin(NcatBotPlugin):
    """Handle QQ group requests that mention the bot."""

    async def on_load(self) -> None:
        self.init_defaults(
            {
                "ai_base_url": "https://api.deepseek.com",
                "ai_api_key": "fake-api-key",
                "ai_model": "deepseek-v4-flash",
                "ai_temperature": 0.7,
                "ai_max_tokens": 800,
            }
        )
        self._last_request_time = None
        self.logger.info("%s 已加载", self.name)

    async def on_close(self) -> None:
        self.logger.info("%s 已卸载", self.name)

    @registrar.qq.on_group_message()
    async def on_group_message(self, event: GroupMessageEvent) -> None:
        if not event.message.is_at(event.self_id):
            return

        self.logger.info(event)
        answer = await message_parser(
            msg=event.message.text,
            last_time=self._last_request_time,
            logger=self.logger,
        )
        self.logger.info(answer)
        await self._reply_group_answer(event, answer, event.message.text)

    @registrar.qq.on_private_message()
    async def on_private_message(self, event: PrivateMessageEvent) -> None:
        """
        Handle private messages sent to the bot.
        """
        """data format :
        private msg: PrivateMessageEvent(data=PrivateMessageEventData(time=1782106570, self_id='1706895031',
        post_type=<PostType.MESSAGE: 'message'>, platform='qq', message_type=<MessageType.PRIVATE: 'private'>,
        sub_type='friend', message_id='1147773616', user_id='1620404337', message=MessageArray([PlainText(text='在')]),
        raw_message='在', sender=QQSender(user_id='1620404337', nickname='DamonZzz', sex='unknown', age=0), font=14, message_seq=1147773616,
        real_id='1147773616', real_seq='70', message_format='array', target_id='1620404337'))
        """
        self.logger.info("private msg: %s", event)
        answer = await message_parser(
            msg=event.raw_message,
            last_time=self._last_request_time,
            logger=self.logger,
        )
        self.logger.info(answer)

        await self._reply_private_answer(event, answer, event.raw_message)

    async def _reply_group_answer(
        self,
        event: GroupMessageEvent,
        answer: dict[str, Any],
        prompt: str,
    ) -> None:
        self._last_request_time = answer["updated_time"]

        if answer["direct_upload"]:
            await event.reply(text=answer["text"], image=answer["file_path"])
            return

        if answer["upload_file"]:
            folder_id = await self.api.qq.file.get_or_create_group_folder(
                event.group_id,
                answer["upload_folder_name"],
            )
            for item in _answer_files(answer):
                await self.api.qq.file.upload_group_file(
                    group_id=event.group_id,
                    file=item["file_path"],
                    name=item["file_name"],
                    folder_id=folder_id,
                )
                _delete_uploaded_file(item["file_path"], self.logger)
            await event.reply(text=answer["text"])
            return

        if answer["text"] == AI_FALLBACK_TRIGGER_TEXT:
            await event.reply(text=await self._ask_ai(prompt))
            return

        await event.reply(text=answer["text"])

    async def _reply_private_answer(
        self,
        event: PrivateMessageEvent,
        answer: dict[str, Any],
        prompt: str,
    ) -> None:
        self._last_request_time = answer["updated_time"]

        if answer["direct_upload"]:
            await event.reply(text=answer["text"], image=answer["file_path"])
            return

        if answer["upload_file"]:
            for item in _answer_files(answer):
                await self.api.qq.file.upload_private_file(
                    user_id=event.user_id,
                    file=item["file_path"],
                    name=item["file_name"],
                )
                _delete_uploaded_file(item["file_path"], self.logger)
            await event.reply(text=answer["text"])
            return

        if answer["text"] == AI_FALLBACK_TRIGGER_TEXT:
            await event.reply(text=await self._ask_ai(prompt))
            return

        await event.reply(text=answer["text"])

    async def _ask_ai(self, prompt: str) -> str:
        messages = [
            {"role": "system", "content": _build_ai_system_prompt()},
            {"role": "user", "content": prompt.strip()},
        ]
        model = _env_or_config("DRIVE_BOT_AI_MODEL", self.get_config("ai_model"))
        api_key = _env_or_config("DRIVE_BOT_AI_API_KEY", self.get_config("ai_api_key"))
        base_url = _env_or_config(
            "DRIVE_BOT_AI_BASE_URL", self.get_config("ai_base_url")
        )
        max_tokens = int(
            _env_or_config(
                "DRIVE_BOT_AI_MAX_TOKENS", self.get_config("ai_max_tokens", 800)
            )
        )
        temperature = float(
            _env_or_config(
                "DRIVE_BOT_AI_TEMPERATURE", self.get_config("ai_temperature", 0.7)
            )
        )
        try:
            ai_api = self.api.ai
        except KeyError:
            from ncatbot.adapter.ai.api import AIBotAPI
            from ncatbot.adapter.ai.config import AIConfig

            ai_api = AIBotAPI(
                AIConfig(
                    api_key=api_key,
                    base_url=base_url,
                    completion_model=_litellm_openai_model(model),
                    max_tokens=max_tokens,
                )
            )

        try:
            return await ai_api.chat_text(
                messages,
                model=_litellm_openai_model(model),
                temperature=temperature,
                max_tokens=max_tokens,
                api_key=api_key,
                api_base=base_url,
            )
        except Exception as exc:
            self.logger.warning("AI 兜底回复失败: %s", exc)
            return f"AI 暂时不可用喵：{exc}"
