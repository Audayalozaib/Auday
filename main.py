import logging
import shutil
import asyncio # تأكد من استيراد asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, InlineQueryHandler, filters

# استيراد المكونات
from config import BOT_TOKEN
import handlers

# إعدادات التسجيل
logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)

async def startup_bot(application):
    """وظيفة تُنفذ قبل بدء التشغيل لإيقاف أي عمليات قديمة"""
    try:
        # إلغاء الـ Webhook إذا كان موجوداً
        await application.bot.delete_webhook(drop_pending_updates=True)
        print("✅ Webhook dropped successfully")
    except Exception as e:
        print(f"⚠️ Warning during startup: {e}")

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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_message))
    app.add_handler(CallbackQueryHandler(handlers.button_callback))
    app.add_handler(InlineQueryHandler(handlers.inline_query))
    app.add_error_handler(handlers.error_handler)
    
    # إضافة مهمة البدء
    app.post_init = startup_bot

    print("✅ Bot is running!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
