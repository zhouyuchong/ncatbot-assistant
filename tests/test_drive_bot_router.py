from unittest import TestCase, main

import tests.bootstrap  # noqa: F401
from ncatbot_assistant.drive_bot.intents import (
    LlmFallbackIntent,
    QueuedTaskIntent,
    ScopeType,
    TaskType,
)
from ncatbot_assistant.drive_bot.router import route_message


class DriveBotRouterTest(TestCase):
    def test_jm_numeric_message_becomes_queued_task(self):
        intent = route_message(
            "/jm 123456",
            scope_type=ScopeType.GROUP,
            user_id="10001",
            group_id="20002",
        )

        self.assertIsInstance(intent, QueuedTaskIntent)
        self.assertEqual(intent.task_type, TaskType.JM_DOWNLOAD)
        self.assertEqual(intent.payload, {"album_id": 123456})

    def test_setu_message_becomes_queued_task_with_tags(self):
        intent = route_message(
            "/setu 原神 猫耳",
            scope_type=ScopeType.PRIVATE,
            user_id="10001",
        )

        self.assertIsInstance(intent, QueuedTaskIntent)
        self.assertEqual(intent.task_type, TaskType.SETU)
        self.assertEqual(intent.payload, {"tags": ["原神", "猫耳"]})

    def test_setu_rejects_more_than_three_tags(self):
        intent = route_message(
            "/setu a b c d",
            scope_type=ScopeType.PRIVATE,
            user_id="10001",
        )

        self.assertEqual(intent.text, "最多支持3个标签")

    def test_daily_message_becomes_queued_task(self):
        intent = route_message("每日新闻", scope_type=ScopeType.GROUP, user_id="u", group_id="g")

        self.assertIsInstance(intent, QueuedTaskIntent)
        self.assertEqual(intent.task_type, TaskType.DAILY)
        self.assertEqual(intent.payload, {})

    def test_jm_search_remains_immediate(self):
        intent = route_message(
            "/jm 原神",
            scope_type=ScopeType.GROUP,
            user_id="10001",
            group_id="20002",
            jm_search_func=lambda tags: "search:" + ",".join(tags),
        )

        self.assertEqual(intent.text, "search:原神")

    def test_usage_remains_immediate(self):
        intent = route_message("帮助", scope_type=ScopeType.PRIVATE, user_id="10001")

        self.assertIn("Drive Bot 使用方法", intent.text)

    def test_unknown_message_becomes_llm_fallback(self):
        intent = route_message("你是谁", scope_type=ScopeType.PRIVATE, user_id="10001")

        self.assertIsInstance(intent, LlmFallbackIntent)
        self.assertEqual(intent.prompt, "你是谁")


if __name__ == "__main__":
    main()
