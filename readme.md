# ncatbot-assistant

基于 NcatBot 5.x 的 QQ 助手项目，目前主要提供 `drive_bot` 插件。插件支持群聊和私聊中的资源搜索、后台下载上传、每日新闻、涩图图片任务，以及带短期会话上下文的 LLM 兜底回复。

## 当前功能

- `/jm 关键词`：搜索 JMComic album。
- `/jm 数字ID`：下载指定 album，按章节生成 PDF 并上传。
- `/setu 标签1 标签2 标签3`：按最多 3 个标签获取图片并上传。
- `每日新闻`：获取今日摸鱼新闻图片并发送。
- `使用方法`、`帮助`、`help`、`/help`：返回插件命令说明。
- 未命中命令的普通聊天：调用 OpenAI-compatible Chat Completion 兜底回复。
- LLM 短期上下文：按私聊用户或群聊内 `group_id + user_id` 保存最近 N 轮对话，让连续聊天能承接前文。
- 后台任务队列：下载、上传和图片处理进入 SQLite-backed 单 worker 队列，避免阻塞普通消息响应。

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
```

`llm.context.max_turns` 表示每个会话保留最近多少轮 user/assistant 对话。该上下文只保存在内存中，重启后会清空；任务状态保存在 SQLite 中。

运行时目录会在启动时自动创建，默认都位于 `data/` 下：

```text
data/
  cache/              # JM 下载缓存
  image/              # setu / 每日新闻图片临时目录
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
