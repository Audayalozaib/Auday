import logging
import requests
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQuery_Handler

# --- الإعدادات ---
# ضع التوكن الخاص بك هنا (احصل عليه من @BotFather)
TELEGRAM_TOKEN = '6741306329:AAF9gyhoD_li410vEdu62s7WlhZVVpKJu58'

# ضع مفتاح TMDB API الخاص بك هنا (احصل عليه من https://www.themoviedb.org/settings/api)
TMDB_API_KEY = '69075ed729d6771ee24e8ce5e2555d92'

TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"

# إعداد السجلات (Logging)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- وظائف المساعدة لجلب البيانات من TMDB ---

def get_genres():
    """جلب قائمة التصنيفات للأفلام"""
    url = f"{TMDB_BASE_URL}/genre/movie/list?api_key={TMDB_API_KEY}&language=ar"
    response = requests.get(url).json()
    return response.get('genres', [])

def get_random_movie(genre_id=None):
    """جلب فيلم عشوائي، اختيارياً حسب التصنيف"""
    page = random.randint(1, 10)  # البحث في أول 10 صفحات للأفلام الشائعة
    url = f"{TMDB_BASE_URL}/discover/movie?api_key={TMDB_API_KEY}&language=ar&sort_by=popularity.desc&page={page}"
    if genre_id:
        url += f"&with_genres={genre_id}"
    
    response = requests.get(url).json()
    results = response.get('results', [])
    if results:
        return random.choice(results)
    return None

# --- معالجات الأوامر (Command Handlers) ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر البداية /start"""
    user = update.effective_user
    welcome_text = (
        f"مرحباً {user.first_name}! 🍿\n\n"
        "أنا بوت **'ماذا أشاهد؟'**. سأساعدك في اختيار فيلمك القادم.\n\n"
        "استخدم الأزرار أدناه للاكتشاف:"
    )
    
    keyboard = [
        [InlineKeyboardButton("🎲 اقتراح عشوائي", callback_data='random')],
        [InlineKeyboardButton("🎭 اختر حسب التصنيف", callback_data='genres')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة ضغطات الأزرار"""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'random':
        await send_movie_suggestion(query, context)
    
    elif query.data == 'genres':
        genres = get_genres()
        keyboard = []
        # تنظيم الأزرار في صفوف (كل صف زرين)
        for i in range(0, len(genres), 2):
            row = [InlineKeyboardButton(genres[i]['name'], callback_data=f"genre_{genres[i]['id']}")]
            if i + 1 < len(genres):
                row.append(InlineKeyboardButton(genres[i+1]['name'], callback_data=f"genre_{genres[i+1]['id']}"))
            keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton("⬅️ عودة", callback_data='back_to_start')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("اختر تصنيفاً يهمك:", reply_markup=reply_markup)

    elif query.data.startswith('genre_'):
        genre_id = query.data.split('_')[1]
        await send_movie_suggestion(query, context, genre_id)

    elif query.data == 'back_to_start':
        keyboard = [
            [InlineKeyboardButton("🎲 اقتراح عشوائي", callback_data='random')],
            [InlineKeyboardButton("🎭 اختر حسب التصنيف", callback_data='genres')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("ماذا تريد أن تفعل الآن؟", reply_markup=reply_markup)

async def send_movie_suggestion(query, context, genre_id=None):
    """إرسال تفاصيل الفيلم المقترح"""
    movie = get_random_movie(genre_id)
    
    if movie:
        title = movie.get('title', 'بدون عنوان')
        overview = movie.get('overview', 'لا يوجد وصف متاح حالياً.')
        rating = movie.get('vote_average', 'N/A')
        release_date = movie.get('release_date', 'غير معروف')
        poster_path = movie.get('poster_path')
        
        caption = (
            f"🎬 **{title}**\n\n"
            f"⭐️ التقييم: {rating}/10\n"
            f"📅 تاريخ الإصدار: {release_date}\n\n"
            f"📝 القصة:\n{overview[:300]}..." # قص الوصف إذا كان طويلاً جداً
        )
        
        keyboard = [[InlineKeyboardButton("🔄 اقتراح آخر", callback_data='random' if not genre_id else f'genre_{genre_id}')],
                    [InlineKeyboardButton("⬅️ القائمة الرئيسية", callback_data='back_to_start')]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        if poster_path:
            photo_url = f"{TMDB_IMAGE_BASE_URL}{poster_path}"
            await query.message.reply_photo(photo=photo_url, caption=caption, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await query.message.reply_text(caption, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await query.message.reply_text("عذراً، لم أستطع العثور على فيلم حالياً. حاول مرة أخرى.")

# --- تشغيل البوت ---

if __name__ == '__main__':
    if TELEGRAM_TOKEN == 'YOUR_TELEGRAM_BOT_TOKEN' or TMDB_API_KEY == 'YOUR_TMDB_API_KEY':
        print("خطأ: يرجى وضع التوكن الخاص بتليجرام ومفتاح TMDB API في الكود أولاً.")
    else:
        application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
        
        # إضافة المعالجات
        application.add_handler(CommandHandler('start', start))
        application.add_handler(CallbackQueryHandler(button_handler))
        
        print("البوت يعمل الآن... اضغط Ctrl+C للإيقاف.")
        application.run_polling()
