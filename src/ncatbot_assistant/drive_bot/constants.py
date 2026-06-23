from __future__ import annotations

from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = str(ROOT_DIR / "data")
CACHE_DIR = str(ROOT_DIR / "data" / "cache")
PDF_DIR = str(ROOT_DIR / "data" / "pdf")
IMAGE_DIR = str(ROOT_DIR / "data" / "image")

JM_MATCH = r"/jm\s+(.+)"
JMCOMIC_PATTERN = r"^/jm\s(\d+)$"
SETU_PATTERN = r"/setu(?:\s+(.*))?$"

DAILY_PIC_URL = "https://api.52vmy.cn/api/wl/moyu"
TARGET_GROUP_IDS = [1019587647]
DAILY_MESSAGE = "早上好！新的一天开始了，祝大家工作顺利，心情愉快！"


JMCOMIC_OPTION = {
    "dir_rule": {"rule": "Bd_Aid", "base_dir": CACHE_DIR},
    "download": {
        "cache": True,
        "image": {
            "decode": True,
            "suffix": ".jpg",
        },
        "threading": {"image": 2},
    },
    "plugins": {
        "after_photo": [
            {
                "plugin": "img2pdf",
                "kwargs": {
                    "pdf_dir": PDF_DIR,
                    "filename_rule": "{Aalbum_id}-{Aname}-{Psort}",
                },
            }
        ]
    },
}


def runtime_directories(root_dir: Path | str = ROOT_DIR) -> tuple[Path, ...]:
    root = Path(root_dir)
    data_dir = root / "data"
    return (
        data_dir,
        data_dir / "cache",
        data_dir / "pdf",
        data_dir / "image",
    )


def ensure_runtime_directories(root_dir: Path | str = ROOT_DIR) -> None:
    for directory in runtime_directories(root_dir):
        directory.mkdir(parents=True, exist_ok=True)
