from __future__ import annotations

import os
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[2]


def main() -> None:
    os.chdir(PROJECT_DIR)

    from ncatbot.app import BotClient

    BotClient().run()
