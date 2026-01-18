import logging
import shutil
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, InlineQueryHandler, filters

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)

from config import BOT_TOKEN
import handlers
import database as db

async def startup_bot(application):
    print("🔄 Connecting to Cloud Database (Channel)...")
    await db.init_db(application)
    print("✅ Database Connected & Synced")

def main():
    print("🚀 Starting Bot...")
    
    if shutil.which("ffmpeg"):
        print("✅ FFmpeg Ready")
    else:
        print("⚠️ FFmpeg Not Found")

    app = ApplicationBuilder().token(BOT_TOKEN).concurrent_updates(True).build()

    # تسجيل المعالجات
    app.add_handler(CommandHandler("start", handlers.start))
    app.add_handler(CommandHandler("help", handlers.help_command))
    app.add_handler(CommandHandler("status", handlers.status_command))
    app.add_handler(CommandHandler("history", handlers.history_command))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_message))
    app.add_handler(CallbackQueryHandler(handlers.button_callback))
    app.add_handler(InlineQueryHandler(handlers.inline_query))
    app.add_error_handler(handlers.error_handler)
    
    # ربط وظيفة بدء التشغيل
    app.post_init = startup_bot

    print("✅ Bot is running!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
