from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main

import tests.bootstrap  # noqa: F401

from ncatbot_assistant.drive_bot.constants import (
    CACHE_DIR,
    IMAGE_DIR,
    JMCOMIC_OPTION,
    PDF_DIR,
    ensure_runtime_directories,
)


class DriveBotRuntimeDirsTest(TestCase):
    def test_cache_image_and_pdf_dirs_live_under_data(self):
        self.assertEqual(Path(CACHE_DIR).parent.name, "data")
        self.assertEqual(Path(IMAGE_DIR).parent.name, "data")
        self.assertEqual(Path(PDF_DIR).parent.name, "data")
        self.assertEqual(JMCOMIC_OPTION["dir_rule"]["base_dir"], CACHE_DIR)
        self.assertEqual(
            JMCOMIC_OPTION["plugins"]["after_photo"][0]["kwargs"]["pdf_dir"],
            PDF_DIR,
        )

    def test_ensure_runtime_directories_creates_required_dirs(self):
        with TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)

            ensure_runtime_directories(root_dir)

            self.assertTrue((root_dir / "data").is_dir())
            self.assertTrue((root_dir / "data" / "cache").is_dir())
            self.assertTrue((root_dir / "data" / "image").is_dir())
            self.assertTrue((root_dir / "data" / "pdf").is_dir())


if __name__ == "__main__":
    main()
