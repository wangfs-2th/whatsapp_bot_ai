"""
配置文件
"""
import os
from dotenv import load_dotenv

load_dotenv()

# WhatsApp Web URL
WHATSAPP_WEB_URL = "https://web.whatsapp.com"

# 浏览器设置（降低封号风险）
CHROME_PROFILE_PATH = os.getenv("CHROME_PROFILE_PATH", "")
HEADLESS_MODE = os.getenv("HEADLESS_MODE", "False").lower() == "true"
USER_AGENT = os.getenv("USER_AGENT", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

# 消息设置
AUTO_REPLY_ENABLED = os.getenv("AUTO_REPLY_ENABLED", "True").lower() == "true"

# 允许 REPLY_DELAY 支持小数（例如 "2.0"），避免 int('2.0') 报错
try:
    REPLY_DELAY = float(os.getenv("REPLY_DELAY", "2"))
except ValueError:
    REPLY_DELAY = 2.0

# 其余节奏参数先转为 float 再转 int，兼容 "2.0" 这类值
def _get_int_env(name: str, default: int) -> int:
    value = os.getenv(name, str(default))
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default

MIN_REPLY_INTERVAL = _get_int_env("MIN_REPLY_INTERVAL", 5)
MAX_MESSAGES_PER_HOUR = _get_int_env("MAX_MESSAGES_PER_HOUR", 20)

# 批量发送设置
MAX_RECIPIENTS_PER_BATCH = _get_int_env("MAX_RECIPIENTS_PER_BATCH", 10)
BATCH_DELAY_BETWEEN = _get_int_env("BATCH_DELAY_BETWEEN", 2)

# 关键词回复配置
KEYWORD_REPLIES = {
    "你好": "你好！有什么可以帮助你的吗？",
    "hello": "Hello! How can I help you?",
    "hi": "Hi there! What can I do for you?",
    "帮助": "我可以帮助你处理一些常见问题。请告诉我你需要什么帮助。",
    "help": "I can help you with common questions. What do you need help with?",
}

# 默认回复消息
DEFAULT_REPLY = "感谢您的消息！我会尽快回复您。"

# AI回复设置
AI_ENABLED = os.getenv("AI_ENABLED", "True").lower() == "true"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
# 通义千问设置
QWEN_API_KEY = os.getenv("QWEN_API_KEY", "")
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen-turbo")
AI_PERSONALITY = os.getenv("AI_PERSONALITY", "你是一个友好、专业的助手，用简洁明了的语言回答问题。")
# AI聊天提示词（用于引导大模型生成聊天风格的回复）
AI_CHAT_PROMPT = os.getenv("AI_CHAT_PROMPT", "请你用一个普通年轻人聊天的语气回答我，像在微信里跟好朋友说话那样。可以适当用'嘛''啦''呀'这些语气词，加点生活化的表达，别说教，别太规整，最好带点小情绪或小幽默，让人感觉是真人而不是AI在回。")
AI_TEMPERATURE = float(os.getenv("AI_TEMPERATURE", "0.7"))
# AI提供商 (openai 或 qwen)
AI_PROVIDER = os.getenv("AI_PROVIDER", "openai").lower()

# 翻译设置
TRANSLATION_ENABLED = os.getenv("TRANSLATION_ENABLED", "True").lower() == "true"
AUTO_TRANSLATE_INCOMING = os.getenv("AUTO_TRANSLATE_INCOMING", "True").lower() == "true"
DEFAULT_OUTGOING_LANGUAGE = os.getenv("DEFAULT_OUTGOING_LANGUAGE", "en")
# 自动回复语言设置（如果未设置，使用默认输出语言）
AUTO_REPLY_LANGUAGE = os.getenv("AUTO_REPLY_LANGUAGE", DEFAULT_OUTGOING_LANGUAGE)

# 监听设置
LISTEN_CONTACTS = os.getenv("LISTEN_CONTACTS", "True").lower() == "true"
# 是否自动回复所有人（True=回复所有人，False=只回复指定联系人列表）
REPLY_TO_ALL_CONTACTS = os.getenv("REPLY_TO_ALL_CONTACTS", "True").lower() == "true"
# 清理联系人列表（去除空字符串和空格）
_specific_contacts_raw = os.getenv("SPECIFIC_CONTACTS", "").strip()
SPECIFIC_CONTACTS = [c.strip() for c in _specific_contacts_raw.split(",") if c.strip()] if _specific_contacts_raw else []

# 数据库设置
DATABASE_PATH = os.getenv("DATABASE_PATH", "whatsapp_bot.db")

# 本地内容回复文件路径
LOCAL_CONTENT_PATH = os.getenv("LOCAL_CONTENT_PATH", "local_replies.json")

# 定时任务设置
SCHEDULED_MESSAGES_ENABLED = os.getenv("SCHEDULED_MESSAGES_ENABLED", "True").lower() == "true"

# 关键词触发设置
KEYWORD_TRIGGER_ENABLED = os.getenv("KEYWORD_TRIGGER_ENABLED", "False").lower() == "true"
KEYWORD_TRIGGER_CONFIG_PATH = os.getenv("KEYWORD_TRIGGER_CONFIG_PATH", "keyword_triggers.json")
