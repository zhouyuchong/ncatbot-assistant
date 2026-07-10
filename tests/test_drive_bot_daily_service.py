from unittest import IsolatedAsyncioTestCase, TestCase, main
from unittest.mock import Mock, patch

import tests.bootstrap  # noqa: F401
from ncatbot_assistant.drive_bot.constants import CURRENTS_LATEST_NEWS_URL
from ncatbot_assistant.drive_bot.services.daily import (
    fetch_latest_news_sync,
    generate_daily_news,
)


def news_item(index: int = 1) -> dict:
    return {
        "id": f"news-{index}",
        "title": f"Headline {index}",
        "description": f"Description {index}",
        "url": f"https://example.com/news/{index}",
        "author": "Reporter",
        "category": ["general"],
        "published": "2026-07-10 01:18:18 +0000",
    }


class DailyNewsServiceTest(IsolatedAsyncioTestCase):
    async def test_generates_digest_from_cleaned_news(self):
        payload = {
            "status": "ok",
            "news": [news_item(), {"title": "Missing URL"}],
        }
        chat_calls = []
        fetch_calls = []

        async def chat(messages):
            chat_calls.append(messages)
            return "今日要闻综述\n1. 示例新闻：https://example.com/news/1"

        def fetch(**kwargs):
            fetch_calls.append(kwargs)
            return payload

        result = await generate_daily_news(
            {
                "tasks": {
                    "daily_news": {
                        "api_key": "secret-key",
                        "language": "en",
                    }
                }
            },
            chat,
            fetch_func=fetch,
        )

        self.assertIn("今日要闻综述", result)
        self.assertEqual(fetch_calls, [{"api_key": "secret-key", "language": "en"}])
        prompt = chat_calls[0][0]["content"]
        self.assertIn("Headline 1", prompt)
        self.assertIn("https://example.com/news/1", prompt)
        self.assertNotIn("Missing URL", prompt)
        self.assertNotIn("secret-key", prompt)
        self.assertIn("简体中文", prompt)
        self.assertIn("综合摘要", prompt)

    async def test_caps_max_items_at_ten(self):
        payload = {"status": "ok", "news": [news_item(i) for i in range(1, 13)]}
        prompts = []

        async def chat(messages):
            prompts.append(messages[0]["content"])
            return "摘要"

        await generate_daily_news(
            {"tasks": {"daily_news": {"api_key": "secret", "max_items": 99}}},
            chat,
            fetch_func=lambda **_kwargs: payload,
        )

        self.assertIn("Headline 10", prompts[0])
        self.assertNotIn("Headline 11", prompts[0])

    async def test_missing_api_key_raises_clear_error(self):
        async def chat(_messages):
            return "unused"

        with self.assertRaisesRegex(ValueError, "tasks.daily_news.api_key"):
            await generate_daily_news({}, chat, fetch_func=lambda **_kwargs: {})

    async def test_rejects_non_ok_status(self):
        async def chat(_messages):
            return "unused"

        with self.assertRaisesRegex(RuntimeError, "Currents"):
            await generate_daily_news(
                {"tasks": {"daily_news": {"api_key": "secret"}}},
                chat,
                fetch_func=lambda **_kwargs: {"status": "error", "news": []},
            )

    async def test_rejects_empty_normalized_news(self):
        async def chat(_messages):
            return "unused"

        with self.assertRaisesRegex(RuntimeError, "有效新闻"):
            await generate_daily_news(
                {"tasks": {"daily_news": {"api_key": "secret"}}},
                chat,
                fetch_func=lambda **_kwargs: {
                    "status": "ok",
                    "news": [{"title": "No URL"}],
                },
            )

    async def test_llm_failure_returns_deterministic_fallback(self):
        async def failing_chat(_messages):
            raise RuntimeError("LLM secret failure")

        result = await generate_daily_news(
            {"tasks": {"daily_news": {"api_key": "secret"}}},
            failing_chat,
            fetch_func=lambda **_kwargs: {"status": "ok", "news": [news_item()]},
        )

        self.assertIn("AI 摘要暂不可用", result)
        self.assertIn("Headline 1", result)
        self.assertIn("Description 1", result)
        self.assertIn("https://example.com/news/1", result)
        self.assertNotIn("LLM secret failure", result)


class DailyNewsHttpTest(TestCase):
    @patch("requests.get")
    def test_fetch_latest_news_uses_currents_query_params(self, get: Mock):
        response = Mock()
        response.json.return_value = {"status": "ok", "news": [news_item()]}
        get.return_value = response

        result = fetch_latest_news_sync("secret", "en")

        self.assertEqual(result["status"], "ok")
        get.assert_called_once_with(
            CURRENTS_LATEST_NEWS_URL,
            params={"language": "en", "apiKey": "secret"},
            timeout=10,
        )
        response.raise_for_status.assert_called_once_with()

    @patch("requests.get")
    def test_fetch_latest_news_sanitizes_request_errors(self, get: Mock):
        get.side_effect = RuntimeError("https://example.test?apiKey=secret")

        with self.assertRaisesRegex(RuntimeError, "Currents 新闻接口请求失败") as error:
            fetch_latest_news_sync("secret", "en")

        self.assertNotIn("secret", str(error.exception))


if __name__ == "__main__":
    main()
