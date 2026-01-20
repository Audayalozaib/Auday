import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

# استيراد عام للأخطاء (للحد من المشاكل)
from pyrogram.errors import all as errors

# ====================================================================
# إعدادات النظام
# ====================================================================
API_ID = int(os.environ.get("API_ID", 6825462))
API_HASH = os.environ.get("API_HASH", "3b3cb233c159b6f48798e10c4b5fdc83")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "6741306329:AAF9gyhoD_li410vEdu62s7WlhZVVpKJu58")
TARGET_CHANNEL_ID = int(os.environ.get("TARGET_CHANNEL_ID", -1002064206339))
OWNER_ID = int(os.environ.get("OWNER_ID", 778375826))

# حالة التسجيل
auth_state = {
    "client": None,
    "phone_code_hash": None,
    "step": "idle" 
}

# البوت
bot = Client("bot_ctrl", bot_token=BOT_TOKEN, api_id=API_ID, api_hash=API_HASH)

# ====================================================================
# دالة التسجيل
# ====================================================================
async def login_process(message: Message):
    if auth_state["client"]:
        try: await auth_state["client"].stop()
        except: pass

    user = Client("temp_login", api_id=API_ID, api_hash=API_HASH, in_memory=True)
    auth_state["client"] = user
    
    try:
        await user.connect()
        await message.reply_text("📱 جاري الاتصال بتيليجرام...")
        
        sent_code = await user.send_code(message.text)
        auth_state["phone_code_hash"] = sent_code.phone_code_hash
        auth_state["step"] = "code"
        
        await message.reply_text("✅ تم إرسال الكود.\n👉 أرسل الكود (أرقام فقط).")
        
    except Exception as e:
        await message.reply_text(f"❌ خطأ: `{str(e)}`")
        try: await user.disconnect()
        except: pass

# ====================================================================
# المعالجات
# ====================================================================

@bot.on_message(filters.command("start") & filters.user(OWNER_ID))
async def start(client, message):
    btn = InlineKeyboardMarkup([[InlineKeyboardButton("🔑 تسجيل الدخول", callback_data="login")]])
    await message.reply_text("مرحباً. اضغط الزر لتسجيل حسابك في البوت.", reply_markup=btn)

@bot.on_callback_query(filters.data("login"))
async def c_login(client, query):
    await query.message.edit("📲 أرسل رقم هاتفك الآن (مثال: +966...")

@bot.on_message(filters.text & filters.user(OWNER_ID))
async def handle(client, message):
    text = message.text
    
    # حالة رقم الهاتف
    if text.startswith("+") and auth_state["step"] == "idle":
        await login_process(message)
        return

    # حالة الكود
    if auth_state["step"] == "code":
        user = auth_state["client"]
        try:
            await user.sign_in(message.chat.id, auth_state["phone_code_hash"], text)
            
            # نجاح
            string = user.export_session_string()
            await message.reply_text(
                f"✅ تم تسجيل الدخول!\n\nكود الجلسة:\n`{string}`",
                parse_mode="Markdown"
            )
            await user.disconnect()
            auth_state["step"] = "idle"
            
        except Exception as e:
            err_name = type(e).__name__
            # فحص اسم الخطأ كنص بدلاً من الاستيراد
            if "Password" in err_name:
                auth_state["step"] = "password"
                await message.reply_text("🔒 أدخل كلمة المرور (2FA).")
            elif "Code" in err_name:
                await message.reply_text("❌ الكود خاطئ.")
            else:
                await message.reply_text(f"❌ خطأ: {err_name}")
                await user.disconnect()
                auth_state["step"] = "idle"
        return

    # حالة كلمة المرور
    if auth_state["step"] == "password":
        user = auth_state["client"]
        try:
            await user.check_password(text)
            string = user.export_session_string()
            await message.reply_text(
                f"✅ تم التحقق!\n\nكود الجلسة:\n`{string}`",
                parse_mode="Markdown"
            )
            await user.disconnect()
            auth_state["step"] = "idle"
        except:
            await message.reply_text("❌ كلمة المرور خاطئة.")
            await user.disconnect()
            auth_state["step"] = "idle"

# ====================================================================
# التشغيل
# ====================================================================
async def main():
    print("Starting...")
    await bot.start()
    await asyncio.Event().wait()

if __name__ == "__main__":
    if not API_ID or not API_HASH:
        print("Missing API_ID or API_HASH")
    else:
        asyncio.run(main())
