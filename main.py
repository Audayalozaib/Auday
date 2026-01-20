import os
import asyncio
import logging
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait, UserBannedInChannel

# ====================================================================
# متغيرات البيئة (Environment Variables)
# في Railway ستضع هذه القيم في قسم Variables
# ====================================================================

# البيانات الأساسية من my.telegram.org
API_ID = int(os.environ.get("API_ID", 6825462))
API_HASH = os.environ.get("API_HASH", "3b3cb233c159b6f48798e10c4b5fdc83")

# بيانات البوت من @BotFather
BOT_TOKEN = os.environ.get("BOT_TOKEN", "6741306329:AAF9gyhoD_li410vEdu62s7WlhZVVpKJu58")

# كود الجلسة (String Session) الذي حصلت عليه من الخطوة 1
STRING_SESSION = os.environ.get("STRING_SESSION", "")

# معرف القناة التي سيرفع إليها اليوزر بوت
TARGET_CHANNEL_ID = int(os.environ.get("TARGET_CHANNEL_ID", -1002064206339))

# معرف المشرف (IDك الشخصي) ليكون البوت مخصص لك فقط (أحذله لجعله عاماً)
OWNER_ID = int(os.environ.get("OWNER_ID", 778375826))

# ====================================================================
# تهيئة العملاء
# ====================================================================
# 1. اليوزر بوت (يستخدم String Session)
user_bot = Client(
    name="user_bot_session",
    session_string=STRING_SESSION,
    api_id=API_ID,
    api_hash=API_HASH,
    no_updates=True  # لتقليل الاستهلاك
)

# 2. البوت المتحكم
controller_bot = Client(
    name="bot_controller",
    bot_token=BOT_TOKEN,
    api_id=API_ID,
    api_hash=API_HASH
)

# التخزين المؤقت للنتائج
search_results = {}

# ====================================================================
# الوظائف المساعدة
# ====================================================================

async def search_content(query: str):
    """بحث باستخدام اليوزر بوت للحصول على نتائج دقيقة"""
    items = []
    try:
        async for msg in user_bot.search_global(query, limit=30):
            if msg.video or (msg.document and msg.document.mime_type and "video" in msg.document.mime_type):
                
                file_name = ""
                if msg.video: file_name = msg.video.file_name or f"Video_{msg.id}.mp4"
                elif msg.document: file_name = msg.document.file_name or f"File_{msg.id}"
                
                if file_name and (msg.video or msg.document).file_size > 500000: # > 500KB
                    items.append({
                        "chat_id": msg.chat.id,
                        "msg_id": msg.id,
                        "name": file_name,
                        "source": msg.chat.title or "Unknown"
                    })
        return items
    except FloodWait as e:
        print(f"FloodWait: {e.value}s")
        await asyncio.sleep(e.value)
        return []
    except Exception as e:
        print(f"Search Error: {e}")
        return []

# ====================================================================
# معالجات البوت المتحكم
# ====================================================================

@controller_bot.on_message(filters.command("start") & filters.user(OWNER_ID) if OWNER_ID else filters.command("start"))
async def start(client, message):
    await message.reply_text(
        "🤖 **البوت نشط وجاهز للعمل!**\n\n"
        "📌 ارسل اسم الفيلم للبحث والرفع.\n"
        "🔧 يستخدم اليوزر بوت للبحث.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔍 بحث", switch_inline_query_current_chat="")]])
    )

@controller_bot.on_message(filters.text & ~filters.command("start"))
async def handle_search(client: Client, message: Message):
    # (اختياري) قفل البوت لصاحبه فقط
    if OWNER_ID and message.from_user.id != OWNER_ID:
        return

    query = message.text
    m = await message.reply_text(f"🔍 جاري البحث عن: `{query}`...")
    
    # نستخدم اليوزر بوت للبحث
    results = await search_content(query)
    
    if not results:
        await m.edit_text("❌ لم يتم العثور على نتائج.")
        return

    buttons = []
    user_cache = {} # تخزين مؤقت لهذا المستخدم
    
    for i, item in enumerate(results[:8]):
        btn_text = f"📥 {item['name'][:30]}..."
        # نستخدم الرسالة ID كجزء من الـ callback لضمان عدم التكرار
        cb_data = f"dl_{item['chat_id']}_{item['msg_id']}"
        user_cache[cb_data] = item
        buttons.append([InlineKeyboardButton(btn_text, callback_data=cb_data)])
    
    # حفظ البيانات في الذاكرة العامة مرتبطة برسالة البحث لاسترجاعها لاحقاً
    search_results[message.id] = user_cache

    await m.edit_text(
        f"✅ تم العثور على {len(results)} نتيجة.\nاختر الملف للنقل:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@controller_bot.on_callback_query(filters.regex("^dl_"))
async def callback_handler(client: Client, query: CallbackQuery):
    data = query.data
    
    # نحتاج لمعرفة أين قمنا بالبحث (لكي نعرف النتائج)
    # هذه طريقة مبسطة، في الإنتاج يفضل استخدام قواعد بيانات
    # لكن هنا سنفترض أن المستخدم يبحث عن طريق البوت مباشرة
    
    try:
        parts = data.split("_")
        chat_id = int(parts[1])
        msg_id = int(parts[2])
        
        await query.answer("⏳ جاري النقل...", show_alert=True)
        
        # تعديل رسالة الأزرار لتظهر حالة التحميل
        msg_status = await query.message.edit_text("⚙️ جاري النقل عبر اليوزر بوت... يرجى الانتظار")

        # النسخ عبر اليوزر بوت
        await user_bot.copy_message(
            chat_id=TARGET_CHANNEL_ID,
            from_chat_id=chat_id,
            message_id=msg_id,
            caption="📤 تم النقل بواسطة البوت الآلي"
        )
        
        await msg_status.edit_text(f"✅ تم النقل بنجاح إلى القناة: `{TARGET_CHANNEL_ID}`")
        
    except UserBannedInChannel:
        await query.message.edit_text("❌ البوت محظور من المصدر.")
    except Exception as e:
        await query.message.edit_text(f"❌ خطأ: {str(e)}")

# ====================================================================
# التشغيل
# ====================================================================

async def start_services():
    print("⚡ بدء تشغيل اليوزر بوت...")
    await user_bot.start()
    print("✅ تم تشغيل اليوزر بوت.")
    
    print("⚡ بدء تشغيل البوت المتحكم...")
    await controller_bot.start()
    print("✅ تم تشغيل البوت.")
    
    print("🚀 النظام يعمل الآن...")
    await asyncio.Event().wait() # إبقاء العملية حية

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_services())
