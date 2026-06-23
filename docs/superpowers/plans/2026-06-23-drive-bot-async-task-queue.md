# Drive Bot Async Task Queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a SQLite-backed single-worker task queue so costly Drive Bot actions run in the background while chat handling remains responsive.

**Architecture:** Introduce a `src/ncatbot_assistant/drive_bot` package with focused modules for intents, routing, estimates, storage, task execution, services, and replies. Keep `plugins/drive_bot/plugin.py` as a thin NcatBot discovery shim and preserve the current LLM fallback behavior outside the queue.

**Tech Stack:** Python 3.9+, `asyncio`, standard-library `sqlite3`, standard-library `unittest`, existing NcatBot plugin API.

---

## File Structure

- Create `src/ncatbot_assistant/drive_bot/intents.py`: dataclasses and constants for chat contexts, intents, task statuses, task records, and task results.
- Create `src/ncatbot_assistant/drive_bot/router.py`: parse raw message text into immediate responses, queued tasks, or LLM fallback.
- Create `src/ncatbot_assistant/drive_bot/estimator.py`: static task estimates and wait-time formatting.
- Create `src/ncatbot_assistant/drive_bot/storage.py`: SQLite schema and task CRUD.
- Create `src/ncatbot_assistant/drive_bot/services/jm.py`: JM search/download implementation and async download wrapper.
- Create `src/ncatbot_assistant/drive_bot/services/setu.py`: setu API, download, and image obfuscation implementation.
- Create `src/ncatbot_assistant/drive_bot/services/daily.py`: daily news image fetch implementation.
- Create `src/ncatbot_assistant/drive_bot/reply.py`: upload/delete helpers and event reply adapter.
- Create `src/ncatbot_assistant/drive_bot/jobs/handlers.py`: execute queued task types.
- Create `src/ncatbot_assistant/drive_bot/jobs/queue.py`: background worker lifecycle.
- Create `src/ncatbot_assistant/drive_bot/ncatbot_plugin.py`: NcatBot adapter implementation.
- Modify `plugins/drive_bot/plugin.py`: thin shim that imports and re-exports `DriveBotPlugin`.
- Modify `config.example.yaml`: add `storage.sqlite_path` and `tasks` estimate config.
- Modify `plugins/drive_bot/README.md`: document queue behavior.
- Add tests under `tests/`.

## Task 1: Intent Models And Router

**Files:**
- Create: `src/ncatbot_assistant/drive_bot/intents.py`
- Create: `src/ncatbot_assistant/drive_bot/router.py`
- Test: `tests/test_drive_bot_router.py`

- [ ] **Step 1: Write failing router tests**

Create `tests/test_drive_bot_router.py` with tests proving `/jm 123` becomes a queued task, `/jm 原神` remains immediate search, usage questions stay immediate, and unknown text becomes LLM fallback.

- [ ] **Step 2: Run red test**

Run: `python3 -m unittest tests/test_drive_bot_router.py`

Expected: import failure because `drive_bot.router` does not exist.

- [ ] **Step 3: Implement intent dataclasses and router**

Add `ImmediateResponse`, `QueuedTaskIntent`, `LlmFallbackIntent`, constants for task types and scopes, plus `route_message(message, scope_type, user_id, group_id=None, jm_search_func=None)`.

- [ ] **Step 4: Run green test**

Run: `python3 -m unittest tests/test_drive_bot_router.py`

Expected: all router tests pass.

## Task 2: Estimator And SQLite Storage

**Files:**
- Create: `src/ncatbot_assistant/drive_bot/estimator.py`
- Create: `src/ncatbot_assistant/drive_bot/storage.py`
- Test: `tests/test_drive_bot_storage.py`

- [ ] **Step 1: Write failing storage tests**

Tests should create a temporary SQLite database, initialize schema, enqueue tasks, verify FIFO claim order, queue position, running recovery, and status transitions.

- [ ] **Step 2: Run red test**

Run: `python3 -m unittest tests/test_drive_bot_storage.py`

Expected: import failure because storage does not exist.

- [ ] **Step 3: Implement estimator and storage**

Use `sqlite3` with explicit connections per operation. Store JSON payloads/results as text. Expose `TaskStore.initialize()`, `enqueue()`, `queue_position()`, `estimated_wait_seconds()`, `claim_next()`, `mark_succeeded()`, `mark_failed()`, `recover_running_tasks()`, and `get()`.

- [ ] **Step 4: Run green test**

Run: `python3 -m unittest tests/test_drive_bot_storage.py`

Expected: storage tests pass.

## Task 3: Queue Worker

**Files:**
- Create: `src/ncatbot_assistant/drive_bot/jobs/queue.py`
- Test: `tests/test_drive_bot_queue.py`

- [ ] **Step 1: Write failing queue tests**

Tests should use fake handlers and fake notifier callbacks to prove a queued task is marked succeeded and notified, and a handler exception marks the task failed and notifies.

- [ ] **Step 2: Run red test**

Run: `python3 -m unittest tests/test_drive_bot_queue.py`

Expected: import failure because queue worker does not exist.

- [ ] **Step 3: Implement queue worker**

Add `TaskQueueWorker` with `start()`, `stop()`, `run_once()`, and internal loop. It should process one task at a time, call handler by task type, persist success/failure, and call notifier with the final task.

- [ ] **Step 4: Run green test**

Run: `python3 -m unittest tests/test_drive_bot_queue.py`

Expected: queue tests pass.

## Task 4: Services, Handlers, And Replies

**Files:**
- Create: `src/ncatbot_assistant/drive_bot/services/jm.py`
- Create: `src/ncatbot_assistant/drive_bot/services/setu.py`
- Create: `src/ncatbot_assistant/drive_bot/services/daily.py`
- Create: `src/ncatbot_assistant/drive_bot/jobs/handlers.py`
- Create: `src/ncatbot_assistant/drive_bot/reply.py`
- Test: `tests/test_drive_bot_handlers.py`

- [ ] **Step 1: Write failing handler tests**

Tests should inject fake service functions and fake reply adapters to verify JM, setu, and daily task handlers return useful result data and call upload/reply methods with the expected scope.

- [ ] **Step 2: Run red test**

Run: `python3 -m unittest tests/test_drive_bot_handlers.py`

Expected: import failure because handlers do not exist.

- [ ] **Step 3: Implement service wrappers, handler dispatch, and reply adapter**

JM download should run through `asyncio.to_thread`. Setu and daily wrappers can await existing async utilities. Reply adapter should support group/private uploads and completion messages.

- [ ] **Step 4: Run green test**

Run: `python3 -m unittest tests/test_drive_bot_handlers.py`

Expected: handler tests pass.

## Task 5: Plugin Wiring And Docs

**Files:**
- Modify: `plugins/drive_bot/plugin.py`
- Modify: `config.example.yaml`
- Modify: `plugins/drive_bot/README.md`
- Test: `tests/test_drive_bot_config.py`

- [ ] **Step 1: Write failing plugin import/config tests**

Extend existing plugin tests to verify default task config and the plugin can import with NcatBot stubs after the refactor.

- [ ] **Step 2: Run red test**

Run: `python3 -m unittest tests/test_drive_bot_config.py`

Expected: failure until plugin wiring exposes the new config defaults cleanly.

- [ ] **Step 3: Wire plugin**

On load, initialize defaults, storage, handlers, and worker. On group/private messages, build `ChatContext`, call router, enqueue queued tasks, reply immediately, or call existing LLM fallback. On close, stop worker.

- [ ] **Step 4: Run full verification**

Run:

```bash
python3 -m unittest discover tests
PYTHONPYCACHEPREFIX=/tmp/ncatbot-assistant-pycache python3 -m py_compile plugins/drive_bot/plugin.py src/ncatbot_assistant/drive_bot/*.py src/ncatbot_assistant/drive_bot/jobs/*.py src/ncatbot_assistant/drive_bot/services/*.py tests/*.py
```

Expected: tests pass and py_compile exits 0.

## Self-Review

- Spec coverage: the plan covers queued task UX, SQLite persistence, one global worker, original-conversation trigger-user notifications, startup recovery, and LLM memory exclusion.
- Placeholder scan: no task depends on unspecified future work.
- Type consistency: modules use the same `ChatContext`, task status, task type, and handler names across tasks.
