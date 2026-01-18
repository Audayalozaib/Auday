# استخدام صورة بايثون خفيفة
FROM python:3.11-slim

# تحديث الحزم وتثبيت FFmpeg (هذا يحل مشكلتك نهائياً)
RUN apt-get update && apt-get install -y ffmpeg

# تعيين مجلد العمل
WORKDIR /app

# نسخ ملف المتطلبات وتثبيتها
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ باقي ملفات البوت
COPY . .

# الأمر لتشغيل البوت
CMD ["python", "perfect_download_bot.py"]
