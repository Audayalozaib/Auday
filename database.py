import json
import logging
import asyncio
from typing import Dict, List
from io import BytesIO

from config import LOG_CHANNEL_ID

logger = logging.getLogger(__name__)

HISTORY_FILENAME = "history.json"
user_history: Dict[int, List[dict]] = {}

async def init_db(application):
    """تحميل البيانات من القناة عند بدء التشغيل"""
    global user_history
    if not LOG_CHANNEL_ID:
        logger.warning("LOG_CHANNEL_ID not set, skipping DB init.")
        return

    try:
        bot = application.bot
        
        # التحقق مما إذا كانت المكتبة تدعم هذه الدالة (للنسخ القديمة)
        if not hasattr(bot, 'get_chat_history'):
            logger.error("⚠️ إصدار python-telegram-bot قديم جداً ولا يدعم جلب السجل.")
            logger.error("⚠️ يرجى تحديث requirements.txt. تعطيل قاعدة البيانات حالياً.")
            user_history = {}
            return

        logger.info("🔍 Searching for history database in channel...")
        
        # استخدام bot.get_chat_history بشكل صحيح
        async for message in bot.get_chat_history(chat_id=LOG_CHANNEL_ID, limit=20):
            if message.document and message.document.file_name == HISTORY_FILENAME:
                file = await message.document.get_file()
                content = await file.download_as_bytearray()
                user_history = json.loads(content.decode('utf-8'))
                logger.info(f"✅ History loaded from channel. Users: {len(user_history)}")
                return
        
        logger.info("🆔 No history file found in channel. Starting with empty DB.")
        user_history = {}

    except Exception as e:
        logger.error(f"❌ Failed to load history: {e}")
        # في حالة الفشل، نبدأ بقاعدة بيانات فارغة لكي لا يتوقف البوت
        user_history = {}

async def add_to_history(application, user_id: int, url: str, title: str):
    """إضافة عملية تحميل وتحديث القناة"""
    global user_history
    if not LOG_CHANNEL_ID:
        return

    user_id_str = str(user_id)
    if user_id_str not in user_history:
        user_history[user_id_str] = []
    
    user_history[user_id_str].insert(0, {"url": url, "title": title})
    if len(user_history[user_id_str]) > 10:
        user_history[user_id_str] = user_history[user_id_str][:10]
    
    try:
        json_data = json.dumps(user_history)
        f = BytesIO(json_data.encode('utf-8'))
        f.name = HISTORY_FILENAME
        
        # استخدام application.bot.send_document
        await application.bot.send_document(LOG_CHANNEL_ID, document=f, caption="🔄 Updated Database")
        logger.info(f"✅ History saved for user {user_id}")
    except Exception as e:
        logger.error(f"❌ Failed to save history: {e}")

def get_history(user_id: int) -> List[dict]:
    return user_history.get(str(user_id), [])
