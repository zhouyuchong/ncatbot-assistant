from unittest import TestCase, main

import tests.bootstrap  # noqa: F401

from ncatbot_assistant.drive_bot.intents import ScopeType
from ncatbot_assistant.drive_bot.llm_context import (
    ConversationKey,
    LlmContextConfig,
    ShortTermConversationMemory,
    get_llm_context_config,
)


class ShortTermConversationMemoryTest(TestCase):
    def test_private_chat_returns_recent_messages_in_order(self):
        memory = ShortTermConversationMemory(max_turns=2)
        key = ConversationKey.private(user_id="u1")

        memory.append_user_message(key, "你好")
        memory.append_assistant_message(key, "你好呀")

        self.assertEqual(
            memory.recent_messages(key),
            [
                {"role": "user", "content": "你好"},
                {"role": "assistant", "content": "你好呀"},
            ],
        )

    def test_group_chat_isolated_by_group_and_user(self):
        memory = ShortTermConversationMemory(max_turns=3)
        key_a = ConversationKey.group(group_id="g1", user_id="u1")
        key_b = ConversationKey.group(group_id="g1", user_id="u2")
        key_c = ConversationKey.group(group_id="g2", user_id="u1")

        memory.append_user_message(key_a, "asyncio")
        memory.append_user_message(key_b, "sql")
        memory.append_user_message(key_c, "docker")

        self.assertEqual(
            memory.recent_messages(key_a), [{"role": "user", "content": "asyncio"}]
        )
        self.assertEqual(
            memory.recent_messages(key_b), [{"role": "user", "content": "sql"}]
        )
        self.assertEqual(
            memory.recent_messages(key_c), [{"role": "user", "content": "docker"}]
        )

    def test_memory_trims_old_messages_by_max_turns(self):
        memory = ShortTermConversationMemory(max_turns=1)
        key = ConversationKey.private(user_id="u1")

        memory.append_user_message(key, "old user")
        memory.append_assistant_message(key, "old assistant")
        memory.append_user_message(key, "new user")
        memory.append_assistant_message(key, "new assistant")

        self.assertEqual(
            memory.recent_messages(key),
            [
                {"role": "user", "content": "new user"},
                {"role": "assistant", "content": "new assistant"},
            ],
        )

    def test_disabled_memory_returns_no_history(self):
        memory = ShortTermConversationMemory(max_turns=3, enabled=False)
        key = ConversationKey.private(user_id="u1")

        memory.append_user_message(key, "你好")
        memory.append_assistant_message(key, "你好呀")

        self.assertEqual(memory.recent_messages(key), [])

    def test_context_config_uses_defaults_and_clamps_max_turns(self):
        self.assertEqual(
            get_llm_context_config({}), LlmContextConfig(enabled=True, max_turns=6)
        )
        self.assertEqual(
            get_llm_context_config(
                {"llm": {"context": {"enabled": False, "max_turns": -3}}}
            ),
            LlmContextConfig(enabled=False, max_turns=0),
        )
        self.assertEqual(
            get_llm_context_config(
                {"llm": {"context": {"enabled": "yes", "max_turns": "2"}}}
            ),
            LlmContextConfig(enabled=True, max_turns=2),
        )

    def test_context_config_parses_string_boolean_values(self):
        self.assertEqual(
            get_llm_context_config({"llm": {"context": {"enabled": "false"}}}),
            LlmContextConfig(enabled=False, max_turns=6),
        )
        self.assertEqual(
            get_llm_context_config({"llm": {"context": {"enabled": "0"}}}),
            LlmContextConfig(enabled=False, max_turns=6),
        )

    def test_conversation_key_from_scope(self):
        self.assertEqual(
            ConversationKey.from_scope(ScopeType.PRIVATE, user_id="u1", group_id=None),
            ConversationKey.private(user_id="u1"),
        )
        self.assertEqual(
            ConversationKey.from_scope(ScopeType.GROUP, user_id="u1", group_id="g1"),
            ConversationKey.group(group_id="g1", user_id="u1"),
        )


if __name__ == "__main__":
    main()
