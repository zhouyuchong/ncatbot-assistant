"""Validated tools with deterministic results and event-derived ownership."""
from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from .conversation_state import PendingAction, TaskConversationStateStore
from .estimator import format_duration
from .intents import QueuedTaskIntent, ScopeType, TaskRecord, TaskStatus, TaskType
from .llm_client import ToolCall
from .llm_context import ConversationKey
from .services.jm import JmSearchItem, format_search_results
from .storage import TaskStore


@dataclass
class ToolExecutionContext:
    key: ConversationKey
    state_store: TaskConversationStateStore
    task_store: TaskStore
    search: Callable[[str], Awaitable[list[JmSearchItem]]]
    enqueue: Callable[[QueuedTaskIntent], TaskRecord]
    logger: Any
    raw_message: str = ''


@dataclass(frozen=True)
class ToolResult:
    reply_text: str
    history_summary: str


def _result(text: str) -> ToolResult:
    return ToolResult(text, text[:500])


def tool_schemas() -> list[dict]:
    definitions = [
        ('jm_search', '用户明确要求搜索 JM 资源。缺少关键词时用空参数追问。讨论搜索功能不要调用。',
         {'keywords': {'type': 'string', 'maxLength': 200, 'description': '用户想搜索的关键词'}}),
        ('jm_download', '用户明确要求下载 JM 资源。album_id 和 result_index 二选一。序号由程序解析，不能猜测 ID。缺参数用空对象。',
         {'album_id': {'type': 'integer', 'minimum': 1, 'maximum': 9223372036854775807, 'description': '用户明确提供的资源 ID'},
          'result_index': {'type': 'integer', 'minimum': 1, 'maximum': 9223372036854775807, 'description': '当前搜索结果的序号，从 1 开始'}}),
        ('task_status', '查询当前用户当前会话的任务状态。未指定编号时查询最近的下载任务。',
         {'task_id': {'type': 'integer', 'minimum': 1, 'maximum': 9223372036854775807}}),
    ]
    return [{'type': 'function', 'function': {'name': name, 'description': description,
            'parameters': {'type': 'object', 'properties': properties, 'additionalProperties': False}}}
            for name, description, properties in definitions]


def _positive_integer(value: Any) -> bool:
    return type(value) is int and 0 < value <= 9223372036854775807


def build_enqueue_reply(task: TaskRecord, store: TaskStore) -> str:
    position = store.queue_position(task.id)
    wait = store.estimated_wait_seconds(task.id)
    notify = '完成后我会 @你。' if task.scope_type == ScopeType.GROUP else '完成后我会通知你。'
    return (f'已收到，任务 #{task.id} 已加入队列。\n当前排队位置：{position}\n'
            f'预计等待：{format_duration(wait)}，预计总耗时：{format_duration(wait + task.estimated_seconds)}。\n{notify}')


async def execute_tool(call: ToolCall, context: ToolExecutionContext) -> ToolResult:
    allowed = {'jm_search': {'keywords'}, 'jm_download': {'album_id', 'result_index'},
               'task_status': {'task_id'}}
    try:
        args = json.loads(call.arguments_json)
    except (TypeError, ValueError):
        return _result('工具参数无效，请重新描述请求或使用明确命令。')
    if call.name not in allowed or not isinstance(args, dict) or set(args) - allowed[call.name]:
        return _result('工具或参数无效，请使用 /help 查看支持的操作。')

    state = context.state_store.get(context.key)
    if call.name == 'jm_search':
        keywords = args.get('keywords', '')
        if not isinstance(keywords, str) or len(keywords) > 200:
            return _result('搜索关键词需要是 200 字符以内的文字。')
        state.search_results = []
        if not keywords.strip():
            state.pending_action = PendingAction('jm_search', 'keywords')
            context.state_store.update(context.key, state)
            return _result('你想搜索什么关键词？')
        state.pending_action = None
        context.state_store.update(context.key, state)
        try:
            items = (await context.search(keywords.strip()))[:10]
        except Exception:
            context.logger.warning('JM 搜索失败')
            return _result('JM 搜索暂时不可用，请稍后重试。')
        state.search_results = items
        context.state_store.update(context.key, state)
        return _result(format_search_results(items, keywords.strip()))

    if call.name == 'jm_download':
        if not args:
            state.pending_action = PendingAction('jm_download', 'album_id_or_result_index')
            context.state_store.update(context.key, state)
            return _result('请提供资源 ID，或告诉我要下载搜索结果中的第几个。')
        if len(args) != 1 or not _positive_integer(next(iter(args.values()))):
            return _result('请提供一个正整数 ID 或结果序号，两者只能选一个。')
        album_id = args.get('album_id')
        if 'result_index' in args:
            index = args['result_index']
            if not state.search_results:
                return _result('当前没有有效搜索结果，请重新搜索或提供资源 ID。')
            if index > len(state.search_results):
                return _result(f'请从 1～{len(state.search_results)} 中选择有效序号。')
            album_id = state.search_results[index - 1].album_id
        intent = QueuedTaskIntent(TaskType.JM_DOWNLOAD, context.key.scope_type, context.key.user_id,
                                  context.raw_message, {'album_id': album_id}, context.key.group_id)
        task = context.enqueue(intent)
        state.pending_action = None
        state.last_download_task_id = task.id
        context.state_store.update(context.key, state)
        return _result(build_enqueue_reply(task, context.task_store))

    state.pending_action = None
    context.state_store.update(context.key, state)
    task_id = args.get('task_id', state.last_download_task_id)
    if task_id is None:
        return _result('当前没有最近的下载任务，请提供任务编号，例如 /task 42。')
    if not _positive_integer(task_id):
        return _result('任务编号必须是正整数。')
    task = context.task_store.get_for_conversation(task_id, context.key)
    if task is None:
        return _result('未找到当前会话中属于你的这个任务，请检查任务编号。')
    labels = {TaskStatus.QUEUED: '排队中', TaskStatus.RUNNING: '运行中',
              TaskStatus.SUCCEEDED: '成功', TaskStatus.FAILED: '失败', TaskStatus.CANCELLED: '已取消'}
    text = f'任务 #{task.id}：{labels[task.status]}。'
    if task.status == TaskStatus.QUEUED:
        text += (f'\n排队位置：{context.task_store.queue_position(task.id)}，'
                 f'预计等待：{format_duration(context.task_store.estimated_wait_seconds(task.id))}。')
    if task.status == TaskStatus.FAILED:
        # Raw upstream exceptions can contain credentials or server internals.
        text += '\n执行失败，可稍后重新提交。'
    return _result(text)
