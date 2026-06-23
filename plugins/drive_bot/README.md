# Drive Bot 使用方法

Drive Bot 支持在 QQ 群聊和私聊中处理资源搜索、文件上传和每日新闻。

当消息没有命中下方已有关键词/命令时，Bot 会使用 OpenAI-compatible Chat Completion 做兜底回复。推荐复制 `config.example.yaml` 为 `config.yaml` 并填写顶层 `llm` 配置：

```yaml
llm:
  api_key: "fake-api-key"
  base_url: "https://api.deepseek.com"
  model: "deepseek-v4-flash"
  temperature: 0.7
  max_tokens: 800
```

`fake-api-key` 仅用于离线测试；实际使用时请改为可用的 API Key。

AI 兜底会自动加载 `resources/skills/neko-on-everything/`，把其中的轻量角色扮演 prompt 注入 system message。这个 skill 只提供回复风格约束，不安装依赖，也不写入长期记忆。

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
```

## 依赖

JM 下载并生成 PDF 需要安装：

```text
jmcomic
img2pdf
Pillow
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

Bot 会返回本插件的命令说明文本。

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

当前搜索固定使用第 1 页；`/jm 搜索 原神 2` 会被解释成搜索 `搜索`、`原神`、`2` 三个关键词，而不是搜索第 2 页。

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
每日新闻
```

Bot 会将每日新闻任务放入后台队列，完成后发送今日摸鱼新闻图片。

## 涩图

发送：

```text
/setu 标签1 标签2 标签3
```

最多支持 3 个标签。任务会进入后台队列，结果会下载后上传为文件。
