import asyncio
import logging
import shutil
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, InlineQueryHandler, filters

# إعدادات التسجيل
logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)

# استيراد المكونات
from config import BOT_TOKEN, MAX_CONCURRENT_DOWNLOADS
import handlers
from utils import active_downloads, cleanup_files, download_media

# تعريف الـ Executor ليكون متاحاً للملفات الأخرى
executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_DOWNLOADS)

def main():
    print("🚀 Starting Bot...")
    
    # التحقق من FFmpeg
    if shutil.which("ffmpeg"):
        print("✅ FFmpeg Ready")
    else:
        print("⚠️ FFmpeg Not Found")

    # بناء التطبيق
    app = ApplicationBuilder().token(BOT_TOKEN).concurrent_updates(True).build()

    # تسجيل المعالجات
    app.add_handler(CommandHandler("start", handlers.start))
    app.add_handler(CommandHandler("help", handlers.help_command))
    app.add_handler(CommandHandler("status", handlers.status_command))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_message))
    app.add_handler(CallbackQueryHandler(handlers.button_callback))
    app.add_handler(InlineQueryHandler(handlers.inline_query))
    
    app.add_error_handler(handlers.error_handler)

    # تشغيل
    print("✅ Bot is running!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
