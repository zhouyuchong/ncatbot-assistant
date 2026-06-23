from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .intents import ScopeType


@dataclass(frozen=True)
class ConversationKey:
    scope_type: ScopeType
    user_id: str
    group_id: str | None = None

    @classmethod
    def private(cls, user_id: str) -> "ConversationKey":
        return cls(scope_type=ScopeType.PRIVATE, user_id=str(user_id), group_id=None)

    @classmethod
    def group(cls, group_id: str | None, user_id: str) -> "ConversationKey":
        return cls(
            scope_type=ScopeType.GROUP,
            group_id=str(group_id or ""),
            user_id=str(user_id),
        )

    @classmethod
    def from_scope(
        cls,
        scope_type: ScopeType,
        user_id: str,
        group_id: str | None,
    ) -> "ConversationKey":
        if scope_type == ScopeType.GROUP:
            return cls.group(group_id=group_id, user_id=user_id)
        return cls.private(user_id=user_id)


@dataclass(frozen=True)
class LlmContextConfig:
    enabled: bool = True
    max_turns: int = 6


class ShortTermConversationMemory:
    def __init__(self, max_turns: int = 6, enabled: bool = True):
        self.max_turns = max(0, int(max_turns))
        self.enabled = bool(enabled)
        self._messages: dict[ConversationKey, list[dict[str, str]]] = {}

    def append_user_message(self, key: ConversationKey, content: str) -> None:
        self._append(key, "user", content)

    def append_assistant_message(self, key: ConversationKey, content: str) -> None:
        self._append(key, "assistant", content)

    def recent_messages(self, key: ConversationKey) -> list[dict[str, str]]:
        if not self.enabled:
            return []
        return [message.copy() for message in self._messages.get(key, [])]

    def clear(self, key: ConversationKey | None = None) -> None:
        if key is None:
            self._messages.clear()
            return
        self._messages.pop(key, None)

    def _append(self, key: ConversationKey, role: str, content: str) -> None:
        if not self.enabled:
            return
        text = content.strip()
        if not text:
            return
        messages = self._messages.setdefault(key, [])
        messages.append({"role": role, "content": text})
        limit = self.max_turns * 2
        if limit <= 0:
            messages.clear()
            return
        del messages[:-limit]


def get_llm_context_config(project_config: dict[str, Any]) -> LlmContextConfig:
    llm_config = project_config.get("llm") if isinstance(project_config, dict) else {}
    if not isinstance(llm_config, dict):
        llm_config = {}
    context_config = llm_config.get("context") or {}
    if not isinstance(context_config, dict):
        context_config = {}
    enabled = context_config.get("enabled", True)
    max_turns = context_config.get("max_turns", 6)
    try:
        max_turns_int = int(max_turns)
    except (TypeError, ValueError):
        max_turns_int = 6
    return LlmContextConfig(enabled=bool(enabled), max_turns=max(0, max_turns_int))
