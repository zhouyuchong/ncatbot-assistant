from __future__ import annotations

from pathlib import Path

from .intents import ScopeType, TaskRecord, TaskStatus


def answer_files(result: dict) -> list[dict[str, str]]:
    if "files" in result:
        return list(result["files"])
    return [{"file_name": result["file_name"], "file_path": result["file_path"]}]


def delete_file(file_path: str, logger) -> None:
    try:
        Path(file_path).unlink(missing_ok=True)
        logger.debug("已删除上传后的文件: %s", file_path)
    except Exception as exc:
        logger.warning("删除上传后的文件失败: %s", exc)


class ReplyAdapter:
    def __init__(self, file_api, event_lookup):
        self.file_api = file_api
        self.event_lookup = event_lookup

    async def upload_files(
        self,
        task: TaskRecord,
        files: list[dict[str, str]],
        folder_name: str,
    ) -> None:
        if task.scope_type == ScopeType.GROUP:
            folder_id = await self.file_api.get_or_create_group_folder(
                task.group_id,
                folder_name,
            )
            for item in files:
                await self.file_api.upload_group_file(
                    group_id=task.group_id,
                    file=item["file_path"],
                    name=item["file_name"],
                    folder_id=folder_id,
                )
            return

        for item in files:
            await self.file_api.upload_private_file(
                user_id=task.user_id,
                file=item["file_path"],
                name=item["file_name"],
            )

    async def reply_direct_image(self, task: TaskRecord, text: str, image_path: str) -> None:
        event = self.event_lookup(task)
        await event.reply(text=text, image=image_path)

    async def notify_task_done(self, task: TaskRecord) -> None:
        event = self.event_lookup(task)
        if task.status == TaskStatus.SUCCEEDED:
            text = self._mention(task) + self._success_text(task)
        else:
            text = self._mention(task) + f"任务 #{task.id} 失败：{task.error}"
        await event.reply(text=text)

    def _mention(self, task: TaskRecord) -> str:
        if task.scope_type == ScopeType.GROUP:
            return f"[CQ:at,qq={task.user_id}] "
        return ""

    def _success_text(self, task: TaskRecord) -> str:
        result = task.result or {}
        if "uploaded_files" in result:
            return f"任务 #{task.id} 完成：已上传 {result['uploaded_files']} 个文件。"
        if "sent_images" in result:
            return f"任务 #{task.id} 完成：已发送图片。"
        return f"任务 #{task.id} 完成。"
