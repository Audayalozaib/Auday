# استخدام صورة بايثون خفيفة
FROM python:3.11-slim

# ضبط دليل العمل داخل الحاوية
WORKDIR /app

# نسخ ملف المتطلبات أولاً لتثبيت المكتبات
COPY requirements.txt .

# تثبيت المكتبات
RUN pip install --no-cache-dir -r requirements.txt

# نسخ ملف البوت
COPY main.py .

# الأمر لتشغيل البوت
CMD ["python", "main.py"]
