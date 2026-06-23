# Drive Bot Short-Term LLM Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add configurable in-memory short-term context for Drive Bot LLM fallback replies.

**Architecture:** Add a focused `llm_context.py` module that stores bounded user/assistant chat messages by private or per-user group conversation key. Wire the plugin's LLM fallback to build messages from system prompt, recent history, and current prompt, then record successful exchanges. Keep commands and queued tasks outside context by only touching the `LlmFallbackIntent` path.

**Tech Stack:** Python 3.9+, standard-library `dataclasses`, `collections`, `unittest`, existing NcatBot plugin adapter stubs.

---

## File Structure

- Create `src/ncatbot_assistant/drive_bot/llm_context.py`: conversation key, bounded in-memory message storage, config parsing.
- Create `tests/test_drive_bot_llm_context.py`: unit tests for memory isolation, trimming, disabled mode, and config parsing.
- Modify `src/ncatbot_assistant/drive_bot/ncatbot_plugin.py`: initialize memory, pass scope into `_ask_ai`, build LLM messages with history, record successful and failed exchanges according to the spec.
- Modify `tests/test_drive_bot_config.py`: plugin-level tests for LLM message construction and context recording.
- Modify `config.example.yaml`: add `llm.context.enabled` and `llm.context.max_turns`.

## Task 1: In-Memory Conversation Context

**Files:**
- Create: `tests/test_drive_bot_llm_context.py`
- Create: `src/ncatbot_assistant/drive_bot/llm_context.py`

- [ ] **Step 1: Write failing memory tests**

Create `tests/test_drive_bot_llm_context.py`:

```python
from unittest import TestCase, main

import tests.bootstrap  # noqa: F401

from ncatbot_assistant.drive_bot.intents import ScopeType
from ncatbot_assistant.drive_bot.llm_context import (
    ConversationKey,
    LlmContextConfig,
    ShortTermConversationMemory,
    get_llm_context_config,
)


class ShortTermConversationMemoryTest(TestCase):
    def test_private_chat_returns_recent_messages_in_order(self):
        memory = ShortTermConversationMemory(max_turns=2)
        key = ConversationKey.private(user_id="u1")

        memory.append_user_message(key, "你好")
        memory.append_assistant_message(key, "你好呀")

        self.assertEqual(
            memory.recent_messages(key),
            [
                {"role": "user", "content": "你好"},
                {"role": "assistant", "content": "你好呀"},
            ],
        )

    def test_group_chat_isolated_by_group_and_user(self):
        memory = ShortTermConversationMemory(max_turns=3)
        key_a = ConversationKey.group(group_id="g1", user_id="u1")
        key_b = ConversationKey.group(group_id="g1", user_id="u2")
        key_c = ConversationKey.group(group_id="g2", user_id="u1")

        memory.append_user_message(key_a, "asyncio")
        memory.append_user_message(key_b, "sql")
        memory.append_user_message(key_c, "docker")

        self.assertEqual(memory.recent_messages(key_a), [{"role": "user", "content": "asyncio"}])
        self.assertEqual(memory.recent_messages(key_b), [{"role": "user", "content": "sql"}])
        self.assertEqual(memory.recent_messages(key_c), [{"role": "user", "content": "docker"}])

    def test_memory_trims_old_messages_by_max_turns(self):
        memory = ShortTermConversationMemory(max_turns=1)
        key = ConversationKey.private(user_id="u1")

        memory.append_user_message(key, "old user")
        memory.append_assistant_message(key, "old assistant")
        memory.append_user_message(key, "new user")
        memory.append_assistant_message(key, "new assistant")

        self.assertEqual(
            memory.recent_messages(key),
            [
                {"role": "user", "content": "new user"},
                {"role": "assistant", "content": "new assistant"},
            ],
        )

    def test_disabled_memory_returns_no_history(self):
        memory = ShortTermConversationMemory(max_turns=3, enabled=False)
        key = ConversationKey.private(user_id="u1")

        memory.append_user_message(key, "你好")
        memory.append_assistant_message(key, "你好呀")

        self.assertEqual(memory.recent_messages(key), [])

    def test_context_config_uses_defaults_and_clamps_max_turns(self):
        self.assertEqual(get_llm_context_config({}), LlmContextConfig(enabled=True, max_turns=6))
        self.assertEqual(
            get_llm_context_config({"llm": {"context": {"enabled": False, "max_turns": -3}}}),
            LlmContextConfig(enabled=False, max_turns=0),
        )
        self.assertEqual(
            get_llm_context_config({"llm": {"context": {"enabled": "yes", "max_turns": "2"}}}),
            LlmContextConfig(enabled=True, max_turns=2),
        )

    def test_conversation_key_from_scope(self):
        self.assertEqual(
            ConversationKey.from_scope(ScopeType.PRIVATE, user_id="u1", group_id=None),
            ConversationKey.private(user_id="u1"),
        )
        self.assertEqual(
            ConversationKey.from_scope(ScopeType.GROUP, user_id="u1", group_id="g1"),
            ConversationKey.group(group_id="g1", user_id="u1"),
        )


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run red test**

Run:

```bash
python3 -m unittest tests/test_drive_bot_llm_context.py
```

Expected: fails with `ModuleNotFoundError: No module named 'ncatbot_assistant.drive_bot.llm_context'`.

- [ ] **Step 3: Implement minimal context module**

Create `src/ncatbot_assistant/drive_bot/llm_context.py`:

```python
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
        return cls(scope_type=ScopeType.GROUP, group_id=str(group_id or ""), user_id=str(user_id))

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
```

- [ ] **Step 4: Run green test**

Run:

```bash
python3 -m unittest tests/test_drive_bot_llm_context.py
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/ncatbot_assistant/drive_bot/llm_context.py tests/test_drive_bot_llm_context.py
git commit -m "feat: add short-term llm context memory"
```

## Task 2: Wire LLM Context Into Plugin Fallback

**Files:**
- Modify: `tests/test_drive_bot_config.py`
- Modify: `src/ncatbot_assistant/drive_bot/ncatbot_plugin.py`

- [ ] **Step 1: Write failing plugin tests**

Add these helpers and tests to `tests/test_drive_bot_config.py`:

```python
class FakeLogger:
    def warning(self, *args, **kwargs):
        pass


class FakeAiApi:
    def __init__(self, response=None, error=None):
        self.response = response or "ok"
        self.error = error
        self.calls = []

    async def chat_text(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        if self.error is not None:
            raise self.error
        return self.response


class FakePlugin:
    def __init__(self, module, ai_api):
        config = {"llm": {"context": {"enabled": True, "max_turns": 2}}}
        context_config = module.get_llm_context_config(config)
        self._conversation_memory = module.ShortTermConversationMemory(
            enabled=context_config.enabled,
            max_turns=context_config.max_turns,
        )
        self.api = types.SimpleNamespace(ai=ai_api)
        self.logger = FakeLogger()

    def get_config(self, key, default=None):
        defaults = {
            "ai_base_url": "https://default.example.com",
            "ai_api_key": "fake-api-key",
            "ai_model": "default-model",
            "ai_temperature": 0.7,
            "ai_max_tokens": 800,
        }
        return defaults.get(key, default)
```

Then add methods to `DriveBotConfigTest`:

```python
    def test_ask_ai_includes_history_before_current_prompt(self):
        module = load_core_plugin_module()
        ai_api = FakeAiApi(response="继续解释 asyncio")
        plugin = FakePlugin(module, ai_api)
        key = module.ConversationKey.private("u1")
        plugin._conversation_memory.append_user_message(key, "我在学 asyncio")
        plugin._conversation_memory.append_assistant_message(key, "可以从事件循环理解")

        result = asyncio.run(
            module.DriveBotPlugin._ask_ai(
                plugin,
                "继续刚才那个",
                scope_type=module.ScopeType.PRIVATE,
                user_id="u1",
                group_id=None,
            )
        )

        self.assertEqual(result, "继续解释 asyncio")
        messages = ai_api.calls[0][0]
        self.assertEqual(messages[1:], [
            {"role": "user", "content": "我在学 asyncio"},
            {"role": "assistant", "content": "可以从事件循环理解"},
            {"role": "user", "content": "继续刚才那个"},
        ])

    def test_ask_ai_records_user_and_assistant_on_success(self):
        module = load_core_plugin_module()
        ai_api = FakeAiApi(response="你好呀")
        plugin = FakePlugin(module, ai_api)

        asyncio.run(
            module.DriveBotPlugin._ask_ai(
                plugin,
                "你好",
                scope_type=module.ScopeType.PRIVATE,
                user_id="u1",
                group_id=None,
            )
        )

        key = module.ConversationKey.private("u1")
        self.assertEqual(plugin._conversation_memory.recent_messages(key), [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好呀"},
        ])

    def test_ask_ai_records_only_user_on_failure(self):
        module = load_core_plugin_module()
        ai_api = FakeAiApi(error=RuntimeError("boom"))
        plugin = FakePlugin(module, ai_api)

        result = asyncio.run(
            module.DriveBotPlugin._ask_ai(
                plugin,
                "你好",
                scope_type=module.ScopeType.PRIVATE,
                user_id="u1",
                group_id=None,
            )
        )

        self.assertIn("AI 暂时不可用", result)
        key = module.ConversationKey.private("u1")
        self.assertEqual(plugin._conversation_memory.recent_messages(key), [
            {"role": "user", "content": "你好"},
        ])
```

Also add `import asyncio` at the top of the test file.

- [ ] **Step 2: Run red plugin tests**

Run:

```bash
python3 -m unittest tests/test_drive_bot_config.py
```

Expected: fails because `ncatbot_plugin` does not expose/import `ConversationKey`, `ShortTermConversationMemory`, `get_llm_context_config`, and `_ask_ai` does not accept scope fields yet.

- [ ] **Step 3: Implement plugin wiring**

Modify `src/ncatbot_assistant/drive_bot/ncatbot_plugin.py`:

```python
from ncatbot_assistant.drive_bot.llm_context import (  # noqa: E402
    ConversationKey,
    ShortTermConversationMemory,
    get_llm_context_config,
)
```

In `on_load`, after `project_config = _load_project_config()`:

```python
        llm_context_config = get_llm_context_config(project_config)
        self._conversation_memory = ShortTermConversationMemory(
            enabled=llm_context_config.enabled,
            max_turns=llm_context_config.max_turns,
        )
```

Change the LLM fallback call in `_handle_message`:

```python
            await event.reply(
                text=await self._ask_ai(
                    intent.prompt,
                    scope_type=scope_type,
                    user_id=user_id,
                    group_id=group_id,
                )
            )
```

Change `_ask_ai` signature and message construction:

```python
    async def _ask_ai(
        self,
        prompt: str,
        scope_type: ScopeType,
        user_id: str,
        group_id: str | None,
    ) -> str:
        key = ConversationKey.from_scope(scope_type, user_id=user_id, group_id=group_id)
        user_prompt = prompt.strip()
        history = self._conversation_memory.recent_messages(key)
        messages = [
            {"role": "system", "content": _build_ai_system_prompt()},
            *history,
            {"role": "user", "content": user_prompt},
        ]
```

After successful `chat_text`, record and return:

```python
            reply = await ai_api.chat_text(...)
            self._conversation_memory.append_user_message(key, user_prompt)
            self._conversation_memory.append_assistant_message(key, reply)
            return reply
```

In the `except Exception as exc` block, record only the user prompt before returning the fallback text:

```python
            self._conversation_memory.append_user_message(key, user_prompt)
            self.logger.warning("AI 兜底回复失败: %s", exc)
            return f"AI 暂时不可用喵：{exc}"
```

- [ ] **Step 4: Run green plugin tests**

Run:

```bash
python3 -m unittest tests/test_drive_bot_config.py
```

Expected: all config/plugin tests pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/ncatbot_assistant/drive_bot/ncatbot_plugin.py tests/test_drive_bot_config.py
git commit -m "feat: use short-term context for llm fallback"
```

## Task 3: Config Example And Full Verification

**Files:**
- Modify: `config.example.yaml`

- [ ] **Step 1: Write failing config example check**

Add a test to `tests/test_drive_bot_config.py`:

```python
    def test_config_example_documents_llm_context_defaults(self):
        import yaml

        config = yaml.safe_load((ROOT / "config.example.yaml").read_text(encoding="utf-8"))

        self.assertEqual(config["llm"]["context"], {"enabled": True, "max_turns": 6})
```

- [ ] **Step 2: Run red config example test**

Run:

```bash
python3 -m unittest tests/test_drive_bot_config.py
```

Expected: fails with `KeyError: 'context'`.

- [ ] **Step 3: Update config example**

Modify `config.example.yaml`:

```yaml
llm:
  api_key: "fake-api-key"
  base_url: "https://api.deepseek.com"
  model: "deepseek-v4-flash"
  temperature: 0.7
  max_tokens: 800
  context:
    enabled: true
    max_turns: 6
```

- [ ] **Step 4: Run full verification**

Run:

```bash
python3 -m unittest discover tests
PYTHONPYCACHEPREFIX=/tmp/ncatbot-assistant-pycache python3 -m py_compile plugins/drive_bot/plugin.py src/ncatbot_assistant/drive_bot/*.py src/ncatbot_assistant/drive_bot/jobs/*.py src/ncatbot_assistant/drive_bot/services/*.py tests/*.py
```

Expected: all tests pass and py_compile exits 0.

- [ ] **Step 5: Commit**

Run:

```bash
git add config.example.yaml tests/test_drive_bot_config.py
git commit -m "docs: document llm context config"
```

## Self-Review

- Spec coverage: tasks cover in-memory storage, scope isolation, configurable enable/max turns, trimming, plugin message construction, success/failure recording, and config example updates.
- Placeholder scan: no task contains TBD, TODO, "similar to", or unspecified error handling.
- Type consistency: `ConversationKey`, `ShortTermConversationMemory`, `LlmContextConfig`, and `get_llm_context_config` names are consistent across tests and implementation steps.
