import os
import re
import logging
import shutil
import tempfile
import glob
import datetime
from typing import Optional, Dict, Any

import yt_dlp

# استيراد الإعدادات
from config import (
    MAX_FILE_SIZE, MAX_DURATION, FFMPEG_PATH, 
    FFPROBE_PATH, MAX_CONCURRENT_DOWNLOADS
)

logger = logging.getLogger(__name__)

# حالة النظام المشتركة
active_downloads: Dict[int, Dict[str, Any]] = {}
download_lock = ... # سيتم تعريفه في main أو يمكن استخدام asyncio.Lock() عام
executor = ... # سيتم تعريفه في main

# ==================== إعدادات yt-dlp ====================
YDL_OPTIONS_BASE = {
    "quiet": True,
    "no_warnings": True,
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "referer": "https://www.google.com/",
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

def get_ydl_options(mode: str, user_id: int) -> dict:
    """إنشاء خيارات yt-dlp"""
    opts = YDL_OPTIONS_BASE.copy()
    
    ffmpeg_abs_path = shutil.which("ffmpeg")
    ffprobe_abs_path = shutil.which("ffprobe")
    
    if ffmpeg_abs_path:
        opts["ffmpeg_location"] = ffmpeg_abs_path
        opts["ffprobe_location"] = ffprobe_abs_path
    
    opts["prefer_ffmpeg"] = True
    opts["hls_prefer_native"] = True

    # استخدام مجلد مؤقت
    temp_dir = tempfile.gettempdir()
    os.makedirs(temp_dir, exist_ok=True)
    file_prefix = os.path.join(temp_dir, f"dl_{user_id}_{int(datetime.datetime.now().timestamp())}")
    
    if mode == "info":
        opts["download"] = False
        return opts

    if mode == "video":
        opts.update({
            "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
            "merge_output_format": "mp4",
            "outtmpl": f"{file_prefix}.%(ext)s",
            "max_filesize": MAX_FILE_SIZE,
            "postprocessors": [{"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}],
        })
    elif mode == "audio":
        opts.update({
            "format": "bestaudio/best",
            "outtmpl": f"{file_prefix}.%(ext)s",
            "max_filesize": MAX_FILE_SIZE,
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"},
                {"key": "FFmpegMetadata"}
            ],
        })
    elif mode == "short":
        opts.update({
            "format": "best[height<=720]",
            "outtmpl": f"{file_prefix}.%(ext)s",
            "max_filesize": MAX_FILE_SIZE,
        })
    
    return opts

def validate_url(url: str) -> Optional[str]:
    """التحقق من صحة الرابط"""
    url = url.strip()
    patterns = [
        r"^https?://(www\.)?youtube\.com/", r"^https?://youtu\.be/",
        r"^https?://(www\.)?tiktok\.com/", r"^https?://(www\.)?instagram\.com/",
        r"^https?://(www\.)?twitter\.com/", r"^https?://(www\.)?x\.com/",
        r"^https?://(www\.)?facebook\.com/", r"^https?://(www\.)?pinterest\.com/",
    ]
    for pattern in patterns:
        if re.match(pattern, url): return url
    return None

def format_file_size(size_bytes: int) -> str:
    """تنسيق حجم الملف"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024: return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f}TB"

def cleanup_files(*file_paths: str) -> None:
    """حذف الملفات المؤقتة"""
    for path in file_paths:
        try:
            if path and os.path.exists(path): os.remove(path)
        except Exception as e:
            logger.warning(f"Failed to cleanup {path}: {e}")

def download_media(url: str, mode: str, user_id: int) -> tuple:
    """دالة التحميل الأساسية (تعمل في Thread)"""
    filename = None
    try:
        ydl_opts = get_ydl_options(mode, user_id)
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            temp_template = ydl.prepare_filename(info)
            ydl.extract_info(url, download=True)
            
            filename = None
            target_ext = ".mp3" if mode == "audio" else ".mp4"
            
            if os.path.exists(temp_template.rsplit(".", 1)[0] + target_ext):
                filename = temp_template.rsplit(".", 1)[0] + target_ext
            else:
                temp_dir = tempfile.gettempdir()
                possible_files = glob.glob(f"{temp_dir}/dl_{user_id}_*")
                if possible_files:
                    filename = max(possible_files, key=os.path.getctime)
                else:
                    raise Exception("No files found.")
            
            if os.path.exists(filename):
                return filename, os.path.getsize(filename)
            raise Exception("File generation failed.")
            
    except Exception as e:
        logger.error(f"Download error: {e}")
        if filename: cleanup_files(filename)
        raise
