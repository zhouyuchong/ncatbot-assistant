"""Drive Bot usage text."""

USAGE_KEYWORDS = ("使用方法", "帮助", "help", "/help")

DRIVE_BOT_USAGE = """Drive Bot 使用方法

1. 搜索 JM 列表
/jm 关键词
示例：/jm 原神
说明：返回搜索结果列表，列表中的方括号数字是 album id。

2. 下载并上传 JM PDF
/jm 数字ID
示例：/jm 123456
说明：下载指定 album id，生成 PDF 后上传；群聊上传到“本子”文件夹，私聊直接发送文件。

3. 每日新闻
每日新闻
说明：获取今日摸鱼新闻图片并直接回复。

4. 涩图
/setu 标签1 标签2 标签3
说明：最多 3 个标签；结果会上传为文件。

提示：发送“使用方法”可再次查看本说明。"""


def is_usage_question(msg: str) -> bool:
    normalized = msg.strip().lower().strip("。.!！?？")
    return normalized in USAGE_KEYWORDS
