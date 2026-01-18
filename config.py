import os
from dotenv import load_dotenv

# تحميل المتغيرات
load_dotenv()

# التوكن والمعلومات
BOT_TOKEN = os.getenv("BOT_TOKEN")
DEVELOPER_ID = int(os.getenv("DEVELOPER_ID", "0"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "0"))

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN is missing in .env file")

# حدود البوت
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
MAX_DURATION = 1800  # 30 دقيقة
MAX_CONCURRENT_DOWNLOADS = 3
DOWNLOAD_TIMEOUT = 300

# المسارات
FFMPEG_PATH = "ffmpeg"
FFPROBE_PATH = "ffprobe"
