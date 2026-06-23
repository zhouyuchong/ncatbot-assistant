from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[3]
PDF_DIR = str(ROOT_DIR / "pdf")
IMAGE_DIR = str(ROOT_DIR / "image")

JM_MATCH = r"/jm\s+(.+)"
JMCOMIC_PATTERN = r"^/jm\s(\d+)$"
SETU_PATTERN = r"/setu(?:\s+(.*))?$"

DAILY_PIC_URL = "https://api.52vmy.cn/api/wl/moyu"
TARGET_GROUP_IDS = [1019587647]
DAILY_MESSAGE = "早上好！新的一天开始了，祝大家工作顺利，心情愉快！"


JMCOMIC_OPTION = {
    "dir_rule": {"rule": "Bd_Aid", "base_dir": "./cache/"},
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
                    "pdf_dir": "./pdf",
                    "filename_rule": "{Aalbum_id}-{Aname}-{Psort}",
                },
            }
        ]
    },
}
