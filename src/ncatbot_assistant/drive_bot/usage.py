"""Drive Bot usage text."""

USAGE_KEYWORDS = ("使用方法", "帮助", "help", "/help")

DRIVE_BOT_USAGE = """Drive Bot 指南 🚀

📚 漫画 (JM)
• 搜索：/jm <关键词> (返回搜索结果及ID)
• 下载：/jm <数字ID> (生成PDF并发送)

📰 资讯与 AI
• 新闻：发送「每日新闻」获取今日摸鱼图
• AI看点：发送「/dailyai」或「每日ai」生成今日AI论文总结

🎨 涩图 (Setu)
• 下载：/setu [标签1] [标签2] (最多3个标签)

💡 其他
• 直接发送文字即可与我闲聊
• 发送「/help」再次查看本说明"""


def is_usage_question(message: str) -> bool:
    normalized = message.strip().lower().strip("。.!！?？")
    return normalized in USAGE_KEYWORDS
