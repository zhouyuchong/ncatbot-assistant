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


if __name__ == "__main__":
    main()
