from __future__ import annotations

"""Drive group helper plugin.

Author: zhouyuchong
Date: 2026-06-22 13:01:18
Description:
LastEditors: zhouyuchong
LastEditTime: 2026-06-22 13:47:25
"""

import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parents[3]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from ncatbot_assistant.drive_bot.config import (  # noqa: E402
    get_storage_path,
    get_task_estimates,
    load_project_config,
)
from ncatbot_assistant.drive_bot.estimator import estimate_seconds, format_duration  # noqa: E402
from ncatbot_assistant.drive_bot.intents import (  # noqa: E402
    ImmediateResponse,
    LlmFallbackIntent,
    QueuedTaskIntent,
    ScopeType,
)
from ncatbot_assistant.drive_bot.jobs.handlers import TaskHandlers  # noqa: E402
from ncatbot_assistant.drive_bot.jobs.queue import TaskQueueWorker  # noqa: E402
from ncatbot_assistant.drive_bot.reply import ReplyAdapter  # noqa: E402
from ncatbot_assistant.drive_bot.router import route_message  # noqa: E402
from ncatbot_assistant.drive_bot.services.jm import search as jm_search  # noqa: E402
from ncatbot_assistant.drive_bot.storage import TaskStore  # noqa: E402
from ncatbot.core import registrar
from ncatbot.event.qq import GroupMessageEvent, PrivateMessageEvent
from ncatbot.plugin import NcatBotPlugin

AI_SYSTEM_PROMPT = (
    "你是一个接入 QQ 的轻量助手。请用简洁、自然的中文回复用户，"
    "不要假装自己能上传文件或执行插件命令。"
)
NEKO_SKILL_DIR = PROJECT_DIR / "resources" / "skills" / "neko-on-everything"
NEKO_SKILL_FILES = (
    "SKILL.md",
    "references/persona.md",
    "references/avatars/code.md",
    "references/avatars/life.md",
    "references/avatars/math.md",
)


def _litellm_openai_model(model: str) -> str:
    if "/" in model:
        return model
    return f"openai/{model}"


def _non_blank(value: Any) -> bool:
    return not (isinstance(value, str) and not value.strip())


def _first_config_value(config: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in config and config[key] is not None and _non_blank(config[key]):
            value = config[key]
            return value.strip() if isinstance(value, str) else value
    return None


@lru_cache(maxsize=1)
def _load_project_config() -> dict[str, Any]:
    return load_project_config()


def _merge_llm_config(
    project_config: dict[str, Any],
    default_config: dict[str, Any],
) -> dict[str, Any]:
    llm_config = project_config.get("llm") or {}
    if not isinstance(llm_config, dict):
        llm_config = {}

    aliases = {
        "base_url": ("base_url", "ai_base_url"),
        "api_key": ("api_key", "ai_api_key"),
        "model": ("model", "ai_model"),
        "temperature": ("temperature", "ai_temperature"),
        "max_tokens": ("max_tokens", "ai_max_tokens"),
    }
    merged = {}
    for key, key_aliases in aliases.items():
        value = _first_config_value(llm_config, key_aliases)
        if value is None:
            value = _first_config_value(default_config, (key, *key_aliases))
        merged[key] = value
    return merged


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
        project_config = _load_project_config()
        self._task_estimates = get_task_estimates(project_config)
        self._events_by_task_id = {}
        self._task_store = TaskStore(get_storage_path(project_config))
        self._task_store.initialize()
        recovered = self._task_store.recover_running_tasks()
        if recovered:
            self.logger.warning("已恢复 %s 个中断任务为失败状态", recovered)
        self._reply_adapter = ReplyAdapter(
            file_api=self.api.qq.file,
            event_lookup=lambda task: self._events_by_task_id[task.id],
        )
        self._task_handlers = TaskHandlers(
            reply=self._reply_adapter,
            logger=self.logger,
        )
        self._task_worker = TaskQueueWorker(
            store=self._task_store,
            handlers={
                task_type: self._task_handlers.handle
                for task_type in self._task_handlers.supported_task_types()
            },
            notify=self._reply_adapter.notify_task_done,
        )
        self._task_worker.start()
        self.logger.info("%s 已加载", self.name)

    async def on_close(self) -> None:
        if hasattr(self, "_task_worker"):
            await self._task_worker.stop()
        self.logger.info("%s 已卸载", self.name)

    @registrar.qq.on_group_message()
    async def on_group_message(self, event: GroupMessageEvent) -> None:
        if not event.message.is_at(event.self_id):
            return

        self.logger.info(event)
        await self._handle_message(
            event=event,
            text=event.message.text,
            scope_type=ScopeType.GROUP,
            group_id=str(event.group_id),
            user_id=str(event.user_id),
        )

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
        await self._handle_message(
            event=event,
            text=event.raw_message,
            scope_type=ScopeType.PRIVATE,
            group_id=None,
            user_id=str(event.user_id),
        )

    async def _handle_message(
        self,
        event,
        text: str,
        scope_type: ScopeType,
        user_id: str,
        group_id: str | None,
    ) -> None:
        intent = route_message(
            text,
            scope_type=scope_type,
            group_id=group_id,
            user_id=user_id,
            jm_search_func=lambda tags: jm_search(tags, self.logger),
        )
        if isinstance(intent, ImmediateResponse):
            await event.reply(text=intent.text)
            return

        if isinstance(intent, QueuedTaskIntent):
            task = self._enqueue_task(intent)
            self._events_by_task_id[task.id] = event
            await event.reply(text=self._build_enqueue_reply(task))
            return

        if isinstance(intent, LlmFallbackIntent):
            await event.reply(text=await self._ask_ai(intent.prompt))

    def _enqueue_task(self, intent: QueuedTaskIntent):
        estimated = estimate_seconds(intent.task_type, self._task_estimates)
        return self._task_store.enqueue(
            task_type=intent.task_type,
            scope_type=intent.scope_type,
            group_id=intent.group_id,
            user_id=intent.user_id,
            raw_message=intent.raw_message,
            payload=intent.payload,
            estimated_seconds=estimated,
        )

    def _build_enqueue_reply(self, task) -> str:
        position = self._task_store.queue_position(task.id)
        wait_seconds = self._task_store.estimated_wait_seconds(task.id)
        notify_text = "完成后我会 @你。" if task.scope_type == ScopeType.GROUP else "完成后我会通知你。"
        return (
            f"已收到，任务 #{task.id} 已加入队列。\n"
            f"当前排队位置：{position}\n"
            f"预计等待：{format_duration(wait_seconds)}，"
            f"预计总耗时：{format_duration(wait_seconds + task.estimated_seconds)}。\n"
            f"{notify_text}"
        )

    async def _ask_ai(self, prompt: str) -> str:
        messages = [
            {"role": "system", "content": _build_ai_system_prompt()},
            {"role": "user", "content": prompt.strip()},
        ]
        llm_config = _merge_llm_config(
            _load_project_config(),
            {
                "ai_base_url": self.get_config("ai_base_url"),
                "ai_api_key": self.get_config("ai_api_key"),
                "ai_model": self.get_config("ai_model"),
                "ai_temperature": self.get_config("ai_temperature", 0.7),
                "ai_max_tokens": self.get_config("ai_max_tokens", 800),
            },
        )
        model = llm_config["model"]
        api_key = llm_config["api_key"]
        base_url = llm_config["base_url"]
        max_tokens = int(llm_config["max_tokens"])
        temperature = float(llm_config["temperature"])
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
