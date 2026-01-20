import logging
import requests
import random
import json
import os
import asyncio
from functools import lru_cache
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from telegram.error import BadRequest, TimedOut, NetworkError, Forbidden

# --- الإعدادات ---
# استبدلها بالتوكن الخاص بك
TELEGRAM_TOKEN = '6741306329:AAF9gyhoD_li410vEdu62s7WlhZVVpKJu58'
TMDB_API_KEY = '69075ed729d6771ee24e8ce5e2555d92'

# ضع قناة الاشتراك الإجباري (بدون @ في الكود، سيتم إضافتها تلقائياً إذا لزم الأمر)
CHANNEL_USERNAME = 'toiii' 

# ضع أرقام ID الأدمن
ADMIN_IDS = [778375826] 

TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
YOUTUBE_BASE_URL = "https://www.youtube.com/watch?v="
USERS_DB = "users.json"

# معرفات ثابتة
GENRE_ID_ANIMATION = 16
CACHE_SIZE = 100

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- إدارة المستخدمين والاشتراك ---

def load_users():
    if not os.path.exists(USERS_DB):
        return []
    try:
        with open(USERS_DB, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading users: {e}")
        return []

def save_user(user_id):
    users = load_users()
    if user_id not in users:
        users.append(user_id)
        try:
            with open(USERS_DB, 'w', encoding='utf-8') as f:
                json.dump(users, f)
        except Exception as e:
            logger.error(f"Error saving user: {e}")

async def is_subscribed(user_id, bot):
    if not CHANNEL_USERNAME or CHANNEL_USERNAME == '@YourChannelHere':
        return True
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Forbidden:
        logger.error(f"Bot is not admin in channel {CHANNEL_USERNAME} or channel ID is wrong.")
        return False
    except Exception as e:
        logger.error(f"Subscription check error: {e}")
        return False

# --- وظائف TMDB ---

@lru_cache(maxsize=CACHE_SIZE)
def _sync_fetch_tmdb(url):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"TMDB Sync Fetch Error for {url}: {e}")
        return None

async def fetch_tmdb(url):
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(None, _sync_fetch_tmdb, url)
    except Exception as e:
        logger.error(f"TMDB Async Fetch Error: {e}")
        return None

async def get_genres(media_type='movie'):
    url = f"{TMDB_BASE_URL}/genre/{media_type}/list?api_key={TMDB_API_KEY}&language=ar"
    data = await fetch_tmdb(url)
    return data.get('genres', []) if data else []

async def get_trending(media_type='movie'):
    url = f"{TMDB_BASE_URL}/trending/{media_type}/day?api_key={TMDB_API_KEY}&language=ar"
    data = await fetch_tmdb(url)
    return data.get('results', []) if data else []

async def get_random_item(media_type='movie', genre_id=None):
    for _ in range(3):
        page = random.randint(1, 20)
        url = f"{TMDB_BASE_URL}/discover/{media_type}?api_key={TMDB_API_KEY}&language=ar&sort_by=popularity.desc&page={page}"
        if genre_id: url += f"&with_genres={genre_id}"
        data = await fetch_tmdb(url)
        results = data.get('results', []) if data else []
        if results: return random.choice(results)
    return None

async def get_item_details(media_type, item_id):
    url = f"{TMDB_BASE_URL}/{media_type}/{item_id}?api_key={TMDB_API_KEY}&language=ar&append_to_response=credits,videos,similar"
    return await fetch_tmdb(url)

async def get_person_details(person_id):
    url = f"{TMDB_BASE_URL}/person/{person_id}?api_key={TMDB_API_KEY}&language=ar&append_to_response=movie_credits,tv_credits"
    return await fetch_tmdb(url)

async def get_collection_details(collection_id):
    url = f"{TMDB_BASE_URL}/collection/{collection_id}?api_key={TMDB_API_KEY}&language=ar"
    return await fetch_tmdb(url)

async def search_items(query, media_type='multi'):
    url = f"{TMDB_BASE_URL}/search/{media_type}?api_key={TMDB_API_KEY}&language=ar&query={query}&page=1"
    data = await fetch_tmdb(url)
    return data.get('results', []) if data else []

def format_item_text(item, details=None, media_type='movie'):
    title = item.get('title') if media_type == 'movie' else item.get('name')
    overview = item.get('overview', 'لا يوجد وصف متاح.')
    rating = item.get('vote_average', 0)
    date = item.get('release_date') if media_type == 'movie' else item.get('first_air_date')
    year = date[:4] if date else 'غير معروف'
    
    safe_overview = overview.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    
    icon = "🎬" if media_type == 'movie' else "📺"
    text = f"{icon} <b>{title}</b>\n\n⭐️ التقييم: <code>{rating}/10</code>\n📅 السنة: <code>{year}</code>"
    
    if details:
        if media_type == 'movie':
            runtime = details.get('runtime')
            if runtime: text += f"\n⏱ المدة: <code>{runtime} دقيقة</code>"
        else:
            seasons = details.get('number_of_seasons')
            episodes = details.get('number_of_episodes')
            if seasons: text += f"\n🎞 المواسم: <code>{seasons}</code>"
            if episodes: text += f"\n📽 الحلقات: <code>{episodes}</code>"
        
        genres = details.get('genres', [])
        if genres:
            g_names = ", ".join([g['name'] for g in genres])
            text += f"\n🎭 التصنيف: <code>{g_names}</code>"
        
        cast = details.get('credits', {}).get('cast', [])[:3]
        if cast:
            actors = ", ".join([actor['name'] for actor in cast])
            text += f"\n🌟 بطولة: <code>{actors}</code>"

    text += f"\n\n📝 <b>القصة:</b>\n<i>{safe_overview[:500]}...</i>"
    return text

# --- دوال مساعدة للإرسال ---

async def send_or_edit(update: Update, context: ContextTypes.DEFAULT_TYPE, text, reply_markup=None, photo_url=None):
    is_callback = bool(update.callback_query)
    chat_id = update.effective_chat.id

    try:
        if is_callback:
            query = update.callback_query
            msg = query.message
            
            if photo_url:
                new_media = InputMediaPhoto(media=photo_url, caption=text, parse_mode='HTML')
                if msg.photo:
                    try:
                        await msg.edit_media(media=new_media, reply_markup=reply_markup)
                    except BadRequest as e:
                        if "not modified" in str(e).lower():
                             await msg.edit_caption(caption=text, reply_markup=reply_markup, parse_mode='HTML')
                        else:
                            await context.bot.send_photo(chat_id=chat_id, photo=photo_url, caption=text, reply_markup=reply_markup, parse_mode='HTML')
                else:
                    try: await msg.delete()
                    except: pass
                    await context.bot.send_photo(chat_id=chat_id, photo=photo_url, caption=text, reply_markup=reply_markup, parse_mode='HTML')
            else:
                if msg.text or msg.caption:
                    try:
                        await msg.edit_text(text, reply_markup=reply_markup, parse_mode='HTML')
                    except BadRequest:
                        try: await msg.delete()
                        except: pass
                        await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode='HTML')
                else:
                    await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode='HTML')
        else:
            if photo_url:
                await update.message.reply_photo(photo=photo_url, caption=text, reply_markup=reply_markup, parse_mode='HTML')
            else:
                await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')
                
    except Exception as e:
        logger.error(f"Error in send_or_edit: {e}")

# --- المعالجات ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user.id)
    
    if not await is_subscribed(user.id, context.bot):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔔 اشترك الآن", url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}")],
            [InlineKeyboardButton("✅ تم الاشتراك", callback_data='check_sub')]
        ])
        text = "⛔️ عذراً، يجب عليك الاشتراك في القناة لاستخدام البوت:"
        if update.message: await update.message.reply_text(text, reply_markup=keyboard)
        else: await send_or_edit(update, context, text, reply_markup=keyboard)
        return

    buttons = [
        [InlineKeyboardButton("🔥 ترند اليوم", callback_data='trending_menu')],
        [InlineKeyboardButton("🎲 فيلم عشوائي", callback_data='random_movie'), InlineKeyboardButton("📺 مسلسل عشوائي", callback_data='random_tv')],
        [InlineKeyboardButton("🔍 بحث", callback_data='prompt_search'), InlineKeyboardButton("🎭 التصنيفات", callback_data='main_categories')],
    ]
    
    if user.id in ADMIN_IDS:
        buttons.append([InlineKeyboardButton("⚙️ لوحة التحكم", callback_data='admin_panel')])
    
    welcome_text = f"👋 أهلاً بك {user.first_name}! 🍿\nماذا تريد أن تشاهد اليوم؟"
    await send_or_edit(update, context, welcome_text, reply_markup=InlineKeyboardMarkup(buttons))

async def check_sub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if await is_subscribed(query.from_user.id, context.bot):
        await query.answer("✅ تم التحقق بنجاح!", show_alert=False)
        await start(update, context)
    else:
        await query.answer("❌ لم تقم بالاشتراك بعد!", show_alert=True)

async def trending_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔥 أفلام رائجة", callback_data='trending_movie')],
        [InlineKeyboardButton("📺 مسلسلات رائجة", callback_data='trending_tv')],
        [InlineKeyboardButton("🔙 رجوع", callback_data='back_to_start')]
    ]
    await send_or_edit(update, context, "📈 اختر قسم الترند:", reply_markup=InlineKeyboardMarkup(keyboard))

async def show_trending_list(update: Update, context: ContextTypes.DEFAULT_TYPE, media_type='movie'):
    results = await get_trending(media_type)
    if not results:
        await send_or_edit(update, context, "❌ حدث خطأ في جلب البيانات.")
        return

    text = f"🔥 <b>الأكثر رواجاً اليوم ({'أفلام' if media_type == 'movie' else 'مسلسلات'})</b>:\n\n"
    keyboard = []
    for i, item in enumerate(results[:10]): 
        title = item.get('title') or item.get('name')
        rating = item.get('vote_average', 0)
        text += f"{i+1}. {title} (⭐️ {rating})\n"
        keyboard.append([InlineKeyboardButton(f"{i+1}. {title}", callback_data=f"info_{media_type}_{item['id']}")])
    
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data='trending_menu')])
    await send_or_edit(update, context, text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_item_info(update: Update, context: ContextTypes.DEFAULT_TYPE, media_type, item_id):
    details = await get_item_details(media_type, item_id)
    if not details:
         await send_or_edit(update, context, "❌ تعذر جلب التفاصيل.")
         return

    caption = format_item_text(details, details, media_type)
    poster_path = details.get('poster_path')
    photo_url = f"{TMDB_IMAGE_BASE_URL}{poster_path}" if poster_path else None
    
    keyboard = []
    row1 = []
    trailer_key = None
    for v in details.get('videos', {}).get('results', []):
        if v['type'] == 'Trailer' and v['site'] == 'YouTube':
            trailer_key = v['key']; break
    if trailer_key: row1.append(InlineKeyboardButton("🎥 الإعلان", url=f"{YOUTUBE_BASE_URL}{trailer_key}"))
    
    if media_type == 'movie' and details.get('belongs_to_collection'):
         cid = details['belongs_to_collection']['id']
         row1.append(InlineKeyboardButton("📚 السلسلة", callback_data=f"collection_{cid}"))
    if row1: keyboard.append(row1)

    keyboard.append([
        InlineKeyboardButton("👥 الممثلين", callback_data=f"coords_{media_type}_{item_id}"),
        InlineKeyboardButton("🎲 مشابه", callback_data=f"similar_{media_type}_{item_id}")
    ])
    keyboard.append([InlineKeyboardButton("🏠 الرئيسية", callback_data='back_to_start')])
    
    await send_or_edit(update, context, caption, reply_markup=InlineKeyboardMarkup(keyboard), photo_url=photo_url)

async def show_credits(update: Update, context: ContextTypes.DEFAULT_TYPE, media_type, item_id):
    details = await get_item_details(media_type, item_id)
    if not details: return
    cast = details.get('credits', {}).get('cast', [])
    if not cast:
        await update.callback_query.answer("لا توجد بيانات للممثلين", show_alert=True)
        return

    text = f"👥 <b>طاقم التمثيل:</b>\n\n"
    keyboard = []
    for actor in cast[:8]:
        text += f"• {actor['name']} ({actor.get('character', 'غير معروف')})\n"
        keyboard.append([InlineKeyboardButton(f"🎭 {actor['name']}", callback_data=f"person_{actor['id']}")])
    
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data=f"info_{media_type}_{item_id}")])
    await send_or_edit(update, context, text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_person(update: Update, context: ContextTypes.DEFAULT_TYPE, person_id):
    data = await get_person_details(person_id)
    if not data: return
    
    name = data.get('name')
    biography = data.get('biography', 'لا يوجد سيرة ذاتية.')
    birthday = data.get('birthday', 'غير معروف')
    profile_pic = data.get('profile_path')
    
    text = f"🎭 <b>{name}</b>\n🎂 الميلاد: <code>{birthday}</code>\n\n📝 <b>السيرة:</b>\n<i>{biography[:500]}...</i>"
    
    keyboard = []
    movies = data.get('movie_credits', {}).get('cast', [])[:5]
    for m in movies:
        keyboard.append([InlineKeyboardButton(f"🎬 {m.get('title')}", callback_data=f"info_movie_{m['id']}")])
            
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data='back_to_start')])
    photo_url = f"{TMDB_IMAGE_BASE_URL}{profile_pic}" if profile_pic else None
    await send_or_edit(update, context, text, reply_markup=InlineKeyboardMarkup(keyboard), photo_url=photo_url)

async def show_similar(update: Update, context: ContextTypes.DEFAULT_TYPE, media_type, item_id):
    details = await get_item_details(media_type, item_id)
    if not details: return
    similar = details.get('similar', {}).get('results', [])
    if not similar:
        await update.callback_query.answer("لا توجد أعمال مشابهة حالياً", show_alert=True)
        return

    text = f"🎲 <b>أعمال قد تعجبك:</b>\n\n"
    keyboard = []
    for item in similar[:8]:
        title = item.get('title') or item.get('name')
        keyboard.append([InlineKeyboardButton(f"👉 {title}", callback_data=f"info_{media_type}_{item['id']}")])
        
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data=f"info_{media_type}_{item_id}")])
    await send_or_edit(update, context, text, reply_markup=InlineKeyboardMarkup(keyboard))

# --- البحث ---

async def prompt_search_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎬 فيلم", callback_data='set_search_movie'), InlineKeyboardButton("📺 مسلسل", callback_data='set_search_tv')],
        [InlineKeyboardButton("🎨 أنمي", callback_data='set_search_anime'), InlineKeyboardButton("👤 ممثل", callback_data='set_search_person')],
        [InlineKeyboardButton("🔙 إلغاء", callback_data='back_to_start')]
    ]
    await send_or_edit(update, context, "🔍 اختر نوع البحث:", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # حالة الإذاعة للأدمن
    if user_id in ADMIN_IDS and context.user_data.get('waiting_for_broadcast'):
        await handle_broadcast_message(update, context)
        return

    # حالة البحث
    if context.user_data.get('search_media_type'):
        query = update.message.text
        await perform_search(update, context, query)
        return

async def perform_search(update: Update, context: ContextTypes.DEFAULT_TYPE, query_str):
    s_type = context.user_data.get('search_media_type', 'multi')
    
    if s_type == 'anime':
        # البحث عن أنمي باستخدام تصنيف الأنمي
        url = f"{TMDB_BASE_URL}/search/multi?api_key={TMDB_API_KEY}&language=ar&query={query_str}"
        data = await fetch_tmdb(url)
        results = [i for i in data.get('results', []) if GENRE_ID_ANIMATION in i.get('genre_ids', [])] if data else []
    else:
        results = await search_items(query_str, s_type)

    if not results:
        await update.message.reply_text("🔍 لا توجد نتائج لهذا البحث.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 الرئيسية", callback_data='back_to_start')]]))
        return
        
    context.user_data['search_results'] = results
    context.user_data['current_index'] = 0
    await show_search_result(update, context)

async def show_search_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    results = context.user_data.get('search_results', [])
    index = context.user_data.get('current_index', 0)
    
    if not results or index >= len(results): 
        await send_or_edit(update, context, "🚫 انتهت النتائج.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 الرئيسية", callback_data='back_to_start')]]))
        return
    
    item = results[index]
    media_type = item.get('media_type', 'movie' if 'release_date' in item else 'tv')
    
    if media_type == 'person':
        text = f"👤 <b>{item.get('name')}</b>\n🎭 المجال: {item.get('known_for_department', 'تمثيل')}"
        photo_url = f"{TMDB_IMAGE_BASE_URL}{item.get('profile_path')}" if item.get('profile_path') else None
        callback_info = f"person_{item['id']}"
    else:
        text = format_item_text(item, media_type=media_type)
        photo_url = f"{TMDB_IMAGE_BASE_URL}{item.get('poster_path')}" if item.get('poster_path') else None
        callback_info = f"info_{media_type}_{item['id']}"

    keyboard = [
        [InlineKeyboardButton("📖 عرض التفاصيل", callback_data=callback_info)],
        [
            InlineKeyboardButton("◀️", callback_data='search_prev'),
            InlineKeyboardButton(f"{index+1}/{len(results)}", callback_data='ignore'),
            InlineKeyboardButton("▶️", callback_data='search_next')
        ],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data='back_to_start')]
    ]
    await send_or_edit(update, context, text, reply_markup=InlineKeyboardMarkup(keyboard), photo_url=photo_url)

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: 
        await update.message.reply_text("الرجاء كتابة ما تريد البحث عنه. مثال: `/search Spiderman`", parse_mode='Markdown')
        return
    query = " ".join(context.args)
    context.user_data['search_media_type'] = 'multi'
    await perform_search(update, context, query)

# --- الأدمن ---

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    keyboard = [
        [InlineKeyboardButton("📊 الإحصائيات", callback_data='admin_stats')],
        [InlineKeyboardButton("📢 إذاعة رسالة", callback_data='admin_ask_broadcast')],
        [InlineKeyboardButton("🔙 رجوع", callback_data='back_to_start')]
    ]
    await send_or_edit(update, context, "⚙️ <b>لوحة التحكم</b>", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    users_count = len(load_users())
    await update.callback_query.answer(f"📊 عدد المشتركين: {users_count}", show_alert=True)

async def admin_ask_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    context.user_data['waiting_for_broadcast'] = True
    await send_or_edit(update, context, "📢 أرسل النص أو الصورة الآن للبث للمشتركين.\nلإلغاء العملية أرسل /start")

async def handle_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['waiting_for_broadcast'] = False
    msg = update.message
    users = load_users()
    sent, failed = 0, 0
    
    status_msg = await msg.reply_text(f"⏳ جاري الإرسال إلى {len(users)} مستخدم...")
    
    for user_id in users:
        try:
            if msg.photo: await context.bot.send_photo(chat_id=user_id, photo=msg.photo[-1].file_id, caption=msg.caption_html, parse_mode='HTML')
            elif msg.video: await context.bot.send_video(chat_id=user_id, video=msg.video.file_id, caption=msg.caption_html, parse_mode='HTML')
            elif msg.text: await context.bot.send_message(chat_id=user_id, text=msg.text_html, parse_mode='HTML')
            sent += 1
            if sent % 25 == 0: await asyncio.sleep(1)
        except: failed += 1
            
    await status_msg.edit_text(f"✅ انتهى الإرسال!\n\n🚀 نجح: {sent}\n❌ فشل: {failed}")

# --- توزيع الأزرار ---

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    try: await query.answer()
    except: pass
    
    if data == 'back_to_start': await start(update, context)
    elif data == 'check_sub': await check_sub_callback(update, context)
    elif data == 'prompt_search': await prompt_search_type(update, context)
    elif data == 'trending_menu': await trending_menu(update, context)
    elif data == 'admin_panel': await admin_panel(update, context)
    elif data == 'admin_stats': await admin_stats(update, context)
    elif data == 'admin_ask_broadcast': await admin_ask_broadcast(update, context)
    elif data.startswith('trending_'): await show_trending_list(update, context, data.split('_')[1])
    elif data.startswith('set_search_'):
        m_type = data.split('_')[2]
        context.user_data['search_media_type'] = m_type
        names = {'movie': 'فيلم', 'tv': 'مسلسل', 'anime': 'أنمي', 'person': 'ممثل'}
        await send_or_edit(update, context, f"🔍 أرسل اسم <b>{names.get(m_type)}</b> الذي تبحث عنه 👇")
    elif data == 'search_next': 
        context.user_data['current_index'] += 1; await show_search_result(update, context)
    elif data == 'search_prev': 
        context.user_data['current_index'] -= 1; await show_search_result(update, context)
    elif data in ['random_movie', 'random_tv']:
        m_type = data.split('_')[1]
        item = await get_random_item(m_type)
        if item: await show_item_info(update, context, m_type, item['id'])
        else: await send_or_edit(update, context, "❌ لم يتم العثور على نتائج.")
    elif data == 'main_categories':
        keyboard = [[InlineKeyboardButton("🎬 أفلام", callback_data='genres_menu_movie'), InlineKeyboardButton("📺 مسلسلات", callback_data='genres_menu_tv')], [InlineKeyboardButton("🔙 رجوع", callback_data='back_to_start')]]
        await send_or_edit(update, context, "🎭 اختر القسم:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data.startswith('genres_menu_'):
        m_type = data.split('_')[2]; genres = await get_genres(m_type)
        keyboard = []
        for i in range(0, len(genres), 2):
            row = [InlineKeyboardButton(genres[i]['name'], callback_data=f"genre_{m_type}_{genres[i]['id']}")]
            if i + 1 < len(genres): row.append(InlineKeyboardButton(genres[i+1]['name'], callback_data=f"genre_{m_type}_{genres[i+1]['id']}"))
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data='main_categories')])
        await send_or_edit(update, context, "🎭 اختر تصنيفاً:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data.startswith('genre_'):
        parts = data.split('_')
        item = await get_random_item(parts[1], genre_id=parts[2])
        if item: await show_item_info(update, context, parts[1], item['id'])
        else: await send_or_edit(update, context, "❌ لم يتم العثور على أعمال.")
    elif data.startswith('info_'):
        _, m_type, i_id = data.split('_'); await show_item_info(update, context, m_type, i_id)
    elif data.startswith('coords_'): 
        _, m_type, i_id = data.split('_'); await show_credits(update, context, m_type, i_id)
    elif data.startswith('similar_'):
        _, m_type, i_id = data.split('_'); await show_similar(update, context, m_type, i_id)
    elif data.startswith('person_'):
        await show_person(update, context, data.split('_')[1])
    elif data.startswith('collection_'):
        col_data = await get_collection_details(data.split('_')[1])
        if col_data:
            text = f"📚 <b>سلسلة: {col_data.get('name')}</b>\n\n"
            keyboard = []
            for part in col_data.get('parts', [])[:10]:
                text += f"• {part.get('title')} ({part.get('release_date', '')[:4]})\n"
                keyboard.append([InlineKeyboardButton(f"🎥 {part.get('title')}", callback_data=f"info_movie_{part['id']}")])
            keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data='back_to_start')])
            await send_or_edit(update, context, text, reply_markup=InlineKeyboardMarkup(keyboard))

if __name__ == '__main__':
    if 'YOUR_TELEGRAM_BOT_TOKEN' in TELEGRAM_TOKEN or 'YOUR_TMDB_API_KEY' in TMDB_API_KEY:
        print("Error: Please set your tokens first.")
    else:
        application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
        application.add_handler(CommandHandler('start', start))
        application.add_handler(CommandHandler('search', search_command))
        application.add_handler(CommandHandler('stats', admin_stats))
        application.add_handler(CallbackQueryHandler(button_handler))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND | filters.PHOTO | filters.VIDEO, handle_message))
        print("Bot is running...")
        application.run_polling()
