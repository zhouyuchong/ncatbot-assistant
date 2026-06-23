# Drive Bot Short-Term LLM Context Design

## Goal

Add short-term conversation context to the Drive Bot LLM fallback so normal chat can refer to recent prior messages. This version keeps context in memory only and does not implement persistent memory, summarization, retrieval, or user profiles.

## Constraints

- Existing command behavior must stay unchanged.
- Only LLM fallback conversations should enter the context window.
- Help messages, `/jm`, `/setu`, daily news, queued task status, and task completion notifications should not be stored in LLM context.
- Context must be isolated by chat scope so one user's conversation does not affect another user's LLM reply.
- The feature must be configurable and easy to disable.
- Restarting the bot may clear all short-term context.

## User Experience

When a user sends normal non-command messages to the bot, the bot should answer with awareness of the recent LLM fallback conversation in that same conversation scope.

Example private chat:

```text
User: 我最近在学 Python 装饰器
Bot: 可以从函数包装的角度理解...
User: 给我一个刚才那个概念的小例子
Bot: 可以，还是用 Python 装饰器举例...
```

Example group chat:

```text
Group user A: @bot 我在学 asyncio
Bot: ...
Group user B: @bot 我在学 SQL
Bot: ...
Group user A: @bot 继续刚才那个
Bot: continues A's asyncio context, not B's SQL context.
```

## Scope Model

Conversation memory uses a stable key derived from the message scope:

- Private chat: `private:{user_id}`
- Group chat: `group:{group_id}:user:{user_id}`

Group context is intentionally isolated per user. This avoids accidental cross-user leakage in noisy groups and keeps the first version predictable. A future version can add shared group context explicitly if needed.

## Architecture

Add `src/ncatbot_assistant/drive_bot/llm_context.py` with a small in-memory context manager.

Core objects:

- `ConversationKey`: immutable value object containing `scope_type`, `user_id`, and optional `group_id`.
- `ShortTermConversationMemory`: stores recent LLM messages by `ConversationKey`.

Core methods:

- `append_user_message(key, content)`: append one user message.
- `append_assistant_message(key, content)`: append one assistant message.
- `recent_messages(key)`: return stored messages in OpenAI chat message format.
- `clear(key=None)`: clear one conversation or all conversations, mainly for tests and future admin tooling.

The memory manager should store only chat roles accepted by the LLM API: `user` and `assistant`. System prompts are built separately and are not stored.

## LLM Flow

Change plugin LLM handling so `_ask_ai` receives the current `scope_type`, `group_id`, and `user_id`.

For an LLM fallback:

1. Build the `ConversationKey`.
2. Read recent messages for that key.
3. Call the LLM with:
   - system prompt
   - recent memory messages
   - current user prompt
4. On success:
   - append the current user prompt
   - append the assistant reply
   - reply to the event
5. On LLM failure:
   - append only the current user prompt
   - return the existing temporary-unavailable error text

Failure replies should not be stored as assistant messages because they are operational errors, not meaningful conversation content.

## Configuration

Extend the top-level `llm` config:

```yaml
llm:
  context:
    enabled: true
    max_turns: 6
```

Defaults:

- `enabled`: `true`
- `max_turns`: `6`

`max_turns` means user/assistant pairs. A `max_turns` value of 6 stores at most 12 history messages per conversation key. The current user prompt is added separately when calling the LLM, so the request can contain up to 12 historical messages plus the current prompt.

If context is disabled, the LLM request should match the current single-turn behavior: system prompt plus current user prompt.

Invalid or missing config values should fall back to defaults. `max_turns` should be clamped to at least 0. A value of 0 keeps no history while preserving the same code path.

## Storage And Trimming

The first version stores context in process memory using standard Python data structures.

Each conversation key has a bounded list of messages. After every append, trim the list to the latest `max_turns * 2` messages. Trimming by messages rather than semantic turns is acceptable because the plugin appends one user and one assistant message on success.

No SQLite table is added in this version.

## Error Handling

- If the LLM API raises an exception, keep the existing user-facing fallback error.
- If context config is malformed, use safe defaults and continue.
- If group context is requested without a `group_id`, construct a key with an empty group id only in tests; live group messages should always provide `group_id`.

## Testing

Add unit tests for:

- Private chat memory returns recent messages in insertion order.
- Group chat memory is isolated by `group_id` and `user_id`.
- Old messages are trimmed when `max_turns` is exceeded.
- Disabled context returns no historical messages.
- Plugin LLM message construction includes history before the current prompt.
- Plugin LLM fallback records user and assistant messages on success.
- Plugin LLM fallback records only the user message on API failure.

Existing router tests should continue proving commands and help responses do not become LLM fallback intents.

## Out Of Scope

- Persistent LLM memory.
- Conversation summarization.
- Retrieval-augmented memory.
- Long-term user profile storage.
- Shared group-level context.
- Admin commands to inspect or clear memory.
