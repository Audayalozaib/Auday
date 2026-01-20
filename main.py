import logging
import requests
import random
import json
import os
from functools import lru_cache
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, InputMediaVideo
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from telegram.error import BadRequest

# --- الإعدادات ---
TELEGRAM_TOKEN = '6741306329:AAF9gyhoD_li410vEdu62s7WlhZVVpKJu58'
TMDB_API_KEY = '69075ed729d6771ee24e8ce5e2555d92'

# ضع قناة الاشتراك الإجباري (مع @)
CHANNEL_USERNAME = 'toiii' 

# ضع أرقام ID الأدمن
ADMIN_IDS = [778375826] 

TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
YOUTUBE_BASE_URL = "https://www.youtube.com/watch?v="
USERS_DB = "users.json"

# معرفات ثابتة
GENRE_ID_ANIMATION = 16
CACHE_SIZE = 100  # عدد الطلبات المحفوظة في الذاكرة

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

# --- وظائف TMDB (مع التخزين المؤقت لتحسين السرعة) ---

@lru_cache(maxsize=CACHE_SIZE)
def fetch_tmdb(url):
    try:
        return requests.get(url).json()
    except:
        return None

def get_genres(media_type='movie'):
    url = f"{TMDB_BASE_URL}/genre/{media_type}/list?api_key={TMDB_API_KEY}&language=ar"
    data = fetch_tmdb(url)
    return data.get('genres', []) if data else []

def get_trending(media_type='movie'):
    # يومي أو أسبوعي (day/week)
    url = f"{TMDB_BASE_URL}/trending/{media_type}/day?api_key={TMDB_API_KEY}&language=ar"
    data = fetch_tmdb(url)
    return data.get('results', []) if data else []

def get_random_item(media_type='movie', genre_id=None):
    page = random.randint(1, 30)
    url = f"{TMDB_BASE_URL}/discover/{media_type}?api_key={TMDB_API_KEY}&language=ar&sort_by=popularity.desc&page={page}"
    if genre_id: url += f"&with_genres={genre_id}"
    
    data = fetch_tmdb(url)
    results = data.get('results', []) if data else []
    if results: return random.choice(results)
    return None

def get_item_details(media_type, item_id):
    # جلب تفاصيل شاملة: الممثلين، الفيديوهات، المشابهات
    url = f"{TMDB_BASE_URL}/{media_type}/{item_id}?api_key={TMDB_API_KEY}&language=ar&append_to_response=credits,videos,similar"
    return fetch_tmdb(url)

def get_person_details(person_id):
    url = f"{TMDB_BASE_URL}/person/{person_id}?api_key={TMDB_API_KEY}&language=ar&append_to_response=movie_credits,tv_credits"
    return fetch_tmdb(url)

def get_collection_details(collection_id):
    url = f"{TMDB_BASE_URL}/collection/{collection_id}?api_key={TMDB_API_KEY}&language=ar"
    return fetch_tmdb(url)

def search_items(query, media_type='multi'): # multi يبحث في الأفلام والمسلسلات والشخصيات
    url = f"{TMDB_BASE_URL}/search/{media_type}?api_key={TMDB_API_KEY}&language=ar&query={query}&page=1"
    data = fetch_tmdb(url)
    return data.get('results', []) if data else []

def format_item_text(item, details=None, media_type='movie'):
    title = item.get('title') if media_type == 'movie' else item.get('name')
    overview = item.get('overview', 'لا يوجد وصف متاح.')
    rating = item.get('vote_average', 0)
    date = item.get('release_date') if media_type == 'movie' else item.get('first_air_date')
    year = date[:4] if date else '----'
    
    # حماية النص من علامات HTML
    safe_overview = overview.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    
    icon = "🎬" if media_type == 'movie' else "📺"
    text = f"{icon} <b>{title}</b>\n⭐️ التقييم: {rating}/10\n📅 السنة: {year}"
    
    if details:
        if media_type == 'movie':
            runtime = details.get('runtime')
            if runtime: text += f"\n⏱ المدة: {runtime} دقيقة"
            genres = details.get('genres', [])
            if genres:
                g_names = ", ".join([g['name'] for g in genres])
                text += f"\n🎭 التصنيف: {g_names}"
        else:
            seasons = details.get('number_of_seasons')
            if seasons: text += f"\n🎞 المواسم: {seasons}"
        
        # عرض 3 ممثلين فقط للإشارة، الأزرار ستكون بالأسفل
        cast = details.get('credits', {}).get('cast', [])[:3]
        if cast:
            actors = ", ".join([actor['name'] for actor in cast])
            text += f"\n🌟 بطولة: {actors}"

    text += f"\n\n📝 <b>القصة:</b>\n{safe_overview[:400]}..."
    return text

# --- دوال مساعدة للإرسال والتعديل ---

async def send_or_edit(update: Update, context: ContextTypes.DEFAULT_TYPE, text, reply_markup=None, photo_url=None, video_url=None):
    """دالة موحدة لإرسال رسالة جديدة أو تعديل الرسالة الحالية"""
    msg = None
    is_callback = bool(update.callback_query)

    try:
        if is_callback:
            msg = update.callback_query.message
            if photo_url:
                if msg.photo:
                    await msg.edit_media(InputMediaPhoto(media=photo_url, caption=text, parse_mode='HTML'), reply_markup=reply_markup)
                else:
                    # إذا كانت الرسالة نصية ونريد تحويلها لصورة، نحذف ونعيد إرسال
                    await msg.delete()
                    await context.bot.send_photo(chat_id=update.effective_chat.id, photo=photo_url, caption=text, reply_markup=reply_markup, parse_mode='HTML')
            elif video_url:
                 if msg.video: # دعم الفيديو نادر في بوستر الأفلام و لكن موجودة في التريلر
                    await msg.edit_media(InputMediaVideo(media=video_url, caption=text, parse_mode='HTML'), reply_markup=reply_markup)
                 else:
                     await msg.delete()
                     await context.bot.send_video(chat_id=update.effective_chat.id, video=video_url, caption=text, reply_markup=reply_markup, parse_mode='HTML')
            else:
                await msg.edit_text(text, reply_markup=reply_markup, parse_mode='HTML')
        else:
            if photo_url:
                await update.message.reply_photo(photo=photo_url, caption=text, reply_markup=reply_markup, parse_mode='HTML')
            else:
                await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')
    except BadRequest as e:
        if "Message is not modified" in str(e): pass
        elif "Message to edit not found" in str(e): pass
        else: logging.error(f"Error in send_or_edit: {e}")
    except Exception as e:
        logging.error(f"Critical Error: {e}")

# --- المعالجات ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    bot = context.bot
    
    save_user(user.id)
    
    if not await is_subscribed(user.id, bot):
        keyboard = [[InlineKeyboardButton("🔔 اشترك الآن", url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}")],
                     [InlineKeyboardButton("✅ تم الاشتراك", callback_data='check_sub')]]
        if update.message:
            await update.message.reply_text("⛔️ عذراً، يجب عليك الاشتراك في القناة لاستخدام البوت:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    welcome_text = f"👋 أهلاً بك {user.first_name}! 🍿\nماذا تريد أن تشاهد اليوم؟"
    keyboard = [
        [InlineKeyboardButton("🔥 ترند اليوم", callback_data='trending_menu')],
        [InlineKeyboardButton("🎲 فيلم عشوائي", callback_data='random_movie')],
        [InlineKeyboardButton("📺 مسلسل عشوائي", callback_data='random_tv')],
        [InlineKeyboardButton("🔍 بحث", callback_data='prompt_search')],
        [InlineKeyboardButton("🎭 التصنيفات", callback_data='main_categories')],
    ]
    
    if user.id in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton("⚙️ لوحة الأدمن", callback_data='admin_panel')])

    await send_or_edit(update, context, welcome_text, reply_markup=InlineKeyboardMarkup(keyboard))

async def check_sub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if await is_subscribed(query.from_user.id, context.bot):
        try:
            await query.delete_message()
        except: pass
        # محاكاة start
        fake_update = Update(update_id=0, message=query.message)
        fake_update.message.from_user = query.from_user
        await start(fake_update, context)
    else:
        await query.answer("❌ لم تقم بالاشتراك بعد!", show_alert=True)

# --- الأقسام الجديدة (ترند، ممثلين، مشابه) ---

async def trending_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🔥 أفلام رائجة", callback_data='trending_movie')],
        [InlineKeyboardButton("📺 مسلسلات رائجة", callback_data='trending_tv')],
        [InlineKeyboardButton("🔙 رجوع", callback_data='back_to_start')]
    ]
    try: await query.edit_message_text("📈 اختر قسم الترند:", reply_markup=InlineKeyboardMarkup(keyboard))
    except: pass

async def show_trending_list(update: Update, context: ContextTypes.DEFAULT_TYPE, media_type='movie'):
    query = update.callback_query
    await query.answer()
    
    results = get_trending(media_type)
    if not results:
        await query.edit_message_text("❌ حدث خطأ في جلب البيانات.")
        return

    # عرض أول 5 نتائج كقائمة
    text = f"🔥 <b>الأكثر رواجاً اليوم ({'أفلام' if media_type == 'movie' else 'مسلسلات'})</b>:\n\n"
    keyboard = []
    for i, item in enumerate(results[:10]): # زيادة العرض لـ 10
        title = item.get('title') or item.get('name')
        rating = item.get('vote_average', 0)
        text += f"{i+1}. {title} ({rating})\n"
        keyboard.append([InlineKeyboardButton(f"{i+1}. {title}", callback_data=f"info_{media_type}_{item['id']}")])
    
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data='trending_menu')])
    
    # التقسيم إذا كان النص طويلاً
    await send_or_edit(update, context, text[:1020], reply_markup=InlineKeyboardMarkup(keyboard))

async def show_credits(update: Update, context: ContextTypes.DEFAULT_TYPE, media_type, item_id):
    query = update.callback_query
    await query.answer()
    
    details = get_item_details(media_type, item_id)
    if not details: return
    
    cast = details.get('credits', {}).get('cast', [])
    if not cast:
        await query.answer("لا يوجد بيانات للممثلين", show_alert=True)
        return

    text = f"👥 <b>طاقم التمثيل:</b>\n\n"
    keyboard = []
    # عرض أهم 10 ممثلين
    for actor in cast[:10]:
        name = actor['name']
        char = actor.get('character', 'Unknown')
        text += f"• {name} ({char})\n"
        keyboard.append([InlineKeyboardButton(f"🎭 {name}", callback_data=f"person_{actor['id']}")])
    
    keyboard.append([InlineKeyboardButton("🔙 رجوع للفيلم", callback_data=f"info_{media_type}_{item_id}")])
    await send_or_edit(update, context, text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_person(update: Update, context: ContextTypes.DEFAULT_TYPE, person_id):
    query = update.callback_query
    await query.answer()
    
    data = get_person_details(person_id)
    if not data: return
    
    name = data.get('name')
    biography = data.get('biography', 'لا يوجد سيرة ذاتية.')
    birthday = data.get('birthday', 'N/A')
    place = data.get('place_of_birth', 'N/A')
    profile_pic = data.get('profile_path')
    
    text = f"🎭 <b>{name}</b>\n🎂 {birthday}\n📍 {place}\n\n📝 <b>السيرة:</b>\n{biography[:600]}..."
    
    keyboard = []
    # إضافة أشهر أعماله
    movies = data.get('movie_credits', {}).get('cast', [])[:5]
    if movies:
        keyboard.append([InlineKeyboardButton("🎬 مشاهدة أشهر أفلامه", callback_data=f"ignore")]) # Placeholder
        for m in movies:
            keyboard.append([InlineKeyboardButton(f"🎥 {m.get('title')}", callback_data=f"info_movie_{m['id']}")])
            
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data='back_to_start')])
    
    photo_url = f"{TMDB_IMAGE_BASE_URL}{profile_pic}" if profile_pic else None
    await send_or_edit(update, context, text, reply_markup=InlineKeyboardMarkup(keyboard), photo_url=photo_url)

async def show_similar(update: Update, context: ContextTypes.DEFAULT_TYPE, media_type, item_id):
    query = update.callback_query
    await query.answer()
    
    details = get_item_details(media_type, item_id)
    if not details: return
    
    similar = details.get('similar', {}).get('results', [])
    if not similar:
        await query.answer("لا توجد اعمال مشابهة حالياً", show_alert=True)
        return

    text = f"🎲 <b>أعمال قد تعجبك:</b>\n\n"
    keyboard = []
    for item in similar[:10]:
        title = item.get('title') or item.get('name')
        text += f"• {title}\n"
        keyboard.append([InlineKeyboardButton(f"👉 {title}", callback_data=f"info_{media_type}_{item['id']}")])
        
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data=f"info_{media_type}_{item_id}")])
    await send_or_edit(update, context, text, reply_markup=InlineKeyboardMarkup(keyboard))

# --- عرض العنصر (Item View) ---

async def show_item_info(update: Update, context: ContextTypes.DEFAULT_TYPE, media_type, item_id):
    query = update.callback_query
    if query: await query.answer()
    
    details = get_item_details(media_type, item_id)
    if not details:
         await send_or_edit(update, context, "❌ تعذر جلب التفاصيل.")
         return

    item = details # الديتيلز تحتوي على بيانات الفيلم نفسها
    caption = format_item_text(item, details, media_type)
    poster_path = item.get('poster_path')
    photo_url = f"{TMDB_IMAGE_BASE_URL}{poster_path}" if poster_path else None
    
    keyboard = []
    
    # الصف الأول (أزرار الفيديو والمعلومات)
    row1 = []
    trailer_key = None
    for v in item.get('videos', {}).get('results', []):
        if v['type'] == 'Trailer' and v['site'] == 'YouTube':
            trailer_key = v['key']; break
    if trailer_key: row1.append(InlineKeyboardButton("🎥 اعلان الفيلم", url=f"{YOUTUBE_BASE_URL}{trailer_key}"))
    
    if media_type == 'movie' and item.get('belongs_to_collection'):
         cid = item['belongs_to_collection']['id']
         row1.append(InlineKeyboardButton("📚 الأجزاء", callback_data=f"collection_{cid}"))
    keyboard.append(row1)

    # الصف الثاني (التفاعل)
    row2 = []
    row2.append(InlineKeyboardButton("👥 الممثلين", callback_data=f"credits_{media_type}_{item_id}"))
    row2.append(InlineKeyboardButton("🎲 مشابه", callback_data=f"similar_{media_type}_{item_id}"))
    keyboard.append(row2)
    
    # الصف الثالث (التحكم)
    row3 = []
    row3.append(InlineKeyboardButton("🔄 آخر", callback_data=f"random_{media_type}"))
    row3.append(InlineKeyboardButton("🏠 الرئيسية", callback_data='back_to_start'))
    keyboard.append(row3)
    
    await send_or_edit(update, context, caption, reply_markup=InlineKeyboardMarkup(keyboard), photo_url=photo_url)

# --- البحث والتصنيفات ---

async def prompt_search_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎬 فيلم", callback_data='set_search_movie')],
        [InlineKeyboardButton("📺 مسلسل", callback_data='set_search_tv')],
        [InlineKeyboardButton("🎨 أنمي", callback_data='set_search_anime')],
        [InlineKeyboardButton("👤 ممثل (شخصية)", callback_data='set_search_person')],
        [InlineKeyboardButton("🔙 إلغاء", callback_data='back_to_start')]
    ]
    try: await update.callback_query.edit_message_text("🔍 اختر نوع البحث:", reply_markup=InlineKeyboardMarkup(keyboard))
    except: pass

async def perform_search(update: Update, context: ContextTypes.DEFAULT_TYPE, query_str):
    s_type = context.user_data.get('search_media_type', 'movie')
    results = []
    
    if s_type == 'person':
        data = search_items(query_str, 'person')
        for p in data:
            results.append({'type': 'person', 'data': p})
    elif s_type == 'anime':
        results = search_items(query_str, 'movie') + search_items(query_str, 'tv')
        # فلترة الأنمي قد يحتاج مكتبة أفضل، هنا نعتمد على النتيجة العامة
    else:
        results = search_items(query_str, s_type)

    if not results:
        await send_or_edit(update, context, "🔍 لا توجد نتائج.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='back_to_start')]]))
        return
        
    context.user_data['search_results'] = results
    context.user_data['current_index'] = 0
    await show_search_result(update, context)

async def show_search_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    results = context.user_data.get('search_results', [])
    index = context.user_data.get('current_index', 0)
    if not results or index >= len(results): index = 0
    
    item = results[index]
    
    # التحقق هل هو شخص أم فيلم
    if isinstance(item, dict) and 'type' in item and item['type'] == 'person':
        p = item['data']
        name = p.get('name')
        known = p.get('known_for_department', 'Acting')
        text = f"👤 <b>{name}</b>\n🎭 المجال: {known}"
        photo_url = f"{TMDB_IMAGE_BASE_URL}{p.get('profile_path')}" if p.get('profile_path') else None
        keyboard = [
            [InlineKeyboardButton("📄 تفاصيل الشخصية", callback_data=f"person_{p['id']}")],
            [InlineKeyboardButton("◀️", callback_data='search_prev'), InlineKeyboardButton(f"{index+1}/{len(results)}", callback_data='ignore'), InlineKeyboardButton("▶️", callback_data='search_next')],
            [InlineKeyboardButton("🏠 الرئيسية", callback_data='back_to_start')]
        ]
        await send_or_edit(update, context, text, reply_markup=InlineKeyboardMarkup(keyboard), photo_url=photo_url)
        return

    # معالجة الأفلام والمسلسلات
    media_type = 'movie' if 'release_date' in item else 'tv'
    item_details = get_item_details(media_type, item['id'])
    caption = format_item_text(item, item_details, media_type)
    poster_path = item.get('poster_path')
    photo_url = f"{TMDB_IMAGE_BASE_URL}{poster_path}" if poster_path else None
    
    keyboard = []
    nav_row = []
    if index > 0: nav_row.append(InlineKeyboardButton("◀️", callback_data='search_prev'))
    nav_row.append(InlineKeyboardButton(f"{index+1}/{len(results)}", callback_data='ignore'))
    if index < len(results)-1: nav_row.append(InlineKeyboardButton("▶️", callback_data='search_next'))
    keyboard.append(nav_row)
    
    action_row = []
    # زر الفتح الكامل
    action_row.append(InlineKeyboardButton("📖 عرض كامل", callback_data=f"info_{media_type}_{item['id']}"))
    keyboard.append(action_row)
    keyboard.append([InlineKeyboardButton("🏠 الرئيسية", callback_data='back_to_start')])
    
    await send_or_edit(update, context, caption, reply_markup=InlineKeyboardMarkup(keyboard), photo_url=photo_url)

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return
    query = " ".join(context.args)
    context.user_data['search_media_type'] = 'multi' # بحث عام
    await perform_search(update, context, query)

# --- الأدمن ---

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id not in ADMIN_IDS: return

    text = "⚙️ <b>لوحة التحكم</b>"
    keyboard = [
        [InlineKeyboardButton("📊 عدد المشتركين", callback_data='admin_stats')],
        [InlineKeyboardButton("📢 إذاعة (رسالة)", callback_data='admin_ask_broadcast')],
        [InlineKeyboardButton("🔙 العودة", callback_data='back_to_start')]
    ]
    await send_or_edit(update, context, text, reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    users_count = len(load_users())
    msg = "📊 عدد المشتركين في البوت: {}".format(users_count)
    if update.callback_query:
        await update.callback_query.answer(msg, show_alert=True)
    else:
        await update.message.reply_text(msg)

async def admin_ask_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    try:
        await update.callback_query.edit_message_text("📢 أرسل النص/الصورة الآن لذيعها للمشتركين.")
    except: pass
    # تفعيل وضع الانتظار للرسالة القادمة
    context.user_data['waiting_for_broadcast'] = True

async def handle_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    if not context.user_data.get('waiting_for_broadcast'): return
    
    context.user_data['waiting_for_broadcast'] = False
    msg = update.message
    users = load_users()
    sent = 0
    failed = 0
    
    status_msg = await msg.reply_text(f"جاري الإرسال إلى {len(users)} مستخدم...")
    
    for user_id in users:
        try:
            if msg.photo:
                await context.bot.send_photo(chat_id=user_id, photo=msg.photo[-1].file_id, caption=msg.caption, parse_mode='HTML')
            elif msg.video:
                await context.bot.send_video(chat_id=user_id, video=msg.video.file_id, caption=msg.caption, parse_mode='HTML')
            elif msg.text:
                await context.bot.send_message(chat_id=user_id, text=msg.text, parse_mode='HTML')
            sent += 1
        except Exception:
            failed += 1
            
    await status_msg.edit_text(f"✅ انتهى الإرسال!\n✅ نجح: {sent}\n❌ فشل: {failed}")

# --- توزيع الأزرار (Button Router) ---

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    # التنقل الرئيسي
    if data == 'back_to_start':
        try: await query.delete_message()
        except: pass
        fake_update = Update(update_id=0, message=query.message)
        await start(fake_update, context)
        
    elif data == 'check_sub': await check_sub_callback(update, context)
    elif data == 'prompt_search': await prompt_search_type(query, context)
    elif data == 'trending_menu': await trending_menu(update, context)
    elif data == 'admin_panel': await admin_panel(update, context)
    elif data == 'admin_stats': await admin_stats(update, context)
    elif data == 'admin_ask_broadcast': await admin_ask_broadcast(update, context)
    elif data.startswith('trending_'): 
        await show_trending_list(update, context, data.split('_')[1])
    
    # البحث
    elif data in ['set_search_movie', 'set_search_tv', 'set_search_anime', 'set_search_person']:
        m_type = data.split('_')[2]
        context.user_data['search_media_type'] = m_type
        try: await query.edit_message_text(f"🔍 أرسل اسم {'الفيلم' if m_type=='movie' else 'المسلسل' if m_type=='tv' else 'الأنمي' if m_type=='anime' else 'الممثل'} 👇")
        except: pass
    elif data == 'search_next': 
        context.user_data['current_index'] += 1; await show_search_result(query, context)
    elif data == 'search_prev': 
        context.user_data['current_index'] -= 1; await show_search_result(query, context)

    # العشوائي
    elif data in ['random_movie', 'random_tv']:
        m_type = data.split('_')[1]
        item = get_random_item(m_type)
        if item: await show_item_info(query, context, m_type, item['id'])
    
    # التصنيفات
    elif data == 'main_categories':
        keyboard = [[InlineKeyboardButton("🎬 أفلام", callback_data='genres_menu_movie')],
                    [InlineKeyboardButton("📺 مسلسلات", callback_data='genres_menu_tv')],
                    [InlineKeyboardButton("🔙 رجوع", callback_data='back_to_start')]]
        await send_or_edit(update, context, "اختر القسم:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data.startswith('genres_menu_'):
        m_type = data.split('_')[2]; genres = get_genres(m_type)
        keyboard = []
        for i in range(0, len(genres), 2):
            row = [InlineKeyboardButton(genres[i]['name'], callback_data=f"genre_{m_type}_{genres[i]['id']}")]
            if i + 1 < len(genres): row.append(InlineKeyboardButton(genres[i+1]['name'], callback_data=f"genre_{m_type}_{genres[i+1]['id']}"))
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data='main_categories')])
        await send_or_edit(update, context, "🎭 اختر تصنيفاً:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data.startswith('genre_'):
        parts = data.split('_')
        item = get_random_item(parts[1], genre_id=parts[2])
        if item: await show_item_info(query, context, parts[1], item['id'])

    # المعلومات التفصيلية
    elif data.startswith('info_'):
        _, m_type, i_id = data.split('_')
        await show_item_info(update, context, m_type, i_id)
    elif data.startswith('credits_'):
        _, m_type, i_id = data.split('_')
        await show_credits(update, context, m_type, i_id)
    elif data.startswith('similar_'):
        _, m_type, i_id = data.split('_')
        await show_similar(update, context, m_type, i_id)
    elif data.startswith('person_'):
        person_id = data.split('_')[1]
        await show_person(update, context, person_id)
    elif data.startswith('collection_'):
        col_id = data.split('_')[1]
        col_data = get_collection_details(col_id)
        if col_data:
            name = col_data.get('name', 'سلسلة')
            parts = col_data.get('parts', [])
            text = f"📚 <b>سلسلة: {name}</b>\n\n"
            keyboard = []
            for part in parts[:10]: # عرض أول 10 أجزاء
                p_date = part.get('release_date', '')[:4] if part.get('release_date') else '----'
                text += f"{part.get('title')} ({p_date})\n"
                keyboard.append([InlineKeyboardButton(f"🎥 {part.get('title')}", callback_data=f"info_movie_{part['id']}")])
            keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data='back_to_start')])
            await send_or_edit(update, context, text, reply_markup=InlineKeyboardMarkup(keyboard))

if __name__ == '__main__':
    if 'YOUR_TELEGRAM_BOT_TOKEN' in TELEGRAM_TOKEN or 'YOUR_TMDB_API_KEY' in TMDB_API_KEY:
        print("Error: Please set your tokens first.")
    else:
        application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
        
        # الأوامر
        application.add_handler(CommandHandler('start', start))
        application.add_handler(CommandHandler('search', search_command))
        application.add_handler(CommandHandler('stats', admin_stats))
        
        # استقبال الرسائل (للأدمن)
        application.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.TEXT & filters.CAPTION, handle_broadcast_message))
        
        # الأزرار
        application.add_handler(CallbackQueryHandler(button_handler))
        
        print("Bot is running with advanced features...")
        application.run_polling()
