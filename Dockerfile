# استخدام صورة بايثون خفيفة
FROM python:3.11-slim

# تحديث الحزم وتثبيت FFmpeg
RUN apt-get update && apt-get install -y ffmpeg

# تعيين مجلد العمل
WORKDIR /app

# نسخ ملف المتطلبات وتثبيتها
# ملاحظة: تم إضافة [job-queue] لحل مشكلة JobQueue
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt "python-telegram-bot[job-queue]"

# نسخ باقي ملفات البوت
COPY . .

# الأمر لتشغيل البوت
CMD ["python", "main.py"]
