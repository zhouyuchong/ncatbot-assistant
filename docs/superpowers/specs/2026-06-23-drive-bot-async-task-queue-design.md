# Drive Bot Async Task Queue Design

## Goal

Refactor Drive Bot so high-cost operations run in a controlled background queue while the bot remains responsive to other messages. The first version focuses on task orchestration and persistence only; it does not implement LLM memory or change the LLM fallback behavior beyond keeping future extension points clean.

## Constraints

- Target deployment is a small VPS with 2 CPU cores and 4 GB RAM.
- Expected active users are fewer than 10.
- High-cost operations should not run concurrently in the first version.
- Task completion notifications should be addressed only to the triggering user.
- SQLite should be introduced now because it will also support future task history and LLM context features.
- LLM memory, conversation summarization, and long-term user profiles are out of scope for this version.

## User Experience

When a user triggers a high-cost task, the bot immediately replies with the task id, estimated wait, estimated total time, and queue position. The task then runs in the background.

While the task is queued or running, the same user and other users can continue asking normal questions or enqueue additional tasks. New high-cost tasks enter the same global FIFO queue.

When the task finishes, the bot sends a completion or failure message in the original conversation. In a group, the message mentions the triggering user; in a private chat, it replies directly.

Example enqueue reply:

```text
已收到，任务 #42 已加入队列。
当前排队位置：2
预计等待：3 分钟，预计总耗时：8 分钟。
完成后我会 @你。
```

Example completion reply:

```text
@用户 任务 #42 完成：已上传 3 个文件，用时 7 分 12 秒。
```

Example failure reply:

```text
@用户 任务 #42 失败：JM 下载完成但未生成 PDF，请检查 img2pdf 依赖。
```

## Task Scope

Queued tasks:

- `/jm 数字ID`: download comic assets, convert to PDF, upload generated files, clean up uploaded files.
- `/setu ...`: fetch image URL, download image, upload generated file.
- `每日新闻`: fetch the daily news image and send it.

Immediate responses:

- Help and usage messages.
- `/jm 关键词` search.
- LLM fallback. The current fallback can remain synchronous for this version.

## Architecture

The plugin entrypoint under `plugins/drive_bot/plugin.py` should stay as a thin NcatBot discovery shim. The actual adapter class should live in the importable application package, adapt NcatBot events into internal message context objects, call a router, enqueue high-cost tasks, send immediate replies, and delegate completion notifications to a background worker.

The core package should be separated into small modules:

```text
plugins/
  drive_bot/
    manifest.toml
    plugin.py
src/
  ncatbot_assistant/
    drive_bot/
      ncatbot_plugin.py
      config.py
      intents.py
      router.py
      estimator.py
      storage.py
      reply.py
      jobs/
        queue.py
        handlers.py
      services/
        jm.py
        setu.py
        daily.py
```

Responsibilities:

- `plugins/drive_bot/plugin.py`: add `src` to `sys.path` and re-export `DriveBotPlugin` for NcatBot discovery.
- `ncatbot_plugin.py`: NcatBot adapter class, event handling, enqueue replies, and current LLM fallback.
- `config.py`: load `config.yaml` and expose project config helpers.
- `intents.py`: define intent, task, and chat context data structures.
- `router.py`: parse raw text into immediate responses, queued tasks, or LLM fallback.
- `estimator.py`: calculate queue position and time estimates.
- `storage.py`: create SQLite schema and provide task CRUD operations.
- `reply.py`: isolate group/private reply and upload behavior.
- `jobs/queue.py`: own worker lifecycle and sequential task execution.
- `jobs/handlers.py`: map task types to service execution.
- `services/*`: implement JM, setu, and daily utilities without tying them to NcatBot event objects.

## Persistence

SQLite stores task state in a single `tasks` table for the first version:

```text
id INTEGER PRIMARY KEY AUTOINCREMENT
task_type TEXT NOT NULL
status TEXT NOT NULL
scope_type TEXT NOT NULL
group_id TEXT
user_id TEXT NOT NULL
raw_message TEXT NOT NULL
payload_json TEXT NOT NULL
result_json TEXT
error TEXT
estimated_seconds INTEGER NOT NULL
created_at REAL NOT NULL
started_at REAL
finished_at REAL
```

Task statuses:

- `queued`
- `running`
- `succeeded`
- `failed`
- `cancelled`

The first version does not need a separate queue table. Queue order is determined by `created_at` and `id` for rows with `queued` status.

On startup, tasks left in `running` from a previous process should be marked `failed` with an error explaining that the process restarted before completion. This avoids accidentally re-uploading files or duplicating partially completed work.

## Execution Model

The first version uses one global worker. The worker repeatedly claims the oldest queued task, marks it running, executes the matching handler, then marks it succeeded or failed.

Blocking CPU or IO-heavy synchronous functions, such as JM download and PDF generation, should run through `asyncio.to_thread` so the event loop stays responsive. Uploads stay inside the task handler and run sequentially.

The worker should start in `on_load` and stop in `on_close`. The stop path should cancel the worker task and avoid starting new work during shutdown.

## Estimation

Estimates can be static in the first version:

- `jm_download`: 480 seconds.
- `setu`: 45 seconds.
- `daily`: 30 seconds.

Estimated wait is the sum of estimated seconds for queued and running tasks ahead of the new task. Queue position is the count of queued tasks ahead plus one.

## Error Handling

If task parsing fails, the bot sends an immediate validation error and does not enqueue a task.

If a task handler raises an exception, the worker marks the task as failed, stores the error string, and notifies the triggering user.

If a file upload succeeds, local generated files should be deleted afterward. If deletion fails, the worker logs a warning but does not fail the completed task.

## Testing

The implementation should add unit tests for:

- Router behavior for queued tasks, immediate commands, and LLM fallback.
- SQLite storage schema, enqueue, queue position, status transitions, and startup recovery.
- Estimator behavior.
- Queue worker success and failure transitions with fake handlers and fake replies.

Existing plugin import tests should keep using stubs for NcatBot dependencies so the test suite remains runnable without a live bot runtime.

## Out Of Scope

- LLM memory implementation.
- Multi-worker concurrency.
- Task cancellation commands.
- Task progress updates.
- Private completion notification for tasks started in a group.
- Re-queueing interrupted running tasks on restart.
