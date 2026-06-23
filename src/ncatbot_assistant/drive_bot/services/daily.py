import asyncio
import os

from ncatbot_assistant.drive_bot.constants import DAILY_PIC_URL, IMAGE_DIR


async def fetch_daily_image():
    return await asyncio.to_thread(fetch_daily_image_sync)


def fetch_daily_image_sync():
    import requests

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        response = requests.get(DAILY_PIC_URL, headers=headers, timeout=10)
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "")
        if "jpeg" in content_type or "jpg" in content_type:
            ext = "jpg"
        elif "png" in content_type:
            ext = "png"
        else:
            ext = "jpg"

        os.makedirs(IMAGE_DIR, exist_ok=True)
        file_path = os.path.join(IMAGE_DIR, f"moyu_image.{ext}")
        with open(file_path, "wb") as file:
            file.write(response.content)

        return file_path

    except requests.exceptions.RequestException:
        return None
