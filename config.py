import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DEVELOPER_ID = int(os.getenv("DEVELOPER_ID", "778375826"))
# هذه القناة سيتم استخدامها أيضاً لحفظ الملفات الكبيرة
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "-1002064206339")) 

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN is missing")

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB حد التيليجرام
MAX_DURATION = 1800
MAX_CONCURRENT_DOWNLOADS = 3
DOWNLOAD_TIMEOUT = 300

FFMPEG_PATH = "ffmpeg"
FFPROBE_PATH = "ffprobe"

# اسم ملف قاعدة البيانات
DB_NAME = "bot_history.db"
