import logging
import requests
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler
from telegram.error import BadRequest

# --- الإعدادات ---
# ضع التوكن الخاص بك هنا (تأكد أنه جديد وآمن)
TELEGRAM_TOKEN = '6741306329:AAF9gyhoD_li410vEdu62s7WlhZVVpKJu58'
TMDB_API_KEY = '69075ed729d6771ee24e8ce5e2555d92'

TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
YOUTUBE_BASE_URL = "https://www.youtube.com/watch?v="

# إعداد السجلات
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- وظائف المساعدة ---

def get_genres():
    url = f"{TMDB_BASE_URL}/genre/movie/list?api_key={TMDB_API_KEY}&language=ar"
    try:
        response = requests.get(url).json()
        return response.get('genres', [])
    except Exception as e:
        logging.error(f"Error fetching genres: {e}")
        return []

def get_random_movie(genre_id=None):
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
    url = f"{TMDB_BASE_URL}/movie/{movie_id}?api_key={TMDB_API_KEY}&language=ar&append_to_response=credits,videos"
    try:
        response = requests.get(url).json()
        return response
    except Exception as e:
        logging.error(f"Error fetching details: {e}")
        return None

def search_movies(query):
    url = f"{TMDB_BASE_URL}/search/movie?api_key={TMDB_API_KEY}&language=ar&query={query}"
    try:
        response = requests.get(url).json()
        return response.get('results', [])
    except Exception as e:
        logging.error(f"Error searching: {e}")
        return []

def format_movie_text(movie, details=None):
    title = movie.get('title', 'بدون عنوان')
    overview = movie.get('overview', 'لا يوجد وصف.')
    rating = movie.get('vote_average', 'N/A')
    release_date = movie.get('release_date', 'غير معروف')
    
    # تنظيف النصوص لـ HTML
    safe_overview = overview.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    
    text = (
        f"🎬 <b>{title}</b>\n"
        f"⭐️ التقييم: {rating}/10\n"
        f"📅 الإصدار: {release_date}"
    )

    if details:
        runtime = details.get('runtime')
        if runtime:
            text += f"\n⏱ المدة: {runtime} دقيقة"
        cast = details.get('credits', {}).get('cast', [])[:3]
        if cast:
            actors = ", ".join([actor['name'] for actor in cast])
            text += f"\n🎭 بطولة: {actors}"

    text += f"\n\n📝 <b>القصة:</b>\n{safe_overview[:400]}..."
    return text

# --- المعالجات ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """يبدأ المحادثة ويرسل القائمة الرئيسية كرسالة نصية جديدة"""
    user = update.effective_user
    welcome_text = (
        f"مرحباً {user.first_name}! 🍿\n"
        "اختر مما يلي للاستكشاف:"
    )
    
    keyboard = [
        [InlineKeyboardButton("🎲 اقتراح عشوائي", callback_data='random')],
        [InlineKeyboardButton("🔍 بحث", callback_data='prompt_search')],
        [InlineKeyboardButton("🎭 التصنيفات", callback_data='genres')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # دائماً نرسل رسالة جديدة في البداية
    if update.message:
        await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='HTML')
    else:
        # إذا تم استدعاؤه داخلياً، نرسل رسالة جديدة
        await update.callback_query.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='HTML')

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة /search"""
    if not context.args:
        await update.message.reply_text("اكتب اسم الفيلم بعد الأمر.\nمثال: /search Batman")
        return
    query = " ".join(context.args)
    await perform_search(update, context, query)

async def perform_search(update: Update, context: ContextTypes.DEFAULT_TYPE, query_str):
    results = search_movies(query_str)
    if not results:
        msg = "لم أجداً شيئاً! 😔"
        if update.callback_query:
            await update.callback_query.answer(msg, show_alert=True)
        else:
            await update.message.reply_text(msg)
        return

    context.user_data['search_results'] = results
    context.user_data['current_index'] = 0
    await show_search_result(update, context)

async def show_search_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    results = context.user_data.get('search_results', [])
    index = context.user_data.get('current_index', 0)
    
    if not results: return
    if index >= len(results): index = 0
    
    movie = results[index]
    movie_details = get_movie_details(movie['id'])
    caption = format_movie_text(movie, movie_details)
    poster_path = movie.get('poster_path')
    
    keyboard = []
    # أزرار التنقل
    nav_row = []
    if index > 0: nav_row.append(InlineKeyboardButton("◀️", callback_data='search_prev'))
    nav_row.append(InlineKeyboardButton(f"{index+1}/{len(results)}", callback_data='ignore'))
    if index < len(results)-1: nav_row.append(InlineKeyboardButton("▶️", callback_data='search_next'))
    keyboard.append(nav_row)
    
    # زر التريلر
    action_row = []
    trailer_key = None
    if movie_details:
        for v in movie_details.get('videos', {}).get('results', []):
            if v['type'] == 'Trailer' and v['site'] == 'YouTube':
                trailer_key = v['key']; break
    if trailer_key:
        action_row.append(InlineKeyboardButton("🎥 Trailer", url=f"{YOUTUBE_BASE_URL}{trailer_key}"))
    
    action_row.append(InlineKeyboardButton("🏠 الرئيسية", callback_data='back_to_start'))
    keyboard.append(action_row)
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # إرسال النتيجة
    if poster_path:
        photo_url = f"{TMDB_IMAGE_BASE_URL}{poster_path}"
        # حاول تعديل الصورة الحالية إذا وجدت
        try:
            if update.callback_query and update.callback_query.message.photo:
                await update.callback_query.edit_message_media(
                    media=InputMediaPhoto(media=photo_url, caption=caption, parse_mode='HTML'),
                    reply_markup=reply_markup
                )
            else:
                raise Exception("Send new photo")
        except Exception:
            if update.callback_query:
                await update.callback_query.message.reply_photo(photo=photo_url, caption=caption, reply_markup=reply_markup, parse_mode='HTML')
            else:
                await update.message.reply_photo(photo=photo_url, caption=caption, reply_markup=reply_markup, parse_mode='HTML')
    else:
        # بلا صورة
        try:
            if update.callback_query:
                await update.callback_query.edit_message_text(caption, reply_markup=reply_markup, parse_mode='HTML')
            else:
                await update.message.reply_text(caption, reply_markup=reply_markup, parse_mode='HTML')
        except BadRequest:
            # فشل التعديل (الرسالة صورة) -> أرسل نص جديد
            if update.callback_query:
                await update.callback_query.message.reply_text(caption, reply_markup=reply_markup, parse_mode='HTML')
            else:
                await update.message.reply_text(caption, reply_markup=reply_markup, parse_mode='HTML')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == 'prompt_search':
        try:
            await query.edit_message_text("أرسل اسم الفيلم الآن أو استخدم:\n\n/search اسم الفيلم", reply_markup=None)
        except:
            await query.message.reply_text("أرسل اسم الفيلم الآن أو استخدم:\n\n/search اسم الفيلم")

    elif data == 'search_next':
        context.user_data['current_index'] += 1
        await show_search_result(query, context)
        
    elif data == 'search_prev':
        context.user_data['current_index'] -= 1
        await show_search_result(query, context)

    elif data == 'random':
        await send_movie_suggestion(query, context)
    
    elif data == 'genres':
        genres = get_genres()
        if not genres:
            await query.message.reply_text("تعذر جلب التصنيفات.")
            return
        keyboard = []
        for i in range(0, len(genres), 2):
            row = [InlineKeyboardButton(genres[i]['name'], callback_data=f"genre_{genres[i]['id']}")]
            if i + 1 < len(genres):
                row.append(InlineKeyboardButton(genres[i+1]['name'], callback_data=f"genre_{genres[i+1]['id']}"))
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("⬅️ عودة", callback_data='back_to_start')])
        
        # محاولة تعديل النص للتصنيفات
        try:
            await query.edit_message_text("اختر تصنيفاً:", reply_markup=InlineKeyboardMarkup(keyboard))
        except BadRequest:
            await query.message.reply_text("اختر تصنيفاً:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith('genre_'):
        genre_id = data.split('_')[1]
        await send_movie_suggestion(query, context, genre_id)

    elif data == 'back_to_start':
        # --- التعديل المطلوب: حذف الرسالة الحالية وإرسال القائمة الجديدة ---
        if 'search_results' in context.user_data: 
            del context.user_data['search_results']
        
        try:
            # حاول حذف الرسالة التي تم الضغط على زرها
            await query.delete_message()
        except Exception as e:
            logging.warning(f"Could not delete message: {e}")
        
        # إرسال رسالة جديدة تحتوي على القائمة الرئيسية
        user = query.from_user
        welcome_text = f"مرحباً {user.first_name}! 🍿\nاختر مما يلي للاستكشاف:"
        
        keyboard = [
            [InlineKeyboardButton("🎲 اقتراح عشوائي", callback_data='random')],
            [InlineKeyboardButton("🔍 بحث", callback_data='prompt_search')],
            [InlineKeyboardButton("🎭 التصنيفات", callback_data='genres')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='HTML')

async def send_movie_suggestion(query, context, genre_id=None):
    movie = get_random_movie(genre_id)
    if movie:
        details = get_movie_details(movie['id'])
        caption = format_movie_text(movie, details)
        poster = movie.get('poster_path')
        
        keyboard = []
        row1 = []
        trailer_key = None
        if details:
            for v in details.get('videos', {}).get('results', []):
                if v['type'] == 'Trailer' and v['site'] == 'YouTube':
                    trailer_key = v['key']; break
        
        if trailer_key:
            row1.append(InlineKeyboardButton("🎥 Trailer", url=f"{YOUTUBE_BASE_URL}{trailer_key}"))
        
        row1.append(InlineKeyboardButton("🔄 آخر", callback_data='random' if not genre_id else f'genre_{genre_id}'))
        keyboard.append(row1)
        keyboard.append([InlineKeyboardButton("🏠 الرئيسية", callback_data='back_to_start')])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if poster:
            photo_url = f"{TMDB_IMAGE_BASE_URL}{poster}"
            try:
                # محاولة تعديل الصورة إذا أمكن
                if query.message.photo:
                    await query.edit_message_media(
                        InputMediaPhoto(media=photo_url, caption=caption, parse_mode='HTML'),
                        reply_markup=reply_markup
                    )
                else:
                    raise Exception("Send new")
            except Exception:
                await query.message.reply_photo(photo=photo_url, caption=caption, reply_markup=reply_markup, parse_mode='HTML')
        else:
            try:
                await query.edit_message_text(caption, reply_markup=reply_markup, parse_mode='HTML')
            except BadRequest:
                await query.message.reply_text(caption, reply_markup=reply_markup, parse_mode='HTML')
    else:
        await query.message.reply_text("لم أجد شيئاً الآن، حاول ثانية.")

# --- التشغيل ---
if __name__ == '__main__':
    if TELEGRAM_TOKEN == 'YOUR_TELEGRAM_BOT_TOKEN' or TMDB_API_KEY == 'YOUR_TMDB_API_KEY':
        print("خطأ: يرجى وضع التوكن ومفتاح API بشكل صحيح.")
    else:
        application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
        application.add_handler(CommandHandler('start', start))
        application.add_handler(CommandHandler('search', search_command))
        application.add_handler(CallbackQueryHandler(button_handler))
        print("البوت يعمل بنجاح...")
        application.run_polling()
