import logging
import os
import asyncio
import requests
from io import BytesIO

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent, constants
from telegram.ext import ContextTypes, CallbackQueryHandler, InlineQueryHandler, CommandHandler, MessageHandler, filters

import yt_dlp

from config import MAX_FILE_SIZE, MAX_DURATION, DEVELOPER_ID, LOG_CHANNEL_ID
from utils import validate_url, format_file_size, cleanup_files, download_media, executor, get_smart_buttons
import database as db

logger = logging.getLogger(__name__)

# ==================== الأوامر ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = f"""
👋 **أهلاً بك يا {user.first_name}!**

🎬 **بوت التحميل المتطور**:
• يدعم اليوتيوب، تيك توك، انستجرام...
• يرفع الملفات الكبيرة تلقائياً للقناة.
• يحفظ سجل تحميلاتك.

📂 أرسل رابط الفيديو الآن، أو اكتب `/history` لرؤية آخر تحميلاتك.
    """
    await update.message.reply_text(text, parse_mode=constants.ParseMode.MARKDOWN)

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض سجل التحميلات من القناة"""
    user_id = update.effective_user.id
    rows = db.get_history(user_id)
    
    if not rows:
        await update.message.reply_text("📂 لا يوجد سجل تحميلات سابق.")
        return
        
    text = "📂 **آخر 10 تحميلات:**\n\n"
    for i, item in enumerate(rows, 1):
        title = item.get('title', 'Unknown')
        url = item.get('url', '')
        text += f"{i}. {title}\n{url}\n\n"
    
    await update.message.reply_text(text, parse_mode=constants.ParseMode.MARKDOWN)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أرسل أي رابط يوتيوب أو تيك توك وسأقوم بتحميله.", parse_mode=constants.ParseMode.MARKDOWN)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🟢 البوت يعمل بشكل طبيعي\n📂 قاعدة البيانات: متصلة بالقناة", parse_mode=constants.ParseMode.MARKDOWN)

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
        # خيارات خفيفة للفحص فقط
        opts = {"quiet": True, "no_warnings": True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        
        title = info.get("title", "Video")[:50]
        uploader = info.get("uploader", "Unknown")
        
        # استخدام الأزرار الذكية حسب الرابط
        keyboard = get_smart_buttons(url)
        
        text = f"✅ **{title}**\n👤 {uploader}"
        await status_msg.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=constants.ParseMode.MARKDOWN)
        
        # حفظ المعلومات المؤقتة
        context.user_data['last_info'] = info

    except Exception as e:
        await status_msg.edit_text(f"❌ حدث خطأ: {str(e)}")

# ==================== الأزرار ====================
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # تحليل البيانات
    try:
        parts = query.data.split("|", 1)
        mode = parts[0]
        url = parts[1]
    except:
        return

    # حالة الرابط المباشر
    if mode == "url":
        await query.edit_message_text(f"🔗 **الرابط المباشر:**\n{url}", parse_mode=constants.ParseMode.MARKDOWN)
        return

    mode_name = "فيديو" if mode == "vid" else "صوت"
    mode_key = "video" if mode == "vid" else "audio"
    
    await query.edit_message_text(f"⏳ جاري تحميل {mode_name}...")
    
    try:
        # تشغيل التحميل في الخلفية
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(executor, download_media, url, mode_key, query.from_user.id)
        filename, file_size = result
        
        # حفظ في السجل (تم التعديل: استخدام context.application بدلاً من context.bot)
        title = context.user_data.get('last_info', {}).get('title', 'Video')
        await db.add_to_history(context.application, query.from_user.id, url, title)
        
        # حذف رسالة التحميل
        try: await context.bot.delete_message(query.message.chat_id, query.message.message_id)
        except: pass

        with open(filename, "rb") as f:
            thumb = None
            # محاولة جلب الصورة المصغرة للصوت
            if mode_key == "audio" and context.user_data.get('last_info', {}).get('thumbnail'):
                try:
                    r = requests.get(context.user_data['last_info']['thumbnail'], stream=True)
                    if r.status_code == 200: thumb = BytesIO(r.content)
                except: pass
            
            # التحقق من الحجم: نسخة احتياطية للقناة إذا كان كبيراً
            if file_size > MAX_FILE_SIZE:
                await context.bot.send_message(query.message.chat_id, "📦 الملف كبير جداً، جاري الرفع للسحابة...")
                
                # رفع الملف للقناة
                sent_msg = await context.bot.send_video(LOG_CHANNEL_ID, f, caption=f"Backup: {title}")
                
                # إنشاء رابط للقناة (يجب أن يكون المستخدم مشتركاً)
                file_link = f"https://t.me/c/{str(LOG_CHANNEL_ID)[4:]}/{sent_msg.message_id}"
                
                await context.bot.send_message(
                    query.message.chat_id, 
                    f"✅ **تم التحميل في السحابة!**\n🔗 [اضغط هنا للتحميل]({file_link})\n\n📏 الحجم: {format_file_size(file_size)}",
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
        await query.edit_message_text(f"❌ فشل التحميل.\n\nالخطأ: {str(e)[:200]}")

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

# ==================== الأخطاء ====================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")
