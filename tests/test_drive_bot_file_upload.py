from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch
from urllib.parse import unquote

import tests.bootstrap  # noqa: F401
from ncatbot.api.qq import QQAPIClient
from ncatbot.adapter.napcat.api.bot_api import NapCatBotAPI
from ncatbot_assistant.drive_bot.intents import ScopeType, TaskRecord, TaskStatus, TaskType
from ncatbot_assistant.drive_bot.reply import ReplyAdapter
from ncatbot_assistant.drive_bot.file_transfer import upload_path


class UploadProtocol:
    """External boundary: retain real NcatBot parsing and stream uploads."""

    def __init__(self):
        self.filename = None
        self.uploads = []
        self.folders_created = []
        self.folders = [{'folder_id': 'existing', 'folder_name': '本子',
                         'creator': 1706895031}]

    async def call(self, action, params=None):
        if action == 'get_group_root_files':
            data = {'files': [{'uploader': 1706895031}],
                    'folders': self.folders}
        elif action == 'upload_file_stream':
            if params.get('is_complete'):
                data = {'status': 'file_complete',
                        'file_path': f'file:///remote/temp/{self.filename}'}
            else:
                self.filename = params['filename']
                data = {}
        elif action in ('upload_group_file', 'upload_private_file'):
            # NapCat decodes file URIs: bare % must fail, encoded %xx must
            # not silently change the real remote filename either.
            path = unquote(params['file'], errors='strict')
            if path != params['file'] or '%' in path:
                raise RuntimeError('识别URL失败')
            self.uploads.append((action, params))
            data = {}
        elif action == 'create_group_file_folder':
            self.folders_created.append(params)
            data = {'groupItem': {'folderInfo': {'folderId': 'created'}}}
        else:
            raise AssertionError(action)
        return {'status': 'ok', 'retcode': 0, 'data': data}


class FileUploadTest(IsolatedAsyncioTestCase):
    def task(self, scope):
        return TaskRecord(id=1, task_type=TaskType.JM_DOWNLOAD,
                          status=TaskStatus.RUNNING, scope_type=scope,
                          group_id='123', user_id='456', raw_message='',
                          payload={}, estimated_seconds=1)

    async def test_special_filename_uploads_in_group_and_private(self):
        for scope in (ScopeType.GROUP, ScopeType.PRIVATE):
            with self.subTest(scope=scope), TemporaryDirectory() as directory:
                source = Path(directory) / '1226813-[牛乳4.5% (作者)] 中文 # %20.pdf'
                source.write_bytes(b'%PDF-test')
                protocol = UploadProtocol()
                reply = ReplyAdapter(QQAPIClient(NapCatBotAPI(protocol)).file, lambda _: None)
                await reply.upload_files(self.task(scope), [
                    {'file_path': str(source), 'file_name': source.name}], '本子')
                self.assertEqual(protocol.uploads[0][1]['name'], source.name)
                self.assertEqual(source.read_bytes(), b'%PDF-test')

    async def test_existing_folder_is_used_with_integer_uploader_and_creator(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / '123.pdf'
            source.write_bytes(b'%PDF-test')
            protocol = UploadProtocol()
            reply = ReplyAdapter(QQAPIClient(NapCatBotAPI(protocol)).file, lambda _: None)
            await reply.upload_files(self.task(ScopeType.GROUP), [
                {'file_path': str(source), 'file_name': source.name}], '本子')
            self.assertEqual(protocol.uploads[0][1]['folder_id'], 'existing')
            self.assertEqual(protocol.folders_created, [])

    async def test_missing_folder_is_created(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / '123.pdf'
            source.write_bytes(b'%PDF-test')
            protocol = UploadProtocol()
            protocol.folders = []
            reply = ReplyAdapter(QQAPIClient(NapCatBotAPI(protocol)).file, lambda _: None)
            await reply.upload_files(self.task(ScopeType.GROUP), [
                {'file_path': str(source), 'file_name': source.name}], '本子')
            self.assertEqual(protocol.uploads[0][1]['folder_id'], 'created')
            self.assertEqual(protocol.folders_created, [{'group_id': 123, 'name': '本子'}])

    async def test_staging_cleans_up_after_failure_and_preserves_source(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / '中文4.5%.pdf'
            source.write_bytes(b'%PDF-test')
            with self.assertRaisesRegex(RuntimeError, 'upload failed'):
                with upload_path(str(source)) as staged:
                    self.assertEqual(Path(staged).read_bytes(), b'%PDF-test')
                    raise RuntimeError('upload failed')
            self.assertFalse(Path(staged).exists())
            self.assertEqual(source.read_bytes(), b'%PDF-test')

    async def test_staging_copies_when_hard_links_are_unavailable(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / '4.5%.pdf'
            source.write_bytes(b'%PDF-test')
            with patch('ncatbot_assistant.drive_bot.file_transfer.os.link',
                       side_effect=OSError('cross-device link')):
                with upload_path(str(source)) as staged:
                    self.assertEqual(Path(staged).read_bytes(), b'%PDF-test')
            self.assertFalse(Path(staged).exists())
            self.assertTrue(source.exists())
