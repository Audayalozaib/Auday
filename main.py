import logging
import requests
import random
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler

# --- الإعدادات ---
# ضع التوكن الخاص بك هنا
TELEGRAM_TOKEN = '6741306329:AAF9gyhoD_li410vEdu62s7WlhZVVpKJu58'

# ضع مفتاح TMDB API الخاص بك هنا
TMDB_API_KEY = '69075ed729d6771ee24e8ce5e2555d92'

TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
YOUTUBE_BASE_URL = "https://www.youtube.com/watch?v="

# إعداد السجلات (Logging)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- وظائف المساعدة لجلب البيانات من TMDB ---

def get_genres():
    """جلب قائمة التصنيفات للأفلام"""
    url = f"{TMDB_BASE_URL}/genre/movie/list?api_key={TMDB_API_KEY}&language=ar"
    try:
        response = requests.get(url).json()
        return response.get('genres', [])
    except Exception as e:
        logging.error(f"Error fetching genres: {e}")
        return []

def get_random_movie(genre_id=None):
    """جلب فيلم عشوائي (يختار صفحة عشوائية من الأفلام الشائعة)"""
    # توسيع نطاق البحث ليشمل 50 صفحة لتنوع أكبر
    page = random.randint(1, 50) 
    url = f"{TMDB_BASE_URL}/discover/movie?api_key={TMDB_API_KEY}&language=ar&sort_by=popularity.desc&page={page}"
    if genre_id:
        url += f"&with_genres={genre_id}"
    
    try:
        response = requests.get(url).json()
        results = response.get('results', [])
        if results:
            return random.choice(results)
    except Exception as e:
        logging.error(f"Error fetching random movie: {e}")
    return None

def get_movie_details(movie_id):
    """جلب تفاصيل كاملة للفيلم (الطاقم، التريلر، المدة)"""
    url = f"{TMDB_BASE_URL}/movie/{movie_id}?api_key={TMDB_API_KEY}&language=ar&append_to_response=credits,videos"
    try:
        response = requests.get(url).json()
        return response
    except Exception as e:
        logging.error(f"Error fetching movie details: {e}")
        return None

def search_movies(query):
    """البحث عن فيلم بالاسم"""
    url = f"{TMDB_BASE_URL}/search/movie?api_key={TMDB_API_KEY}&language=ar&query={query}"
    try:
        response = requests.get(url).json()
        return response.get('results', [])
    except Exception as e:
        logging.error(f"Error searching movie: {e}")
        return []

# --- دالة تنسيق رسالة الفيلم ---

def format_movie_text(movie, details=None):
    """تنسيق تفاصيل الفيلم في رسالة HTML جميلة"""
    title = movie.get('title', 'بدون عنوان')
    overview = movie.get('overview', 'لا يوجد وصف متاح.')
    rating = movie.get('vote_average', 'N/A')
    release_date = movie.get('release_date', 'غير معروف')
    
    # تنظيف النص من الرموز التي قد تعطل HTML (مثل < > &)
    safe_overview = overview.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    
    text = (
        f"🎬 <b>{title}</b>\n"
        f"⭐️ التقييم: {rating}/10\n"
        f"📅 تاريخ الإصدار: {release_date}"
    )

    # إضافة تفاصيل إضافية إذا كانت موجودة (مدة الفيلم والممثلين)
    if details:
        runtime = details.get('runtime')
        if runtime:
            text += f"\n⏱ المدة: {runtime} دقيقة"
        
        cast = details.get('credits', {}).get('cast', [])[:3] # جلب أول 3 ممثلين
        if cast:
            actors = ", ".join([actor['name'] for actor in cast])
            text += f"\n🎭 بطولة: {actors}"

    text += f"\n\n📝 <b>القصة:</b>\n{safe_overview[:400]}..."
    
    return text

# --- معالجات الأوامر (Command Handlers) ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر البداية /start"""
    user = update.effective_user
    welcome_text = (
        f"مرحباً {user.first_name}! 🍿\n\n"
        "أنا بوت دليل الأفلام الذكي. يمكنك استكشاف أفلام عشوائية أو البحث عن فيلم محدد.\n\n"
        "اختر مما يلي للبدء:"
    )
    
    keyboard = [
        [InlineKeyboardButton("🎲 اقتراح عشوائي", callback_data='random')],
        [InlineKeyboardButton("🔍 بحث عن فيلم", callback_data='prompt_search')],
        [InlineKeyboardButton("🎭 اختر حسب التصنيف", callback_data='genres')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='HTML')
    else:
        await update.callback_query.edit_message_text(welcome_text, reply_markup=reply_markup, parse_mode='HTML')

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر البحث النصي /search"""
    if not context.args:
        await update.message.reply_text("الرجاء كتابة اسم الفيلم بعد الأمر. مثال:\n/search Inception")
        return
    
    query = " ".join(context.args)
    await perform_search(update, context, query)

async def perform_search(update: Update, context: ContextTypes.DEFAULT_TYPE, query):
    """تنفيذ البحث وعرض النتيجة الأولى"""
    results = search_movies(query)
    if not results:
        msg = "لم أجد أي أفلام بهذا الاسم. حاول باسم آخر أو بالإنجليزية."
        if update.callback_query:
            await update.callback_query.answer(msg, show_alert=True)
        else:
            await update.message.reply_text(msg)
        return

    # تخزين نتائج البحث في الذاكرة المؤقتة للمستخدم للتنقل بينها
    context.user_data['search_results'] = results
    context.user_data['current_index'] = 0
    
    await show_search_result(update, context)

async def show_search_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض نتيجة البحث الحالية مع أزرار التنقل"""
    results = context.user_data.get('search_results', [])
    index = context.user_data.get('current_index', 0)
    
    if index >= len(results):
        index = 0
        
    movie = results[index]
    movie_details = get_movie_details(movie['id'])
    
    caption = format_movie_text(movie, movie_details)
    poster_path = movie.get('poster_path')
    
    # إعداد الأزرار (السابق/التالي + التفاصيل)
    keyboard = []
    
    # أزرار التنقل
    nav_buttons = []
    if index > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ السابق", callback_data='search_prev'))
    nav_buttons.append(InlineKeyboardButton(f"{index + 1}/{len(results)}", callback_data='ignore'))
    if index < len(results) - 1:
        nav_buttons.append(InlineKeyboardButton("التالي ▶️", callback_data='search_next'))
    keyboard.append(nav_buttons)
    
    # زر التريلر
    trailer_key = None
    if movie_details:
        videos = movie_details.get('videos', {}).get('results', [])
        for video in videos:
            if video['type'] == 'Trailer' and video['site'] == 'YouTube':
                trailer_key = video['key']
                break
    
    action_buttons = []
    if trailer_key:
        action_buttons.append(InlineKeyboardButton("🎥 مشاهدة التريلر", url=f"{YOUTUBE_BASE_URL}{trailer_key}"))
    
    action_buttons.append(InlineKeyboardButton("🏠 الرئيسية", callback_data='back_to_start'))
    keyboard.append(action_buttons)
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # إرسال الصورة أو النص
    if poster_path:
        photo_url = f"{TMDB_IMAGE_BASE_URL}{poster_path}"
        if update.callback_query:
            # نحاول تعديل الرسالة إذا كانت صورة، إذا فشل نرسل رسالة جديدة
            try:
                await update.callback_query.edit_message_media(
                    media=InputMediaPhoto(media=photo_url, caption=caption, parse_mode='HTML'),
                    reply_markup=reply_markup
                )
            except Exception:
                 await update.callback_query.message.reply_photo(photo=photo_url, caption=caption, reply_markup=reply_markup, parse_mode='HTML')
        else:
            await update.message.reply_photo(photo=photo_url, caption=caption, reply_markup=reply_markup, parse_mode='HTML')
    else:
        if update.callback_query:
            await update.callback_query.edit_message_text(caption, reply_markup=reply_markup, parse_mode='HTML')
        else:
            await update.message.reply_text(caption, reply_markup=reply_markup, parse_mode='HTML')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة جميع ضغطات الأزرار"""
    query = update.callback_query
    await query.answer()
    
    data = query.data

    # --- البحث ---
    if data == 'prompt_search':
        # نقوم بحذف الأمر السابق لطلب البحث الجديد (اختصار للتجربة)
        # في الواقع يفضل استخدام ConversationHandler هنا، لكن للتبسيط سنطلب منه كتابة الأمر
        try:
            await query.edit_message_text("🔍 للبحث عن فيلم، الرجاء كتابة الأمر:\n\n`/search اسم الفيلم`\n\nمثال: `/search Batman`", parse_mode='Markdown')
        except Exception:
             pass

    elif data == 'search_next':
        context.user_data['current_index'] += 1
        await show_search_result(query, context)
        
    elif data == 'search_prev':
        context.user_data['current_index'] -= 1
        await show_search_result(query, context)

    # --- عشوائي وتصنيفات ---
    elif data == 'random':
        await send_movie_suggestion(query, context)
    
    elif data == 'genres':
        genres = get_genres()
        if not genres:
            await query.edit_message_text("تعذر جلب التصنيفات حالياً.")
            return

        keyboard = []
        # تنظيم الأزرار في صفوف
        for i in range(0, len(genres), 2):
            row = [InlineKeyboardButton(genres[i]['name'], callback_data=f"genre_{genres[i]['id']}")]
            if i + 1 < len(genres):
                row.append(InlineKeyboardButton(genres[i+1]['name'], callback_data=f"genre_{genres[i+1]['id']}"))
            keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton("⬅️ عودة", callback_data='back_to_start')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("اختر تصنيفاً يهمك:", reply_markup=reply_markup)

    elif data.startswith('genre_'):
        genre_id = data.split('_')[1]
        await send_movie_suggestion(query, context, genre_id)

    elif data == 'back_to_start':
        # إعادة تعيين البيانات
        if 'search_results' in context.user_data:
            del context.user_data['search_results']
        await start(update, context)

async def send_movie_suggestion(query, context, genre_id=None):
    """إرسال اقتراح فيلم عشوائي"""
    movie = get_random_movie(genre_id)
    
    if movie:
        movie_details = get_movie_details(movie['id'])
        caption = format_movie_text(movie, movie_details)
        poster_path = movie.get('poster_path')
        
        keyboard = []
        
        # زر التريلر
        trailer_key = None
        if movie_details:
            videos = movie_details.get('videos', {}).get('results', [])
            for video in videos:
                if video['type'] == 'Trailer' and video['site'] == 'YouTube':
                    trailer_key = video['key']
                    break
        
        row_buttons = []
        if trailer_key:
            row_buttons.append(InlineKeyboardButton("🎥 مشاهدة التريلر", url=f"{YOUTUBE_BASE_URL}{trailer_key}"))
        
        row_buttons.append(InlineKeyboardButton("🔄 اقتراح آخر", callback_data='random' if not genre_id else f'genre_{genre_id}'))
        keyboard.append(row_buttons)
        
        keyboard.append([InlineKeyboardButton("⬅️ القائمة الرئيسية", callback_data='back_to_start')])
        reply_markup = InlineKeyboardMarkup(keyboard)

        if poster_path:
            photo_url = f"{TMDB_IMAGE_BASE_URL}{poster_path}"
            try:
                if query.message.photo:
                     await query.edit_message_media(media=InputMediaPhoto(media=photo_url, caption=caption, parse_mode='HTML'), reply_markup=reply_markup)
                else:
                     await query.message.reply_photo(photo=photo_url, caption=caption, reply_markup=reply_markup, parse_mode='HTML')
            except Exception:
                # في حال فشل التعديل (مثلاً الرسالة قديمة جداً)
                await query.message.reply_photo(photo=photo_url, caption=caption, reply_markup=reply_markup, parse_mode='HTML')
        else:
            try:
                await query.edit_message_text(caption, reply_markup=reply_markup, parse_mode='HTML')
            except Exception:
                await query.message.reply_text(caption, reply_markup=reply_markup, parse_mode='HTML')
    else:
        await query.message.reply_text("عذراً، لم أستطع العثور على فيلم حالياً. حاول مرة أخرى.")

# --- تشغيل البوت ---
from telegram import InputMediaPhoto # استيراد ضروري لتعديل الصور

if __name__ == '__main__':
    if TELEGRAM_TOKEN == 'YOUR_TELEGRAM_BOT_TOKEN' or TMDB_API_KEY == 'YOUR_TMDB_API_KEY':
        print("خطأ: يرجى وضع التوكن الخاص بتليجرام ومفتاح TMDB API في الكود أولاً.")
    else:
        application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
        
        # إضافة المعالجات
        application.add_handler(CommandHandler('start', start))
        application.add_handler(CommandHandler('search', search_command))
        application.add_handler(CallbackQueryHandler(button_handler))
        
        print("البوت المحسن يعمل الآن... اضغط Ctrl+C للإيقاف.")
        application.run_polling()
