"""Bounded, ephemeral state for a user's current task conversation."""
from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Callable

from .llm_context import ConversationKey
from .services.jm import JmSearchItem


@dataclass(frozen=True)
class PendingAction:
    tool_name: str
    missing_field: str


@dataclass
class TaskConversationState:
    search_results: list[JmSearchItem] = field(default_factory=list)
    pending_action: PendingAction | None = None
    last_download_task_id: int | None = None
    last_task_id: int | None = None
    updated_at: float = 0


class TaskConversationStateStore:
    def __init__(self, clock: Callable[[], float] = time.monotonic,
                 ttl_seconds: int = 900, max_sessions: int = 1000):
        self.clock = clock
        self.ttl_seconds = ttl_seconds
        self.max_sessions = max_sessions
        self._states: OrderedDict[ConversationKey, TaskConversationState] = OrderedDict()
        self._messages: OrderedDict[tuple[ConversationKey, str], float] = OrderedDict()
        self._locks: dict[ConversationKey, tuple[asyncio.Lock, int]] = {}

    def _expire(self) -> None:
        now = self.clock()
        for key in list(self._states):
            if now - self._states[key].updated_at >= self.ttl_seconds:
                del self._states[key]
        while self._messages:
            key, timestamp = next(iter(self._messages.items()))
            if now - timestamp < self.ttl_seconds:
                break
            del self._messages[key]

    def get(self, key: ConversationKey) -> TaskConversationState:
        self._expire()
        return deepcopy(self._states.get(key, TaskConversationState()))

    def update(self, key: ConversationKey, state: TaskConversationState) -> None:
        self._expire()
        snapshot = deepcopy(state)
        snapshot.updated_at = self.clock()
        self._states[key] = snapshot
        self._states.move_to_end(key)
        while len(self._states) > self.max_sessions:
            self._states.popitem(last=False)

    def clear(self, key: ConversationKey) -> None:
        self._states.pop(key, None)

    def claim_message(self, key: ConversationKey, message_id: str) -> bool:
        # Events without an ID cannot safely be deduplicated against one another.
        if not message_id:
            return True
        self._expire()
        identity = (key, message_id)
        if identity in self._messages:
            return False
        self._messages[identity] = self.clock()
        while len(self._messages) > 2000:
            self._messages.popitem(last=False)
        return True

    @asynccontextmanager
    async def lock(self, key: ConversationKey):
        lock, count = self._locks.get(key, (asyncio.Lock(), 0))
        self._locks[key] = (lock, count + 1)
        try:
            async with lock:
                yield
        finally:
            _, count = self._locks[key]
            if count == 1:
                del self._locks[key]
            else:
                self._locks[key] = (lock, count - 1)
