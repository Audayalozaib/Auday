import logging
import requests
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler
from telegram.error import BadRequest

# --- الإعدادات ---
TELEGRAM_TOKEN = '6741306329:AAF9gyhoD_li410vEdu62s7WlhZVVpKJu58'
TMDB_API_KEY = '69075ed729d6771ee24e8ce5e2555d92'

TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
YOUTUBE_BASE_URL = "https://www.youtube.com/watch?v="

# معرفات تصنيفات TMDB الثابتة (تستخدم للأنمي)
GENRE_ID_ANIMATION = 16

# إعداد السجلات
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- وظائف المساعدة ---

def get_genres(media_type='movie'):
    """جلب التصنيفات"""
    url = f"{TMDB_BASE_URL}/genre/{media_type}/list?api_key={TMDB_API_KEY}&language=ar"
    try:
        response = requests.get(url).json()
        return response.get('genres', [])
    except Exception as e:
        logging.error(f"Error fetching genres: {e}")
        return []

def get_random_item(media_type='movie', genre_id=None):
    """جلب عنصر عشوائي (فيلم، مسلسل، أو أنمي)"""
    page = random.randint(1, 50)
    url = f"{TMDB_BASE_URL}/discover/{media_type}?api_key={TMDB_API_KEY}&language=ar&sort_by=popularity.desc&page={page}"
    
    # إضافة التصنيف إذا وجد
    if genre_id:
        url += f"&with_genres={genre_id}"
    
    try:
        response = requests.get(url).json()
        results = response.get('results', [])
        if results:
            return random.choice(results)
    except Exception as e:
        logging.error(f"Error fetching random item: {e}")
    return None

def get_item_details(media_type, item_id):
    """جلب التفاصيل الكاملة"""
    url = f"{TMDB_BASE_URL}/{media_type}/{item_id}?api_key={TMDB_API_KEY}&language=ar&append_to_response=credits,videos"
    try:
        response = requests.get(url).json()
        return response
    except Exception as e:
        logging.error(f"Error fetching details: {e}")
        return None

def search_items(query, media_type='movie'):
    """البحث"""
    url = f"{TMDB_BASE_URL}/search/{media_type}?api_key={TMDB_API_KEY}&language=ar&query={query}"
    try:
        response = requests.get(url).json()
        return response.get('results', [])
    except Exception as e:
        logging.error(f"Error searching: {e}")
        return []

def format_item_text(item, details=None, media_type='movie'):
    """تنسيق النص"""
    title = item.get('title') if media_type == 'movie' else item.get('name')
    overview = item.get('overview', 'لا يوجد وصف.')
    rating = item.get('vote_average', 'N/A')
    date = item.get('release_date') if media_type == 'movie' else item.get('first_air_date')
    year = date[:4] if date else 'غير معروف'
    
    safe_overview = overview.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    
    icon = "🎬"
    if media_type == 'tv': icon = "📺"
    # تمييز بسيط للأنمي بناءً على التصنيفات إذا أمكن، أو الاعتماد على السياق
    
    text = f"{icon} <b>{title}</b>\n⭐️ {rating}/10\n📅 {year}"

    if details:
        if media_type == 'movie':
            runtime = details.get('runtime')
            if runtime: text += f"\n⏱ المدة: {runtime} دقيقة"
        else:
            seasons = details.get('number_of_seasons')
            if seasons: text += f"\n🎞 المواسم: {seasons}"
        
        cast = details.get('credits', {}).get('cast', [])[:3]
        if cast:
            actors = ", ".join([actor['name'] for actor in cast])
            text += f"\n🎭 بطولة: {actors}"

    text += f"\n\n📝 <b>القصة:</b>\n{safe_overview[:400]}..."
    return text

# --- المعالجات ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_text = f"مرحباً {user.first_name}! 🍿\nاختر القسم الذي تود استكشافه:"
    
    keyboard = [
        [InlineKeyboardButton("🎲 فيلم عشوائي", callback_data='random_movie')],
        [InlineKeyboardButton("📺 مسلسل عشوائي", callback_data='random_tv')],
        [InlineKeyboardButton("🎨 أنمي عشوائي", callback_data='random_anime')],
        [InlineKeyboardButton("🔍 بحث", callback_data='prompt_search')],
        [InlineKeyboardButton("🎭 تصنيفات", callback_data='main_categories')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='HTML')
    else:
        await update.callback_query.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='HTML')

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("اكتب اسم الفيلم أو المسلسل.\nمثال: /search Naruto")
        return
    query = " ".join(context.args)
    context.user_data['search_media_type'] = 'multi' # بحث شامل
    await perform_search(update, context, query)

async def prompt_search_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎬 فيلم", callback_data='set_search_movie')],
        [InlineKeyboardButton("📺 مسلسل", callback_data='set_search_tv')],
        [InlineKeyboardButton("🎨 أنمي", callback_data='set_search_anime')],
        [InlineKeyboardButton("🔙 إلغاء", callback_data='back_to_start')]
    ]
    try:
        await update.callback_query.edit_message_text("ما نوع ما تريد البحث عنه؟", reply_markup=InlineKeyboardMarkup(keyboard))
    except:
        await update.callback_query.message.reply_text("ما نوع ما تريد البحث عنه؟", reply_markup=InlineKeyboardMarkup(keyboard))

async def perform_search(update: Update, context: ContextTypes.DEFAULT_TYPE, query_str):
    media_type = context.user_data.get('search_media_type', 'movie')
    results = []
    
    # التعامل مع البحث الشامل (يمكن للمستخدم البحث في كل شيء أو نوع محدد)
    # للتبسيط هنا، سنبحث في النوع المحدد
    if media_type == 'anime':
        # الأنمي يمكن أن يكون أفلام (movie) أو مسلسلات (tv)، سنبحث في الاثنين مع فلتر الأنمي
        results = search_items(query_str, 'movie')
        tv_results = search_items(query_str, 'tv')
        # دمج النتائج (قد يحتاج تحسين لكنه يعمل للتجربة)
        all_results = results + tv_results
        # فلترة يدوية بسيطة للتأكد من أنها أنمي (لأن TMDB لا تدعم فلتر الأنمي في search مباشرة)
        # لكن سنكتفي بعرض النتائج الأولية
        results = all_results
    else:
        results = search_items(query_str, media_type)

    if not results:
        msg = "لم أجد نتائج! 😔"
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
    # تحديد نوع الوسائط من أول نتيجة (لأن البحث الشامل قد يخلط)
    media_type = 'movie' # افتراضي
    if results:
        # محاولة تخمين النوع من البيانات (بسيط)
        if 'first_air_date' in results[0]: media_type = 'tv'
        else: media_type = 'movie'
        
    index = context.user_data.get('current_index', 0)
    
    if not results: return
    if index >= len(results): index = 0
    
    item = results[index]
    item_details = get_item_details(media_type, item['id'])
    caption = format_item_text(item, item_details, media_type)
    poster_path = item.get('poster_path')
    
    keyboard = []
    # التنقل
    nav_row = []
    if index > 0: nav_row.append(InlineKeyboardButton("◀️", callback_data='search_prev'))
    nav_row.append(InlineKeyboardButton(f"{index+1}/{len(results)}", callback_data='ignore'))
    if index < len(results)-1: nav_row.append(InlineKeyboardButton("▶️", callback_data='search_next'))
    keyboard.append(nav_row)
    
    # التريلر والعودة
    action_row = []
    trailer_key = None
    if item_details:
        for v in item_details.get('videos', {}).get('results', []):
            if v['type'] == 'Trailer' and v['site'] == 'YouTube':
                trailer_key = v['key']; break
    if trailer_key:
        action_row.append(InlineKeyboardButton("🎥 Trailer", url=f"{YOUTUBE_BASE_URL}{trailer_key}"))
    
    action_row.append(InlineKeyboardButton("🏠 الرئيسية", callback_data='back_to_start'))
    keyboard.append(action_row)
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # إرسال
    if poster_path:
        photo_url = f"{TMDB_IMAGE_BASE_URL}{poster_path}"
        try:
            if update.callback_query and update.callback_query.message.photo:
                await update.callback_query.edit_message_media(
                    media=InputMediaPhoto(media=photo_url, caption=caption, parse_mode='HTML'),
                    reply_markup=reply_markup
                )
            else:
                raise Exception("Send new")
        except Exception:
            if update.callback_query:
                await update.callback_query.message.reply_photo(photo=photo_url, caption=caption, reply_markup=reply_markup, parse_mode='HTML')
            else:
                await update.message.reply_photo(photo=photo_url, caption=caption, reply_markup=reply_markup, parse_mode='HTML')
    else:
        try:
            if update.callback_query:
                await update.callback_query.edit_message_text(caption, reply_markup=reply_markup, parse_mode='HTML')
            else:
                await update.message.reply_text(caption, reply_markup=reply_markup, parse_mode='HTML')
        except BadRequest:
            if update.callback_query:
                await update.callback_query.message.reply_text(caption, reply_markup=reply_markup, parse_mode='HTML')
            else:
                await update.message.reply_text(caption, reply_markup=reply_markup, parse_mode='HTML')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    # --- البحث ---
    if data == 'prompt_search':
        await prompt_search_type(query, context)
    elif data == 'set_search_movie':
        context.user_data['search_media_type'] = 'movie'
        try: await query.edit_message_text("أرسل اسم الفيلم 👇")
        except: await query.message.reply_text("أرسل اسم الفيلم 👇")
    elif data == 'set_search_tv':
        context.user_data['search_media_type'] = 'tv'
        try: await query.edit_message_text("أرسل اسم المسلسل 👇")
        except: await query.message.reply_text("أرسل اسم المسلسل 👇")
    elif data == 'set_search_anime':
        context.user_data['search_media_type'] = 'anime'
        try: await query.edit_message_text("أرسل اسم الأنمي 👇")
        except: await query.message.reply_text("أرسل اسم الأنمي 👇")

    elif data == 'search_next':
        context.user_data['current_index'] += 1
        await show_search_result(query, context)
    elif data == 'search_prev':
        context.user_data['current_index'] -= 1
        await show_search_result(query, context)

    # --- التنقل الرئيسي ---
    elif data == 'back_to_start':
        if 'search_results' in context.user_data: del context.user_data['search_results']
        try: await query.delete_message()
        except: pass
        await start(update, context)

    elif data == 'main_categories':
        keyboard = [
            [InlineKeyboardButton("🎬 تصنيفات الأفلام", callback_data='genres_menu_movie')],
            [InlineKeyboardButton("📺 تصنيفات المسلسلات", callback_data='genres_menu_tv')],
            [InlineKeyboardButton("🔙 رجوع", callback_data='back_to_start')]
        ]
        try: await query.edit_message_text("اختر القسم:", reply_markup=InlineKeyboardMarkup(keyboard))
        except: await query.message.reply_text("اختر القسم:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith('genres_menu_'):
        m_type = data.split('_')[2]
        genres = get_genres(m_type)
        if not genres:
            await query.message.reply_text("تعذر جلب التصنيفات.")
            return
        keyboard = []
        for i in range(0, len(genres), 2):
            row = [InlineKeyboardButton(genres[i]['name'], callback_data=f"genre_{m_type}_{genres[i]['id']}")]
            if i + 1 < len(genres):
                row.append(InlineKeyboardButton(genres[i+1]['name'], callback_data=f"genre_{m_type}_{genres[i+1]['id']}"))
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data='main_categories')])
        try: await query.edit_message_text("اختر تصنيفاً:", reply_markup=InlineKeyboardMarkup(keyboard))
        except: await query.message.reply_text("اختر تصنيفاً:", reply_markup=InlineKeyboardMarkup(keyboard))

    # --- العشوائي ---
    elif data in ['random_movie', 'random_tv', 'random_anime']:
        m_type = 'movie' if 'movie' in data else 'tv'
        g_id = GENRE_ID_ANIMATION if 'anime' in data else None
        
        # تصحيح: الأنمي في المسلسلات يعتبر TV مع تصنيف أنمي
        if data == 'random_anime':
             # سنبحث في المسلسلات لأن معظم الأنمي مسلسلات
             await send_item_suggestion(query, context, media_type='tv', genre_id=GENRE_ID_ANIMATION)
        else:
             await send_item_suggestion(query, context, media_type=m_type, genre_id=g_id)

    elif data.startswith('genre_'):
        parts = data.split('_')
        m_type = parts[1]
        g_id = parts[2]
        await send_item_suggestion(query, context, media_type=m_type, genre_id=g_id)

async def send_item_suggestion(query, context, media_type='movie', genre_id=None):
    item = get_random_item(media_type, genre_id)
    if item:
        details = get_item_details(media_type, item['id'])
        caption = format_item_text(item, details, media_type)
        poster = item.get('poster_path')
        
        keyboard = []
        row1 = []
        trailer_key = None
        if details:
            for v in details.get('videos', {}).get('results', []):
                if v['type'] == 'Trailer' and v['site'] == 'YouTube':
                    trailer_key = v['key']; break
        
        if trailer_key:
            row1.append(InlineKeyboardButton("🎥 Trailer", url=f"{YOUTUBE_BASE_URL}{trailer_key}"))
        
        # تحديد زر "آخر"
        next_cb = f"random_{media_type}"
        if genre_id == GENRE_ID_ANIMATION:
            next_cb = "random_anime"
        elif genre_id:
            next_cb = f"genre_{media_type}_{genre_id}"
            
        row1.append(InlineKeyboardButton("🔄 آخر", callback_data=next_cb))
        keyboard.append(row1)
        
        keyboard.append([InlineKeyboardButton("🏠 الرئيسية", callback_data='back_to_start')])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if poster:
            photo_url = f"{TMDB_IMAGE_BASE_URL}{poster}"
            try:
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

if __name__ == '__main__':
    if TELEGRAM_TOKEN == 'YOUR_TELEGRAM_BOT_TOKEN' or TMDB_API_KEY == 'YOUR_TMDB_API_KEY':
        print("خطأ: Tokens missing.")
    else:
        application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
        application.add_handler(CommandHandler('start', start))
        application.add_handler(CommandHandler('search', search_command))
        application.add_handler(CallbackQueryHandler(button_handler))
        print("Media Bot (Movies, TV, Anime) is running...")
        application.run_polling()
