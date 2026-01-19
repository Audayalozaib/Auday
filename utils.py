import os
import re
import logging
import shutil
import tempfile
import glob
import datetime
import asyncio
from typing import Optional, Dict, Any, Tuple
from concurrent.futures import ThreadPoolExecutor

import yt_dlp

from config import (
    MAX_FILE_SIZE, MAX_DURATION, FFMPEG_PATH, 
    FFPROBE_PATH, MAX_CONCURRENT_DOWNLOADS, LOG_CHANNEL_ID
)

logger = logging.getLogger(__name__)

active_downloads: Dict[int, Dict[str, Any]] = {}
executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_DOWNLOADS)

# ==================== إعدادات yt-dlp المحسنة (وضع Android) ====================
YDL_OPTIONS_BASE = {
    "quiet": True,
    "no_warnings": True,
    # تظاهر بأنك تطبيق يوتيوب على أندرويد (تجاوز ناجح للحظر)
    "user_agent": "com.google.android.youtube/17.36.4 (Linux; U; Android 12; GB) gzip",
    "referer": "https://www.google.com/",
    "concurrent_fragment_downloads": 3, # تقليل التحميل المتزامن لتجنب الحظر
    "retries": 10,
    "fragment_retries": 10,
    "retry_sleep": lambda x: min(30, 2 ** x),
    # استكمال التحميل
    "continuedl": True,
    "nooverwrites": True,
    "extractor_args": {
        "youtube": {
            "player_client": ["android"], # إجبار استخدام عميل أندرويد
            "skip": ["hls", "dash"],
            "max_comments": 0,
        }
    },
    "postprocessor_args": {
        "ffmpeg": ["-avoid_negative_ts", "make_zero"]
    }
}

def get_ydl_options(mode: str, user_id: int) -> dict:
    opts = YDL_OPTIONS_BASE.copy()
    
    ffmpeg_abs_path = shutil.which("ffmpeg")
    if ffmpeg_abs_path:
        opts["ffmpeg_location"] = ffmpeg_abs_path
    
    opts["prefer_ffmpeg"] = True
    opts["hls_prefer_native"] = True
    temp_dir = tempfile.gettempdir()
    os.makedirs(temp_dir, exist_ok=True)
    file_prefix = os.path.join(temp_dir, f"dl_{user_id}_{int(datetime.datetime.now().timestamp())}")
    
    # إذا قمت بإضافة متغير HTTP_PROXY في Railway لاحقاً فسيتم تفعيله تلقائياً
    proxy_url = os.getenv("HTTP_PROXY")
    if proxy_url:
        opts["proxy"] = proxy_url
        logger.info(f"✅ Using Proxy: {proxy_url}")
    
    if mode == "info":
        opts["download"] = False
        return opts

    if mode == "video":
        opts.update({
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "merge_output_format": "mp4",
            "outtmpl": f"{file_prefix}.%(ext)s",
            "max_filesize": MAX_FILE_SIZE,
            "postprocessors": [
                {"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"},
                {"key": "FFmpegMetadata"},
            ],
        })
    elif mode == "audio":
        opts.update({
            "format": "bestaudio/best",
            "outtmpl": f"{file_prefix}.%(ext)s",
            "max_filesize": MAX_FILE_SIZE,
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"},
                {"key": "FFmpegMetadata"},
                {"key": "EmbedThumbnail"}
            ],
        })
    
    return opts

def validate_url(url: str) -> Optional[str]:
    url = url.strip()
    patterns = [
        r"^https?://(www\.)?youtube\.com/", r"^https?://youtu\.be/",
        r"^https?://(www\.)?tiktok\.com/", r"^https?://(www\.)?instagram\.com/",
        r"^https?://(www\.)?twitter\.com/", r"^https?://(www\.)?x\.com/",
        r"^https?://(www\.)?facebook\.com/", r"^https?://(www\.)?pinterest\.com/",
        r"^https?://soundcloud\.com/", 
    ]
    for pattern in patterns:
        if re.match(pattern, url): return url
    return None

def format_file_size(size_bytes: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024: return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f}TB"

def cleanup_files(*file_paths: str) -> None:
    for path in file_paths:
        try:
            if path and os.path.exists(path): os.remove(path)
        except: pass

def download_media(url: str, mode: str, user_id: int) -> Tuple[str, int]:
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
                    raise Exception("File not found after download.")
            
            if os.path.exists(filename):
                return filename, os.path.getsize(filename)
            raise Exception("File generation failed.")
            
    except Exception as e:
        logger.error(f"Download error: {e}")
        if filename: cleanup_files(filename)
        raise

def get_smart_buttons(url: str):
    from telegram import InlineKeyboardButton
    if "soundcloud.com" in url or "spotify.com" in url:
        return [[InlineKeyboardButton("🎵 MP3", callback_data=f"aud|{url}")]]
    elif "tiktok.com" in url:
        return [[InlineKeyboardButton("🎬 بدون علامة مائية", callback_data=f"vid|{url}")]]
    else:
        return [
            [InlineKeyboardButton("🎬 MP4", callback_data=f"vid|{url}"),
             InlineKeyboardButton("🎵 MP3", callback_data=f"aud|{url}")],
            [InlineKeyboardButton("📂 رابط مباشر", callback_data=f"url|{url}")]
        ]
