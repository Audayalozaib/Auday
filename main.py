import os
import re
import logging
import subprocess
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InputTextMessageContent
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    InlineQueryHandler,
    ContextTypes,
    filters
)
import yt_dlp

# ================== إعدادات عامة ==================

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
FFMPEG_LOCATION = "/nix/store"   # الحل النهائي لـ Railway

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================== خيارات yt-dlp الأساسية ==================

YDL_OPTIONS_BASE = {
    "quiet": True,
    "no_warnings": True,
    "user_agent": "Mozilla/5.0 (Linux; Android 10)",
    "referer": "https://www.google.com/",
    "concurrent_fragment_downloads": 5,
    "retries": 5,
    "fragment_retries": 5,
    "extractor_args": {
        "youtube": {
            "player_client": ["android", "web"],
            "skip": ["hls", "dash"]
        }
    },
    "ffmpeg_location": FFMPEG_LOCATION,
}

# ================== أوامر البوت ==================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 أهلاً بك في بوت التحميل\n\n"
        "📥 أرسل رابط فيديو (يوتيوب / تيك توك / انستغرام)\n"
        "🎧 اختر فيديو أو صوت\n\n"
        "🚀 جاهز!"
    )

# ================== استقبال الروابط ==================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    url = update.message.text.strip()
    if not re.match(r"^https?://", url):
        return

    status = await update.message.reply_text("🔍 جاري فحص الرابط...")

    try:
        with yt_dlp.YoutubeDL(YDL_OPTIONS_BASE) as ydl:
            info = ydl.extract_info(url, download=False)

        filesize = info.get("filesize") or info.get("filesize_approx")
        if filesize and filesize > MAX_FILE_SIZE:
            await status.edit_text("⛔ الملف أكبر من 50MB")
            return

        if info.get("duration", 0) > 1800:
            await status.edit_text("⛔ الفيديو أطول من 30 دقيقة")
            return

        keyboard = [
            [
                InlineKeyboardButton("🎬 فيديو", callback_data=f"vid|{url}"),
                InlineKeyboardButton("🎵 صوت", callback_data=f"aud|{url}")
            ]
        ]
        await status.edit_text(
            f"✅ تم العثور على:\n{info.get('title','فيديو')}\n\nاختر الصيغة:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except Exception as e:
        logger.error(e)
        await status.edit_text("❌ فشل في قراءة الرابط")

# ================== أزرار التحميل ==================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    mode, url = query.data.split("|")
    await query.edit_message_text("⏳ جاري التحميل...")

    file_prefix = f"download_{query.from_user.id}"
    filename = None

    ydl_opts = YDL_OPTIONS_BASE.copy()

    if mode == "vid":
        ydl_opts.update({
            "format": "bestvideo+bestaudio/best",
            "merge_output_format": "mp4",
            "outtmpl": f"{file_prefix}.%(ext)s",
            "max_filesize": MAX_FILE_SIZE,
        })
    else:
        ydl_opts.update({
            "format": "bestaudio/best",
            "outtmpl": f"{file_prefix}.%(ext)s",
            "max_filesize": MAX_FILE_SIZE,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
        })

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

        if mode == "aud":
            filename = filename.rsplit(".", 1)[0] + ".mp3"

        if not os.path.exists(filename):
            raise Exception("File not found")

        if os.path.getsize(filename) > MAX_FILE_SIZE:
            await query.edit_message_text("⛔ الملف الناتج أكبر من 50MB")
            return

        with open(filename, "rb") as f:
            if mode == "vid":
                await query.message.reply_video(f, caption=info.get("title"))
            else:
                await query.message.reply_audio(f, title=info.get("title"))

        await query.delete_message()

    except Exception as e:
        logger.error(e)
        await query.edit_message_text("❌ حدث خطأ أثناء التحميل")

    finally:
        if filename and os.path.exists(filename):
            os.remove(filename)

# ================== البحث بالإنلاين ==================

async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query
    if not query:
        return

    results = []
    try:
        opts = YDL_OPTIONS_BASE.copy()
        opts["extract_flat"] = True

        with yt_dlp.YoutubeDL(opts) as ydl:
            entries = ydl.extract_info(f"ytsearch5:{query}", download=False)["entries"]

        for i, e in enumerate(entries):
            results.append(
                InlineQueryResultArticle(
                    id=str(i),
                    title=e["title"],
                    input_message_content=InputTextMessageContent(e["url"]),
                    description=e["url"]
                )
            )

    except Exception as e:
        logger.error(e)

    await update.inline_query.answer(results)

# ================== تشغيل البوت ==================

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(InlineQueryHandler(inline_query))

    print("✅ البوت يعمل الآن")
    app.run_polling(drop_pending_updates=True)
