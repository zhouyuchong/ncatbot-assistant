"""NcatBot plugin entrypoint for Drive Bot."""

import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_DIR / "src"

for path in (SRC_DIR, PROJECT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from ncatbot_assistant.drive_bot.ncatbot_plugin import DriveBotPlugin  # noqa: E402,F401
