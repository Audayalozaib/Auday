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
TELEGRAM_TOKEN = '6741306329:AAF9gyhoD_li410vEdu62s7WlhZVVpKJu58'
TMDB_API_KEY = '69075ed729d6771ee24e8ce5e2555d92'
CHANNEL_USERNAME = '@toiii' 
ADMIN_IDS = [778375826] 

TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
YOUTUBE_BASE_URL = "https://www.youtube.com/watch?v="
USERS_DB = "users.json"
GENRE_ID_ANIMATION = 16

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- إدارة البيانات ---
def load_users():
    if not os.path.exists(USERS_DB): return []
    try:
        with open(USERS_DB, 'r', encoding='utf-8') as f: return json.load(f)
    except: return []

def save_user(user_id):
    users = load_users()
    if user_id not in users:
        users.append(user_id)
        with open(USERS_DB, 'w', encoding='utf-8') as f: json.dump(users, f)

# --- التحقق من الاشتراك ---
async def is_subscribed(user_id, bot):
    if not CHANNEL_USERNAME or "YourChannelHere" in CHANNEL_USERNAME: return True
    try:
        chat_id = CHANNEL_USERNAME if CHANNEL_USERNAME.startswith('@') else f"@{CHANNEL_USERNAME}"
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except: return False

# --- وظائف TMDB ---
@lru_cache(maxsize=128)
def _sync_fetch(url):
    try:
        res = requests.get(url, timeout=10)
        return res.json() if res.status_code == 200 else None
    except: return None

async def fetch_tmdb(url):
    return await asyncio.get_running_loop().run_in_executor(None, _sync_fetch, url)

async def get_item_details(media_type, item_id):
    url = f"{TMDB_BASE_URL}/{media_type}/{item_id}?api_key={TMDB_API_KEY}&language=ar&append_to_response=credits,videos,similar"
    return await fetch_tmdb(url)

async def get_genres(media_type='movie'):
    url = f"{TMDB_BASE_URL}/genre/{media_type}/list?api_key={TMDB_API_KEY}&language=ar"
    data = await fetch_tmdb(url)
    return data.get('genres', []) if data else []

async def get_random_item(media_type='movie', genre_id=None):
    for _ in range(5):
        page = random.randint(1, 50)
        url = f"{TMDB_BASE_URL}/discover/{media_type}?api_key={TMDB_API_KEY}&language=ar&sort_by=popularity.desc&page={page}"
        if genre_id: url += f"&with_genres={genre_id}"
        data = await fetch_tmdb(url)
        if data and data.get('results'): return random.choice(data['results'])
    return None

# --- التنسيق والإرسال ---
def format_item_text(item, media_type='movie'):
    title = item.get('title') or item.get('name') or "غير معروف"
    overview = item.get('overview') or "لا يوجد وصف متاح حالياً."
    rating = item.get('vote_average', 0)
    date = item.get('release_date') or item.get('first_air_date') or "----"
    
    text = f"🎬 <b>{title}</b>\n\n"
    text += f"⭐️ التقييم: <code>{rating}/10</code>\n"
    text += f"📅 السنة: <code>{date[:4]}</code>\n"
    
    if 'genres' in item:
        g_names = ", ".join([g['name'] for g in item['genres']])
        text += f"🎭 التصنيف: <code>{g_names}</code>\n"
    
    if 'number_of_seasons' in item:
        text += f"🎞 المواسم: <code>{item['number_of_seasons']}</code>\n"
        text += f"📽 الحلقات: <code>{item.get('number_of_episodes', '??')}</code>\n"
    
    if 'runtime' in item and item['runtime']:
        text += f"⏱ المدة: <code>{item['runtime']} دقيقة</code>\n"

    text += f"\n📝 <b>القصة:</b>\n<i>{overview[:500]}...</i>"
    return text

async def send_or_edit(update, context, text, reply_markup=None, photo=None):
    chat_id = update.effective_chat.id
    try:
        if update.callback_query:
            msg = update.callback_query.message
            if photo:
                if msg.photo:
                    await msg.edit_media(InputMediaPhoto(photo, caption=text, parse_mode='HTML'), reply_markup=reply_markup)
                else:
                    try: await msg.delete()
                    except: pass
                    await context.bot.send_photo(chat_id, photo, caption=text, reply_markup=reply_markup, parse_mode='HTML')
            else:
                if msg.text or msg.caption:
                    await msg.edit_text(text, reply_markup=reply_markup, parse_mode='HTML')
                else:
                    await context.bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode='HTML')
        else:
            if photo:
                await context.bot.send_photo(chat_id, photo, caption=text, reply_markup=reply_markup, parse_mode='HTML')
            else:
                await context.bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode='HTML')
    except Exception as e:
        logger.error(f"Send error: {e}")
        await context.bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode='HTML')

# --- المعالجات ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    save_user(user_id)
    
    if not await is_subscribed(user_id, context.bot):
        btn = [[InlineKeyboardButton("📢 اشترك في القناة", url=f"https://t.me/{CHANNEL_USERNAME.replace('@','')}")],
               [InlineKeyboardButton("✅ تم الاشتراك", callback_data='check_sub')]]
        await send_or_edit(update, context, "⚠️ عذراً، يجب عليك الاشتراك في القناة أولاً لاستخدام البوت.", InlineKeyboardMarkup(btn))
        return

    btn = [
        [InlineKeyboardButton("🔥 الترند", callback_data='trending'), InlineKeyboardButton("🎲 عشوائي", callback_data='random_menu')],
        [InlineKeyboardButton("🔍 بحث", callback_data='search_menu'), InlineKeyboardButton("🎭 تصنيفات", callback_data='main_genres')],
    ]
    if user_id in ADMIN_IDS:
        btn.append([InlineKeyboardButton("⚙️ لوحة الأدمن", callback_data='admin_panel')])
        
    await send_or_edit(update, context, f"👋 أهلاً بك {update.effective_user.first_name}!\nاستكشف عالم الأفلام والمسلسلات الآن:", InlineKeyboardMarkup(btn))

async def handle_interaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    await query.answer()

    if data == 'check_sub': await start(update, context)
    elif data == 'back': await start(update, context)
    
    # لوحة الأدمن
    elif data == 'admin_panel' and user_id in ADMIN_IDS:
        btn = [[InlineKeyboardButton("📊 الإحصائيات", callback_data='admin_stats')],
               [InlineKeyboardButton("📢 إذاعة رسالة", callback_data='admin_broadcast')],
               [InlineKeyboardButton("🔙 رجوع", callback_data='back')]]
        await send_or_edit(update, context, "⚙️ <b>لوحة تحكم الأدمن:</b>", InlineKeyboardMarkup(btn))
    
    elif data == 'admin_stats' and user_id in ADMIN_IDS:
        await query.answer(f"📊 عدد المستخدمين: {len(load_users())}", show_alert=True)
    
    elif data == 'admin_broadcast' and user_id in ADMIN_IDS:
        context.user_data['state'] = 'broadcast'
        await send_or_edit(update, context, "📢 أرسل الآن ما تريد إذاعته (نص، صورة، فيديو):")

    # القائمة العشوائية
    elif data == 'random_menu':
        btn = [[InlineKeyboardButton("🎬 فيلم", callback_data='rand_movie'), InlineKeyboardButton("📺 مسلسل", callback_data='rand_tv')],
               [InlineKeyboardButton("🔙 رجوع", callback_data='back')]]
        await send_or_edit(update, context, "🎲 اختر النوع الذي تريد اقتراحه:", InlineKeyboardMarkup(btn))

    elif data.startswith('rand_'):
        m_type = 'movie' if 'movie' in data else 'tv'
        item = await get_random_item(m_type)
        if item: await show_item_info(update, context, m_type, item['id'])

    # التصنيفات
    elif data == 'main_genres':
        btn = [[InlineKeyboardButton("🎬 أفلام", callback_data='genres_movie'), InlineKeyboardButton("📺 مسلسلات", callback_data='genres_tv')],
               [InlineKeyboardButton("🔙 رجوع", callback_data='back')]]
        await send_or_edit(update, context, "🎭 اختر القسم:", InlineKeyboardMarkup(btn))

    elif data.startswith('genres_'):
        m_type = data.split('_')[1]
        genres = await get_genres(m_type)
        btn = []
        for i in range(0, len(genres), 2):
            row = [InlineKeyboardButton(genres[i]['name'], callback_data=f"gsearch_{m_type}_{genres[i]['id']}")]
            if i+1 < len(genres): row.append(InlineKeyboardButton(genres[i+1]['name'], callback_data=f"gsearch_{m_type}_{genres[i+1]['id']}"))
            btn.append(row)
        btn.append([InlineKeyboardButton("🔙 رجوع", callback_data='main_genres')])
        await send_or_edit(update, context, "🎭 اختر التصنيف:", InlineKeyboardMarkup(btn))

    elif data.startswith('gsearch_'):
        _, m_type, g_id = data.split('_')
        item = await get_random_item(m_type, g_id)
        if item: await show_item_info(update, context, m_type, item['id'])

    # الترند
    elif data == 'trending':
        data = await fetch_tmdb(f"{TMDB_BASE_URL}/trending/all/day?api_key={TMDB_API_KEY}&language=ar")
        if data and data.get('results'):
            txt = "🔥 <b>أهم الترندات اليوم:</b>\n\n"
            btn = []
            for i, item in enumerate(data['results'][:10]):
                name = item.get('title') or item.get('name')
                m_type = item.get('media_type', 'movie')
                txt += f"{i+1}. {name}\n"
                btn.append([InlineKeyboardButton(f"{i+1}. {name}", callback_data=f"info_{m_type}_{item['id']}")])
            btn.append([InlineKeyboardButton("🔙 رجوع", callback_data='back')])
            await send_or_edit(update, context, txt, InlineKeyboardMarkup(btn))

    # البحث
    elif data == 'search_menu':
        btn = [[InlineKeyboardButton("🎬 فيلم", callback_data='set_search_movie'), InlineKeyboardButton("📺 مسلسل", callback_data='set_search_tv')],
               [InlineKeyboardButton("🎨 أنمي", callback_data='set_search_anime'), InlineKeyboardButton("👤 ممثل", callback_data='set_search_person')],
               [InlineKeyboardButton("🔙 رجوع", callback_data='back')]]
        await send_or_edit(update, context, "🔍 اختر نوع البحث الذي تريده:", InlineKeyboardMarkup(btn))

    elif data.startswith('set_search_'):
        context.user_data['search_type'] = data.split('_')[2]
        context.user_data['state'] = 'waiting_search'
        await send_or_edit(update, context, "🔍 أرسل الآن اسم ما تبحث عنه 👇")

    # عرض المعلومات
    elif data.startswith('info_'):
        _, m_type, i_id = data.split('_')
        await show_item_info(update, context, m_type, i_id)
    
    elif data.startswith('credits_'):
        _, m_type, i_id = data.split('_')
        item = await get_item_details(m_type, i_id)
        if item:
            cast = item.get('credits', {}).get('cast', [])[:10]
            txt = "👥 <b>طاقم التمثيل:</b>\n\n"
            btn = []
            for actor in cast:
                txt += f"• {actor['name']} ({actor.get('character', '??')})\n"
                btn.append([InlineKeyboardButton(f"🎭 {actor['name']}", callback_data=f"person_{actor['id']}")])
            btn.append([InlineKeyboardButton("🔙 رجوع", callback_data=f"info_{m_type}_{i_id}")])
            await send_or_edit(update, context, txt, InlineKeyboardMarkup(btn))

    elif data.startswith('similar_'):
        _, m_type, i_id = data.split('_')
        item = await get_item_details(m_type, i_id)
        if item:
            similar = item.get('similar', {}).get('results', [])[:8]
            txt = "🎲 <b>أعمال مشابهة قد تعجبك:</b>\n\n"
            btn = []
            for s in similar:
                name = s.get('title') or s.get('name')
                btn.append([InlineKeyboardButton(f"👉 {name}", callback_data=f"info_{m_type}_{s['id']}")])
            btn.append([InlineKeyboardButton("🔙 رجوع", callback_data=f"info_{m_type}_{i_id}")])
            await send_or_edit(update, context, txt, InlineKeyboardMarkup(btn))

    elif data.startswith('person_'):
        p_id = data.split('_')[1]
        p = await fetch_tmdb(f"{TMDB_BASE_URL}/person/{p_id}?api_key={TMDB_API_KEY}&language=ar&append_to_response=movie_credits")
        if p:
            txt = f"👤 <b>{p['name']}</b>\n🎂 الميلاد: <code>{p.get('birthday', '??')}</code>\n\n📝 <b>السيرة:</b>\n<i>{p.get('biography', 'لا توجد')[:500]}...</i>"
            poster = f"{TMDB_IMAGE_BASE_URL}{p.get('profile_path')}" if p.get('profile_path') else None
            btn = [[InlineKeyboardButton("🏠 الرئيسية", callback_data='back')]]
            await send_or_edit(update, context, txt, InlineKeyboardMarkup(btn), photo=poster)

    elif data.startswith('collection_'):
        c_id = data.split('_')[1]
        c = await fetch_tmdb(f"{TMDB_BASE_URL}/collection/{c_id}?api_key={TMDB_API_KEY}&language=ar")
        if c:
            txt = f"📚 <b>سلسلة: {c['name']}</b>\n\n"
            btn = []
            for part in c.get('parts', []):
                txt += f"• {part.get('title')} ({part.get('release_date', '')[:4]})\n"
                btn.append([InlineKeyboardButton(f"🎥 {part.get('title')}", callback_data=f"info_movie_{part['id']}")])
            btn.append([InlineKeyboardButton("🔙 رجوع", callback_data='back')])
            await send_or_edit(update, context, txt, InlineKeyboardMarkup(btn))

async def show_item_info(update, context, m_type, i_id):
    item = await get_item_details(m_type, i_id)
    if not item: return
    txt = format_item_text(item, m_type)
    poster = f"{TMDB_IMAGE_BASE_URL}{item.get('poster_path')}" if item.get('poster_path') else None
    
    btn = []
    # الإعلان
    trailer = next((v['key'] for v in item.get('videos', {}).get('results', []) if v['type'] == 'Trailer' and v['site'] == 'YouTube'), None)
    row1 = []
    if trailer: row1.append(InlineKeyboardButton("🎥 الإعلان", url=f"{YOUTUBE_BASE_URL}{trailer}"))
    if m_type == 'movie' and item.get('belongs_to_collection'):
        row1.append(InlineKeyboardButton("📚 السلسلة", callback_data=f"collection_{item['belongs_to_collection']['id']}"))
    if row1: btn.append(row1)
    
    btn.append([InlineKeyboardButton("👥 الممثلين", callback_data=f"credits_{m_type}_{i_id}"),
                InlineKeyboardButton("🎲 مشابه", callback_data=f"similar_{m_type}_{i_id}")])
    btn.append([InlineKeyboardButton("🏠 الرئيسية", callback_data='back')])
    await send_or_edit(update, context, txt, InlineKeyboardMarkup(btn), photo=poster)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = context.user_data.get('state')

    if state == 'broadcast' and user_id in ADMIN_IDS:
        context.user_data['state'] = None
        users = load_users()
        sent, fail = 0, 0
        status = await update.message.reply_text(f"⏳ جاري الإذاعة لـ {len(users)} مستخدم...")
        for uid in users:
            try:
                await update.message.copy(chat_id=uid)
                sent += 1
                if sent % 25 == 0: await asyncio.sleep(1)
            except: fail += 1
        await status.edit_text(f"✅ تم الانتهاء:\n🚀 نجح: {sent}\n❌ فشل: {fail}")
        return

    if state == 'waiting_search' or (update.message.text and not update.message.text.startswith('/')):
        query = update.message.text
        s_type = context.user_data.get('search_type', 'multi')
        
        if s_type == 'anime':
            url = f"{TMDB_BASE_URL}/search/multi?api_key={TMDB_API_KEY}&language=ar&query={query}"
            res = await fetch_tmdb(url)
            results = [i for i in res.get('results', []) if GENRE_ID_ANIMATION in i.get('genre_ids', [])] if res else []
        else:
            url = f"{TMDB_BASE_URL}/search/{s_type}?api_key={TMDB_API_KEY}&language=ar&query={query}"
            res = await fetch_tmdb(url)
            results = res.get('results', []) if res else []

        if results:
            txt = f"🔍 نتائج البحث عن: <b>{query}</b>\n"
            btn = []
            for item in results[:8]:
                name = item.get('title') or item.get('name')
                m_type = item.get('media_type', s_type if s_type != 'multi' else ('movie' if 'release_date' in item else 'tv'))
                if name: btn.append([InlineKeyboardButton(f"🎬 {name}", callback_data=f"info_{m_type}_{item['id']}")])
            btn.append([InlineKeyboardButton("🔙 رجوع", callback_data='back')])
            await update.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(btn), parse_mode='HTML')
        else:
            await update.message.reply_text("❌ لم يتم العثور على نتائج.")
        context.user_data['state'] = None

if __name__ == '__main__':
    if 'YOUR_' in TELEGRAM_TOKEN: print("⚠️ يرجى ضبط التوكنات!")
    else:
        app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CallbackQueryHandler(handle_interaction))
        app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
        print("🚀 البوت الشامل يعمل الآن...")
        app.run_polling()
