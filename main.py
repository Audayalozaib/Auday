import os
import asyncio
import logging
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import SessionPasswordNeededError, PhoneCodeInvalidError

# ====================================================================
# إعدادات النظام
# ====================================================================
API_ID = int(os.environ.get("API_ID", 6825462))
API_HASH = os.environ.get("API_HASH", "3b3cb233c159b6f48798e10c4b5fdc83")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "6741306329:AAF9gyhoD_li410vEdu62s7WlhZVVpKJu58")
TARGET_CHANNEL_ID = int(os.environ.get("TARGET_CHANNEL_ID", -1002064206339))
OWNER_ID = int(os.environ.get("OWNER_ID", 778375826))

# ====================================================================
# حالة التسجيل (لا تعدل عليها)
# ====================================================================
auth_data = {
    "client": None,      # سيتم تخزين عميل اليوزر بوت هنا مؤقتاً
    "phone_code_hash": None,
    "step": "idle"       # idle, waiting_code, waiting_2fa
}

# ====================================================================
# تهيئة البوت المتحكم (يعمل دائماً)
# ====================================================================
bot = Client("bot_ctrl", bot_token=BOT_TOKEN, api_id=API_ID, api_hash=API_HASH)

# ====================================================================
# دالة بدء التسجيل
# ====================================================================
async def start_auth_process(message: Message):
    # إذا كان هناك عميل يعمل بالفعل، أغلقه أولاً
    if auth_data["client"]:
        try:
            await auth_data["client"].stop()
        except: pass

    # إنشاء عميل يوزر بوت مؤقت بدون جلسة لطلب الكود
    user = Client(name="temp_auth_user", api_id=API_ID, api_hash=API_HASH, in_memory=True)
    auth_data["client"] = user
    
    try:
        await user.connect()
        phone_number = message.text
        
        await message.reply_text("📱 جاري طلب الكود من تيليجرام...")
        
        # إرسال رقم الهاتف
        sent_code = await user.send_code(phone_number)
        
        auth_data["phone_code_hash"] = sent_code.phone_code_hash
        auth_data["step"] = "waiting_code"
        
        await message.reply_text(
            "✅ تم إرسال كود التفعيل إلى تليجرام.\n\n"
            "👉 **أرسل الكود الآن (الأرقام فقط) عبر البوت هنا.**"
        )
        
    except Exception as e:
        await message.reply_text(f"❌ حدث خطأ أثناء إرسال الرقم: `{e}`")
        await user.disconnect()

# ====================================================================
# معالجات البوت (أوامر التسجيل)
# ====================================================================

@bot.on_message(filters.command("start") & filters.user(OWNER_ID))
async def start_cmd(client, message):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 تسجيل دخول اليوزر بوت", callback_data="login_userbot")]
    ])
    await message.reply_text("🤖 البوت جاهز.\nاضغط على الزر أدناه لتسجيل الدخول بحسابك الشخصي.", reply_markup=keyboard)

@bot.on_callback_query(filters.data("login_userbot"))
async def login_callback(client, callback_query):
    await callback_query.message.edit("📲 أرسل رقم هاتفك الآن (مع مفتاح الدولة، مثلاً: +9665000000)")

@bot.on_message(filters.text & filters.user(OWNER_ID))
async def handle_text(client, message):
    txt = message.text
    
    # 1. إذا كان المستخدم يرسل رقم الهاتف
    if txt.startswith("+") and txt[1:].isdigit() and auth_data["step"] == "idle":
        await start_auth_process(message)
        return

    # 2. إذا كان المستخدم يرسل كود التفعيل
    if auth_data["step"] == "waiting_code":
        user = auth_data["client"]
        try:
            # محاولة تسجيل الدخول
            await user.sign_in(
                message.chat.id, 
                auth_data["phone_code_hash"], 
                txt
            )
            
            # نجاح الدخول!
            auth_data["step"] = "idle"
            string_session = user.export_session_string()
            
            await message.reply_text(
                f"✅ **تم تسجيل الدخول بنجاح!**\n\n"
                f"🔑 هذا هو كود الجلسة الخاص بك (String Session):\n\n"
                f"`{string_session}`\n\n"
                f"⚠️ انسخه واحفظه في Railway في متغير `STRING_SESSION` ثم أعد تشغيل البوت.",
                parse_mode="Markdown"
            )
            
            await user.disconnect()
            
        except SessionPasswordNeededError:
            auth_data["step"] = "waiting_2fa"
            await message.reply_text("🔒 الحساب محمي بكلمة مرور (2FA).\n\n👉 **أرسل كلمة المرور الآن.**")
            
        except PhoneCodeInvalidError:
            await message.reply_text("❌ الكود خاطئ! حاول مرة أخرى.")
            await user.disconnect()
            auth_data["step"] = "idle"
            
        except Exception as e:
            await message.reply_text(f"❌ خطأ: `{e}`")
            await user.disconnect()
            auth_data["step"] = "idle"
        return

    # 3. إذا كان المستخدم يرسل كلمة المرور (2FA)
    if auth_data["step"] == "waiting_2fa":
        user = auth_data["client"]
        try:
            await user.check_password(txt)
            
            # نجاح الدخول بكلمة المرور
            auth_data["step"] = "idle"
            string_session = user.export_session_string()
            
            await message.reply_text(
                f"✅ **تم التحقق بنجاح!**\n\n"
                f"🔑 كود الجلسة:\n\n`{string_session}`\n\n"
                f"⚠️ انسخه وضعه في Railway (STRING_SESSION).",
                parse_mode="Markdown"
            )
            
            await user.disconnect()
            
        except Exception as e:
            await message.reply_text(f"❌ كلمة المرور خاطئة أو حدث خطأ: `{e}`")
            await user.disconnect()
            auth_data["step"] = "idle"

# ====================================================================
# التشغيل
# ====================================================================
async def main():
    print("Bot is running...")
    await bot.start()
    print("Bot started!")
    await asyncio.Event().wait()

if __name__ == "__main__":
    # التأكد من وجود المتغيرات الأساسية
    if not BOT_TOKEN or not API_ID or not API_HASH:
        print("Error: Please set BOT_TOKEN, API_ID, API_HASH in environment variables.")
    else:
        asyncio.run(main())
