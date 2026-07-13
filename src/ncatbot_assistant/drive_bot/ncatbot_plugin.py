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
from ncatbot_assistant.drive_bot.constants import ensure_runtime_directories  # noqa: E402
from ncatbot_assistant.drive_bot.estimator import estimate_seconds, format_duration  # noqa: E402
from ncatbot_assistant.drive_bot.intents import (  # noqa: E402
    ImmediateResponse,
    LlmFallbackIntent,
    QueuedTaskIntent,
    ScopeType,
    ShowUserProfileIntent,
)
from ncatbot_assistant.drive_bot.jobs.handlers import TaskHandlers  # noqa: E402
from ncatbot_assistant.drive_bot.jobs.queue import TaskQueueWorker  # noqa: E402
from ncatbot_assistant.drive_bot.llm_context import (  # noqa: E402
    ConversationKey,
    ShortTermConversationMemory,
    get_llm_context_config,
)
from ncatbot_assistant.drive_bot.reply import ReplyAdapter  # noqa: E402
from ncatbot_assistant.drive_bot.router import route_message  # noqa: E402
from ncatbot_assistant.drive_bot.services.daily import generate_daily_news  # noqa: E402
from ncatbot_assistant.drive_bot.services.daily_ai import generate_daily_ai_summary  # noqa: E402
from ncatbot_assistant.drive_bot.services.anime_news import get_anime_news  # noqa: E402
from ncatbot_assistant.drive_bot.services.trending_paper import generate_trending_paper_summary  # noqa: E402
from ncatbot_assistant.drive_bot.services.jm import search as jm_search  # noqa: E402
from ncatbot_assistant.drive_bot.storage import TaskStore  # noqa: E402
from ncatbot_assistant.drive_bot.user_memory import (  # noqa: E402
    DailyUserMemoryScheduler,
    UserMemoryConfig,
    UserMemoryStore,
    UserMemorySummarizer,
    build_user_memory_injection,
    get_user_memory_config,
)
from ncatbot.core import registrar
from ncatbot.event.qq import GroupMessageEvent, PrivateMessageEvent
from ncatbot.plugin import NcatBotPlugin

AI_SYSTEM_PROMPT = (
    "你是一个接入 QQ 的轻量助手。请用简洁、自然的中文回复用户，"
    "不要假装自己能上传文件或执行插件命令。"
)
NEKO_PROMPT_PATH = PROJECT_DIR / "resources" / "skills" / "neko_prompt_r18.md"


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
        "short_conversation_max_tokens": ("short_conversation_max_tokens", "ai_short_conversation_max_tokens"),
        "long_conversation_max_tokens": ("long_conversation_max_tokens", "ai_long_conversation_max_tokens"),
    }
    merged = {}
    for key, key_aliases in aliases.items():
        value = _first_config_value(llm_config, key_aliases)
        if value is None:
            value = _first_config_value(default_config, (key, *key_aliases))
        if value is None and key in {"short_conversation_max_tokens", "long_conversation_max_tokens"}:
            continue
        merged[key] = value
    return merged


@lru_cache(maxsize=1)
def _load_neko_prompt() -> str:
    if not NEKO_PROMPT_PATH.exists():
        return ""
    return NEKO_PROMPT_PATH.read_text(encoding="utf-8").strip()


def _build_ai_system_prompt() -> str:
    neko_prompt = _load_neko_prompt()
    if not neko_prompt:
        return AI_SYSTEM_PROMPT
    return f"{AI_SYSTEM_PROMPT}\n\n{neko_prompt}"


def _intent_type(intent) -> str:
    if isinstance(intent, LlmFallbackIntent):
        return "llm_fallback"
    if isinstance(intent, QueuedTaskIntent):
        return "queued_task"
    if isinstance(intent, ShowUserProfileIntent):
        return "show_user_profile"
    if isinstance(intent, ImmediateResponse):
        return "immediate"
    return "unknown"


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
        ensure_runtime_directories()
        llm_context_config = get_llm_context_config(project_config)
        self._user_memory_config = get_user_memory_config(project_config)
        self._conversation_memory = ShortTermConversationMemory(
            enabled=llm_context_config.enabled,
            max_turns=llm_context_config.max_turns,
        )
        self._task_estimates = get_task_estimates(project_config)
        self._events_by_task_id = {}
        storage_path = get_storage_path(project_config)
        self._task_store = TaskStore(storage_path)
        self._task_store.initialize()
        self._user_memory_store = UserMemoryStore(storage_path)
        self._user_memory_store.initialize()
        recovered = self._task_store.recover_running_tasks()
        if recovered:
            self.logger.warning("已恢复 %s 个中断任务为失败状态", recovered)
        self._reply_adapter = ReplyAdapter(
            file_api=self.api.qq.file,
            event_lookup=lambda task: self._events_by_task_id[task.id],
        )

        async def daily_func():
            return await generate_daily_news(
                project_config=project_config,
                chat_text_func=self._ask_memory_summary,
                logger=self.logger,
            )

        async def daily_ai_func():
            return await generate_daily_ai_summary(
                project_config=project_config,
                chat_text_func=self._ask_memory_summary,
            )

        async def anime_news_func():
            return await get_anime_news(project_config)

        async def trending_paper_func():
            return await generate_trending_paper_summary(
                project_config=project_config,
                chat_text_func=self._ask_memory_summary,
            )

        self._task_handlers = TaskHandlers(
            reply=self._reply_adapter,
            logger=self.logger,
            daily_function=daily_func,
            daily_ai_function=daily_ai_func,
            anime_news_function=anime_news_func,
            trending_paper_function=trending_paper_func,
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
        self._user_memory_summarizer = UserMemorySummarizer(
            store=self._user_memory_store,
            config=self._user_memory_config,
            chat_text=self._ask_memory_summary,
        )
        self._user_memory_scheduler = DailyUserMemoryScheduler(
            summarize=self._user_memory_summarizer.summarize_due_users,
            config=self._user_memory_config,
            logger=self.logger,
        )
        self._user_memory_scheduler.start()
        self.logger.info("%s 已加载", self.name)

    async def on_close(self) -> None:
        if hasattr(self, "_task_worker"):
            await self._task_worker.stop()
        if hasattr(self, "_user_memory_scheduler"):
            await self._user_memory_scheduler.stop()
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
        if isinstance(intent, ShowUserProfileIntent):
            await event.reply(text=DriveBotPlugin._build_user_profile_reply(self, user_id))
            return

        DriveBotPlugin._record_user_memory_message(
            self,
            scope_type=scope_type,
            group_id=group_id,
            user_id=user_id,
            text=text,
            intent_type=_intent_type(intent),
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
            await event.reply(
                text=await self._ask_ai(
                    intent.prompt,
                    scope_type=scope_type,
                    user_id=user_id,
                    group_id=group_id,
                )
            )

    def _build_user_profile_reply(self, user_id: str) -> str:
        config = getattr(self, "_user_memory_config", UserMemoryConfig())
        if not config.enabled:
            return "用户画像功能未启用"
        store = getattr(self, "_user_memory_store", None)
        if store is None:
            return "用户画像存储暂时不可用"
        profile = store.get_or_create_profile(user_id)
        text = profile.user_prompt.strip()
        if not text:
            return "暂无用户画像 prompt"
        return f"当前用户画像 prompt：\n{text}"

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

    def _record_user_memory_message(
        self,
        scope_type: ScopeType,
        group_id: str | None,
        user_id: str,
        text: str,
        intent_type: str,
    ) -> None:
        config = getattr(self, "_user_memory_config", UserMemoryConfig())
        if not config.enabled or not config.group_enabled or scope_type != ScopeType.GROUP:
            return
        store = getattr(self, "_user_memory_store", None)
        if store is None:
            return
        try:
            store.record_message(
                scope_type=scope_type,
                group_id=group_id,
                user_id=user_id,
                message_text=text,
                intent_type=intent_type,
            )
        except Exception as exc:
            self.logger.warning("记录用户记忆失败: %s", exc)

    async def _ask_ai(
        self,
        prompt: str,
        scope_type: ScopeType,
        user_id: str,
        group_id: str | None,
    ) -> str:
        key = ConversationKey.from_scope(
            scope_type,
            user_id=user_id,
            group_id=group_id,
        )
        user_prompt = prompt.strip()
        history = self._conversation_memory.recent_messages(key)
        user_memory_message = DriveBotPlugin._user_memory_message(self, scope_type, user_id)
        messages = [
            {"role": "system", "content": _build_ai_system_prompt()},
            *([user_memory_message] if user_memory_message else []),
            *history,
            {"role": "user", "content": user_prompt},
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
        short_max = llm_config.get("short_conversation_max_tokens")
        max_tokens = int(short_max) if short_max is not None else int(llm_config["max_tokens"])
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
            self.logger.info("Calling LLM (short conversation) with model=%s, max_tokens=%s, temperature=%s", model, max_tokens, temperature)
            reply = await ai_api.chat_text(
                messages,
                model=_litellm_openai_model(model),
                temperature=temperature,
                max_tokens=max_tokens,
                api_key=api_key,
                api_base=base_url,
            )
            self._conversation_memory.append_user_message(key, user_prompt)
            self._conversation_memory.append_assistant_message(key, reply)
            return reply
        except Exception as exc:
            self._conversation_memory.append_user_message(key, user_prompt)
            self.logger.warning("AI 兜底回复失败: %s", exc)
            return f"AI 暂时不可用喵：{exc}"

    def _user_memory_message(
        self,
        scope_type: ScopeType,
        user_id: str,
    ) -> dict[str, str] | None:
        config = getattr(self, "_user_memory_config", UserMemoryConfig())
        if not config.enabled or not config.group_enabled or scope_type != ScopeType.GROUP:
            return None
        store = getattr(self, "_user_memory_store", None)
        if store is None:
            return None
        profile = store.get_or_create_profile(user_id)
        if not profile.enabled:
            return None
        return build_user_memory_injection(profile.user_prompt)

    async def _ask_memory_summary(self, messages: list[dict[str, str]]) -> str:
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
        long_max = llm_config.get("long_conversation_max_tokens")
        max_tokens = int(long_max) if long_max is not None else int(llm_config["max_tokens"])
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

        self.logger.info("Calling LLM (long conversation) with model=%s, max_tokens=%s, temperature=%s", model, max_tokens, temperature)
        return await ai_api.chat_text(
            messages,
            model=_litellm_openai_model(model),
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=api_key,
            api_base=base_url,
        )
