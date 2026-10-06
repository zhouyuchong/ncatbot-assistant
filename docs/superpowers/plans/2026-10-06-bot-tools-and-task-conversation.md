# 指令工具化与连续对话办事 Implementation Plan

> **For agentic workers:** 使用 superpowers:executing-plans 在当前会话逐项执行；仅在用户另行选择委派时使用 superpowers:subagent-driven-development。步骤使用复选框跟踪。

**Goal:** 在新分支上实现“自然语言搜索 → 选择搜索结果 → 下载 → 查询任务状态”的完整对话流程，保留现有命令入口并控制 LLM 消耗。

**Architecture:** 明确命令继续走确定性路由；普通消息使用一次带工具定义的 LLM 请求，返回聊天文本或一个工具调用。程序校验工具参数、执行搜索或复用现有任务队列，并保存按会话隔离的结构化办事状态；工具结果由程序直接回复。

**Tech Stack:** Python 3.12+、现有 NcatBot、LiteLLM、SQLite、asyncio、unittest。

**Spec:** 本文件“设计基线”是本轮讨论的设计基线，计划与设计合并保存。用户已于 2026-10-06 确认按本计划实现；下方保留设计基线，并在文末记录实际验证。

**Branch:** `codex/smarter-bot-interaction`，从 `main` 的 `b541edf` 创建。

## Global Constraints

- Python 3.12+，复用已有依赖，不引入 Agent 框架或向量数据库。
- 首期仅工具化 JM 搜索、下载和任务状态查询；新闻、论文、图片等原有命令继续可用。
- 群聊仍需 @ bot 才处理消息，私聊直接处理；不监听群聊以触发自主发言，不实现免重复 @。
- 每条自然语言请求最多调用一次 LLM；明确命令调用零次 LLM；工具结果不再交给 LLM 润色。
- 会话按私聊 user_id、群聊 group_id + user_id 隔离；任务查询必须同时匹配会话和所有者。
- 重任务继续复用现有 SQLite 单 worker 队列，不允许模型直接下载或上传。
- 不自动重试 LLM 请求，不执行一条响应中的多个工具调用，不递归执行工具。
- 验证使用 mock 搜索、mock LLM、临时 SQLite，不调用真实付费 API、不下载真实资源。

## Review Focus

1. 模型同时返回文字和工具调用时，只展示程序执行后的真实结果，不展示“已经下载成功”等未经验证的文字。
2. 一条模型响应包含多个工具调用时，整条拒绝执行，提示用户一次提出一个操作。
3. 新搜索失败或无结果后，“第二个”不能继续指向旧搜索结果。
4. 同一会话同时收到两条消息时，历史、结果序号和任务引用保持一致；不同会话可以独立处理。
5. 进程重启后临时会话状态丢失，不猜测“第二个”或“刚才那个”；明确任务编号仍可查询 SQLite 中的真实状态。

## 设计基线

### 1. 当前代码与改动动机

- `router.py` 匹配命令及整句别名，未命中的消息返回 `LlmFallbackIntent`。
- `ncatbot_plugin.py` 分别处理即时回复、入队和 `_ask_ai()`，目前 AI 只生成文本，无法调用插件能力。
- `services/jm.py` 搜索直接返回字符串，无法可靠地保存结果序号；同步搜索目前在消息路由中执行。
- `llm_context.py` 仅保存最近普通聊天；命令结果、任务编号、待补充参数没有进入办事状态。
- `storage.py` 已保存任务类型、所有者、会话、状态和结果，可作为查询的事实来源。
- `jobs/queue.py` 已负责真实执行和更新任务状态，沿用这一边界。

### 2. 用户可见行为

```text
用户：@bot 搜索「关键词」的本子
bot：1. [123456] 标题 A
     2. [234567] 标题 B
     可以用 /jm ID 下载，或告诉我“下载第二个”。
用户：@bot 下载第二个
bot：任务 #42 已加入队列，显示排队位置与预估耗时。
用户：@bot 刚才那个下载好了吗？
bot：读取任务 #42 的当前状态并回复。
```

- “帮我找本子”缺少关键词时，追问关键词；下一条处理中的消息补全它。
- “下载第二个”缺少有效搜索结果或序号越界时，提示重新搜索或选择有效序号，不创建任务。
- “我上次下载很慢”“这个搜索功能不错”属于讨论，不应创建任务。
- “完成了吗”仅在存在明确最近下载任务时查询；否则请用户给任务编号。
- 用户明确转向聊天或其他命令时，撤销待补充参数，不把新话题当关键词。
- 搜索结果增加序号，保留原 album ID；现有 `/jm ID` 下载方式兼容。
- 新增 `/task <任务编号>` 查询入口；`/task` 查询当前会话最近一次下载任务。

### 3. 工具边界

| 工具 | 参数 | 程序行为 |
| --- | --- | --- |
| `jm_search` | `keywords: string` | 清除旧结果；异步在线程中搜索；保存最多 10 条结果并编号 |
| `jm_download` | `album_id: integer` 或 `result_index: integer`，必须二选一 | 检查正整数；序号从当前结果取真实 ID；生成下载意图并入队 |
| `task_status` | 可选 `task_id: integer` | 指定编号或当前最近下载任务；校验归属后查询数据库 |

搜索关键词不能为空且最多 200 字符；未知工具、未知参数、无效 JSON、布尔值冒充整数、非正整数都拒绝执行。ID 限制为 SQLite 可表示的正整数（最大 9223372036854775807）；超长数字命令在整数转换前拒绝。所有用户/群标识从事件获取，不接受模型传入的身份参数。模型给出的 album ID 可用于明确 ID 下载，但 result_index 必须通过程序解析，不允许模型生成序号到 ID 的映射。

缺少参数时，执行器返回固定追问并设置 `PendingAction`；追问不触发第二次 LLM。后续自然语言依然走单次 LLM，模型结合待办摘要决定补全、聊天或转向新操作。不得把下一条消息无条件解释为待办参数。

### 4. 会话状态与成本

- `TaskConversationState` 保存 `search_results`、`pending_action`、`last_download_task_id`、`updated_at`。
- 临时状态只在内存中保存，有效期默认 15 分钟；超时和重启后清空，通过可注入时钟测试。
- 最大保存 1000 个会话，超过后淘汰最久未更新的状态；会话锁空闲后释放，避免锁表无限增长。
- 搜索结果最多 10 条；模型只接收序号、ID、截断到 80 字符的标题。结构化原始标题供程序展示，不从自然语言聊天文本反解析。
- 办事状态注入摘要最多 1500 字符；单条工具结果写入聊天历史的摘要最多 500 字符，沿用现有 max_turns。
- 保存用户请求、程序的结果摘要或追问，使“上次做过什么”进入连续上下文；工具的完整响应不重复注入。
- 状态查询结果每次从 SQLite 获取，不缓存为“实时进度”；现有队列不支持百分比，仅展示排队、运行、成功、失败、取消及可用的排队估计。
- 默认 `llm.tools.enabled: true`，可关闭以回退到原有普通聊天；关闭后命令和 `/task` 仍可用。
- 默认 `llm.tools.timeout_seconds: 30`；沿用现有 model/base_url/api_key/temperature/short_conversation_max_tokens。
- 记录调用次数和服务端返回的 token usage（可用时）；日志不输出凭据、完整提示词或完整聊天记录。不承诺与原聊天 token 完全相同，工具 schema 会增加输入成本。

### 5. 调用流程及可靠性

1. 消息进入已有群聊/私聊入口；同一 `ConversationKey` 下串行处理，锁覆盖回复发送，防止展示列表与结果状态乱序。
2. 明确命令走路由：JM 搜索也返回意图，由异步执行器执行；其他旧命令维持原行为。
3. 普通消息构造既有聊天历史、角色设定及精简办事摘要；通过 LiteLLM 的异步 completion 获取文本和工具调用，禁用自动重试。
4. 模型可返回聊天文本或一个工具调用；聊天文本继续沿用现有角色风格。空响应和错误返回简洁失败提示。
5. 工具注册表校验参数；搜索、查询直接执行；下载通过现有 `_enqueue_task()`，立即保存真实任务 ID。
6. 工具调用后的回复只使用执行结果。将真实结果摘要记录到历史，不向模型发送工具结果进行下一轮调用。
7. 下一条用户请求以新的普通请求处理；历史内只保存文本摘要，不保存未闭合的 tool_calls 协议消息。

对同一个收到的 QQ 消息，以会话 + message_id 去重，默认保留 15 分钟、最多 2000 条；重复投递不重复创建任务。用户后来用新的消息再次提出下载请求属于新操作，不用 album ID 全局去重。

模型接口不支持 tools、超时或参数错误时，本次请求不再降级调用另一个模型；提示使用明确命令。消息重试不能绕过本地去重。搜索失败清空结果，返回服务不可用提示。

已知运行限制：当前完成通知依赖进程内 `_events_by_task_id`，重启后旧排队任务通知可能无法送达。首期不重构通知恢复；查询仍以 SQLite 状态为准，成功状态代表 handler 返回成功，不声称已经成功发送完成通知。

## 文件职责与接口

新建文件：

- `conversation_state.py`：结构化临时会话状态、过期、容量、锁与消息去重。
- `tools.py`：工具 schema、参数校验、工具执行与确定性回复，不负责 LLM 网络请求。
- `llm_client.py`：调用现有 LiteLLM 依赖，解析完整响应为文本或工具调用。
- `conversation.py`：协调命令、自然语言、状态、工具执行与历史写入；插件只提供事件和已有服务回调。

修改文件：

- `intents.py`、`router.py`、`commands.py`：结构化 JM 搜索意图、任务查询意图及 `/task` 定义。
- `services/jm.py`：新增结构化搜索接口，保留字符串搜索包装函数兼容旧调用。
- `storage.py`：新增带所有者和会话过滤的任务查询。
- `ncatbot_plugin.py`：接入协调器；保留后台 worker、每日记忆总结和既有其他业务。
- `config.py`、`config.example.yaml`、`usage.py`、两个 README：配置与使用说明。

核心接口（放在各自负责的模块中）：

```python
# services/jm.py
@dataclass(frozen=True)
class JmSearchItem:
    album_id: int
    title: str
def search_items(tags: list[str], logger, limit: int = 10) -> list[JmSearchItem]: ...

# intents.py
@dataclass(frozen=True)
class JmSearchIntent:
    keywords: str
@dataclass(frozen=True)
class TaskStatusIntent:
    task_id: int | None = None

# conversation_state.py（TaskConversationState/PendingAction 同模块定义）
class TaskConversationStateStore:
    def get(self, key: ConversationKey) -> TaskConversationState: ...
    def update(self, key: ConversationKey, state: TaskConversationState) -> None: ...
    def clear(self, key: ConversationKey) -> None: ...

# storage.py，None 包含不存在和不属于该会话两种情况
def get_for_conversation(self, task_id: int, key: ConversationKey) -> TaskRecord | None: ...

# llm_client.py
@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments_json: str
@dataclass(frozen=True)
class LlmDecision:
    text: str
    tool_calls: tuple[ToolCall, ...]
async def complete_once(messages: list[dict[str, str]], config: dict,
                        tools: list[dict]) -> LlmDecision: ...

# tools.py：ToolExecutionContext 包含 key、state_store、task_store、
# async search 回调、enqueue 回调以及 logger；身份不取自 arguments。
@dataclass(frozen=True)
class ToolResult:
    reply_text: str
    history_summary: str
def tool_schemas() -> list[dict]: ...
async def execute_tool(call: ToolCall, context: ToolExecutionContext) -> ToolResult: ...

# conversation.py
async def handle_conversation_message(text: str, key: ConversationKey,
                                      message_id: str, runtime: ConversationRuntime) -> str | None: ...
# None 表示重复投递无需回复；runtime 提供上述依赖、路由及现有历史存储。
```

## Task 1：结构化搜索与命令直达

**Files:** 修改 `services/jm.py`、`intents.py`、`router.py`、`ncatbot_plugin.py`；新增 `tests/test_drive_bot_jm_search.py`，修改 `tests/test_drive_bot_router.py`。

**Interfaces:** 产出 `JmSearchItem`、`search_items()`、`JmSearchIntent`；`route_message()` 不再调用同步搜索回调，插件在线程中执行搜索意图。

- [x] 写失败测试：`test_search_items_preserves_ids_and_order` 验证结果 ID 与顺序；`test_search_limits_to_ten` 验证 10 条上限；`test_jm_keywords_returns_search_intent` 验证路由无网络副作用；保留数字 ID 入队测试。
- [x] 执行 `uv run python -m unittest tests.test_drive_bot_jm_search tests.test_drive_bot_router`，确认新增断言失败。
- [x] 实现结构化搜索、序号展示和字符串包装兼容；用 `asyncio.to_thread` 执行同步 JM 客户端搜索。
- [x] 重跑上述测试及 `tests.test_drive_bot_handlers`，确认通过。
- [x] 提交本任务：`feat: return structured JM search results`。

## Task 2：会话状态及受限任务查询

**Files:** 新建 `conversation_state.py`、`tests/test_drive_bot_conversation_state.py`；修改 `storage.py`、`tests/test_drive_bot_storage.py`。

**Interfaces:** 产出 `TaskConversationState`、`PendingAction`、`TaskConversationStateStore` 和 `TaskStore.get_for_conversation()`；复用 `ConversationKey`。

- [x] 写失败测试：不同用户/群/私聊隔离；15 分钟边界过期；1000 会话容量淘汰；返回状态副本不意外污染存储；去重 15 分钟及 2000 条容量；跨用户/跨群查询返回 None；重启模拟后临时结果不存在但指定任务编号仍可查询。
- [x] 执行 `uv run python -m unittest tests.test_drive_bot_conversation_state tests.test_drive_bot_storage`，确认新增断言失败。
- [x] 实现状态存储、可注入时钟、同会话异步锁及消息去重；查询 SQL 同时限定 scope_type、group_id、user_id。
- [x] 重跑上述测试，确认通过。
- [x] 提交本任务：`feat: track task conversations and scoped task lookup`。

## Task 3：确定性工具执行与任务查询命令

**Files:** 新建 `tools.py`、`tests/test_drive_bot_tools.py`；修改 `intents.py`、`commands.py`、`router.py`、`tests/test_drive_bot_router.py`。

**Interfaces:** 产出三项工具的 `tool_schemas()`、`ToolExecutionContext`、`ToolResult`、`execute_tool()` 和 `TaskStatusIntent`；使用 Task 1 搜索数据、Task 2 状态和查询接口，入队委托现有回调。

- [x] 写失败测试：序号 2 精确映射第二条 ID；无结果/越界不入队；缺关键词设置待办；ID 与序号同时出现拒绝；未知工具/参数、坏 JSON、bool/负数拒绝；新搜索失败或为空清空旧结果；查询每次读取最新状态，不能看到他人任务。
- [x] 增加 `/task`、`/task 42`、非法任务编号的路由测试；无最近任务时提示提供编号。
- [x] 执行 `uv run python -m unittest tests.test_drive_bot_tools tests.test_drive_bot_router`，确认新增断言失败。
- [x] 实现参数验证、固定追问、序号解析、入队回复及所有 TaskStatus 的确定性展示；没有百分比数据时不编造进度。
- [x] 重跑上述测试，确认通过。
- [x] 提交本任务：`feat: execute validated tools and query task status`。

## Task 4：单次 LLM 决策接口与成本配置

**Files:** 新建 `llm_client.py`、`tests/test_drive_bot_llm_client.py`；修改 `config.py`、`tests/test_drive_bot_config.py`、`config.example.yaml`。

**Interfaces:** 产出 `ToolCall`、`LlmDecision`、`complete_once()`；沿用项目 LLM 配置合并，增加 enabled 与 timeout_seconds。

- [x] 写失败测试：正常文本、单工具、多工具、坏参数 JSON、空响应；mock `litellm.acompletion` 断言每次只调用一次，tools 正确透传、自动重试关闭、超时 30 秒；错误没有第二次降级调用；usage 缺失不影响返回。
- [x] 配置测试验证默认值、关闭工具及非正超时回退默认值；请求参数沿用当前模型和 short token 上限。
- [x] 执行 `uv run python -m unittest tests.test_drive_bot_llm_client tests.test_drive_bot_config`，确认新增断言失败。
- [x] 实现异步 completion 调用及响应解析，保留完整工具参数交由执行器校验；本地检查实际 LiteLLM 接口，若需查文档使用官方文档，不发付费探测请求。
- [x] 重跑上述测试，确认通过。
- [x] 提交本任务：`feat: add single-call LLM tool decisions`。

## Task 5：接通连续办事流程

**Files:** 新建 `conversation.py`、`tests/test_drive_bot_conversation.py`；修改 `ncatbot_plugin.py`、`llm_context.py`（只补必要的摘要记录接口）、`tests/test_drive_bot_llm_context.py`。

**Interfaces:** 产出 `ConversationRuntime`、`handle_conversation_message()`；消费前四项接口及现有入队/历史能力。插件将 QQ message_id 和 ConversationKey 传入协调器。

- [x] 写失败测试：命令搜索后自然语言选择下载；自然语言搜索→下载第二个→查询状态；缺关键词追问→补全；用户转话题撤销待办；只讨论功能时 mock 模型返回聊天，不执行工具。
- [x] 写成本和可靠性测试：明确命令零 LLM 调用、自然语言一次调用、工具结果无第二次调用；摘要不超过 1500/500 字符；多工具整条拒绝；文字加工具时忽略未验证文字；重复 message_id 只入队一次；同会话并发顺序一致、不同会话不互相阻塞。
- [x] 写重启/过期测试：选择结果失效后不下载；指定任务编号仍查询真实状态；LLM 失败保留可恢复的待办且不执行工具。
- [x] 执行 `uv run python -m unittest tests.test_drive_bot_conversation tests.test_drive_bot_llm_context`，确认新增断言失败。
- [x] 实现协调流程；统一命令和工具的结果状态记录，下载成功入队后保存真实 ID，记录精简历史；工具关闭时沿用原聊天路径。其他命令清除待办但仍正常执行。
- [x] 重跑上述测试，并运行 `uv run python -m unittest discover tests`，确认通过。
- [x] 提交本任务：`feat: connect tools to multi-turn task conversations`。

## Task 6：使用说明与完整验收

**Files:** 修改 `readme.md`、`plugins/drive_bot/README.md`、`usage.py`；检查 `config.example.yaml`。

- [x] 文档说明自然语言流程、序号选择、`/task`、15 分钟临时状态、重启行为、成本上限、工具开关以及首期支持范围。
- [x] 在 mock 集成测试中走完整流程：搜索两条结果→选择第二条→入队→worker 更新成功→查询返回成功；失败任务返回真实失败状态。
- [x] 运行 `uv run python -m unittest discover tests`，要求所有测试通过。
- [x] 运行 `git diff --check`，要求无空白错误；检查 diff 不含配置凭据和真实聊天数据。
- [x] 将验证结果补充到本计划；提交本任务：`docs: explain tool-based task conversations`。

## 验收与后续范围

首期完成标准：用户可以用自然语言完成搜索和下载，使用“第二个”准确选择上次展示的结果，再查询真实任务状态；命令兼容、会话隔离、错误不误执行、调用次数符合预算。

本地自动测试能验证程序边界和调用预算；mock 无法证明真实模型的意图识别质量。用户安排真实试用后，再观察“明确请求”“只讨论功能”“含糊指代”“转话题”等样本；不在本计划阶段调用付费接口。

后续独立评估：新闻/论文/图片工具扩展、免重复 @、分页搜索、取消任务、任务通知重启恢复。主动参与群聊暂不纳入路线。

## 计划自检与执行记录

- [x] 首期范围与本轮讨论一致，群聊自主参与已排除。
- [x] 每个设计要求已映射到任务和对应验证。
- [x] 接口名称与任务依赖一致；Review Focus 五项均有测试归属。
- [x] 初始计划只新增文档；用户确认后六项业务实现任务均已完成。
- [x] 用户评审计划。
- [x] 开始实施并记录验证结果。

### 实施验证（2026-10-06）

- 六项任务已完成，实现落在 `codex/smarter-bot-interaction`。
- `uv` 受沙箱缓存权限及 macOS 系统配置崩溃影响，改用已有 `.venv/bin/python`，未安装依赖。
- `.venv/bin/python -m unittest discover tests`：102 个测试通过（独立审查前）。
- `git diff --check`：通过。
- 数据类型 `ToolCall` / `LlmDecision` 提前在 Task 3 定义，以满足工具执行接口；网络实现仍在 Task 4。
- 搜索、LLM 与 worker 外部执行均使用 mock；任务状态与归属查询使用真实临时 SQLite。未调用真实付费 API 或进行真实下载。
- 临时状态、过期、参数补全、序号下载、实时查询、失败任务、去重、并发隔离和调用次数均有自动化验证。
- 独立审查完成，审查者复跑初始 102 个测试；发现的问题均已补回归测试并修复。
- 修复了发送回复不在会话锁内导致的列表乱序、超大编号异常、状态查询残留旧待办、裸 `/jm` 调用 LLM、原始消息日志和 JSON 摘要截断问题。
- 修复后 `.venv/bin/python -m unittest discover tests`：108 个测试通过；`compileall` 与 `git diff --check` 通过。

### 实施裁定与验证边界

1. 遵循用户指定，在已创建的新分支和当前工作目录开发，不额外创建 worktree；工作目录中没有其他未提交业务修改。
2. 使用已有虚拟环境运行测试；`uv` 的环境故障不影响 Python 测试，但本次没有重新验证 `uv run` 启动。
3. `ToolCall` / `LlmDecision` 数据类型提前到 Task 3 定义；只改变实现顺序，没有改变接口。
4. 按费用约束，未进行真实模型、真实资源下载或付费 token 计费验证。mock 验证调用预算，真实意图识别质量与模型端 tools 支持需要部署后试用。
5. 重启后旧任务完成通知恢复继续按原设计延期；明确编号可查询数据库，旧任务的完成通知仍可能无法送达。
6. 既有短期聊天和任务事件映射的长期保留策略不在本期改动范围；长时间运行的内存增长风险仍需后续独立处理。新增办事状态和去重缓存已限制容量。

最终审查未留下需要延期的本次新增问题。


### 后续扩展：每日新闻与动漫新闻（2026-10-06）

用户在试用后要求接入两种新闻工具。新增无参数 `daily_news` → `TaskType.DAILY` 和 `anime_news` → `TaskType.ANIME_NEWS`，复用既有新闻服务、入队回调和完成通知。两个工具拒绝未知参数，不开放时间/主题筛选。

新增 `last_task_id` 保存最近入队任务，保留 `last_download_task_id` 解析明确的旧下载引用；`/task` 和默认状态工具改为查询最近提交任务。新闻命令和自然语言工具共用执行入口，其他已存在的队列命令也更新最近任务引用。调用预算仍为一次决策；每日新闻摘要的原有 LLM 请求独立计费，动漫新闻读取配置文件。

日志明确区分 `llm_requests=1`、模型返回的 `tool_calls` 数和实际新闻入队日志。接入中修复动漫新闻 handler 捕获异常后返回成功的问题，错误交由 worker 标记为失败。

验证：115 个 unittest 测试通过，覆盖两类自然语言请求的 schema 注册、真实临时 SQLite 入队、handler 输出、状态查询、命令零决策调用、未知参数拒绝、重复消息去重、多工具不执行、动漫新闻失败及日志计数。LLM 和外部新闻数据使用 mock，没有调用真实付费接口。

新闻工具扩展已完成独立只读代码审查，未发现新的需修复问题；语法检查与 diff 空白检查通过。
