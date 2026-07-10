# Currents 每日新闻文本摘要设计

## 背景与目标

现有“每日新闻”任务请求旧接口并把响应作为图片发送。旧接口已经失效，新实现改用 Currents `latest-news` API，解析 JSON 新闻列表，并向 QQ 用户发送中文文本摘要。

最终消息包含：

- 一段中文综合摘要；
- 5～10 条重点新闻；
- 每条重点新闻的中文标题或标题翻译、简短说明和原文链接。

## 配置

在现有 `config.example.yaml` 的 `tasks` 下增加：

```yaml
tasks:
  daily_news:
    api_key: "your-currents-api-key"
    language: "en"
    max_items: 10
```

`api_key` 必填。`language` 默认 `en`，`max_items` 默认 `10`，并限制最终送入摘要流程的新闻数量不超过 10 条。仓库实际使用的示例文件名是 `config.example.yaml`，因此不新增名字相近的 `config.yaml.example`。

## 架构与职责

### 新闻服务

重写 `src/ncatbot_assistant/drive_bot/services/daily.py`，将职责从下载图片改为生成每日新闻文本：

1. 从 `project_config.tasks.daily_news` 读取 Currents 配置；
2. 请求 `https://api.currentsapi.services/v1/latest-news`，使用查询参数传递 `language` 和 `apiKey`；
3. 校验 HTTP 状态、JSON 顶层 `status` 以及 `news` 列表；
4. 清洗 `title`、`description`、`url`、`author`、`category` 和 `published` 字段，丢弃没有标题或链接的记录；
5. 截取最多 `max_items` 条记录并构造受控长度的 LLM 输入；
6. 调用注入的现有长文本 LLM 方法生成中文摘要；
7. 若 LLM 调用失败，返回规则生成的新闻列表，保证 Currents 数据可用时任务仍能产出结果。

HTTP 请求继续通过线程包装同步 `requests` 调用，保持与项目现有依赖和异步任务队列兼容。API key 只作为请求参数使用，不写入日志或错误消息。

### 插件装配

`DriveBotPlugin.on_load` 创建每日新闻函数闭包，将已加载的 `project_config` 和 `_ask_memory_summary` 注入新闻服务，再传给 `TaskHandlers`。这样新闻服务可以独立测试，也能复用现有 OpenAI-compatible LLM 配置，无需增加第二套 LLM 客户端。

### 任务输出

`TaskHandlers._handle_daily` 改为接收新闻文本，并通过 `ReplyAdapter.reply_direct_text` 发送。任务结果记录 `sent_text: 1` 和实际文本，不再记录图片路径。

## 数据与提示词

送入 LLM 的内容只包含每条新闻必要字段，并给记录编号。提示词明确要求：

- 使用简体中文；
- 先给出一段综合摘要；
- 再选择 5～10 条最值得关注、尽量覆盖不同类别的新闻；
- 不编造输入之外的事实；
- 每条保留对应原文链接；
- 输出适合 QQ 纯文本消息，不使用表格。

规则降级输出以“今日新闻速览”开头，逐条包含原始标题、截断后的描述和原文链接，并注明“AI 摘要暂不可用”。它不尝试机器翻译，避免在 LLM 不可用时引入额外服务依赖。

## 错误处理

以下情况使任务失败并返回清晰错误：

- 未配置 `tasks.daily_news.api_key`；
- Currents 请求超时、网络失败或返回非成功 HTTP 状态；
- 响应不是合法 JSON；
- 顶层 `status` 不是 `ok`；
- `news` 不是列表，或清洗后没有包含标题和链接的新闻。

LLM 失败不是任务失败条件；服务记录警告并使用规则降级文本。错误内容不包含 API key，也不直接回显完整上游响应。

## 测试

新增每日新闻服务单元测试，覆盖：

- Currents 请求 URL、查询参数和超时；
- 示例响应字段解析、条数限制和无效记录过滤；
- LLM 提示词包含新闻信息且要求中文、摘要与链接；
- LLM 失败时返回规则降级结果；
- 缺少 API key、异常状态和空新闻列表的错误；
- 每日新闻处理器发送纯文本，不再发送图片；
- `config.example.yaml` 文档化 `tasks.daily_news.api_key` 等配置。

测试不访问真实 Currents 或 LLM 服务，通过依赖注入或补丁提供确定性响应。完成后运行每日新闻相关测试及完整测试套件。

## 文档范围

更新根 README 和插件 README，把“今日摸鱼新闻图片”改为 Currents 新闻中文摘要，并说明 API key 配置位置。路由命令“每日新闻”、任务类型和预计耗时配置保持不变。
