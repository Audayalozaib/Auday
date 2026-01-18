import logging
import os
import asyncio
import requests
from io import BytesIO

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent, constants
from telegram.ext import ContextTypes, CallbackQueryHandler, InlineQueryHandler, CommandHandler, MessageHandler, filters

from config import MAX_FILE_SIZE, MAX_DURATION, DEVELOPER_ID, LOG_CHANNEL_ID
from utils import validate_url, format_file_size, cleanup_files, download_media, executor, get_smart_buttons
import database as db
import yt_dlp

logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = f"👋 **أهلاً بك يا {user.first_name}!**\n🎬 أرسل رابط الفيديو لأحمله لك.\n\n📂 استخدم `/history` لرؤية آخر تحميلاتك."
    await update.message.reply_text(text, parse_mode=constants.ParseMode.MARKDOWN)

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض سجل التحميلات"""
    user_id = update.effective_user.id
    rows = db.get_history(user_id)
    
    if not rows:
        await update.message.reply_text("لا يوجد سجل تحميلات سابق.")
        return
        
    text = "📂 **آخر 10 تحميلات:**\n\n"
    for i, (url, title) in enumerate(rows, 1):
        text += f"{i}. {title}\n{url}\n\n"
    
    await update.message.reply_text(text, parse_mode=constants.ParseMode.MARKDOWN)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أرسل أي رابط.", parse_mode=constants.ParseMode.MARKDOWN)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🟢 البوت يعمل بشكل طبيعي", parse_mode=constants.ParseMode.MARKDOWN)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    
    url = update.message.text.strip()
    if url.startswith('/'): return
    
    if not validate_url(url):
        await update.message.reply_text("❌ رابط غير مدعوم.")
        return

    status_msg = await update.message.reply_text("🔍 جاري الفحص...")
    
    try:
        # استخدام خيارات بسيطة للفحص السريع
        opts = {"quiet": True, "no_warnings": True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        
        title = info.get("title", "Video")[:50]
        uploader = info.get("uploader", "Unknown")
        
        # استخدام الأزرار الذكية
        keyboard = get_smart_buttons(url)
        
        text = f"✅ **{title}**\n👤 {uploader}"
        await status_msg.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=constants.ParseMode.MARKDOWN)
        
        context.user_data['last_info'] = info

    except Exception as e:
        await status_msg.edit_text(f"❌ حدث خطأ: {str(e)}")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # تحليل الأمر: mode|url
    try:
        parts = query.data.split("|", 1)
        mode = parts[0]
        url = parts[1]
    except:
        return

    # إذا كان الرابط المباشر
    if mode == "url":
        # نرسل الرابط فقط
        await query.edit_message_text(f"🔗 **الرابط المباشر:**\n{url}", parse_mode=constants.ParseMode.MARKDOWN)
        return

    mode_name = "فيديو" if mode == "vid" else "صوت"
    mode_key = "video" if mode == "vid" else "audio"
    
    await query.edit_message_text(f"⏳ جاري تحميل {mode_name}...")
    
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(executor, download_media, url, mode_key, query.from_user.id)
        filename, file_size = result
        
        # حفظ في السجل
        title = context.user_data.get('last_info', {}).get('title', 'Video')
        db.add_to_history(query.from_user.id, url, title)
        
        try: await context.bot.delete_message(query.message.chat_id, query.message.message_id)
        except: pass

        with open(filename, "rb") as f:
            thumb = None
            if mode_key == "audio" and context.user_data.get('last_info', {}).get('thumbnail'):
                try:
                    r = requests.get(context.user_data['last_info']['thumbnail'], stream=True)
                    if r.status_code == 200: thumb = BytesIO(r.content)
                except: pass
            
            # التحقق من الحجم للتحميل المباشر
            if file_size > MAX_FILE_SIZE:
                # ملف كبير جداً للإرسال المباشر -> رفع للقناة (Cloud Backup)
                await context.bot.send_message(query.message.chat_id, "📦 الملف كبير، جاري الرفع للسحابة...")
                
                # الرفع للقناة
                sent_msg = await context.bot.send_video(LOG_CHANNEL_ID, f, caption=f"Backup: {title}")
                
                # إرسال الرابط للمستخدم
                file_link = f"https://t.me/c/{str(LOG_CHANNEL_ID)[4:]}/{sent_msg.message_id}"
                await context.bot.send_message(
                    query.message.chat_id, 
                    f"✅ تم التحميل في السحابة!\n🔗 [اضغط هنا للتحميل]({file_link})\n\n📏 الحجم: {format_file_size(file_size)}",
                    parse_mode=constants.ParseMode.MARKDOWN
                )
                
            else:
                # إرسال عادي
                if mode_key == "audio":
                    await context.bot.send_audio(query.message.chat_id, f, caption="🎵 تم التحميل", thumbnail=thumb)
                else:
                    await context.bot.send_video(query.message.chat_id, f, caption="🎬 تم التحميل")
                
        cleanup_files(filename)
        
    except Exception as e:
        logger.error(f"Error: {e}")
        await query.edit_message_text(f"❌ فشل التحميل.\n\n{str(e)}")

# ==================== البحث ====================
async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_str = update.inline_query.query.strip()
    if not query_str: return
    
    results = []
    try:
        opts = {"quiet": True, "extract_flat": True, "max_downloads": 5}
        with yt_dlp.YoutubeDL(opts) as ydl:
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

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Error: {context.error}")
