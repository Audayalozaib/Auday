import sqlite3
import logging
import os
from datetime import datetime
from config import DB_NAME

logger = logging.getLogger(__name__)

def init_db():
    """تهيئة قاعدة البيانات"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            url TEXT,
            title TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def add_to_history(user_id: int, url: str, title: str):
    """إضافة رابط للسجل"""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO history (user_id, url, title) VALUES (?, ?, ?)", (user_id, url, title[:100]))
        conn.commit()
        conn.close()
        # الاحتفاظ بآخر 10 فقط
        clean_old_history(user_id)
    except Exception as e:
        logger.error(f"DB Error: {e}")

def get_history(user_id: int):
    """جلب آخر 10 سجلات"""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT url, title FROM history WHERE user_id=? ORDER BY id DESC LIMIT 10", (user_id,))
        rows = cursor.fetchall()
        conn.close()
        return rows
    except Exception as e:
        logger.error(f"DB Error: {e}")
        return []

def clean_old_history(user_id: int):
    """حذف السجلات القديمة (الاحتفاظ بـ 10 فقط)"""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM history WHERE id NOT IN (
                SELECT id FROM history WHERE user_id=? ORDER BY id DESC LIMIT 10
            )
        """, (user_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        pass
