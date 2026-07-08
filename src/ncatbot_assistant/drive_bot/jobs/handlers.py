from __future__ import annotations

import os
from collections.abc import Awaitable, Callable

from ncatbot_assistant.drive_bot.intents import TaskRecord, TaskType
from ncatbot_assistant.drive_bot.reply import ReplyAdapter, delete_file as default_delete_file
from ncatbot_assistant.drive_bot.services.daily import fetch_daily_image
from ncatbot_assistant.drive_bot.services.jm import download_album
from ncatbot_assistant.drive_bot.services.setu import download as download_setu_image
from ncatbot_assistant.drive_bot.services.setu import fetch_url as fetch_setu_url
from ncatbot_assistant.drive_bot.constants import IMAGE_DIR


class NullLogger:
    def debug(self, *_args, **_kwargs):
        pass

    def warning(self, *_args, **_kwargs):
        pass


class TaskHandlers:
    def __init__(
        self,
        reply: ReplyAdapter,
        logger=None,
        jm_download: Callable[[int, object], list[dict[str, str]] | Awaitable[list[dict[str, str]]]] | None = None,
        setu_get_url: Callable[[list[list[str]], object], Awaitable[tuple[bool, str]]] | None = None,
        setu_download_image: Callable[[str, str, object], Awaitable[bool]] | None = None,
        daily_function: Callable[[], Awaitable[str]] | None = None,
        daily_ai_function: Callable[[], Awaitable[str]] | None = None,
        image_dir: str = IMAGE_DIR,
        delete_file: Callable[[str, object], None] = default_delete_file,
    ):
        self.reply = reply
        self.logger = logger or NullLogger()
        self.jm_download = jm_download or download_album
        self.setu_get_url = setu_get_url or fetch_setu_url
        self.setu_download_image = setu_download_image or download_setu_image
        self.daily_function = daily_function or fetch_daily_image
        self.daily_ai_function = daily_ai_function
        self.image_dir = image_dir
        self.delete_file = delete_file

    def supported_task_types(self) -> tuple[TaskType, ...]:
        return (TaskType.JM_DOWNLOAD, TaskType.SETU, TaskType.DAILY, TaskType.DAILY_AI)

    async def handle(self, task: TaskRecord) -> dict:
        if task.task_type == TaskType.JM_DOWNLOAD:
            return await self._handle_jm(task)
        if task.task_type == TaskType.SETU:
            return await self._handle_setu(task)
        if task.task_type == TaskType.DAILY:
            return await self._handle_daily(task)
        if task.task_type == TaskType.DAILY_AI:
            return await self._handle_daily_ai(task)
        raise ValueError(f"unsupported task type: {task.task_type}")

    async def _handle_jm(self, task: TaskRecord) -> dict:
        files = await _maybe_await(self.jm_download(int(task.payload["album_id"]), self.logger))
        await self.reply.upload_files(task, files, "本子")
        for item in files:
            self.delete_file(item["file_path"], self.logger)
        return {"uploaded_files": len(files), "files": files}

    async def _handle_setu(self, task: TaskRecord) -> dict:
        tags = [[tag] for tag in task.payload.get("tags", [])]
        ok, url = await self.setu_get_url(tags, self.logger)
        if not ok:
            raise RuntimeError(url)

        file_name = os.path.basename(url).replace(".jpg", ".png")
        file_path = os.path.join(self.image_dir, file_name)
        downloaded = await self.setu_download_image(url, file_path, self.logger)
        if not downloaded:
            raise RuntimeError("涩图下载失败")

        files = [{"file_name": file_name, "file_path": file_path}]
        await self.reply.upload_files(task, files, "涩图")
        self.delete_file(file_path, self.logger)
        return {"uploaded_files": 1, "files": files}

    async def _handle_daily(self, task: TaskRecord) -> dict:
        file_path = await self.daily_function()
        if not file_path:
            raise RuntimeError("获取每日图片失败，接口暂时不可用，请稍后再试。")
        await self.reply.reply_direct_image(task, "请查收", file_path)
        return {"sent_images": 1, "file_path": file_path}


    async def _handle_daily_ai(self, task: TaskRecord) -> dict:
        if not self.daily_ai_function:
            raise RuntimeError("未配置 daily_ai_function")
        try:
            text = await _maybe_await(self.daily_ai_function())
            await self.reply.reply_direct_text(task, text)
            return {"sent_text": 1, "text": text}
        except Exception as e:
            error_msg = f"获取每日AI失败：{e}"
            await self.reply.reply_direct_text(task, error_msg)
            return {"error": str(e)}


async def _maybe_await(value):
    if hasattr(value, "__await__"):
        return await value
    return value
