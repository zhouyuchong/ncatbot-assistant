# Drive Bot User Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build persistent group-only user memory with daily incremental summarization and group LLM prompt injection.

**Architecture:** Add a focused memory module for config, SQLite persistence, prompt formatting, and async scheduling. Wire it into `DriveBotPlugin` after routing for group capture and before short-term history for group LLM fallback injection.

**Tech Stack:** Python 3.12, sqlite3, unittest, asyncio, existing ncatbot plugin and LLM adapter APIs.

---

## File Structure

- Create `src/ncatbot_assistant/drive_bot/user_memory.py` for config parsing, storage, summary prompt construction, summarization service, and daily scheduler.
- Modify `src/ncatbot_assistant/drive_bot/ncatbot_plugin.py` to initialize memory, capture group messages, inject prompts, and stop the scheduler.
- Modify `config.example.yaml` to document `llm.memory`.
- Add `tests/test_drive_bot_user_memory.py` for storage/config/summarization unit tests.
- Extend `tests/test_drive_bot_llm_context.py` or add plugin-focused tests for message construction with memory injection.

## Task 1: Memory Config And Store

- [ ] Write failing tests in `tests/test_drive_bot_user_memory.py` for `get_user_memory_config`, table initialization, `record_message`, `get_or_create_profile`, and `unsummarized_messages`.
- [ ] Run `uv run python -m unittest tests.test_drive_bot_user_memory -v` and verify the tests fail because `user_memory` does not exist.
- [ ] Create `src/ncatbot_assistant/drive_bot/user_memory.py` with `UserMemoryConfig`, `UserMemoryProfile`, `UserMemoryMessage`, `get_user_memory_config`, and `UserMemoryStore`.
- [ ] Run `uv run python -m unittest tests.test_drive_bot_user_memory -v` and verify the new tests pass.

## Task 2: Summary Prompt And Incremental Update

- [ ] Add failing tests for `build_user_memory_summary_messages` filtering command-like intent rows when `include_commands` is false.
- [ ] Add failing tests for `UserMemorySummarizer.summarize_due_users` updating `user_prompt`, advancing `last_summarized_message_id`, and preserving old prompt on LLM failure.
- [ ] Run the focused user-memory tests and verify the new tests fail for missing summary behavior.
- [ ] Implement summary message construction and `UserMemorySummarizer`.
- [ ] Run the focused user-memory tests and verify they pass.

## Task 3: Plugin Capture And Prompt Injection

- [ ] Add failing tests using a lightweight `DriveBotPlugin` instance for group LLM fallback message construction with an enabled profile prompt.
- [ ] Add failing tests proving private LLM fallback does not inject or capture long-term memory.
- [ ] Run the focused plugin/context tests and verify failure.
- [ ] Modify `DriveBotPlugin` to initialize `UserMemoryStore`, capture group at-bot messages after routing, inject user profile prompts for group LLM fallback, and skip private memory behavior.
- [ ] Run the focused plugin/context tests and verify they pass.

## Task 4: Daily Scheduler And Config Example

- [ ] Add failing scheduler tests with an immediate interval or fake clock if practical; otherwise test `seconds_until_next_run` deterministically.
- [ ] Implement `DailyUserMemoryScheduler` with `start()` and async `stop()`.
- [ ] Wire scheduler startup in `on_load` and shutdown in `on_close`.
- [ ] Update `config.example.yaml` with the `llm.memory` section from the spec.
- [ ] Run scheduler and user-memory tests.

## Task 5: Full Verification

- [ ] Run `uv run python -m unittest -v`.
- [ ] Inspect `git diff --check`.
- [ ] Review the diff for accidental unrelated changes.
