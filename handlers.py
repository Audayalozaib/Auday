import logging
import os
import asyncio # استيراد asyncio لإصلاح مشكلة الـ loop
import requests
from io import BytesIO

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent, constants
from telegram.ext import ContextTypes, CallbackQueryHandler, InlineQueryHandler, CommandHandler, MessageHandler, filters

from config import MAX_FILE_SIZE, MAX_DURATION, DEVELOPER_ID
from utils import (
    validate_url, format_file_size, cleanup_files, download_media, 
    get_ydl_options, YDL_OPTIONS_BASE, active_downloads, executor # استيراد executor من utils
)

logger = logging.getLogger(__name__)

# ==================== الأوامر ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = f"👋 **أهلاً بك يا {user.first_name}!**\n🎬 أرسل رابط الفيديو لأحمله لك."
    await update.message.reply_text(text, parse_mode=constants.ParseMode.MARKDOWN)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أرسل أي رابط يوتيوب أو تيك توك.", parse_mode=constants.ParseMode.MARKDOWN)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🟢 البوت يعمل بشكل طبيعي", parse_mode=constants.ParseMode.MARKDOWN)

# ==================== الرسائل ====================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    
    url = update.message.text.strip()
    if url.startswith('/'): return
    
    if not validate_url(url):
        await update.message.reply_text("❌ رابط غير مدعوم.")
        return

    status_msg = await update.message.reply_text("🔍 جاري الفحص...")
    
    try:
        with yt_dlp.YoutubeDL(get_ydl_options("info", update.effective_user.id)) as ydl:
            info = ydl.extract_info(url, download=False)
        
        title = info.get("title", "Video")[:50]
        uploader = info.get("uploader", "Unknown")
        
        keyboard = [
            [InlineKeyboardButton("🎬 MP4", callback_data=f"vid|{url}"),
             InlineKeyboardButton("🎵 MP3", callback_data=f"aud|{url}")]
        ]
        
        text = f"✅ **{title}**\n👤 {uploader}"
        await status_msg.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=constants.ParseMode.MARKDOWN)
        
        context.user_data['last_info'] = info

    except Exception as e:
        await status_msg.edit_text(f"❌ حدث خطأ: {str(e)}")

# ==================== الأزرار ====================
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    mode, url = query.data.split("|", 1)
    mode_name = "فيديو" if mode == "vid" else "صوت"
    mode_key = "video" if mode == "vid" else "audio"
    
    await query.edit_message_text(f"⏳ جاري تحميل {mode_name}...")
    
    try:
        # الإصلاح: استخدام asyncio.get_event_loop()
        loop = asyncio.get_event_loop()
        
        # استدعاء download_media باستخدام executor من utils
        result = await loop.run_in_executor(executor, download_media, url, mode_key, query.from_user.id)
        filename, file_size = result
        
        # حذف رسالة التحميل
        try: await context.bot.delete_message(query.message.chat_id, query.message.message_id)
        except: pass

        with open(filename, "rb") as f:
            thumb = None
            if mode_key == "audio" and context.user_data.get('last_info', {}).get('thumbnail'):
                try:
                    r = requests.get(context.user_data['last_info']['thumbnail'], stream=True)
                    if r.status_code == 200: thumb = BytesIO(r.content)
                except: pass
            
            if mode_key == "audio":
                await context.bot.send_audio(query.message.chat_id, f, caption="🎵 تم التحميل", thumbnail=thumb)
            else:
                await context.bot.send_video(query.message.chat_id, f, caption="🎬 تم التحميل")
                
        cleanup_files(filename)
        
    except Exception as e:
        logger.error(f"Error: {e}")
        # الإصلاح: إرسال الخطأ للمستخدم لنعرف سببه
        await query.edit_message_text(f"❌ فشل التحميل.\n\nالخطأ: {str(e)[:200]}")

# ==================== البحث ====================
async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_str = update.inline_query.query.strip()
    if not query_str: return
    
    results = []
    try:
        with yt_dlp.YoutubeDL(YDL_OPTIONS_BASE) as ydl:
            data = ydl.extract_info(f"ytsearch5:{query_str}", download=False)
            for i, vid in enumerate(data.get("entries", [])[:5]):
                results.append(
                    InlineQueryResultArticle(
                        id=str(i),
                        title=vid.get("title"),
                        input_message_content=InputTextMessageContent(vid.get("url")),
                        thumb_url=vid.get("thumbnail")
                    )
                )
    except: pass
    await update.inline_query.answer(results)

# ==================== الأخطاء ====================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")
