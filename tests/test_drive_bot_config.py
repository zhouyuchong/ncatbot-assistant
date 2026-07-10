import asyncio
import importlib.util
import sys
import types
from pathlib import Path
from unittest import TestCase, main

import tests.bootstrap  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]


def load_plugin_module():
    sys.modules.setdefault("ncatbot", types.ModuleType("ncatbot"))

    ncatbot_core = types.ModuleType("ncatbot.core")
    ncatbot_core.registrar = types.SimpleNamespace(
        qq=types.SimpleNamespace(
            on_group_message=lambda: lambda fn: fn,
            on_private_message=lambda: lambda fn: fn,
        )
    )
    sys.modules["ncatbot.core"] = ncatbot_core

    ncatbot_event_qq = types.ModuleType("ncatbot.event.qq")
    ncatbot_event_qq.GroupMessageEvent = object
    ncatbot_event_qq.PrivateMessageEvent = object
    sys.modules["ncatbot.event.qq"] = ncatbot_event_qq

    ncatbot_plugin = types.ModuleType("ncatbot.plugin")
    ncatbot_plugin.NcatBotPlugin = object
    sys.modules["ncatbot.plugin"] = ncatbot_plugin

    spec = importlib.util.spec_from_file_location(
        "drive_bot_plugin", ROOT / "plugins" / "drive_bot" / "plugin.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_core_plugin_module():
    load_plugin_module()
    from ncatbot_assistant.drive_bot import ncatbot_plugin

    return ncatbot_plugin


class FakeLogger:
    def info(self, *args, **kwargs):
        pass

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
        self._user_memory_config = module.UserMemoryConfig()
        self._user_memory_store = module.UserMemoryStore(":memory:")
        self._user_memory_store.initialize()
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


class FakeReplyEvent:
    def __init__(self):
        self.replies = []

    async def reply(self, **kwargs):
        self.replies.append(kwargs)


class DriveBotConfigTest(TestCase):
    def test_llm_config_prefers_top_level_config_yaml_values(self):
        module = load_core_plugin_module()
        config = {
            "llm": {
                "base_url": "https://llm.example.com",
                "api_key": "real-key",
                "model": "deepseek-chat",
                "temperature": 0.2,
                "max_tokens": 256,
            }
        }
        defaults = {
            "ai_base_url": "https://default.example.com",
            "ai_api_key": "fake-api-key",
            "ai_model": "default-model",
            "ai_temperature": 0.7,
            "ai_max_tokens": 800,
        }

        merged = module._merge_llm_config(config, defaults)

        self.assertEqual(
            merged,
            {
                "base_url": "https://llm.example.com",
                "api_key": "real-key",
                "model": "deepseek-chat",
                "temperature": 0.2,
                "max_tokens": 256,
            },
        )

    def test_llm_config_accepts_legacy_ai_key_names(self):
        module = load_core_plugin_module()
        config = {
            "llm": {
                "ai_base_url": "https://legacy.example.com",
                "ai_api_key": "legacy-key",
                "ai_model": "legacy-model",
                "ai_temperature": 0.4,
                "ai_max_tokens": 512,
            }
        }
        defaults = {}

        merged = module._merge_llm_config(config, defaults)

        self.assertEqual(merged["base_url"], "https://legacy.example.com")
        self.assertEqual(merged["api_key"], "legacy-key")
        self.assertEqual(merged["model"], "legacy-model")
        self.assertEqual(merged["temperature"], 0.4)
        self.assertEqual(merged["max_tokens"], 512)

    def test_plugin_entrypoint_exports_drive_bot_plugin(self):
        module = load_plugin_module()

        self.assertTrue(hasattr(module, "DriveBotPlugin"))

    def test_config_example_documents_llm_context_defaults(self):
        config_text = (ROOT / "config.example.yaml").read_text(encoding="utf-8")

        self.assertIn("  context:\n    enabled: true\n    max_turns: 6", config_text)

    def test_config_example_documents_currents_daily_news(self):
        config_text = (ROOT / "config.example.yaml").read_text(encoding="utf-8")

        self.assertIn(
            '  daily_news:\n    api_key: "your-currents-api-key"',
            config_text,
        )
        self.assertIn('    language: "en"', config_text)
        self.assertIn("    max_items: 10", config_text)

    def test_ai_system_prompt_includes_single_neko_prompt_file(self):
        module = load_core_plugin_module()
        module._load_neko_prompt.cache_clear()

        prompt = module._build_ai_system_prompt()
        prompt_file_text = module.NEKO_PROMPT_PATH.read_text(encoding="utf-8").strip()
        first_prompt_line = next(
            line.strip() for line in prompt_file_text.splitlines() if line.strip()
        )

        self.assertIn(module.AI_SYSTEM_PROMPT, prompt)
        self.assertIn(first_prompt_line, prompt)

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
        self.assertEqual(
            messages[1:],
            [
                {"role": "user", "content": "我在学 asyncio"},
                {"role": "assistant", "content": "可以从事件循环理解"},
                {"role": "user", "content": "继续刚才那个"},
            ],
        )

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
        self.assertEqual(
            plugin._conversation_memory.recent_messages(key),
            [
                {"role": "user", "content": "你好"},
                {"role": "assistant", "content": "你好呀"},
            ],
        )

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
        self.assertEqual(
            plugin._conversation_memory.recent_messages(key),
            [
                {"role": "user", "content": "你好"},
            ],
        )

    def test_group_ask_ai_injects_user_memory_before_short_term_history(self):
        module = load_core_plugin_module()
        ai_api = FakeAiApi(response="短一点解释")
        plugin = FakePlugin(module, ai_api)
        plugin._user_memory_store.update_profile_prompt("u1", "用户偏好简短回答。", 0)
        key = module.ConversationKey.group("g1", "u1")
        plugin._conversation_memory.append_user_message(key, "我在学 asyncio")

        asyncio.run(
            module.DriveBotPlugin._ask_ai(
                plugin,
                "继续",
                scope_type=module.ScopeType.GROUP,
                user_id="u1",
                group_id="g1",
            )
        )

        messages = ai_api.calls[0][0]
        self.assertIn("用户偏好简短回答", messages[1]["content"])
        self.assertEqual(messages[2], {"role": "user", "content": "我在学 asyncio"})
        self.assertEqual(messages[-1], {"role": "user", "content": "继续"})

    def test_handle_group_message_records_user_memory_after_routing(self):
        module = load_core_plugin_module()
        plugin = FakePlugin(module, FakeAiApi(response="ok"))
        event = FakeReplyEvent()

        asyncio.run(
            module.DriveBotPlugin._handle_message(
                plugin,
                event=event,
                text="帮助",
                scope_type=module.ScopeType.GROUP,
                user_id="u1",
                group_id="g1",
            )
        )

        messages = plugin._user_memory_store.unsummarized_messages("u1", limit=10)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].message_text, "帮助")
        self.assertEqual(messages[0].intent_type, "immediate")

    def test_handle_private_message_does_not_record_user_memory(self):
        module = load_core_plugin_module()
        plugin = FakePlugin(module, FakeAiApi(response="ok"))
        event = FakeReplyEvent()

        asyncio.run(
            module.DriveBotPlugin._handle_message(
                plugin,
                event=event,
                text="帮助",
                scope_type=module.ScopeType.PRIVATE,
                user_id="u1",
                group_id=None,
            )
        )

        self.assertEqual(plugin._user_memory_store.unsummarized_messages("u1", limit=10), [])

    def test_show_user_profile_replies_with_current_user_prompt_without_recording_memory(self):
        module = load_core_plugin_module()
        plugin = FakePlugin(module, FakeAiApi(response="should not call ai"))
        plugin._user_memory_store.update_profile_prompt("u1", "用户偏好简短回答。", 0)
        event = FakeReplyEvent()

        asyncio.run(
            module.DriveBotPlugin._handle_message(
                plugin,
                event=event,
                text="/showUserProfile",
                scope_type=module.ScopeType.GROUP,
                user_id="u1",
                group_id="g1",
            )
        )

        self.assertEqual(event.replies, [{"text": "当前用户画像 prompt：\n用户偏好简短回答。"}])
        self.assertEqual(plugin._user_memory_store.unsummarized_messages("u1", limit=10), [])


if __name__ == "__main__":
    main()
