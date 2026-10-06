# ncatbot-assistant

基于 NcatBot 5.x 的 QQ 助手项目，目前主要提供 `drive_bot` 插件。插件支持群聊和私聊中的资源搜索、后台下载上传、每日新闻、涩图图片任务，以及带短期会话上下文的 LLM 兜底回复。

## 当前功能

- `/jm 关键词`：搜索 JMComic album。
- `/jm 数字ID`：下载指定 album，按章节生成 PDF 并上传。
- `/setu 标签1 标签2 标签3`：按最多 3 个标签获取图片并上传。
- `/news`：默认获取腾讯新闻热点榜，利用 LLM 生成中文摘要并发送；兼容整句 `每日新闻`。
- `/dailyai`：读取本地指定的 Markdown 论文数据，利用 LLM 生成今日 AI 技术看点；兼容整句 `每日ai`。
- `/anime-news`：读取已配置的动漫新闻文件并发送；兼容整句 `动漫新闻`。
- `/profile`：查看当前用户画像 prompt。
- `/task [任务编号]`：查询当前会话中自己的任务，省略编号查询最近下载任务。
- 自然语言办事：支持 JM 搜索、选择结果下载和查询任务状态，例如“搜索原神的本子”“下载第二个”“刚才下载好了吗”。
- `使用方法`、`帮助`、`help`、`/help`：返回插件命令说明。
- 未命中命令的普通聊天：调用 OpenAI-compatible Chat Completion 兜底回复。
- LLM 短期上下文：按私聊用户或群聊内 `group_id + user_id` 保存最近 N 轮对话，让连续聊天能承接前文。
- 后台任务队列：下载、上传和图片处理进入 SQLite-backed 单 worker 队列，避免阻塞普通消息响应。

## 连续对话办事

群聊每次仍需 @ Bot，私聊直接发送。例如：

```text
搜索原神的本子
下载第二个
刚才下载好了吗？
```

搜索结果显示序号和资源 ID。“第二个”由程序从当前搜索结果取 ID，下载进入原有后台队列。任务查询从 SQLite 读取真实状态，仅能查看当前群聊/私聊中属于自己的任务。

明确命令不调用 LLM。启用工具时，每条普通消息最多一次 LLM 请求，工具结果由程序回复，不额外调用模型润色，也不自动重试。工具描述会增加输入 token；调用日志会记录服务端返回的 token usage（可用时）。本期只有 JM 搜索、下载和任务查询支持自然语言工具，其他业务继续使用命令。

搜索结果、待补充参数和最近下载任务编号保存在内存中，15 分钟无状态更新后失效，重启清空。失效后请重新搜索，或用 `/task 42` 查询已持久化的任务。搜索失败或无结果会清除旧搜索结果。详细配置见 [Drive Bot 使用说明](plugins/drive_bot/README.md)。

## 项目结构

```text
plugins/
  drive_bot/
    manifest.toml
    plugin.py              # NcatBot 插件发现入口
    README.md              # drive_bot 详细使用说明
src/
  ncatbot_assistant/
    drive_bot/
      ncatbot_plugin.py    # NcatBot 适配层
      router.py            # 消息路由
      storage.py           # SQLite 任务存储
      llm_context.py       # LLM 短期上下文
      jobs/                # 后台任务队列和 handler
      services/            # JM、setu、每日新闻服务
tests/
```

## 配置

复制配置模板：

```bash
cp config.example.yaml config.yaml
```

重点配置：

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

`llm.context.max_turns` 表示每个会话保留最近多少轮 user/assistant 对话。该上下文只保存在内存中，重启后会清空；任务状态保存在 SQLite 中。

`tasks.daily_news.provider` 默认是 `qq-news`，参考 DailyHotApi 的腾讯新闻实现，直接请求上游热点榜，无需 API Key，也无需部署 DailyHotApi。`max_items` 控制交给 LLM 归纳的新闻数量，范围为 `1～10`。LLM 失败或返回空摘要时，Bot 会降级发送原始标题、描述和链接。

旧配置未填写 `provider` 时也会使用腾讯新闻源。若需继续使用 Currents，请显式设置 `provider: currents` 并填写有效的 `api_key`；`language` 仅对 Currents 生效，默认为 `en`。

运行时目录会在启动时自动创建，默认都位于 `data/` 下：

```text
data/
  cache/              # JM 下载缓存
  image/              # setu 图片临时目录
  pdf/                # JM 生成 PDF 临时目录
  drive_bot.sqlite3   # 后台任务队列状态库
```

## 运行与测试

要求 Python 3.12+。

安装依赖：

```bash
uv sync
```

本地运行：

```bash
uv run ncatbot-assistant
```

运行测试：

```bash
uv run python -m unittest discover tests
```

语法检查：

```bash
PYTHONPYCACHEPREFIX=/tmp/ncatbot-assistant-pycache python3 -m py_compile plugins/drive_bot/plugin.py src/ncatbot_assistant/drive_bot/*.py src/ncatbot_assistant/drive_bot/jobs/*.py src/ncatbot_assistant/drive_bot/services/*.py tests/*.py
```

## 参考

- NapCat QQ: https://github.com/NapNeko/NapCatQQ
- NapCat 文档: https://napneko.github.io/guide/install
- NcatBot 文档: https://docs.ncatbot.xyz/guide/dto79lp7/
- JMComic Crawler: https://github.com/hect0x7/JMComic-Crawler-Python
- setu 参考: https://github.com/Raven95676/astrbot_plugin_setu#
- neko prompt： https://github.com/H0rseGun/Neko-for-everything/blob/main/neko-v2-r18.txt
