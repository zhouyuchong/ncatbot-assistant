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


if __name__ == "__main__":
    main()
