import json
import logging
import asyncio
from typing import Dict, List
from io import BytesIO

from config import LOG_CHANNEL_ID

logger = logging.getLogger(__name__)

HISTORY_FILENAME = "history.json"
# التخزين المؤقت في الذاكرة
user_history: Dict[int, List[dict]] = {}

async def init_db(bot):
    """تحميل البيانات من القناة عند بدء التشغيل"""
    global user_history
    if not LOG_CHANNEL_ID:
        logger.warning("LOG_CHANNEL_ID not set, skipping DB init.")
        return

    try:
        logger.info("🔍 Searching for history database in channel...")
        # البحث عن آخر 10 رسائل للعثور على ملف التاريخ
        async for message in bot.get_chat_history(chat_id=LOG_CHANNEL_ID, limit=10):
            if message.document and message.document.file_name == HISTORY_FILENAME:
                # تم العثور على الملف، تحميله
                file = await message.document.get_file()
                content = await file.download_as_bytearray()
                user_history = json.loads(content.decode('utf-8'))
                logger.info(f"✅ History loaded from channel. Users: {len(user_history)}")
                return
        
        # إذا لم يتم العثور عليه
        logger.info("🆔 No history file found in channel. Starting with empty DB.")
        user_history = {}

    except Exception as e:
        logger.error(f"❌ Failed to load history: {e}")
        user_history = {}

async def add_to_history(bot, user_id: int, url: str, title: str):
    """إضافة عملية تحميل وتحديث القناة"""
    global user_history
    if not LOG_CHANNEL_ID:
        return

    user_id_str = str(user_id)
    if user_id_str not in user_history:
        user_history[user_id_str] = []
    
    # إضافة جديد
    user_history[user_id_str].insert(0, {"url": url, "title": title})
    
    # الاحتفاظ بآخر 10 فقط
    if len(user_history[user_id_str]) > 10:
        user_history[user_id_str] = user_history[user_id_str][:10]
    
    # حفظ التغييرات في القناة
    try:
        json_data = json.dumps(user_history)
        f = BytesIO(json_data.encode('utf-8'))
        f.name = HISTORY_FILENAME
        
        # إرسال الملف الجديد للقناة
        await bot.send_document(LOG_CHANNEL_ID, document=f, caption="🔄 Updated Database")
        logger.info(f"✅ History saved for user {user_id}")
    except Exception as e:
        logger.error(f"❌ Failed to save history: {e}")

def get_history(user_id: int) -> List[dict]:
    """جلب السجل من الذاكرة"""
    return user_history.get(str(user_id), [])
