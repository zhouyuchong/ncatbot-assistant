# Drive Bot 使用方法

Drive Bot 支持在 QQ 群聊和私聊中处理资源搜索、文件上传和每日新闻。

当消息没有命中下方已有关键词/命令时，Bot 会使用 OpenAI-compatible Chat Completion 做兜底回复。推荐复制 `code/.env.example` 为 `code/.env` 并填写：

```dotenv
DRIVE_BOT_AI_API_KEY=fake-api-key
DRIVE_BOT_AI_BASE_URL=https://api.deepseek.com
DRIVE_BOT_AI_MODEL=deepseek-v4-flash
DRIVE_BOT_AI_TEMPERATURE=0.7
DRIVE_BOT_AI_MAX_TOKENS=800
```

`fake-api-key` 仅用于离线测试；实际使用时请改为可用的 API Key。

AI 兜底会自动加载 `code/skills/neko-on-everything/`，把其中的轻量角色扮演 prompt 注入 system message。这个 skill 只提供回复风格约束，不安装依赖，也不写入长期记忆。

## 依赖

JM 下载并生成 PDF 需要安装：

```text
jmcomic
img2pdf
Pillow
```

插件的 `manifest.toml` 已声明这些依赖。若手动运行 `code/` 目录下的兼容入口，请同步安装 `code/requirements.txt` 中的依赖。

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

两次下载之间有 60 秒冷却时间。

## 每日新闻

发送：

```text
每日新闻
```

Bot 会获取今日摸鱼新闻图片并直接回复。

## 涩图

发送：

```text
/setu 标签1 标签2 标签3
```

最多支持 3 个标签。结果会下载后上传为文件。
