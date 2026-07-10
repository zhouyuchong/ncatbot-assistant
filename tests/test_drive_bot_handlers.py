from unittest import IsolatedAsyncioTestCase, main

import tests.bootstrap  # noqa: F401
from ncatbot_assistant.drive_bot.intents import ScopeType, TaskRecord, TaskStatus, TaskType
from ncatbot_assistant.drive_bot.jobs.handlers import TaskHandlers
from ncatbot_assistant.drive_bot.reply import ReplyAdapter


class FakeEvent:
    def __init__(self):
        self.replies = []

    async def reply(self, text=None, image=None):
        self.replies.append({"text": text, "image": image})


class FakeFileApi:
    def __init__(self):
        self.group_uploads = []
        self.private_uploads = []

    async def get_or_create_group_folder(self, group_id, folder_name):
        return f"folder:{group_id}:{folder_name}"

    async def upload_group_file(self, group_id, file, name, folder_id):
        self.group_uploads.append((group_id, file, name, folder_id))

    async def upload_private_file(self, user_id, file, name):
        self.private_uploads.append((user_id, file, name))


class DriveBotHandlersTest(IsolatedAsyncioTestCase):
    async def test_jm_handler_uploads_group_files_and_returns_count(self):
        event = FakeEvent()
        file_api = FakeFileApi()
        reply = ReplyAdapter(file_api=file_api, event_lookup=lambda _task: event)
        handlers = TaskHandlers(
            reply=reply,
            jm_download=lambda album_id, _logger: [
                {"file_name": f"{album_id}.pdf", "file_path": "/tmp/123.pdf"}
            ],
            delete_file=lambda _path, _logger: None,
        )
        task = TaskRecord(
            id=1,
            task_type=TaskType.JM_DOWNLOAD,
            status=TaskStatus.RUNNING,
            scope_type=ScopeType.GROUP,
            group_id="g1",
            user_id="u1",
            raw_message="/jm 123",
            payload={"album_id": 123},
            estimated_seconds=480,
        )

        result = await handlers.handle(task)

        self.assertEqual(result["uploaded_files"], 1)
        self.assertEqual(file_api.group_uploads[0][0], "g1")
        self.assertEqual(file_api.group_uploads[0][2], "123.pdf")

    async def test_setu_handler_uploads_private_file(self):
        event = FakeEvent()
        file_api = FakeFileApi()
        reply = ReplyAdapter(file_api=file_api, event_lookup=lambda _task: event)

        async def get_url(tags, _logger):
            self.assertEqual(tags, [["cat"]])
            return True, "https://example.com/cat.jpg"

        async def download_image(_url, save_path, _logger):
            self.assertTrue(save_path.endswith(".png"))
            return True

        handlers = TaskHandlers(
            reply=reply,
            setu_get_url=get_url,
            setu_download_image=download_image,
            image_dir="/tmp",
            delete_file=lambda _path, _logger: None,
        )
        task = TaskRecord(
            id=2,
            task_type=TaskType.SETU,
            status=TaskStatus.RUNNING,
            scope_type=ScopeType.PRIVATE,
            user_id="u2",
            raw_message="/setu cat",
            payload={"tags": ["cat"]},
            estimated_seconds=45,
        )

        result = await handlers.handle(task)

        self.assertEqual(result["uploaded_files"], 1)
        self.assertEqual(file_api.private_uploads[0][0], "u2")

    async def test_daily_handler_replies_with_direct_text(self):
        event = FakeEvent()
        reply = ReplyAdapter(file_api=FakeFileApi(), event_lookup=lambda _task: event)

        async def daily():
            return "今日新闻摘要"

        handlers = TaskHandlers(reply=reply, daily_function=daily)
        task = TaskRecord(
            id=3,
            task_type=TaskType.DAILY,
            status=TaskStatus.RUNNING,
            scope_type=ScopeType.PRIVATE,
            user_id="u3",
            raw_message="每日新闻",
            payload={},
            estimated_seconds=30,
        )

        result = await handlers.handle(task)

        self.assertEqual(result, {"sent_text": 1, "text": "今日新闻摘要"})
        self.assertEqual(event.replies[0], {"text": "今日新闻摘要", "image": None})

    async def test_group_task_done_reply_does_not_include_manual_cq_at(self):
        event = FakeEvent()
        reply = ReplyAdapter(file_api=FakeFileApi(), event_lookup=lambda _task: event)
        task = TaskRecord(
            id=1,
            task_type=TaskType.JM_DOWNLOAD,
            status=TaskStatus.SUCCEEDED,
            scope_type=ScopeType.GROUP,
            group_id="g1",
            user_id="1620404337",
            raw_message="/jm 123",
            payload={"album_id": 123},
            result={"uploaded_files": 1},
            estimated_seconds=480,
        )

        await reply.notify_task_done(task)

        self.assertEqual(
            event.replies[0],
            {"text": "任务 #1 完成：已上传 1 个文件。", "image": None},
        )
        self.assertNotIn("[CQ:at", event.replies[0]["text"])


if __name__ == "__main__":
    main()
