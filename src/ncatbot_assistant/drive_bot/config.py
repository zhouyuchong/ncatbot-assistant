from __future__ import annotations

from functools import lru_cache
from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parents[3]


def load_yaml_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return {}
    return data


@lru_cache(maxsize=1)
def load_project_config() -> dict[str, Any]:
    return load_yaml_config(PROJECT_DIR / "config.yaml")


def get_storage_path(config: dict[str, Any]) -> Path:
    storage_config = config.get("storage") or {}
    if not isinstance(storage_config, dict):
        storage_config = {}
    sqlite_path = storage_config.get("sqlite_path") or "data/drive_bot.sqlite3"
    path = Path(sqlite_path)
    if not path.is_absolute():
        path = PROJECT_DIR / path
    return path


def get_task_estimates(config: dict[str, Any]) -> dict[str, int]:
    task_config = config.get("tasks") or {}
    if not isinstance(task_config, dict):
        return {}
    estimates = task_config.get("estimates") or {}
    if not isinstance(estimates, dict):
        return {}
    return {str(key): int(value) for key, value in estimates.items()}


@dataclass(frozen=True)
class LlmToolsConfig:
    enabled: bool = True
    timeout_seconds: float = 30


def get_llm_tools_config(config: dict[str, Any]) -> LlmToolsConfig:
    llm = config.get('llm') or {}
    tools = (llm.get('tools') or {}) if isinstance(llm, dict) else {}
    if not isinstance(tools, dict):
        tools = {}
    enabled = tools.get('enabled', True)
    if isinstance(enabled, str):
        enabled = enabled.strip().lower() not in {'false', '0', 'no', 'off'}
    try:
        value = tools.get('timeout_seconds', 30)
        timeout = float(value)
        if isinstance(value, bool) or not math.isfinite(timeout) or timeout <= 0:
            timeout = 30
    except (TypeError, ValueError):
        timeout = 30
    return LlmToolsConfig(bool(enabled), timeout)
