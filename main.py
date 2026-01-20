import logging
import requests
import random
import json
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, filters
from telegram.error import BadRequest

# --- الإعدادات ---
TELEGRAM_TOKEN = '6741306329:AAF9gyhoD_li410vEdu62s7WlhZVVpKJu58'
TMDB_API_KEY = '69075ed729d6771ee24e8ce5e2555d92'

# ضع قناة الاشتراك الإجباري (مع @)
CHANNEL_USERNAME = '@toiii' 

# ضع أرقام ID الأدمن
ADMIN_IDS = [778375826] 

TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
YOUTUBE_BASE_URL = "https://www.youtube.com/watch?v="
USERS_DB = "users.json"

# معرفات ثابتة
GENRE_ID_ANIMATION = 16

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- إدارة المستخدمين والاشتراك ---

def load_users():
    if not os.path.exists(USERS_DB):
        return []
    try:
        with open(USERS_DB, 'r') as f:
            return json.load(f)
    except:
        return []

def save_user(user_id):
    users = load_users()
    if user_id not in users:
        users.append(user_id)
        with open(USERS_DB, 'w') as f:
            json.dump(users, f)

async def is_subscribed(user_id, bot):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception:
        return False

# --- وظائف TMDB ---

def get_genres(media_type='movie'):
    url = f"{TMDB_BASE_URL}/genre/{media_type}/list?api_key={TMDB_API_KEY}&language=ar"
    try:
        response = requests.get(url).json()
        return response.get('genres', [])
    except: return []

def get_random_item(media_type='movie', genre_id=None):
    page = random.randint(1, 50)
    url = f"{TMDB_BASE_URL}/discover/{media_type}?api_key={TMDB_API_KEY}&language=ar&sort_by=popularity.desc&page={page}"
    if genre_id: url += f"&with_genres={genre_id}"
    try:
        response = requests.get(url).json()
        results = response.get('results', [])
        if results: return random.choice(results)
    except: pass
    return None

def get_item_details(media_type, item_id):
    url = f"{TMDB_BASE_URL}/{media_type}/{item_id}?api_key={TMDB_API_KEY}&language=ar&append_to_response=credits,videos"
    try:
        return requests.get(url).json()
    except: return None

def get_collection_details(collection_id):
    url = f"{TMDB_BASE_URL}/collection/{collection_id}?api_key={TMDB_API_KEY}&language=ar"
    try:
        return requests.get(url).json()
    except: return None

def search_items(query, media_type='movie'):
    url = f"{TMDB_BASE_URL}/search/{media_type}?api_key={TMDB_API_KEY}&language=ar&query={query}"
    try:
        return requests.get(url).json().get('results', [])
    except: return []

def format_item_text(item, details=None, media_type='movie'):
    title = item.get('title') if media_type == 'movie' else item.get('name')
    overview = item.get('overview', 'لا يوجد وصف.')
    rating = item.get('vote_average', 'N/A')
    date = item.get('release_date') if media_type == 'movie' else item.get('first_air_date')
    year = date[:4] if date else '----'
    safe_overview = overview.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    
    icon = "🎬" if media_type == 'movie' else "📺"
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

    text += f"\n\n📝 <b>القصة:</b>\n{safe_overview[:350]}..."
    return text

# --- المعالجات ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    bot = context.bot
    
    # حفظ المستخدم
    save_user(user.id)
    
    # التحقق من الاشتراك
    if not await is_subscribed(user.id, bot):
        keyboard = [[InlineKeyboardButton("🔔 اشترك الآن", url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}"),
                     [InlineKeyboardButton("✅ تم الاشتراك", callback_data='check_sub')]]
        await update.message.reply_text("⛔️ عذراً، يجب عليك الاشتراك في القناة لاستخدام البوت:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    welcome_text = f"مرحباً {user.first_name}! 🍿\nاختر القسم:"
    keyboard = [
        [InlineKeyboardButton("🎲 فيلم عشوائي", callback_data='random_movie')],
        [InlineKeyboardButton("📺 مسلسل عشوائي", callback_data='random_tv')],
        [InlineKeyboardButton("🎨 أنمي عشوائي", callback_data='random_anime')],
        [InlineKeyboardButton("🔍 بحث", callback_data='prompt_search')],
        [InlineKeyboardButton("🎭 تصنيفات", callback_data='main_categories')],
    ]
    
    if user.id in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton("⚙️ الأدمن", callback_data='admin_panel')])

    await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def check_sub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if await is_subscribed(query.from_user.id, context.bot):
        try:
            await query.delete_message()
        except: pass
        # محاكاة أمر start لإعادة القائمة
        fake_update = Update(update_id=0, message=query.message)
        fake_update.message.from_user = query.from_user
        await start(fake_update, context)
    else:
        await query.answer("❌ لم تقم بالاشتراك بعد!", show_alert=True)

# --- أوامر الأدمن ---

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    users_count = len(load_users())
    await update.message.reply_text(f"📊 <b>عدد المشتركين:</b> {users_count}", parse_mode='HTML')

async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    if not context.args:
        await update.message.reply_text("استخدم: /cast الرسالة هنا")
        return
    
    text_to_send = " ".join(context.args)
    users = load_users()
    sent_count = 0
    failed_count = 0
    
    msg = await update.message.reply_text(f"جاري الإرسال إلى {len(users)} مستخدم...")
    
    for user_id in users:
        try:
            await context.bot.send_message(chat_id=user_id, text=text_to_send)
            sent_count += 1
        except:
            failed_count += 1
    
    await msg.edit_text(f"✅ تم الإرسال!\n\n✅ نجح: {sent_count}\n❌ فشل: {failed_count}")

# --- باقي الوظائف (بحث، عرض، إلخ) ---

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id not in ADMIN_IDS: return

    text = "🛠 **لوحة التحكم**"
    keyboard = [
        [InlineKeyboardButton("📊 عدد المشتركين", callback_data='admin_stats')],
        [InlineKeyboardButton("🔙 العودة", callback_data='back_to_start')]
    ]
    try: await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    except: pass

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return
    query = " ".join(context.args)
    context.user_data['search_media_type'] = 'multi'
    await perform_search(update, context, query)

async def prompt_search_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎬 فيلم", callback_data='set_search_movie')],
        [InlineKeyboardButton("📺 مسلسل", callback_data='set_search_tv')],
        [InlineKeyboardButton("🎨 أنمي", callback_data='set_search_anime')],
        [InlineKeyboardButton("🔙 إلغاء", callback_data='back_to_start')]
    ]
    try: await update.callback_query.edit_message_text("ماذا تبحث؟", reply_markup=InlineKeyboardMarkup(keyboard))
    except: pass

async def perform_search(update: Update, context: ContextTypes.DEFAULT_TYPE, query_str):
    media_type = context.user_data.get('search_media_type', 'movie')
    results = []
    if media_type == 'anime':
        results = search_items(query_str, 'movie') + search_items(query_str, 'tv')
    else:
        results = search_items(query_str, media_type)

    if not results: return
    context.user_data['search_results'] = results
    context.user_data['current_index'] = 0
    await show_search_result(update, context)

async def show_search_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    results = context.user_data.get('search_results', [])
    media_type = 'movie' if results and 'release_date' in results[0] else 'tv'
    index = context.user_data.get('current_index', 0)
    if not results: return
    if index >= len(results): index = 0
    
    item = results[index]
    item_details = get_item_details(media_type, item['id'])
    caption = format_item_text(item, item_details, media_type)
    poster_path = item.get('poster_path')
    
    keyboard = []
    nav_row = []
    if index > 0: nav_row.append(InlineKeyboardButton("◀️", callback_data='search_prev'))
    nav_row.append(InlineKeyboardButton(f"{index+1}/{len(results)}", callback_data='ignore'))
    if index < len(results)-1: nav_row.append(InlineKeyboardButton("▶️", callback_data='search_next'))
    keyboard.append(nav_row)
    
    action_row = []
    trailer_key = None
    if item_details:
        for v in item_details.get('videos', {}).get('results', []):
            if v['type'] == 'Trailer' and v['site'] == 'YouTube':
                trailer_key = v['key']; break
    if trailer_key: action_row.append(InlineKeyboardButton("🎥 Trailer", url=f"{YOUTUBE_BASE_URL}{trailer_key}"))
    
    if media_type == 'movie' and item_details and item_details.get('belongs_to_collection'):
         cid = item_details['belongs_to_collection']['id']
         action_row.append(InlineKeyboardButton("📚 الأجزاء", callback_data=f"collection_{cid}"))

    action_row.append(InlineKeyboardButton("🏠 الرئيسية", callback_data='back_to_start'))
    keyboard.append(action_row)
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    if poster_path:
        photo_url = f"{TMDB_IMAGE_BASE_URL}{poster_path}"
        try:
            if update.callback_query and update.callback_query.message.photo:
                await update.callback_query.edit_message_media(InputMediaPhoto(media=photo_url, caption=caption, parse_mode='HTML'), reply_markup=reply_markup)
            else: raise Exception("Send new")
        except:
            target = update.callback_query.message if update.callback_query else update.message
            await target.reply_photo(photo=photo_url, caption=caption, reply_markup=reply_markup, parse_mode='HTML')
    else:
        try:
            if update.callback_query: await update.callback_query.edit_message_text(caption, reply_markup=reply_markup, parse_mode='HTML')
            else: await update.message.reply_text(caption, reply_markup=reply_markup, parse_mode='HTML')
        except: pass

async def show_collection(update: Update, context: ContextTypes.DEFAULT_TYPE, collection_id):
    query = update.callback_query
    await query.answer()
    col_data = get_collection_details(collection_id)
    if not col_data: return
    name = col_data.get('name', 'سلسلة')
    parts = col_data.get('parts', [])
    text = f"📚 <b>سلسلة: {name}</b>\n\n"
    for i, part in enumerate(parts):
        p_date = part.get('release_date', '')[:4] if part.get('release_date') else '----'
        text += f"{i+1}. {part.get('title')} ({p_date})\n"
    
    keyboard = [[InlineKeyboardButton("🏠 الرئيسية", callback_data='back_to_start')]]
    try: await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    except: await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == 'check_sub': await check_sub_callback(update, context)
    elif data == 'prompt_search': await prompt_search_type(query, context)
    elif data in ['set_search_movie', 'set_search_tv', 'set_search_anime']:
        m_type = data.split('_')[2]; context.user_data['search_media_type'] = m_type
        try: await query.edit_message_text(f"أرسل اسم ال{'فيلم' if m_type=='movie' else 'مسلسل' if m_type=='tv' else 'أنمي'} 👇")
        except: pass
    elif data == 'search_next': context.user_data['current_index'] += 1; await show_search_result(query, context)
    elif data == 'search_prev': context.user_data['current_index'] -= 1; await show_search_result(query, context)
    elif data == 'admin_panel': await admin_panel(update, context)
    elif data == 'admin_stats': await admin_stats(update, context)
    elif data.startswith('collection_'): await show_collection(update, context, data.split('_')[1])
    elif data == 'back_to_start':
        try: await query.delete_message()
        except: pass
        # إعادة البدء
        fake_update = Update(update_id=0, message=query.message)
        await start(fake_update, context)
    elif data == 'main_categories':
        keyboard = [[InlineKeyboardButton("🎬 أفلام", callback_data='genres_menu_movie')],[InlineKeyboardButton("📺 مسلسلات", callback_data='genres_menu_tv')],[InlineKeyboardButton("🔙 رجوع", callback_data='back_to_start')]]
        try: await query.edit_message_text("اختر:", reply_markup=InlineKeyboardMarkup(keyboard))
        except: pass
    elif data.startswith('genres_menu_'):
        m_type = data.split('_')[2]; genres = get_genres(m_type)
        keyboard = []
        for i in range(0, len(genres), 2):
            row = [InlineKeyboardButton(genres[i]['name'], callback_data=f"genre_{m_type}_{genres[i]['id']}")]
            if i + 1 < len(genres): row.append(InlineKeyboardButton(genres[i+1]['name'], callback_data=f"genre_{m_type}_{genres[i+1]['id']}"))
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data='main_categories')])
        try: await query.edit_message_text("اختر تصنيفاً:", reply_markup=InlineKeyboardMarkup(keyboard))
        except: pass
    elif data in ['random_movie', 'random_tv', 'random_anime']:
        m_type = 'movie' if 'movie' in data else 'tv'
        g_id = GENRE_ID_ANIMATION if 'anime' in data else None
        if data == 'random_anime': await send_item_suggestion(query, context, media_type='tv', genre_id=GENRE_ID_ANIMATION)
        else: await send_item_suggestion(query, context, media_type=m_type, genre_id=g_id)
    elif data.startswith('genre_'):
        parts = data.split('_')
        await send_item_suggestion(query, context, media_type=parts[1], genre_id=parts[2])

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
                if v['type'] == 'Trailer' and v['site'] == 'YouTube': trailer_key = v['key']; break
        if trailer_key: row1.append(InlineKeyboardButton("🎥 Trailer", url=f"{YOUTUBE_BASE_URL}{trailer_key}"))
        
        if media_type == 'movie' and details and details.get('belongs_to_collection'):
            row1.append(InlineKeyboardButton("📚 الأجزاء", callback_data=f"collection_{details['belongs_to_collection']['id']}"))

        next_cb = f"random_{media_type}"
        if genre_id == GENRE_ID_ANIMATION: next_cb = "random_anime"
        elif genre_id: next_cb = f"genre_{media_type}_{genre_id}"
        row1.append(InlineKeyboardButton("🔄 آخر", callback_data=next_cb))
        keyboard.append(row1)
        keyboard.append([InlineKeyboardButton("🏠 الرئيسية", callback_data='back_to_start')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if poster:
            photo_url = f"{TMDB_IMAGE_BASE_URL}{poster}"
            try:
                if query.message.photo:
                    await query.edit_message_media(InputMediaPhoto(media=photo_url, caption=caption, parse_mode='HTML'), reply_markup=reply_markup)
                else: raise Exception("Send new")
            except: await query.message.reply_photo(photo=photo_url, caption=caption, reply_markup=reply_markup, parse_mode='HTML')
        else:
            try: await query.edit_message_text(caption, reply_markup=reply_markup, parse_mode='HTML')
            except: await query.message.reply_text(caption, reply_markup=reply_markup, parse_mode='HTML')

if __name__ == '__main__':
    if 'YOUR_TELEGRAM_BOT_TOKEN' in TELEGRAM_TOKEN or 'YOUR_TMDB_API_KEY' in TMDB_API_KEY:
        print("Error: Set tokens.")
    else:
        application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
        application.add_handler(CommandHandler('start', start))
        application.add_handler(CommandHandler('search', search_command))
        application.add_handler(CommandHandler('stats', admin_stats))
        application.add_handler(CommandHandler('cast', admin_broadcast))
        application.add_handler(CallbackQueryHandler(button_handler))
        print("Bot is running with Admin & Force Sub features...")
        application.run_polling()
