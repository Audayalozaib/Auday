import logging
import requests
import asyncio  # استيراد asyncio للتنفيذ غير المتزامن
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.constants import ParseMode, ChatAction

# إعداد التسجيل (Logging)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- الإعدادات ---
# تنبيه: ضع توكن البوت الخاص بك هنا
TOKEN = "6741306329:AAFYULFymDdqDblIhHUhMf2uiPSLl_i70Os"
QURAN_API_BASE = "https://api.alquran.cloud/v1"
AZKAR_API_URL = "https://raw.githubusercontent.com/nawafalqari/azkar-api/master/azkar.json"

# --- دوال مساعدة ---

async def http_get(url: str):
    """
    دالة لجلب البيانات بشكل غير متزامن (Non-blocking).
    نستخدمها بدلاً من requests.get المباشر لمنع البوت من التجمد أثناء الانتظار.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, requests.get, url)

def send_action(action: ChatAction):
    """ديكوراتور لإظهار حالة التحميل (كتابة، رفع ملف، إلخ)"""
    def decorator(func):
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            chat_id = update.effective_chat.id
            if update.message:
                await context.bot.send_chat_action(chat_id=chat_id, action=action)
            elif update.callback_query:
                await context.bot.send_chat_action(chat_id=chat_id, action=action)
            return await func(update, context)
        return wrapper
    return decorator

# --- المعالجات (Handlers) ---

@send_action(ChatAction.TYPING)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # تصميم القائمة بنظام الشبكة (Grid Layout)
    keyboard = [
        [
            InlineKeyboardButton("📖 القرآن الكريم", callback_data='quran_list'),
            InlineKeyboardButton("📚 التفسير الميسر", callback_data='tafsir_list')
        ],
        [
            InlineKeyboardButton("🎧 الصوتيات", callback_data='audio_list'),
            InlineKeyboardButton("📿 الأذكار اليومية", callback_data='azkar_categories')
        ],
        [
            InlineKeyboardButton("🔍 بحث في الآيات", callback_data='search_prompt'),
            InlineKeyboardButton("🎲 آية عشوائية", callback_data='random_ayah')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = (
        "﷽\n"
        "<b>أهلاً بك في المصحف الشامل ✨</b>\n\n"
        "بوت متكامل يوفر لك:\n"
        "▫️ تلاوة وقراءة القرآن الكريم\n"
        "▫️ التفسير الميسر للآيات\n"
        "▫️ استماع لأجمل التلاوات\n"
        "▫️ الأذكار اليومية والمباحث\n\n"
        "<i>تفضل باختيار ما تريد من القائمة أدناه 👇</i>"
    )
    
    if update.message:
        await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    elif update.callback_query:
        try:
            # محاولة تعديل الرسالة الحالية
            await update.callback_query.edit_message_text(welcome_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        except Exception:
            # إذا فشل التعديل (مثلاً الرسالة قديمة)، نرسل رسالة جديدة
            await update.callback_query.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

# --- قسم القراءة والتفسير ---

async def show_quran_list(update: Update, context: ContextTypes.DEFAULT_TYPE, page=0, mode='read'):
    """عرض قائمة السور مع نوعها (مكي/مدني)"""
    query = update.callback_query
    await query.answer()
    
    try:
        # استخدام الدالة غير المتزامنة http_get
        response = await http_get(f"{QURAN_API_BASE}/surah")
        if response.status_code != 200:
            raise Exception("فشل الاتصال بخدمة القرآن")
            
        surahs = response.json()['data']
        per_page = 15
        start_idx = page * per_page
        end_idx = start_idx + per_page
        current_surahs = surahs[start_idx:end_idx]
        
        keyboard = []
        for surah in current_surahs:
            rev_type = "مكية" if surah['revelationType'] == 'Meccan' else "مدنية"
            prefix = "surah_" if mode == 'read' else "tafsir_"
            btn_text = f"{surah['number']}. {surah['name']} [{rev_type}]"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"{prefix}{surah['number']}")])
        
        # أزرار التنقل
        nav_buttons = []
        page_prefix = "qpage_" if mode == 'read' else "tpage_"
        
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("◀️ السابق", callback_data=f"{page_prefix}{page-1}"))
        if end_idx < len(surahs):
            nav_buttons.append(InlineKeyboardButton("التالي ▶️", callback_data=f"{page_prefix}{page+1}"))
        
        if nav_buttons:
            keyboard.append(nav_buttons)
        
        keyboard.append([InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data='main_menu')])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        title = "📖 اختر السورة للقراءة:" if mode == 'read' else "📚 اختر السورة للتفسير:"
        await query.edit_message_text(title, reply_markup=reply_markup)
    except Exception as e:
        logging.error(e)
        await query.edit_message_text("❌ عذراً، حدث خطأ أثناء تحميل القائمة. يرجى المحاولة لاحقاً.")

async def show_surah_content(update: Update, context: ContextTypes.DEFAULT_TYPE, surah_number, mode='read'):
    """عرض محتوى السورة بشكل مرتب"""
    query = update.callback_query
    await query.answer()
    # إرسال حالة الكتابة لفترة طويلة لأن السورة قد تأخذ وقتاً
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    
    try:
        edition = "ar.alafasy" if mode == 'read' else "ar.muyassar"
        response = await http_get(f"{QURAN_API_BASE}/surah/{surah_number}/{edition}")
        
        if response.status_code != 200:
            raise Exception("فشل جلب البيانات")
            
        data = response.json()['data']
        header = f"▫️ {data['englishName']} ({data['englishNameTranslation']})\n"
        header += f"▫️ نوعها: {'مكية' if data['revelationType'] == 'Meccan' else 'مدنية'}\n"
        header += f"▫️ عدد الآيات: {data['numberOfAyahs']}\n"
        
        title_text = f"<b>سورة {data['name']}</b>\n\n{header}\n"
        
        message_buffer = title_text
        for ayah in data['ayahs']:
            # تحسين تنسيق الآيات
            ayah_text = f"۞ {ayah['text']}\n" if mode == 'read' else f"({ayah['numberInSurah']}) {ayah['text']}\n"
            
            # تقسيم الرسالة إذا كانت طويلة جداً
            if len(message_buffer) + len(ayah_text) > 3800:
                await query.message.reply_text(message_buffer, parse_mode=ParseMode.HTML)
                message_buffer = "" # تفريغ المخزن
            message_buffer += ayah_text
        
        # إرسال ما تبقى في المخزن
        if message_buffer:
            keyboard = [[InlineKeyboardButton("🔙 العودة للسور", callback_data='quran_list' if mode == 'read' else 'tafsir_list')]]
            await query.message.reply_text(message_buffer, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
            
    except Exception as e:
        logging.error(e)
        await query.message.reply_text("❌ عذراً، تعذر تحميل السورة في الوقت الحالي.")

# --- قسم الصوت ---

@send_action(ChatAction.UPLOAD_AUDIO) 
async def show_audio_list(update: Update, context: ContextTypes.DEFAULT_TYPE, page=0):
    query = update.callback_query
    await query.answer()
    
    try:
        response = await http_get(f"{QURAN_API_BASE}/surah")
        if response.status_code != 200: raise Exception("API Error")
        
        surahs = response.json()['data']
        per_page = 15
        start_idx = page * per_page
        end_idx = start_idx + per_page
        current_surahs = surahs[start_idx:end_idx]
        
        keyboard = []
        for surah in current_surahs:
            keyboard.append([InlineKeyboardButton(f"🎧 سورة {surah['name']}", callback_data=f"audio_{surah['number']}")])
        
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("◀️ السابق", callback_data=f"apage_{page-1}"))
        if end_idx < len(surahs):
            nav_buttons.append(InlineKeyboardButton("التالي ▶️", callback_data=f"apage_{page+1}"))
        
        if nav_buttons:
            keyboard.append(nav_buttons)
        
        keyboard.append([InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data='main_menu')])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("🎧 اختر السورة للاستماع بصوت الشيخ مشاري العفاسي:", reply_markup=reply_markup)
    except Exception as e:
        logging.error(e)
        await query.edit_message_text("❌ خطأ في تحميل القائمة الصوتية.")

@send_action(ChatAction.UPLOAD_AUDIO)
async def send_audio(update: Update, context: ContextTypes.DEFAULT_TYPE, surah_number):
    query = update.callback_query
    await query.answer("جاري إرسال التلاوة...")
    
    try:
        # استخدام رابط مباشر موثوق
        audio_url = f"https://cdn.islamic.network/quran/audio-surah/128/ar.alafasy/{surah_number}.mp3"
        surah_name = f"سورة رقم {surah_number}"
        
        # محاولة جلب اسم السورة عربي
        try:
            res = await http_get(f"{QURAN_API_BASE}/surah/{surah_number}")
            data = res.json()['data']
            surah_name = data['name']
        except:
            pass
            
        await query.message.reply_audio(
            audio=audio_url, 
            title=f"سورة {surah_name}", 
            caption="🎧 تلاوة خاشعة بصوت الشيخ مشاري العفاسي\nجزاه الله خيراً",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logging.error(e)
        await query.message.reply_text("❌ عذراً، لم نتمكن من تحميل الملف الصوتي.")

# --- آية عشوائية ---

@send_action(ChatAction.TYPING)
async def random_ayah(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        response = await http_get(f"{QURAN_API_BASE}/ayah/random/ar.alafasy")
        if response.status_code != 200: raise Exception("API Error")
        
        data = response.json()['data']
        text = (
            "🌟 <b>آية للتدبر</b> 🌟\n\n"
            f"<i>{data['text']}</i>\n\n"
            f"📖 <b>سورة {data['surah']['name']}</b> - الآية {data['numberInSurah']}"
        )
        
        keyboard = [
            [InlineKeyboardButton("🔄 آية أخرى", callback_data='random_ayah')],
            [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data='main_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # محاولة التعديل، وإذا فشلت نرسل رسالة جديدة
        try:
            if query.message.text:
                await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
            else:
                await query.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        except Exception:
            await query.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
            
    except Exception as e:
        logging.error(e)
        try:
            await query.edit_message_text("❌ حدث خطأ في جلب الآية.")
        except:
            await query.message.reply_text("❌ حدث خطأ في جلب الآية.")

# --- قسم الأذكار ---

async def show_azkar_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [
            InlineKeyboardButton("☀️ أذكار الصباح", callback_data='zkr_أذكار الصباح'),
            InlineKeyboardButton("🌙 أذكار المساء", callback_data='zkr_أذكار المساء')
        ],
        [
            InlineKeyboardButton("💤 أذكار النوم", callback_data='zkr_أذكار النوم'),
            InlineKeyboardButton("🔙 العودة", callback_data='main_menu')
        ]
    ]
    await query.edit_message_text("📿 اختر فئة الأذكار:", reply_markup=InlineKeyboardMarkup(keyboard))

@send_action(ChatAction.TYPING)
async def show_azkar_content(update: Update, context: ContextTypes.DEFAULT_TYPE, category):
    query = update.callback_query
    await query.answer()
    
    try:
        response = await http_get(AZKAR_API_URL)
        if response.status_code != 200: raise Exception("API Azkar Error")
        
        azkar_data = response.json()
        
        # --- التصحيح الجوهري هنا ---
        # الـ API يعيد قائمة من الكائنات، كل كائن يحتوي على 'category' و 'array'
        # لذا يجب البحث داخل القائمة عن الفئة المطلوبة
        target_list = []
        for item in azkar_data:
            if item.get('category') == category:
                target_list = item.get('array', [])
                break
        
        if not target_list:
            await query.edit_message_text("❌ لم يتم العثور على أذكار لهذه الفئة.")
            return

        text = f"📿 <b>{category}</b>\n\n"
        message_buffer = text
        
        for idx, item in enumerate(target_list, 1):
            zkr_text = (
                f"━━━━━━━━━━━━━━━\n"
                f"<b>❝ الذكر رقم {idx} ❞</b>\n"
                f"{item['zekr']}\n"
                f"🔄 <b>التكرار:</b> {item['count']}\n"
            )
            
            if len(message_buffer) + len(zkr_text) > 3500:
                await query.message.reply_text(message_buffer, parse_mode=ParseMode.HTML)
                message_buffer = ""
            message_buffer += zkr_text
        
        keyboard = [[InlineKeyboardButton("🔙 العودة للأذكار", callback_data='azkar_categories')]]
        
        if message_buffer:
            await query.message.reply_text(message_buffer, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
            
    except Exception as e:
        logging.error(e)
        await query.message.reply_text("❌ حدث خطأ في تحميل الأذكار.")

# --- قسم البحث ---

async def search_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton("🔙 إلغاء والعودة", callback_data='main_menu')]]
    await query.edit_message_text("📝 <b>أرسل الكلمة أو النص الذي تريد البحث عنه:</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    context.user_data['state'] = 'searching'

@send_action(ChatAction.TYPING)
async def handle_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('state') == 'searching':
        keyword = update.message.text
        try:
            response = await http_get(f"{QURAN_API_BASE}/search/{keyword}/all/ar.alafasy")
            
            if response.status_code != 200: raise Exception("Search Error")
            
            data = response.json()
            results = []
            # التحقق من وجود البيانات في الاستجابة
            if data.get('data') and isinstance(data['data'], dict):
                results = data['data'].get('matches', [])

            if not results:
                await update.message.reply_text(f"❌ <b>عذراً</b>، لم يتم العثور على نتائج للبحث عن '<i>{keyword}</i>'.", parse_mode=ParseMode.HTML)
            else:
                await update.message.reply_text(f"✅ <b>تم العثور على {len(results)} نتيجة</b> لـ '<i>{keyword}</i>':\n", parse_mode=ParseMode.HTML)
                
                message_buffer = ""
                # عرض أول 10 نتائج فقط
                for res in results[:10]: 
                    res_text = (
                        f"📖 {res['text']}\n"
                        f"<i>[سورة {res['surah']['name']} - آية {res['numberInSurah']}]</i>\n\n"
                    )
                    
                    if len(message_buffer) + len(res_text) > 3500:
                        await update.message.reply_text(message_buffer, parse_mode=ParseMode.HTML)
                        message_buffer = ""
                    message_buffer += res_text
                
                if message_buffer:
                    await update.message.reply_text(message_buffer, parse_mode=ParseMode.HTML)
            
            keyboard = [[InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data='main_menu')]]
            await update.message.reply_text("انتهى البحث 👇", reply_markup=InlineKeyboardMarkup(keyboard))
            
        except Exception as e:
            logging.error(e)
            await update.message.reply_text("❌ حدث خطأ أثناء عملية البحث.")
        
        context.user_data['state'] = None

# --- معالج الأزرار الرئيسي ---

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    if data == 'main_menu':
        await start(update, context)
    
    elif data == 'quran_list':
        await show_quran_list(update, context, 0, 'read')
    elif data == 'tafsir_list':
        await show_quran_list(update, context, 0, 'tafsir')
        
    elif data.startswith('qpage_'):
        page = int(data.split('_')[1])
        await show_quran_list(update, context, page, 'read')
    elif data.startswith('tpage_'):
        page = int(data.split('_')[1])
        await show_quran_list(update, context, page, 'tafsir')
        
    elif data.startswith('surah_'):
        surah_num = data.split('_')[1]
        await show_surah_content(update, context, surah_num, 'read')
    elif data.startswith('tafsir_'):
        surah_num = data.split('_')[1]
        await show_surah_content(update, context, surah_num, 'tafsir')
        
    elif data == 'audio_list':
        await show_audio_list(update, context, 0)
    elif data.startswith('apage_'):
        page = int(data.split('_')[1])
        await show_audio_list(update, context, page)
    elif data.startswith('audio_'):
        surah_num = int(data.split('_')[1])
        await send_audio(update, context, surah_num)
        
    elif data == 'azkar_categories':
        await show_azkar_categories(update, context)
    elif data.startswith('zkr_'):
        category = data.replace('zkr_', '')
        await show_azkar_content(update, context, category)
        
    elif data == 'search_prompt':
        await search_prompt(update, context)
    elif data == 'random_ayah':
        await random_ayah(update, context)

if __name__ == '__main__':
    # تأكد من وضع التوكن الصحيح في الأعلى
    if TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ الرجاء وضع التوكن الخاص بك في الكود.")
    else:
        app = ApplicationBuilder().token(TOKEN).build()
        
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CallbackQueryHandler(button_handler))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search))
        
        print("✅ البوت يعمل الآن...")
        app.run_polling()
