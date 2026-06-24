# Drive Bot User Memory Design

## Goal

Add persistent user-level LLM memory for group chats. The bot records group messages that mention it, summarizes each user's new messages into a global user prompt on a daily schedule, and injects that prompt into future group LLM fallback replies alongside the existing short-term conversation context.

## Scope

This first version supports group messages only. Private messages keep their current behavior: no long-term message capture, no profile creation, and no user-memory prompt injection.

Long-term memory is global per `user_id`, not per group. The existing short-term context remains scoped to the current group and user, so replies combine global user preference with local recent conversation.

## Data Model

Store user memory in the existing SQLite database.

`user_messages` records raw group messages that mention the bot:

- `id`: monotonically increasing message id.
- `scope_type`: `group` for this version.
- `group_id`: group where the message was sent.
- `user_id`: sender id.
- `message_text`: raw text passed to the router.
- `intent_type`: `llm_fallback`, `queued_task`, or `immediate`.
- `created_at`: Unix timestamp.

`user_profiles` stores one global memory prompt per user:

- `user_id`: primary key.
- `user_prompt`: summarized prompt to inject into LLM requests.
- `last_summarized_message_id`: last `user_messages.id` included in the summary.
- `updated_at`: Unix timestamp for the last successful update.
- `summary_error`: last summarization error, if any.
- `enabled`: boolean gate for future user-level opt-out.

## Capture Behavior

Only group messages that mention the bot are captured. Capture happens after routing so the stored row can include the intent type.

All group at-bot messages are logged for auditability, but summarization treats them differently:

- `llm_fallback`: high-signal conversation material.
- `queued_task`: weak signal. It may express a recurring interest but should not create strong personality claims.
- `immediate`: low signal and normally ignored for the generated prompt.

Private messages are not captured in this version.

## Summarization

A lightweight async scheduler runs daily around the configured local hour, defaulting to midnight in `Asia/Shanghai`. It summarizes only users with unsummarized group messages.

For each user:

1. Read the current profile.
2. Read new messages with `id > last_summarized_message_id`, capped by `max_daily_messages`.
3. Ask the LLM to produce a compact updated user prompt from the previous prompt and new messages.
4. Store the updated prompt, advance `last_summarized_message_id`, clear `summary_error`, and set `updated_at`.
5. On failure, keep the previous prompt and record `summary_error`.

The summarization prompt must treat user messages as data, not instructions. It should extract only stable preferences, durable background, explicit goals, preferred answer style, and recurring interests. It must avoid sensitive inferences and avoid overfitting to one-off commands.

## LLM Reply Flow

Group LLM fallback replies use this message order:

1. System prompt with the bot's base behavior and role skill.
2. Optional user-memory system message when a non-empty enabled profile exists for `user_id`.
3. Existing short-term group/user conversation history.
4. Current user prompt.

The user-memory message tells the model that the profile is reference context only and should not be exposed or quoted back verbatim.

Private LLM fallback replies keep their current message order: system prompt, short-term history, current prompt.

## Configuration

Extend `llm` config:

```yaml
llm:
  memory:
    enabled: true
    group_enabled: true
    private_enabled: false
    summarize_hour: 0
    timezone: "Asia/Shanghai"
    max_daily_messages: 200
    prompt_max_chars: 1500
    include_commands: false
```

Defaults are safe and preserve behavior if the section is absent. `private_enabled` defaults to `false` and is not implemented beyond config parsing.

## Error Handling

- Message capture failure should be logged but must not block the user reply.
- Missing or malformed config values fall back to defaults.
- Summarization failure stores an error on the profile and leaves the old prompt unchanged.
- Empty summaries should not replace a useful previous prompt unless there is no stable memory to keep.

## Tests

Add tests for:

- Memory config defaults and parsing.
- SQLite table initialization.
- Capturing group messages and creating profiles.
- Private messages not being captured by plugin flow.
- Incremental unsummarized-message lookup and cursor advancement.
- User prompt injection in group LLM fallback.
- No user prompt injection in private LLM fallback.
- Summary prompt construction filtering immediate messages when `include_commands` is false.

## Out Of Scope

- Private-message long-term memory.
- User commands to view, clear, or disable memory.
- Vector retrieval.
- Real-time per-message summarization.
- Group-level shared profiles.
