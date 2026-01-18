FROM python:3.11-slim

# تحديث النظام وتثبيت FFmpeg
RUN apt-get update && apt-get install -y ffmpeg

WORKDIR /app

# نسخ ملف المتطلبات
COPY requirements.txt .

# ==================== الإجبار على التحديث ====================
# 1. إلغاء تثبيت python-telegram-bot القديمة إن وجدت
RUN pip uninstall python-telegram-bot -y || true

# 2. تثبيت نسخة محددة وحديثة مباشرة (بدلاً من الاعتماد فقط على requirements.txt)
RUN pip install "python-telegram-bot==20.8" "python-telegram-bot[job-queue]" --upgrade

# 3. تثبيت باقي المكتبات
RUN pip install --no-cache-dir -r requirements.txt

# نسخ ملفات البوت
COPY . .

CMD ["python", "main.py"]
