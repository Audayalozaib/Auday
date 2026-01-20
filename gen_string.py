from pyrogram import Client

# ضع بيانات API الخاصة بك
API_ID = 1234567
API_HASH = "YOUR_API_HASH"

print("جاري توليد كود الجلسة... يرجى إدخال رقم هاتفك عند الطلب.")

with Client("my_account", api_id=API_ID, api_hash=API_HASH) as app:
    print("\n✅ تم تسجيل الدخول بنجاح!")
    print("============================================")
    print("انسخ الكود التالي وضعه في متغير STRING_SESSION في السكربت:")
    print("============================================")
    print(app.export_session_string())
