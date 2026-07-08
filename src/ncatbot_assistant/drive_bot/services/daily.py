import asyncio
import os

from ncatbot_assistant.drive_bot.constants import DAILY_PIC_URL, IMAGE_DIR


async def fetch_daily_image():
    return await asyncio.to_thread(fetch_daily_image_sync)


def fetch_daily_image_sync():
    import requests
    from PIL import Image
    import io

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        response = requests.get(DAILY_PIC_URL, headers=headers, timeout=10)
        response.raise_for_status()

        # 使用 PIL 读取并压缩图片
        img = Image.open(io.BytesIO(response.content))
        
        # 转换成 RGB，因为 JPEG 不支持 Alpha 通道
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
            
        # 如果宽度大于 1000px，进行等比例缩放以减小尺寸和体积
        max_width = 1000
        if img.width > max_width:
            ratio = max_width / img.width
            new_size = (max_width, int(img.height * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)

        os.makedirs(IMAGE_DIR, exist_ok=True)
        file_path = os.path.join(IMAGE_DIR, "moyu_image.jpg")
        
        # 保存为压缩的 JPEG，设置 quality 和 optimize
        img.save(file_path, "JPEG", quality=75, optimize=True)

        return file_path

    except Exception:
        return None

