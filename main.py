"""Compatibility entrypoint for running the configured NcatBot app."""

import os
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
os.chdir(APP_DIR)

from ncatbot.app import BotClient

if __name__ == "__main__":
    BotClient().run()
