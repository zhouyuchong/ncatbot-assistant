"""Single-request LLM decisions, preserving structured tool calls."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments_json: str


@dataclass(frozen=True)
class LlmDecision:
    text: str = ''
    tool_calls: tuple[ToolCall, ...] = ()
