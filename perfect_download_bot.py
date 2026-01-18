"""
🎬 بوت تحميل الوسائط المثالي (نسخة السحابة)
================================
يدعم: YouTube, TikTok, Instagram, Twitter, Facebook, Pinterest + 1700+ موقع
"""

import os
import re
import asyncio
import logging
import tempfile
import traceback
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InputTextMessageContent,
    constants
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    InlineQueryHandler,
    ContextTypes,
    filters,
    JobQueue
)
from telegram.error import (
    TelegramError,
    RetryAfter,
    BadRequest,
    Forbidden
)
import yt_dlp

# ==================== إعداد البيئة ====================
load_dotenv()

# ==================== الإعدادات ====================
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ يجب تعيين BOT_TOKEN في المتغيرات البيئية")

# حدود البوت
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
MAX_DURATION = 1800  # 30 دقيقة
MAX_CONCURRENT_DOWNLOADS = 3
DOWNLOAD_TIMEOUT = 300  # 5 دقائق

# مسارات الأدوات (سيتم البحث عنها تلقائياً في النظام/Docker)
FFMPEG_PATH = "ffmpeg"
FFPROBE_PATH = "ffprobe"

# إعدادات المطوّر
DEVELOPER_ID = int(os.getenv("DEVELOPER_ID", "0"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "0"))

# ==================== إعداد التسجيل ====================
logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)

# تقليل تسجيل httpx
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("yt_dlp").setLevel(logging.WARNING)

# ==================== حالة التنزيل النشط ====================
active_downloads: Dict[int, Dict[str, Any]] = {}
download_lock = asyncio.Lock()
executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_DOWNLOADS)

# تعريف start_time كمتغير عام
start_time = datetime.now()

# ==================== إعدادات yt-dlp ====================
YDL_OPTIONS_BASE = {
    "quiet": True,
    "no_warnings": True,
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "referer": "https://www.google.com/",
    # سيتم تحديد المسار داخل get_ydl_options
    "concurrent_fragment_downloads": 5,
    "retries": 5,
    "fragment_retries": 5,
    "retry_sleep": lambda x: min(30, 2 ** x),
    "extractor_args": {
        "youtube": {
            "player_client": ["android", "web"],
            "skip": ["hls", "dash"],
            "max_comments": 0,
        }
    },
    "postprocessor_args": {
        "ffmpeg": ["-avoid_negative_ts", "make_zero"]
    }
}

def get_ydl_options(mode: str, url: str, user_id: int) -> dict:
    """إنشاء خيارات yt-dlp بناءً على وضع التحميل"""
    # 1. نسخ الخيارات الأساسية
    opts = YDL_OPTIONS_BASE.copy()
    
    # 2. تحديد مسار FFmpeg (سيقوم النظام بإيجاده في Docker/Railway)
    ffmpeg_abs_path = shutil.which("ffmpeg")
    ffprobe_abs_path = shutil.which("ffprobe")
    
    if ffmpeg_abs_path:
        opts["ffmpeg_location"] = ffmpeg_abs_path
        opts["ffprobe_location"] = ffprobe_abs_path
        logger.info(f"✅ FFmpeg found at: {ffmpeg_abs_path}")
    else:
        logger.error("❌ FFmpeg not found! Make sure it's installed.")
    
    # 3. أوامر إجبارية لضمان التحويل
    opts["prefer_ffmpeg"] = True
    opts["hls_prefer_native"] = True

    # 4. إعداد مسار التخزين المؤقت (متوافق مع Linux السحابي)
    # استخدام /tmp في Railway أو مجلد النظام المؤقت
    temp_dir = tempfile.gettempdir()
    os.makedirs(temp_dir, exist_ok=True)
    
    file_prefix = os.path.join(temp_dir, f"dl_{user_id}_{int(datetime.now().timestamp())}")
    
    if mode == "info":
        opts["download"] = False
        return opts

    if mode == "video":
        opts.update({
            "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
            "merge_output_format": "mp4",
            "outtmpl": f"{file_prefix}.%(ext)s",
            "max_filesize": MAX_FILE_SIZE,
            "postprocessors": [{
                "key": "FFmpegVideoRemuxer",
                "preferedformat": "mp4",
            }],
        })
    elif mode == "audio":
        opts.update({
            "format": "bestaudio/best",
            "outtmpl": f"{file_prefix}.%(ext)s",
            "max_filesize": MAX_FILE_SIZE,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }, {
                "key": "FFmpegMetadata",
            }],
        })
    elif mode == "short":
        opts.update({
            "format": "best[height<=720]",
            "outtmpl": f"{file_prefix}.%(ext)s",
            "max_filesize": MAX_FILE_SIZE,
        })
    
    return opts

# ==================== دوال مساعدة ====================
def validate_url(url: str) -> Optional[str]:
    """التحقق من صحة الرابط"""
    url = url.strip()
    
    patterns = [
        r"^https?://(www\.)?youtube\.com/",
        r"^https?://youtu\.be/",
        r"^https?://(www\.)?tiktok\.com/",
        r"^https?://(www\.)?instagram\.com/",
        r"^https?://(www\.)?twitter\.com/",
        r"^https?://(www\.)?x\.com/",
        r"^https?://(www\.)?facebook\.com/",
        r"^https?://(www\.)?pinterest\.com/",
        r"^https?://(www\.)?reddit\.com/",
    ]
    
    for pattern in patterns:
        if re.match(pattern, url):
            return url
    
    return None

def format_file_size(size_bytes: int) -> str:
    """تنسيق حجم الملف"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f}TB"

def cleanup_files(*file_paths: str) -> None:
    """حذف الملفات المؤقتة"""
    for path in file_paths:
        try:
            if path and os.path.exists(path):
                os.remove(path)
                logger.debug(f"Cleaned up: {path}")
        except Exception as e:
            logger.warning(f"Failed to cleanup {path}: {e}")

# ==================== المعالجات ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """أمر /start"""
    user = update.effective_user
    logger.info(f"User {user.id} (@{user.username}) started the bot")
    
    welcome_text = f"""
👋 **أهلاً بك يا {user.first_name}!**

🎬 **بوت التحميل المثالي** supports تحميل الوسائط من:

📌 **YouTube** - فيديو/صوت/قوائم
📌 **TikTok** - فيديو بدون علامة مائية
📌 **Instagram** - ريلز/ستوريز/منشورات
📌 **Twitter/X** - فيديو/صور GIF
📌 **Facebook** - فيديو/REELs
📌 **Pinterest** - صور/PINs
📌 **Reddit** - فيديو/صور

━━━━━━━━━━━━━━━━━━━━━
🔗 **طريقة الاستخدام:**
1️⃣ أرسل رابط الفيديو
2️⃣ اختر الصيغة المطلوبة
3️⃣ استمتع بالتحميل!

━━━━━━━━━━━━━━━━━━━━━
⚠️ **قيود:**
• الحد الأقصى: 50MB
• المدة القصوى: 30 دقيقة
    """
    
    await update.message.reply_text(welcome_text, parse_mode=constants.ParseMode.MARKDOWN)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """أمر /help"""
    help_text = """
📖 **مساعدة بوت التحميل**

**الأوامر المتاحة:**
• `/start` - بدء البوت
• `/help` - عرض هذه المساعدة
• `/status` - حالة البوت

**المواقع المدعومة:**
✓ YouTube, TikTok, Instagram
✓ Twitter, Facebook, Pinterest
✓ Reddit, LinkedIn, Vimeo
✓ +1700 موقع آخر!

**نصائح:**
• شارك رابط منشور كامل للحصول على أفضل نتيجة
• للفيديوهات الطويلة، سيتم اقتصاصها تلقائياً
• يدعم تحميل الفيديو بصيغة MP4 أو الصوت MP3
    """
    
    await update.message.reply_text(help_text, parse_mode=constants.ParseMode.MARKDOWN)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """عرض حالة البوت"""
    async with download_lock:
        active_count = len(active_downloads)
    
    uptime = datetime.now() - start_time
    
    status_text = f"""
📊 **حالة البوت**

🟢 **الحالة:** يعمل بشكل طبيعي
📥 **التنزيلات النشطة:** {active_count}/{MAX_CONCURRENT_DOWNLOADS}
⏱️ **الحد الأقصى للمدة:** {MAX_DURATION // 60} دقيقة
📦 **الحد الأقصى للحجم:** {format_file_size(MAX_FILE_SIZE)}

**إحصائيات:**
• وقت التشغيل: {uptime}
    """
    
    await update.message.reply_text(status_text, parse_mode=constants.ParseMode.MARKDOWN)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """استقبال الروابط والرسائل"""
    if not update.message or not update.message.text:
        return
    
    user = update.effective_user
    url = update.message.text.strip()
    
    if url.startswith('/'):
        return
    
    valid_url = validate_url(url)
    if not valid_url:
        await update.message.reply_text(
            "❌ **رابط غير مدعوم!**\n\n"
            "يرجى إرسال رابط من أحد المواقع المدعومة:\n"
            "• YouTube • TikTok • Instagram\n"
            "• Twitter • Facebook • Pinterest"
        )
        return
    
    logger.info(f"User {user.id} sent URL: {valid_url[:50]}...")
    
    status_msg = await update.message.reply_text(
        "🔍 **جاري فحص الرابط...**"
    )
    
    try:
        with yt_dlp.YoutubeDL(get_ydl_options("info", valid_url, user.id)) as ydl:
            info = ydl.extract_info(valid_url, download=False)
        
        filesize = info.get("filesize") or info.get("filesize_approx") or 0
        if filesize > MAX_FILE_SIZE:
            await status_msg.edit_text(
                f"⛔ **الملف كبير جداً!**\n\n"
                f"📏 الحجم: {format_file_size(filesize)}\n"
                f"📦 الحد الأقصى: {format_file_size(MAX_FILE_SIZE)}"
            )
            return
        
        duration = info.get("duration", 0)
        if duration > MAX_DURATION:
            await status_msg.edit_text(
                f"⛔ **الفيديو طويل جداً!**\n\n"
                f"⏱️ المدة: {duration // 60}:{duration % 60:02d}\n"
                f"⏱️ الحد الأقصى: {MAX_DURATION // 60} دقيقة"
            )
            return
        
        title = info.get("title", 'فيديو')[:100]
        thumbnail = info.get("thumbnail")
        uploader = info.get("uploader", 'Unknown')
        view_count = info.get("view_count", 0)
        
        keyboard = [
            [
                InlineKeyboardButton("🎬 فيديو MP4", callback_data=f"vid|{valid_url}"),
                InlineKeyboardButton("🎵 صوت MP3", callback_data=f"aud|{valid_url}")
            ]
        ]
        
        info_text = f"""
✅ **تم العثور على الفيديو!**

📌 **العنوان:** {title}
👤 **المستخدم:** {uploader}
👁️ **المشاهدات:** {view_count:,}
📏 **الحجم:** {format_file_size(filesize)}
⏱️ **المدة:** {duration // 60}:{duration % 60:02d}

━━━━━━━━━━━━━━━━━━━━━
🎯 **اختر الصيغة:**
        """
        
        await status_msg.edit_text(
            info_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=constants.ParseMode.MARKDOWN
        )
        
        context.user_data['last_video_info'] = {
            'title': title,
            'thumbnail': thumbnail
        }
        
    except yt_dlp.utils.DownloadError as e:
        logger.error(f"Download error: {e}")
        await status_msg.edit_text(
            f"❌ **تعذر استخراج المعلومات**\n\n"
            f"السبب: {str(e)[:200]}"
        )
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        await status_msg.edit_text(
            "❌ **حدث خطأ غير متوقع!**\n\n"
            "يرجى المحاولة مرة أخرى لاحقاً"
        )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """معالجة أزرار التحميل"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    chat_id = query.message.chat_id
    message_id = query.message.message_id
    
    async with download_lock:
        if len(active_downloads) >= MAX_CONCURRENT_DOWNLOADS:
            await query.edit_message_text(
                "⏳ **البوت مشغول حالياً!**\n\n"
                f"الحد الأقصى: {MAX_CONCURRENT_DOWNLOADS} تحميلات متزامنة\n"
                "يرجى المحاولة بعد قليل..."
            )
            return
        active_downloads[user.id] = {'started_at': datetime.now()}
    
    try:
        mode, url = query.data.split("|", 1)
    except ValueError:
        await query.edit_message_text("❌ بيانات غير صالحة!")
        return
    
    mode_map = {
        'vid': ('فيديو', 'video'),
        'aud': ('صوت', 'audio')
    }
    mode_name, mode_key = mode_map.get(mode, ('ملف', 'video'))
    
    logger.info(f"User {user.id} downloading {mode_name} from {url[:30]}...")
    
    await query.edit_message_text(
        f"⏳ **جاري تحميل {mode_name}...**\n\n"
        "📥 يتم الآن استخراج الفيديو من المصدر...\n"
        "قد يستغرق هذا بعض الوقت حسب حجم الفيديو"
    )
    
    video_info = context.user_data.get('last_video_info', {})
    title = video_info.get('title', 'فيديو')
    thumbnail = video_info.get('thumbnail')
    
    filename = None
    file_size = 0
    
    try:
        loop = asyncio.get_event_loop()
        
        result = await loop.run_in_executor(
            executor,
            download_media,
            url,
            mode_key,
            user.id,
            title
        )
        
        filename, file_size = result
        
        if not filename or not os.path.exists(filename):
            raise Exception("لم يتم إنشاء الملف")
        
        if os.path.getsize(filename) > MAX_FILE_SIZE:
            cleanup_files(filename)
            await query.edit_message_text(
                "⛔ **الملف الناتج أكبر من 50MB!**\n\n"
                "جرب تحميل صيغة مختلفة أو فيديو أقصر"
            )
            return
        
        try:
            await context.bot.delete_message(chat_id, message_id)
        except:
            pass
        
        with open(filename, "rb") as f:
            if mode_key == "audio":
                thumb_file = None
                # محاولة تحميل الصورة المصغرة للصوت
                if thumbnail:
                     try:
                         import requests
                         r = requests.get(thumbnail, stream=True)
                         if r.status_code == 200:
                             from io import BytesIO
                             thumb_file = BytesIO(r.content)
                     except:
                         pass

                await context.bot.send_audio(
                    chat_id=chat_id,
                    audio=f,
                    title=title,
                    performer="🎵 البوت",
                    caption=f"🎵 {title}\n\n📥 تحميل بواسطة @{(await context.bot.get_me()).username}",
                    thumbnail=thumb_file # تم التصحيح: thumbnail
                )
                if thumb_file: thumb_file.close()
            else:
                await context.bot.send_video(
                    chat_id=chat_id,
                    video=f,
                    caption=f"🎬 {title}\n\n📥 تحميل بواسطة @{(await context.bot.get_me()).username}",
                )
        
        logger.info(f"User {user.id} successfully downloaded {mode_name}")
        
        success_msg = await context.bot.send_message(
            chat_id=chat_id,
            text=f"✅ **تم تحميل {mode_name} بنجاح!**\n\n📏 الحجم: {format_file_size(file_size)}"
        )
        
        context.job_queue.run_once(
            lambda ctx: ctx.bot.delete_message(chat_id, success_msg.message_id),
            when=10,
            name=f"cleanup_{user.id}_{datetime.now().timestamp()}"
        )
        
    except RetryAfter as e:
        logger.warning(f"Rate limited, retry after {e.retry_after}s")
        await query.edit_message_text(
            f"⏳ **مطلوب انتظار...**\n\n"
            f"يرجى الانتظار {e.retry_after} ثانية ثم المحاولة"
        )
    except BadRequest as e:
        logger.error(f"Bad request: {e}")
        if "Message is not modified" not in str(e):
            await query.edit_message_text(
                f"❌ **خطأ في الطلب:**\n\n{str(e)[:200]}"
            )
    except Exception as e:
        logger.error(f"Download failed: {e}", exc_info=True)
        error_text = str(e).lower()
        
        if "content" in error_text and "stretch" in error_text:
            msg = "❌ **فشل في معالجة الفيديو!**\n\nالفيديو قد يكون محمياً أو غير متاح للتحميل"
        elif "ffmpeg" in error_text:
            msg = "❌ **خطأ في معالجة الوسائط!**\n\nمشكلة في برنامج التحويل، يرجى المحاولة لاحقاً"
        elif "not found" in error_text or "404" in error_text:
            msg = "❌ **الفيديو غير متاح!**\n\nالفيديو قد يكون محذوفاً أو خاصاً"
        else:
            msg = f"❌ **فشل التحميل!**\n\n{str(e)[:150]}"
        
        await query.edit_message_text(msg)
    
    finally:
        if filename:
            cleanup_files(filename)
        async with download_lock:
            active_downloads.pop(user.id, None)

def download_media(url: str, mode: str, user_id: int, title: str) -> tuple:
    """تحميل الوسائط (يُنفذ في ThreadPool)"""
    import glob
    
    filename = None
    try:
        ydl_opts = get_ydl_options(mode, url, user_id)
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            temp_template = ydl.prepare_filename(info)
            
            ydl.extract_info(url, download=True)
            
            filename = None
            target_ext = ".mp3" if mode == "audio" else ".mp4"
            
            # 1. البحث عن الملف المحول
            if os.path.exists(temp_template.rsplit(".", 1)[0] + target_ext):
                filename = temp_template.rsplit(".", 1)[0] + target_ext
            
            # 2. إذا لم يجده، ابحث عن أي ملف حديث لهذا المستخدم
            if not filename:
                temp_dir = tempfile.gettempdir()
                possible_files = glob.glob(f"{temp_dir}/dl_{user_id}_*")
                if possible_files:
                    filename = max(possible_files, key=os.path.getctime)
                    logger.warning(f"Expected converted file but found: {filename}")
                else:
                    raise Exception("No files found in temp directory after download.")

            if os.path.exists(filename):
                file_size = os.path.getsize(filename)
                logger.info(f"Downloaded file size: {file_size} bytes at {filename}")
                return filename, file_size
        
        raise Exception("Download process finished but no file generated.")

    except Exception as e:
        logger.error(f"Download error in thread: {e}")
        if filename and os.path.exists(filename):
            cleanup_files(filename)
        raise

# ==================== البحث بالإنلاين ====================
async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """البحث بالإنلاين"""
    query = update.inline_query.query.strip()
    if not query or len(query) < 3:
        return
    
    logger.info(f"Inline query from {update.inline_query.from_user.id}: {query[:30]}...")
    
    results = []
    
    try:
        search_opts = YDL_OPTIONS_BASE.copy()
        search_opts["extract_flat"] = True
        search_opts["max_downloads"] = 5
        
        with yt_dlp.YoutubeDL(search_opts) as ydl:
            search_results = ydl.extract_info(f"ytsearch5:{query}", download=False)
            
            for i, video in enumerate(search_results.get("entries", [])[:5]):
                results.append(
                    InlineQueryResultArticle(
                        id=str(i),
                        title=video.get("title", 'فيديو')[:100],
                        input_message_content=InputTextMessageContent(
                            video.get("url", ''),
                            parse_mode=constants.ParseMode.MARKDOWN
                        ),
                        description=f"{video.get('uploader', '')} | {video.get('duration', '')}",
                        thumb_url=video.get("thumbnail")
                    )
                )
    
    except Exception as e:
        logger.error(f"Inline search error: {e}")
    
    await update.inline_query.answer(results, cache_time=300)

# ==================== معالج الأخطاء ====================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """معالج الأخطاء العام"""
    error = context.error
    
    logger.error(
        "Exception while handling update",
        exc_info=(error if not isinstance(error, TelegramError) else None)
    )
    
    if isinstance(error, BadRequest):
        if "Message is not modified" in str(error):
            return
        if "Message to edit not found" in str(error):
            return
    
    if DEVELOPER_ID != 0:
        try:
            tb = ''.join(traceback.format_exception(type(error), error, error.__traceback__))
            error_text = f"""
🚨 **خطأ في البوت**

**الخطأ:** `{type(error).__name__}`
**الرسالة:** {str(error)[:500]}

**Traceback:**            """
            
            await context.bot.send_message(
                chat_id=DEVELOPER_ID,
                text=error_text,
                parse_mode=constants.ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Failed to notify developer: {e}")

# ==================== دالة التنظيف التلقائي ====================
async def cleanup_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """تنظيف الملفات القديمة والمتحميلات المعلقة"""
    async with download_lock:
        now = datetime.now()
        
        stale = [
            uid for uid, data in active_downloads.items()
            if (now - data['started_at']).total_seconds() > 1800
        ]
        for uid in stale:
            active_downloads.pop(uid, None)
            logger.warning(f"Removed stale download for user {uid}")

# ==================== تشغيل البوت ====================
def main() -> None:
    """تشغيل البوت - نسخة محسنة ومستقرة"""
    logger.info("🚀 Starting Media Downloader Bot...")
    
    # التحقق من FFmpeg
    if shutil.which("ffmpeg"):
        logger.info("✅ FFmpeg is installed and ready.")
    else:
        logger.warning("⚠️ FFmpeg NOT found! Make sure it's installed via Dockerfile or system package manager.")

    # بناء التطبيق
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .concurrent_updates(True)
        .build()
    )
    
    # تسجيل المعالجات
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & ~filters.FORWARDED,
            handle_message
        )
    )
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(InlineQueryHandler(inline_query))
    app.add_error_handler(error_handler)
    
    # إضافة مهمة التنظيف
    app.job_queue.run_repeating(cleanup_job, interval=300, first=60)

    logger.info("✅ Bot setup complete. Starting connection...")
    
    try:
        app.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
    except Exception as e:
        logger.error(f"💥 Bot crashed with error: {e}", exc_info=True)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user (Ctrl+C)")
    except Exception as e:
        logger.error(f"💥 Fatal error in main execution: {e}", exc_info=True)
