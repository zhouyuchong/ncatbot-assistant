"""
Author: zhouyuchong
Date: 2025-08-04 10:53:56
Description:
LastEditors: zhouyuchong
LastEditTime: 2025-08-13 15:59:27
"""

import os

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PDF_DIR = os.path.join(ROOT_DIR, "pdf")
IMAGE_DIR = os.path.join(ROOT_DIR, "image")

DOWNLOAD_TIME_INTERVAL = 60
JM_MATCH = r"/jm\s+(.+)"
JMCOMIC_PATTERN = r"^/jm\s(\d+)$"
# SETU_PATTERN = r"^/setu\s*(.*)$"
SETU_PATTERN = r"/setu(?:\s+(.*))?$"

DAILY_PIC_URL = "https://api.52vmy.cn/api/wl/moyu"
TARGET_GROUP_IDS = [1019587647]
# 每天早上8点发送的消息内容
DAILY_MESSAGE = "早上好！新的一天开始了，祝大家工作顺利，心情愉快！"


JMCOMIC_OPTION = {
    "dir_rule": {"rule": "Bd_Aid", "base_dir": "./cache/"},
    "download": {
        "cache": True,
        "image": {
            "decode": True,  # 是否解码图片'
            "suffix": ".jpg",  # 转为jpg格式的图片
        },
        "threading": {"image": 2},
    },
    "plugins": {
        "after_photo": [
            {
                "plugin": "img2pdf",
                "kwargs": {
                    "pdf_dir": "./pdf",  # pdf存放文件夹
                    "filename_rule": "{Aalbum_id}-{Aname}-{Psort}",
                },
            }
        ]
    },
}
