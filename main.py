import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

# ====================================================================
# إعدادات السكربت - عدل هنا فقط
# ====================================================================

# 1. ضع توكن البوت هنا (من @BotFather)
BOT_TOKEN = "6741306329:AAF9gyhoD_li410vEdu62s7WlhZVVpKJu58"  

# 2. ضع الـ API ID و HASH (يمكنك الحصول عليها من my.telegram.org)
# ملاحظة: حتى لو كان البوت، هذه القيم مطلوبة للاتصال بسريرفز تيليجرام
API_ID = 6825462  
API_HASH = "3b3cb233c159b6f48798e10c4b5fdc83"  

# 3. معرف القناة التي سيتم تنزيل/حفظ الأفلام فيها
# يجب أن يكون البوت مشرفاً في هذه القناة
MY_CHANNEL_ID = -1002064206339  

# اسم الجلسة (يمكنك تركه كما هو)
SESSION_NAME = "movie_downloader_bot"

# ====================================================================
# تهيئة البوت
# ====================================================================

logging.basicConfig(level=logging.INFO)
bot = Client(SESSION_NAME, api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ====================================================================
# دالة البحث
# ====================================================================

async def search_movies(query: str):
    """تقوم بالبحث عن الرسائل التي تحتوي على فيديو أو وثائق"""
    results = []
    try:
        # البحث باستخدام pyrogram (يبحث في المحتوى المتاح للبوت)
        async for message in bot.search_global(query, limit=15):
            
            # تصفية النتائج (نريد فيديوهات أو ملفات فيديو فقط)
            if message.video or (message.document and message.document.mime_type and "video" in message.document.mime_type):
                
                # التأكد من أن اسم الملف موجود
                file_name = ""
                if message.video:
                    file_name = message.video.file_name or f"Video_{message.id}.mp4"
                elif message.document:
                    file_name = message.document.file_name or f"File_{message.id}"
                
                # تخطي الملفات غير المسماة أو الصغيرة جداً
                if file_name and (message.video or message.document).file_size > 1024 * 1024: # أكبر من 1 ميجابايت
                    results.append({
                        "msg_id": message.id,
                        "chat_id": message.chat.id,
                        "title": message.chat.title or "Private Channel",
                        "file_name": file_name
                    })
                    
    except Exception as e:
        print(f"Error searching: {e}")
        
    return results

# ====================================================================
# معالجات الأوامر
# ====================================================================

@bot.on_message(filters.command("start"))
async def start_bot(client: Client, message: Message):
    await message.reply_text(
        "🎬 **مرحباً بك في بوت تحميل الأفلام!**\n\n"
        "أرسل لي **اسم الفيلم** (بالعربي أو الإنجليزي)\n"
        "وسأبحث عنه لك وأقوم بنسخه إلى القناة الخاصة بنا.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📞 قناة البوت", url="https://t.me/your_channel")]
        ])
    )

@bot.on_message(filters.text & ~filters.command("start"))
async def handle_search_query(client: Client, message: Message):
    query = message.text
    chat_id = message.chat.id
    
    # رسالة انتظار
    status = await message.reply_text(f"🔍 جاري البحث عن: **{query}**...")
    
    # تنفيذ البحث
    found_results = await search_movies(query)
    
    if not found_results:
        await status.edit_text("❌ لم أعثر على هذا الفيلم في قواعد البيانات المتاحة.")
        return

    # إنشاء الأزرار
    keyboard = []
    for i, res in enumerate(found_results[:10]): # عرض أول 10 نتائج فقط
        # اختصار الاسم ليناسب الزر
        short_name = res['file_name'][:35] + "..." if len(res['file_name']) > 35 else res['file_name']
        btn_text = f"📥 {short_name}"
        
        # البيانات التي سيتم إرسالها عند الضغط (نخزن المعرفات هنا)
        callback_data = f"dl_{res['chat_id']}_{res['msg_id']}_{chat_id}"
        
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=callback_data)])

    await status.edit_text(
        f"✅ تم العثور على **{len(found_results)}** نتيجة.\n"
        "اضغط على الزر المطلوب للتنزيل إلى القناة:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@bot.on_callback_query(filters.regex(r"^dl_"))
async def process_download(client: Client, callback_query: CallbackQuery):
    # فك تشفير البيانات من الزر
    try:
        parts = callback_query.data.split("_")
        target_chat_id = int(parts[1])   # مصدر الفيلم
        target_msg_id = int(parts[2])    # معرف رسالة الفيلم
        user_chat_id = int(parts[3])    # الشخص الذي طلب (للرد عليه)
        
        # التحقق: هل الشخص الذي ضغط هو نفسه صاحب البحث؟ (اختياري للحد من الاستخدام)
        if callback_query.from_user.id != user_chat_id:
            await callback_query.answer("⛔ هذه النتيجة ليست لك!", show_alert=True)
            return
            
        await callback_query.answer("⏳ جاري النقل...", show_alert=True)
        msg_process = await callback_query.message.edit_text("⚙️ جاري النقل، يرجى الانتظار...")

        # عملية النسخ إلى القناة المستهدفة
        try:
            await bot.copy_message(
                chat_id=MY_CHANNEL_ID,
                from_chat_id=target_chat_id,
                message_id=target_msg_id,
                caption="✅ تم النقل بواسطة البوت الآلي"
            )
            await msg_process.edit_text(f"✅ **تم النقل بنجاح!**\nتم حفظ الفيلم في القناة: {MY_CHANNEL_ID}")
            
        except Exception as err:
            await msg_process.edit_text(f"❌ حدث خطأ أثناء النقل: `{err}`")

    except Exception as e:
        print(f"Callback Error: {e}")
        await callback_query.answer("❌ حدث خطأ في الزر", show_alert=True)

# ====================================================================
# التشغيل
# ====================================================================

print("🚀 البوت يعمل الآن...")
bot.run()
