async def fetch_url(tags: list[list[str]], logger):
    return await setu_get_url(tags, logger)


async def download(url: str, save_path: str, logger):
    return await download_image(url, save_path, logger)


async def setu_get_url(tags=None, logger=None):
    import aiohttp

    tags = tags or []
    try:
        async with aiohttp.ClientSession() as session:
            data = {
                "r18": 2,
                "size": ["original"],
                "tag": tags,
                "excludeAI": False,
            }
            async with session.post(
                "https://api.lolicon.app/setu/v2",
                json=data,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as response:
                resp = await response.json()
                logger.info(resp)
                if not resp["data"]:
                    logger.warning("没有满足条件的图片")
                    return False, "没有满足条件的图片"
                logger.debug(f"获取图片信息成功: {resp}")
                download_url = resp["data"][0]["urls"]["original"]
                logger.debug(f"获取图片链接成功: {download_url}")
                return True, download_url
    except Exception as exc:
        logger.error(f"获取图片失败: {exc}")
        if "503" in str(exc):
            return False, "setu 服务器异常"
        return True, "获取图片失败"


async def download_image(url: str, save_path: str, logger):
    import os

    import aiohttp

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                content = await response.read()
                content = await image_obfus(content, logger)
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                with open(save_path, "wb") as file:
                    file.write(content)
                logger.debug(f"图片已保存到: {save_path}")
                return True

            logger.warning(f"下载失败，状态码: {response.status}")
            return False


async def image_obfus(img_data, logger):
    import random
    from io import BytesIO

    from PIL import Image as ImageP

    try:
        with BytesIO(img_data) as input_buffer:
            with ImageP.open(input_buffer) as img:
                if img.mode != "RGB":
                    img = img.convert("RGB")

                width, height = img.size
                pixels = img.load()

                points = []
                for _ in range(3):
                    while True:
                        x = random.randint(0, width - 1)
                        y = random.randint(0, height - 1)
                        if (x, y) not in points:
                            points.append((x, y))
                            break

                for x, y in points:
                    r, g, b = pixels[x, y]
                    new_r = max(0, min(255, r + random.choice([-1, 1])))
                    new_g = max(0, min(255, g + random.choice([-1, 1])))
                    new_b = max(0, min(255, b + random.choice([-1, 1])))
                    pixels[x, y] = (new_r, new_g, new_b)

                with BytesIO() as output:
                    img.save(output, format="PNG")
                    return output.getvalue()

    except Exception as exc:
        logger.warning(f"破坏图片哈希时发生错误: {exc}")
        return img_data
