"""Compatibility helpers for NcatBot 5 / NapCat file transfers."""
from __future__ import annotations

from contextlib import contextmanager
import logging
import os
from pathlib import Path
import re
import shutil
from tempfile import TemporaryDirectory
from uuid import uuid4

log = logging.getLogger(__name__)


class UploadTimeoutProtocol:
    """Give final QQ transfers two minutes; retain other API timeouts."""

    def __init__(self, protocol):
        self.protocol = protocol

    async def call(self, action, params=None):
        if action in ("upload_group_file", "upload_private_file"):
            return await self.protocol.call(action, params, timeout=120.0)
        return await self.protocol.call(action, params)


def with_upload_timeout(file_api):
    """Build a local NapCat client without mutating the bot's shared protocol."""
    from ncatbot.adapter.napcat.api.bot_api import NapCatBotAPI
    from ncatbot.api.qq import QQAPIClient
    from ncatbot.api.qq.file import QQFile
    from ncatbot.api.qq.proxy import QQLoggingProxy

    if not isinstance(file_api, QQFile):
        return file_api
    raw_api = file_api._api
    if isinstance(raw_api, QQLoggingProxy):
        raw_api = raw_api._real
    if not isinstance(raw_api, NapCatBotAPI):
        return file_api
    # NcatBot's high-level upload API does not expose the protocol timeout.
    # Retain its preupload/error handling, overriding only the final transfer.
    return QQAPIClient(NapCatBotAPI(UploadTimeoutProtocol(raw_api._protocol))).file


@contextmanager
def upload_path(file_path: str):
    """Stage unsafe basenames without changing the displayed name or source.

    NcatBot forwards the stream upload's file:// URI unchanged. NapCat URL
    decodes that URI, so a literal % in the basename can fail or change paths.
    """
    source = Path(file_path)
    if re.fullmatch(r"[A-Za-z0-9_.-]+", source.name):
        yield file_path
        return
    suffix = source.suffix if re.fullmatch(r"\.[A-Za-z0-9]+", source.suffix) else ""
    with TemporaryDirectory(prefix="ncatbot_upload_") as directory:
        staged = Path(directory) / f"{uuid4().hex}{suffix}"
        try:
            os.link(source, staged)
        except OSError:
            shutil.copyfile(source, staged)
        yield str(staged)


async def get_group_folder(file_api, group_id: str, folder_name: str) -> str:
    # QQFile has no public raw-call entry point in NcatBot 5.5.6. Keep this
    # compatibility access here; other implementations use their own helper.
    raw_api = getattr(file_api, "_api", None)
    if raw_api is None or not callable(getattr(raw_api, "call", None)):
        return await file_api.get_or_create_group_folder(group_id, folder_name)
    try:
        response = await raw_api.call("get_group_root_files", {"group_id": int(group_id)})
        # Only folder IDs/names are needed. Avoid validating unrelated uploader
        # and creator fields, which NapCat returns as integers in some versions.
        for folder in (response.get("data") or {}).get("folders") or []:
            if folder.get("folder_name") == folder_name and folder.get("folder_id"):
                return str(folder["folder_id"])
    except Exception as exc:
        log.warning("获取群文件目录失败: %s", exc)
        return ""
    try:
        result = await file_api.create_group_file_folder(group_id, folder_name)
        return (result.groupItem.folderInfo.folderId
                if result.groupItem and result.groupItem.folderInfo else "") or ""
    except Exception as exc:
        log.warning("创建群文件夹失败: %s", exc)
        return ""
