'''
Author: zhouyuchong
Date: 2025-08-13 15:43:09
Description: 
LastEditors: zhouyuchong
LastEditTime: 2025-08-13 16:11:27
'''
import os
import requests
import asyncio 
import aiohttp

from .constants import DAILY_PIC_URL, IMAGE_DIR

async def daily_function():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        # 发送GET请求，获取响应
        response = requests.get(DAILY_PIC_URL, headers=headers, timeout=10)
        response.raise_for_status()  # 检查请求是否成功（状态码200）

        # 从响应头获取图片类型，确定文件扩展名
        content_type = response.headers.get("Content-Type", "")
        if "jpeg" in content_type or "jpg" in content_type:
            ext = "jpg"
        elif "png" in content_type:
            ext = "png"
        else:
            ext = "jpg"  # 默认扩展名

        # 保存图片到本地（当前目录，文件名可自定义）
        file_name = f"moyu_image.{ext}"
        file_name = os.path.join(IMAGE_DIR, file_name)
        with open(file_name, "wb") as f:
            f.write(response.content)  # 写入二进制数据

        print(f"图片已成功保存到：{file_name}")
        return file_name

    except requests.exceptions.RequestException as e:
        print(f"请求失败：{e}")
        return None

if __name__ == "__main__":
    daily_function()