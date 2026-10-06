# Drive Bot 使用方法

Drive Bot 支持在 QQ 群聊和私聊中处理资源搜索、文件上传和每日新闻。

当消息没有命中下方已有命令或整句别名时，Bot 会使用 OpenAI-compatible Chat Completion 做兜底回复。推荐复制 `config.example.yaml` 为 `config.yaml` 并填写顶层 `llm` 配置：

```yaml
llm:
  api_key: "fake-api-key"
  base_url: "https://api.deepseek.com"
  model: "deepseek-v4-flash"
  temperature: 0.7
  max_tokens: 800
  short_conversation_max_tokens: 800
  long_conversation_max_tokens: 4000
  tools:
    enabled: true
    timeout_seconds: 30
  context:
    enabled: true
    max_turns: 6
```

`fake-api-key` 仅用于离线测试；实际使用时请改为可用的 API Key。

AI 兜底会自动加载 `resources/skills/neko_prompt_r18.md`，把其中的角色 prompt 注入 system message。这个 prompt 影响普通聊天的回复风格，不安装依赖，也不写入长期记忆。

## LLM 短期上下文

LLM 兜底回复支持短期会话上下文。Bot 会为普通聊天保存最近 N 轮 user/assistant 对话，并在下一次 LLM 请求时按 `system prompt + 最近历史 + 当前问题` 发送。

上下文隔离规则：

- 私聊：按 `user_id` 隔离。
- 群聊：按 `group_id + user_id` 隔离，避免群里不同用户的聊天互相串上下文。

上下文只保存在内存中，重启后会清空。普通聊天，以及搜索、下载入队、任务查询等办事请求及其简短结果会进入上下文。工具结果摘要最多 500 字符；帮助、画像展示及后台完成通知不会写入短期上下文。程序另外保存结构化办事状态，避免从聊天文本猜测资源 ID。

配置项：

- `llm.context.enabled`：是否启用短期上下文，默认 `true`。
- `llm.context.max_turns`：每个会话最多保留多少轮 user/assistant 对话，默认 `6`。

## 自然语言工具与连续办事

目前工具支持 JM 搜索、下载和任务状态查询。示例（群聊每条都需要 @ Bot）：

```text
你：搜索原神的本子
Bot：1. [123456]: 标题 A
     2. [234567]: 标题 B
你：下载第二个
Bot：任务 #42 已加入队列……
你：刚才那个下载好了吗？
Bot：任务 #42：运行中。
```

参数不完整时会追问，例如“帮我搜索本子”会询问关键词。你可以补充关键词，也可以转向聊天或使用其他命令。没有有效结果时，“第二个”不会触发下载；序号必须在当前展示范围内。讨论功能本身无需执行工具。

临时办事状态按私聊用户、群聊内 `group_id + user_id` 隔离，包含最近搜索结果、待补充参数和最近下载任务编号。默认 15 分钟未更新后失效，重启后清空；最多保留 1000 个会话。模型只接收最多 1500 字符的办事摘要，完整数据由程序保存。

配置：

- `llm.tools.enabled`：默认 `true`，需要配置的模型接口支持 OpenAI-compatible tools；设置为 `false` 可恢复原有聊天方式，明确命令继续可用。
- `llm.tools.timeout_seconds`：工具决策请求超时，默认 30 秒。
- 工具决策复用 `llm.model`、`base_url`、`api_key`、`temperature` 和 `short_conversation_max_tokens`。

启用工具后，明确命令调用零次 LLM，普通消息最多一次请求。每次最多执行一个工具，搜索和任务结果直接由程序生成回复，不再交给模型润色。不会自动重试或在接口失败后追加一次降级模型调用；接口不支持工具或超时时，使用 `/jm`、`/task` 等命令即可。schema 会增加输入 token，日志提供调用次数与可用的 token usage，不输出完整对话和 API Key。

重复投递的相同 QQ 消息在 15 分钟内去重（最多 2000 条）。再次主动发送新的下载消息仍是新任务。

## 查询任务状态

```text
/task
/task 42
```

省略编号时查询当前会话最近的下载任务；指定编号可以查询当前会话中自己的持久化任务。状态包括排队、运行、成功、失败、取消；排队状态附位置和预计等待，不提供虚构的百分比进度。

临时上下文过期或 Bot 重启后，仍可用明确编号查询数据库。任务成功表示执行 handler 成功，完成通知是否发送是独立结果。当前版本仍依赖内存事件发送完成通知，重启前创建的排队任务可能无法发送通知；通知恢复不在本期改动范围。

新闻、AI 看点、热门论文、图片等暂未工具化，继续使用下方命令。Bot 不会主动参与群聊，也不自动处理未 @ 的续聊消息。

## 后台任务队列

下载、上传、图片处理这类耗时操作会进入后台队列。Bot 会先回复任务编号、排队位置和预估耗时，然后继续响应其他消息。任务完成或失败后，群聊中会在原会话 @ 触发者；私聊中会直接回复触发者。

第一版使用全局单 worker，适合 2 核 4G VPS：同一时间只处理一个重任务，后续任务按进入顺序排队。任务状态保存在 SQLite 中，默认路径为：

```yaml
storage:
  sqlite_path: "data/drive_bot.sqlite3"

tasks:
  estimates:
    jm_download: 480
    setu: 45
    daily: 30
    daily_ai: 60
  daily_news:
    provider: "qq-news"
    api_key: "" # 仅 currents 需要
    language: "en"
    max_items: 10
  daily_ai:
    base_path: "/path/to/your/markdown/folder"
```

启动时会自动创建运行目录。默认结构：

```text
data/
  cache/              # JM 下载缓存
  image/              # setu 图片临时目录
  pdf/                # JM 生成 PDF 临时目录
  drive_bot.sqlite3   # 后台任务队列状态库
```

## 依赖

JM 下载并生成 PDF、图片下载、AI 兜底需要安装：

```text
jmcomic
img2pdf
Pillow
requests
aiohttp
litellm
PyYAML
```

插件的 `manifest.toml` 已声明这些依赖。若手动运行本项目，请同步安装 `requirements.txt` 中的依赖，并使用 `PYTHONPATH=src python -m ncatbot_assistant`。

## 查看使用方法

发送：

```text
使用方法
```

也支持：

```text
使用方法。
帮助
help
/help
```

Bot 会返回本插件的命令说明文本。正式入口统一使用 `/命令`；中文短语只作为整句别名兼容，避免普通聊天里提到关键词时误触发任务。

群聊中需要 @ Bot 才会处理消息；私聊中会直接处理收到的消息。

## JM 搜索

发送：

```text
/jm 关键词
```

示例：

```text
/jm 原神
```

当 `/jm` 后面不是纯数字时，Bot 会把后续内容按空格拆成搜索关键词，并返回搜索结果列表。列表中方括号里的数字是 album id。

搜索结果最多展示 10 条，附序号和 album ID，可接着说“下载第二个”。当前搜索固定使用第 1 页；`/jm 搜索 原神 2` 会被解释成搜索 `搜索`、`原神`、`2` 三个关键词，而不是搜索第 2 页。

## JM 下载

发送：

```text
/jm 数字ID
```

示例：

```text
/jm 123456
```

当 `/jm` 后面是纯数字时，Bot 会下载指定 album id，按章节生成 PDF 后上传：

- 群聊：上传到群文件夹 `本子`
- 私聊：直接通过私聊文件发送
- 多章节：逐个上传章节 PDF；每个文件上传成功后会立即删除本地 PDF，降低磁盘和内存压力
- PDF 文件名：`album_id-漫画名称-章节序号.pdf`，例如 `1186989-漫画名称-2.pdf`
- 下载任务会进入后台队列，完成后主动通知触发者。

## 每日新闻

发送：

```text
/news
```

也兼容整句 `每日新闻`。

Bot 会将每日新闻任务放入后台队列，默认从腾讯新闻热点榜获取新闻，并利用已配置的 LLM 生成中文综合摘要和最多 10 条重点新闻（含原文链接）。实现参考 DailyHotApi 的 `qq-news` 路由，直接请求腾讯上游，无需部署 DailyHotApi 或配置 API Key。榜单说明和重复文章会被过滤。

可在 `config.yaml` 中配置新闻源和条数：

```yaml
tasks:
  daily_news:
    provider: "qq-news"
    max_items: 10
```

`max_items` 范围为 `1～10`。LLM 失败或返回空摘要时，Bot 会降级发送原始标题、描述和链接；接口不可用或数据为空时，任务会返回明确错误。

旧配置未填写 `provider` 时也使用腾讯新闻源。若需保留 Currents，请设置 `provider: currents`，并配置 `api_key` 和 `language: en`。只有 Currents 需要 API Key，`language` 也仅对该源生效。

## 每日 AI 看点

发送：

```text
/dailyai
```

也兼容整句 `每日ai`。

Bot 会读取配置文件 `tasks.daily_ai.base_path` 中指定路径下的今日（`YYYYMMDD`）目录里的所有 `.md` 文件，合并后交由大模型生成今日 AI 论文总结。建议配合 `long_conversation_max_tokens` 参数以防止回复截断。

## 动漫新闻

发送：

```text
/anime-news
```

也兼容整句 `动漫新闻`。

Bot 会读取 `tasks.anime_news.file_path` 中配置的本地文件并发送内容。

## 涩图

发送：

```text
/setu 标签1 标签2 标签3
```

最多支持 3 个标签。任务会进入后台队列，结果会下载后上传为文件。

## 用户画像

发送：

```text
/profile
```

Bot 会返回当前用户画像 prompt。旧命令 `/showUserProfile` 仍然可用。
