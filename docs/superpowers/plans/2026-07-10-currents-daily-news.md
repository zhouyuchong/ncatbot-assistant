# Currents Daily News Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the expired daily-news image API with Currents JSON news fetching and a Chinese LLM-generated text digest with a deterministic fallback.

**Architecture:** `services/daily.py` owns Currents configuration, HTTP fetching, response normalization, prompt construction, LLM invocation, and fallback formatting. `DriveBotPlugin` injects project configuration and its existing long-form LLM callable, while `TaskHandlers` sends the returned digest as plain text.

**Tech Stack:** Python 3.12, asyncio, requests, PyYAML, unittest/pytest-compatible tests, existing NcatBot reply and LLM adapters.

## Global Constraints

- Currents endpoint is exactly `https://api.currentsapi.services/v1/latest-news`.
- API key is read from `tasks.daily_news.api_key` and must never appear in logs or raised error messages.
- Language defaults to `en`; maximum input items defaults to and is capped at `10`.
- Successful output is Chinese plain text containing an overview and 5–10 highlighted items with original links.
- LLM failure returns a deterministic digest; Currents/configuration/response failures fail the task clearly.
- Existing “每日新闻” routing, task type, and estimate remain unchanged.

---

### Task 1: Currents news service

**Files:**
- Create: `tests/test_drive_bot_daily_service.py`
- Modify: `src/ncatbot_assistant/drive_bot/services/daily.py`
- Modify: `src/ncatbot_assistant/drive_bot/constants.py`

**Interfaces:**
- Consumes: project configuration mapping and `chat_text_func(messages: list[dict[str, str]]) -> Awaitable[str]`.
- Produces: `generate_daily_news(project_config, chat_text_func, logger=None) -> Awaitable[str]`.
- Produces: `fetch_latest_news_sync(api_key: str, language: str, timeout: int = 10) -> dict[str, Any]`.

- [ ] **Step 1: Write failing service tests**

Create tests with a representative Currents payload and injected fetcher/LLM behavior:

```python
class DailyNewsServiceTest(IsolatedAsyncioTestCase):
    async def test_generates_chinese_digest_from_cleaned_news(self):
        payload = {
            "status": "ok",
            "news": [
                {
                    "title": "Example headline",
                    "description": "Example description",
                    "url": "https://example.com/news",
                    "author": "Reporter",
                    "category": ["general"],
                    "published": "2026-07-10 01:18:18 +0000",
                }
            ],
        }
        calls = []

        async def chat(messages):
            calls.append(messages)
            return "今日要闻综述\n1. 示例新闻：https://example.com/news"

        result = await generate_daily_news(
            {"tasks": {"daily_news": {"api_key": "secret"}}},
            chat,
            fetch_func=lambda **kwargs: payload,
        )

        self.assertIn("今日要闻综述", result)
        self.assertIn("Example headline", calls[0][0]["content"])
        self.assertIn("https://example.com/news", calls[0][0]["content"])
        self.assertNotIn("secret", calls[0][0]["content"])
```

Add focused tests proving: `language` and the secret are passed only to the fetcher; `max_items` caps at 10; records without title or URL are removed; missing key raises `ValueError`; non-`ok` status and empty normalized news raise `RuntimeError`; an LLM exception returns text containing `AI 摘要暂不可用`, the title, description, and URL. Patch `requests.get` in a synchronous test and assert endpoint, `params={"language": "en", "apiKey": "secret"}`, and `timeout=10`.

- [ ] **Step 2: Run service tests and verify RED**

Run: `PYTHONPATH=src uv run pytest tests/test_drive_bot_daily_service.py -q`

Expected: FAIL because `generate_daily_news` and the Currents constant do not exist.

- [ ] **Step 3: Implement minimal service**

Replace image handling with focused helpers and dependency injection:

```python
async def generate_daily_news(
    project_config: dict[str, Any],
    chat_text_func: Callable[[list[dict[str, str]]], Awaitable[str]],
    logger=None,
    fetch_func: Callable[..., dict[str, Any]] | None = None,
) -> str:
    config = _daily_news_config(project_config)
    api_key = str(config.get("api_key") or "").strip()
    if not api_key:
        raise ValueError("配置文件中未配置 tasks.daily_news.api_key")
    language = str(config.get("language") or "en").strip() or "en"
    max_items = max(1, min(_parse_int(config.get("max_items"), 10), 10))
    fetch = fetch_func or fetch_latest_news
    payload = await _maybe_await(fetch(api_key=api_key, language=language))
    news = _normalize_news_payload(payload)[:max_items]
    messages = [{"role": "user", "content": _build_summary_prompt(news)}]
    try:
        return await chat_text_func(messages)
    except Exception as exc:
        if logger:
            logger.warning("每日新闻 LLM 摘要失败: %s", exc)
        return _build_fallback_digest(news)
```

Use `asyncio.to_thread(fetch_latest_news_sync, ...)` for the default async fetcher. `fetch_latest_news_sync` calls `requests.get(CURRENTS_LATEST_NEWS_URL, params=..., timeout=10)`, raises a sanitized `RuntimeError("Currents 新闻接口请求失败")` on request/JSON errors, and never embeds the URL query or secret. Normalize only dictionaries with non-empty string `title` and `url`; coerce optional fields safely. Build a Chinese prompt requiring overview, 5–10 diverse items, no invented facts, preserved URLs, and no Markdown table. Build a numbered fallback digest with descriptions truncated to 240 characters.

- [ ] **Step 4: Run service tests and verify GREEN**

Run: `PYTHONPATH=src uv run pytest tests/test_drive_bot_daily_service.py -q`

Expected: all service tests PASS.

- [ ] **Step 5: Commit service**

```bash
git add tests/test_drive_bot_daily_service.py src/ncatbot_assistant/drive_bot/services/daily.py src/ncatbot_assistant/drive_bot/constants.py
git commit -m "feat: fetch and summarize Currents daily news"
```

### Task 2: Text task handling and plugin wiring

**Files:**
- Modify: `tests/test_drive_bot_handlers.py`
- Modify: `tests/test_drive_bot_config.py`
- Modify: `src/ncatbot_assistant/drive_bot/jobs/handlers.py`
- Modify: `src/ncatbot_assistant/drive_bot/ncatbot_plugin.py`

**Interfaces:**
- Consumes: `generate_daily_news(project_config, chat_text_func, logger)` from Task 1.
- Produces: daily handler result `{"sent_text": 1, "text": digest}` and plugin-injected `daily_function`.

- [ ] **Step 1: Change handler test to require text output**

Replace the image assertion with:

```python
async def test_daily_handler_replies_with_direct_text(self):
    event = FakeEvent()
    reply = ReplyAdapter(file_api=FakeFileApi(), event_lookup=lambda _task: event)

    async def daily():
        return "今日新闻摘要"

    handlers = TaskHandlers(reply=reply, daily_function=daily)
    result = await handlers.handle(daily_task)

    self.assertEqual(result, {"sent_text": 1, "text": "今日新闻摘要"})
    self.assertEqual(event.replies[0], {"text": "今日新闻摘要", "image": None})
```

Add an isolated plugin-load test that patches the imported `generate_daily_news`, invokes the captured daily callable from `TaskHandlers`, and asserts the patched function receives the loaded `project_config`, the bound `_ask_memory_summary` callable, and the plugin logger. Assert the `TaskHandlers` constructor receives that callable as `daily_function`.

- [ ] **Step 2: Run integration tests and verify RED**

Run: `PYTHONPATH=src uv run pytest tests/test_drive_bot_handlers.py tests/test_drive_bot_config.py -q`

Expected: handler test FAIL because the current implementation sends an image; plugin wiring assertion FAIL because daily news is not injected.

- [ ] **Step 3: Implement text handling and wiring**

In `TaskHandlers`, type the daily callable as returning text and implement:

```python
async def _handle_daily(self, task: TaskRecord) -> dict:
    text = await _maybe_await(self.daily_function())
    if not text:
        raise RuntimeError("获取每日新闻失败，接口暂时不可用，请稍后再试。")
    await self.reply.reply_direct_text(task, text)
    return {"sent_text": 1, "text": text}
```

Import `generate_daily_news` in `ncatbot_plugin.py`, create a `daily_func` closure next to `daily_ai_func`, and construct handlers with both `daily_function=daily_func` and `daily_ai_function=daily_ai_func`.

- [ ] **Step 4: Run integration tests and verify GREEN**

Run: `PYTHONPATH=src uv run pytest tests/test_drive_bot_handlers.py tests/test_drive_bot_config.py -q`

Expected: all selected tests PASS.

- [ ] **Step 5: Commit integration**

```bash
git add tests/test_drive_bot_handlers.py tests/test_drive_bot_config.py src/ncatbot_assistant/drive_bot/jobs/handlers.py src/ncatbot_assistant/drive_bot/ncatbot_plugin.py
git commit -m "feat: send daily news as summarized text"
```

### Task 3: Configuration and user documentation

**Files:**
- Modify: `tests/test_drive_bot_config.py`
- Modify: `config.example.yaml`
- Modify: `readme.md`
- Modify: `plugins/drive_bot/README.md`

**Interfaces:**
- Consumes: `tasks.daily_news` contract from Task 1.
- Produces: copyable configuration and accurate command documentation.

- [ ] **Step 1: Add failing configuration documentation test**

```python
def test_config_example_documents_currents_daily_news(self):
    config_text = (ROOT / "config.example.yaml").read_text(encoding="utf-8")
    self.assertIn('  daily_news:\n    api_key: "your-currents-api-key"', config_text)
    self.assertIn('    language: "en"', config_text)
    self.assertIn("    max_items: 10", config_text)
```

- [ ] **Step 2: Run the test and verify RED**

Run: `PYTHONPATH=src uv run pytest tests/test_drive_bot_config.py::DriveBotConfigTest::test_config_example_documents_currents_daily_news -q`

Expected: FAIL because the example has no `daily_news` block.

- [ ] **Step 3: Update configuration and READMEs**

Add this sibling of `daily_ai`:

```yaml
  daily_news:
    api_key: "your-currents-api-key"
    language: "en"
    max_items: 10
```

Change root and plugin README descriptions from fetching/sending a 摸鱼新闻图片 to fetching Currents news and sending a Chinese digest. Add a configuration note that `tasks.daily_news.api_key` is required and link users to the Currents API key source without embedding a key.

- [ ] **Step 4: Run config test and documentation checks**

Run: `PYTHONPATH=src uv run pytest tests/test_drive_bot_config.py -q`

Expected: all config tests PASS.

Run: `rg -n "摸鱼新闻图片|每日新闻图片|今日摸鱼图" readme.md plugins/drive_bot/README.md src tests config.example.yaml`

Expected: no stale daily-news image descriptions.

- [ ] **Step 5: Commit documentation**

```bash
git add tests/test_drive_bot_config.py config.example.yaml readme.md plugins/drive_bot/README.md
git commit -m "docs: configure Currents daily news"
```

### Task 4: Regression verification

**Files:**
- Modify only if a regression is found: files already listed above.

**Interfaces:**
- Consumes: completed Tasks 1–3.
- Produces: verified repository state.

- [ ] **Step 1: Run focused daily-news tests**

Run: `PYTHONPATH=src uv run pytest tests/test_drive_bot_daily_service.py tests/test_drive_bot_handlers.py tests/test_drive_bot_config.py tests/test_drive_bot_router.py -q`

Expected: all selected tests PASS without warnings caused by this feature.

- [ ] **Step 2: Run the full test suite**

Run: `PYTHONPATH=src uv run pytest -q`

Expected: all repository tests PASS.

- [ ] **Step 3: Check formatting and diff integrity**

Run: `git diff --check HEAD~4..HEAD`

Expected: no whitespace errors.

Run: `git status --short`

Expected: clean working tree.
