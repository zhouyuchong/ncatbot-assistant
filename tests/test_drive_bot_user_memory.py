import tempfile
from pathlib import Path
from unittest import IsolatedAsyncioTestCase, TestCase, main

import tests.bootstrap  # noqa: F401

from ncatbot_assistant.drive_bot.intents import ScopeType
from ncatbot_assistant.drive_bot.user_memory import (
    UserMemoryConfig,
    UserMemorySummarizer,
    UserMemoryStore,
    build_user_memory_summary_messages,
    get_user_memory_config,
    seconds_until_next_run,
)


class UserMemoryConfigTest(TestCase):
    def test_memory_config_uses_safe_defaults(self):
        self.assertEqual(get_user_memory_config({}), UserMemoryConfig())

    def test_memory_config_parses_values_and_clamps_limits(self):
        config = get_user_memory_config(
            {
                "llm": {
                    "memory": {
                        "enabled": "false",
                        "group_enabled": "yes",
                        "private_enabled": "true",
                        "summarize_hour": "30",
                        "timezone": "",
                        "max_daily_messages": "-1",
                        "prompt_max_chars": "0",
                        "include_commands": "1",
                    }
                }
            }
        )

        self.assertEqual(
            config,
            UserMemoryConfig(
                enabled=False,
                group_enabled=True,
                private_enabled=True,
                summarize_hour=23,
                timezone="Asia/Shanghai",
                max_daily_messages=1,
                prompt_max_chars=1,
                include_commands=True,
            ),
        )


class UserMemoryStoreTest(TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "memory.sqlite3"
        self.store = UserMemoryStore(self.db_path)
        self.store.initialize()

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_record_group_message_creates_profile_and_returns_message_id(self):
        message_id = self.store.record_message(
            scope_type=ScopeType.GROUP,
            group_id="g1",
            user_id="u1",
            message_text="@bot 你好",
            intent_type="llm_fallback",
        )

        profile = self.store.get_or_create_profile("u1")

        self.assertEqual(message_id, 1)
        self.assertEqual(profile.user_id, "u1")
        self.assertEqual(profile.user_prompt, "")
        self.assertEqual(profile.last_summarized_message_id, 0)
        self.assertTrue(profile.enabled)

    def test_unsummarized_messages_are_incremental_and_ordered(self):
        first = self.store.record_message(
            ScopeType.GROUP,
            "g1",
            "u1",
            "第一条",
            "llm_fallback",
        )
        second = self.store.record_message(
            ScopeType.GROUP,
            "g2",
            "u1",
            "第二条",
            "queued_task",
        )
        self.store.record_message(
            ScopeType.GROUP,
            "g1",
            "u2",
            "别人的消息",
            "llm_fallback",
        )
        self.store.update_profile_prompt("u1", "旧画像", first)

        messages = self.store.unsummarized_messages("u1", limit=10)

        self.assertEqual([message.id for message in messages], [second])
        self.assertEqual(messages[0].message_text, "第二条")
        self.assertEqual(messages[0].group_id, "g2")
        self.assertEqual(messages[0].intent_type, "queued_task")

    def test_due_users_only_includes_enabled_profiles_with_new_messages(self):
        message_id = self.store.record_message(
            ScopeType.GROUP,
            "g1",
            "u1",
            "新消息",
            "llm_fallback",
        )
        self.store.record_message(
            ScopeType.GROUP,
            "g1",
            "u2",
            "已总结消息",
            "llm_fallback",
        )
        self.store.update_profile_prompt("u2", "画像", message_id + 1)
        self.store.set_profile_enabled("u3", False)
        self.store.record_message(
            ScopeType.GROUP,
            "g1",
            "u3",
            "禁用用户",
            "llm_fallback",
        )

        self.assertEqual(self.store.due_user_ids(), ["u1"])


class UserMemorySummaryPromptTest(TestCase):
    def test_summary_messages_filter_commands_when_disabled(self):
        store = UserMemoryStore(":memory:")
        store.initialize()
        store.record_message(ScopeType.GROUP, "g1", "u1", "请用短句回答我", "llm_fallback")
        store.record_message(ScopeType.GROUP, "g1", "u1", "/setu 猫耳", "queued_task")
        messages = store.unsummarized_messages("u1", limit=10)

        prompt_messages = build_user_memory_summary_messages(
            previous_prompt="旧画像",
            messages=messages,
            include_commands=False,
            prompt_max_chars=500,
        )

        prompt_text = prompt_messages[-1]["content"]
        self.assertIn("旧画像", prompt_text)
        self.assertIn("请用短句回答我", prompt_text)
        self.assertNotIn("/setu 猫耳", prompt_text)


class UserMemorySummarizerTest(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.store = UserMemoryStore(Path(self.tmpdir.name) / "memory.sqlite3")
        self.store.initialize()

    async def asyncTearDown(self):
        self.tmpdir.cleanup()

    async def test_summarizer_updates_prompt_and_advances_cursor(self):
        first = self.store.record_message(
            ScopeType.GROUP,
            "g1",
            "u1",
            "我喜欢回答短一点",
            "llm_fallback",
        )
        self.store.record_message(ScopeType.GROUP, "g1", "u1", "/setu 猫耳", "queued_task")
        calls = []

        async def fake_chat(messages):
            calls.append(messages)
            return "用户偏好简短回答。"

        summarizer = UserMemorySummarizer(
            self.store,
            UserMemoryConfig(max_daily_messages=10, include_commands=False),
            fake_chat,
        )

        summarized = await summarizer.summarize_due_users()
        profile = self.store.get_or_create_profile("u1")

        self.assertEqual(summarized, 1)
        self.assertEqual(profile.user_prompt, "用户偏好简短回答。")
        self.assertEqual(profile.last_summarized_message_id, first + 1)
        self.assertIsNone(profile.summary_error)
        self.assertNotIn("/setu 猫耳", calls[0][-1]["content"])

    async def test_summarizer_keeps_old_prompt_on_failure(self):
        message_id = self.store.record_message(
            ScopeType.GROUP,
            "g1",
            "u1",
            "新偏好",
            "llm_fallback",
        )
        self.store.update_profile_prompt("u1", "旧画像", message_id - 1)

        async def broken_chat(_messages):
            raise RuntimeError("llm down")

        summarizer = UserMemorySummarizer(self.store, UserMemoryConfig(), broken_chat)

        summarized = await summarizer.summarize_due_users()
        profile = self.store.get_or_create_profile("u1")

        self.assertEqual(summarized, 0)
        self.assertEqual(profile.user_prompt, "旧画像")
        self.assertEqual(profile.last_summarized_message_id, message_id - 1)
        self.assertEqual(profile.summary_error, "llm down")


class UserMemorySchedulerTest(TestCase):
    def test_seconds_until_next_run_uses_next_day_after_target_hour(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        now = datetime(2026, 6, 24, 1, 30, tzinfo=ZoneInfo("Asia/Shanghai"))

        self.assertEqual(seconds_until_next_run(0, "Asia/Shanghai", now), 81000.0)


if __name__ == "__main__":
    main()
