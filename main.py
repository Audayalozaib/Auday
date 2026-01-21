import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.constants import ParseMode, ChatAction

# إعداد التسجيل (Logging)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- الإعدادات ---
TOKEN = "6741306329:AAF9gyhoD_li410vEdu62s7WlhZVVpKJu58"
QURAN_API_BASE = "https://api.alquran.cloud/v1"
AZKAR_API_URL = "https://raw.githubusercontent.com/nawafalqari/azkar-api/master/azkar.json"

# --- دوال مساعدة ---

async def send_action(action: ChatAction):
    """ديكوراتور لإرسال حالة التحميل (جاري الكتابة/الرفع) قبل تنفيذ الأمر"""
    def decorator(func):
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if update.message:
                await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=action)
            elif update.callback_query:
                await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=action)
            return await func(update, context)
        return wrapper
    return decorator

# --- المعالجات (Handlers) ---

@send_action(ChatAction.TYPING)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📖 قراءة القرآن", callback_data='quran_list')],
        [InlineKeyboardButton("📚 تفسير القرآن (الميسر)", callback_data='tafsir_list')],
        [InlineKeyboardButton("🎧 استماع (مشاري العفاسي)", callback_data='audio_list')],
        [InlineKeyboardButton("🎲 آية عشوائية", callback_data='random_ayah')],
        [InlineKeyboardButton("🔍 بحث عن آية", callback_data='search_prompt')],
        [InlineKeyboardButton("📿 الأذكار", callback_data='azkar_categories')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = (
        "<b>مرحباً بك في بوت القرآن الكريم المتكامل ✨</b>\n\n"
        "يمكنك من خلال هذا البوت:\n"
        "- 📖 قراءة السور بوضوح\n"
        "- 📚 فهم المعنى عبر التفسير الميسر\n"
        "- 🎧 الاستماع للتلاوات\n"
        "- 🎲 قراءة آية عشوائية للتدبر\n"
        "- 🔍 البحث عن كلمات في القرآن\n"
        "- 📿 الأذكار اليومية\n\n"
        "<i>اختر من القائمة أدناه ما تريد:</i>"
    )
    
    if update.message:
        await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    else:
        await update.callback_query.edit_message_text(welcome_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

# --- قسم القراءة والتفسير ---

async def show_quran_list(update: Update, context: ContextTypes.DEFAULT_TYPE, page=0, mode='read'):
    """عرض قائمة السور (للقراءة أو التفسير)"""
    query = update.callback_query
    await query.answer()
    
    try:
        response = requests.get(f"{QURAN_API_BASE}/surah")
        if response.status_code != 200:
            raise Exception("فشل الاتصال بـ API القرآن")
            
        surahs = response.json()['data']
        per_page = 10
        start_idx = page * per_page
        end_idx = start_idx + per_page
        current_surahs = surahs[start_idx:end_idx]
        
        keyboard = []
        for surah in current_surahs:
            # تحديد بادمة الطلب بناءً على الوضع (قراءة أو تفسير)
            prefix = "surah_" if mode == 'read' else "tafsir_"
            keyboard.append([InlineKeyboardButton(f"{surah['number']}. {surah['name']} ({surah['englishName']})", callback_data=f"{prefix}{surah['number']}")])
        
        # أزرار التنقل
        nav_buttons = []
        # نحتاج لتمرير الوضع الحالي (mode) في أزرار التنقل
        page_prefix = "qpage_" if mode == 'read' else "tpage_"
        
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"{page_prefix}{page-1}"))
        if end_idx < len(surahs):
            nav_buttons.append(InlineKeyboardButton("التالي ➡️", callback_data=f"{page_prefix}{page+1}"))
        
        if nav_buttons:
            keyboard.append(nav_buttons)
        
        keyboard.append([InlineKeyboardButton("🏠 العودة للقائمة الرئيسية", callback_data='main_menu')])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        title = "اختر السورة للقراءة:" if mode == 'read' else "اختر السورة للتفسير:"
        await query.edit_message_text(title, reply_markup=reply_markup)
    except Exception as e:
        logging.error(e)
        await query.edit_message_text("❌ حدث خطأ أثناء جلب قائمة السور. حاول مرة أخرى لاحقاً.")

async def show_surah_content(update: Update, context: ContextTypes.DEFAULT_TYPE, surah_number, mode='read'):
    """عرض محتوى السورة (نص أو تفسير)"""
    query = update.callback_query
    await query.answer("جاري جلب السورة...")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    
    try:
        # تحديد النسخة: النص العادي (ar.alafasy يحتوي على النص) أو التفسير (ar.muyassar)
        edition = "ar.alafasy" if mode == 'read' else "ar.muyassar"
        response = requests.get(f"{QURAN_API_BASE}/surah/{surah_number}/{edition}")
        
        if response.status_code != 200:
            raise Exception("فشل جلب بيانات السورة")
            
        data = response.json()['data']
        title_type = "سورة" if mode == 'read' else "تفسير سورة"
        
        text = f"<b>{title_type} {data['name']}</b>\n\n"
        
        # إرسال على دفعات لتجنب حد الرسائل
        message_buffer = text
        for ayah in data['ayahs']:
            ayah_text = ayah['text']
            if mode == 'tafsir':
                # تنظيف النص قليلاً في حالة التفسير إذا احتوى على رموز غير ضرورية
                pass 
            
            # إضافة الآية للنص
            chunk = f"({ayah['numberInSurah']}) {ayah_text}\n\n"
            
            if len(message_buffer) + len(chunk) > 3500:
                await query.message.reply_text(message_buffer, parse_mode=ParseMode.HTML)
                message_buffer = ""
            message_buffer += chunk
        
        if message_buffer:
            keyboard = [[InlineKeyboardButton("🏠 العودة للقائمة", callback_data='quran_list' if mode == 'read' else 'tafsir_list')]]
            await query.message.reply_text(message_buffer, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
            
    except Exception as e:
        logging.error(e)
        await query.message.reply_text("❌ حدث خطأ أثناء تحميل السورة.")

# --- قسم الصوت ---

@send_action(ChatAction.UPLOAD_AUDIO)
async def show_audio_list(update: Update, context: ContextTypes.DEFAULT_TYPE, page=0):
    query = update.callback_query
    await query.answer()
    
    try:
        response = requests.get(f"{QURAN_API_BASE}/surah")
        if response.status_code != 200: raise Exception("API Error")
        
        surahs = response.json()['data']
        per_page = 10
        start_idx = page * per_page
        end_idx = start_idx + per_page
        current_surahs = surahs[start_idx:end_idx]
        
        keyboard = []
        for surah in current_surahs:
            keyboard.append([InlineKeyboardButton(f"🎧 {surah['name']}", callback_data=f"audio_{surah['number']}")])
        
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"apage_{page-1}"))
        if end_idx < len(surahs):
            nav_buttons.append(InlineKeyboardButton("التالي ➡️", callback_data=f"apage_{page+1}"))
        
        if nav_buttons:
            keyboard.append(nav_buttons)
        
        keyboard.append([InlineKeyboardButton("🏠 العودة للقائمة الرئيسية", callback_data='main_menu')])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("اختر السورة للاستماع إليها بصوت الشيخ مشاري العفاسي:", reply_markup=reply_markup)
    except Exception as e:
        await query.edit_message_text("حدث خطأ في تحميل قائمة الصوتيات.")

@send_action(ChatAction.UPLOAD_AUDIO)
async def send_audio(update: Update, context: ContextTypes.DEFAULT_TYPE, surah_number):
    query = update.callback_query
    await query.answer("جاري تجهيز التلاوة...")
    
    try:
        # رابط مباشر للسورة كاملة
        audio_url = f"https://cdn.islamic.network/quran/audio-surah/128/ar.alafasy/{surah_number}.mp3"
        
        # محاولة جلب اسم السورة للعنوان
        surah_name = f"سورة رقم {surah_number}"
        try:
            res = requests.get(f"{QURAN_API_BASE}/surah/{surah_number}").json()['data']
            surah_name = res['name']
        except:
            pass
            
        await query.message.reply_audio(
            audio=audio_url, 
            title=f"سورة {surah_name}", 
            caption="تلاوة بصوت الشيخ مشاري العفاسي 🎧",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        await query.message.reply_text("عذراً، تعذر تحميل الملف الصوتي حالياً.")

# --- آية عشوائية ---

@send_action(ChatAction.TYPING)
async def random_ayah(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        response = requests.get(f"{QURAN_API_BASE}/ayah/random/ar.alafasy")
        if response.status_code != 200: raise Exception("API Error")
        
        data = response.json()['data']
        text = (
            f"🎲 <b>آية عشوائية للتدبر</b>\n\n"
            f"「{data['text']}」\n\n"
            f"📖 سورة {data['surah']['name']} - آية {data['numberInSurah']}"
        )
        
        keyboard = [[InlineKeyboardButton("🔄 آية أخرى", callback_data='random_ayah')], [InlineKeyboardButton("🏠 الرئيسية", callback_data='main_menu')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if query.message.text:
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        else:
            # إذا كان الرد على رسالة أخرى (نادر في هذا السياق)
            await query.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
            
    except Exception as e:
        logging.error(e)
        await query.edit_message_text("حدث خطأ في جلب الآية.")

# --- قسم الأذكار ---

async def show_azkar_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("☀️ أذكار الصباح", callback_data='zkr_أذكار الصباح')],
        [InlineKeyboardButton("🌙 أذكار المساء", callback_data='zkr_أذكار المساء')],
        [InlineKeyboardButton("💤 أذكار النوم", callback_data='zkr_أذكار النوم')],
        [InlineKeyboardButton("🏠 العودة للقائمة الرئيسية", callback_data='main_menu')]
    ]
    await query.edit_message_text("اختر فئة الأذكار:", reply_markup=InlineKeyboardMarkup(keyboard))

@send_action(ChatAction.TYPING)
async def show_azkar_content(update: Update, context: ContextTypes.DEFAULT_TYPE, category):
    query = update.callback_query
    await query.answer()
    
    try:
        response = requests.get(AZKAR_API_URL)
        if response.status_code != 200: raise Exception("API Azkar Error")
        
        azkar_data = response.json()
        # المفتاح في ملف JSON قد يحتوي على مسافات، نبحث عنه
        category_azkar = azkar_data.get(category, [])
        
        if not category_azkar:
            await query.edit_message_text("عذراً، لم يتم العثور على أذكار لهذه الفئة.")
            return

        text = f"📿 <b>{category}</b>\n\n"
        # إرسال الأذكار في رسائل متعددة إذا كانت طويلة
        message_buffer = text
        count = 0
        
        for item in category_azkar:
            count += 1
            zkr_text = (
                f"<b>🔹 الذكر رقم {count}:</b>\n"
                f"{item['zekr']}\n"
                f"<i>التكرار: {item['count']}</i>\n\n"
            )
            
            if len(message_buffer) + len(zkr_text) > 3500:
                await query.message.reply_text(message_buffer, parse_mode=ParseMode.HTML)
                message_buffer = ""
            message_buffer += zkr_text
        
        keyboard = [[InlineKeyboardButton("🏠 العودة للأذكار", callback_data='azkar_categories')]]
        
        if message_buffer:
            await query.message.reply_text(message_buffer, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
            
    except Exception as e:
        logging.error(e)
        await query.message.reply_text("حدث خطأ أثناء تحميل الأذكار.")

# --- قسم البحث ---

async def search_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📝 من فضلك أرسل الكلمة التي تود البحث عنها في القرآن الكريم:")
    context.user_data['state'] = 'searching'

@send_action(ChatAction.TYPING)
async def handle_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('state') == 'searching':
        keyword = update.message.text
        try:
            response = requests.get(f"{QURAN_API_BASE}/search/{keyword}/all/ar.alafasy") # البحث في النص العربي
            
            if response.status_code != 200: raise Exception("Search Error")
            
            data = response.json()
            if not data.get('data'):
                # بعض الاستجابات قد تأتي مختلفة
                results = []
            else:
                results = data['data'].get('matches', [])

            if not results:
                await update.message.reply_text(f"❌ لم يتم العثور على نتائج للكلمة '<b>{keyword}</b>'.", parse_mode=ParseMode.HTML)
            else:
                text = f"🔍 <b>نتائج البحث عن '{keyword}':</b>\n\n"
                
                # عرض أول 10 نتائج فقط لتجنب التلصيق
                message_buffer = text
                for res in results[:10]: 
                    res_text = (
                        f"📖 {res['text']}\n"
                        f"<i>(سورة {res['surah']['name']} - آية {res['numberInSurah']})</i>\n\n"
                    )
                    
                    if len(message_buffer) + len(res_text) > 3500:
                        await update.message.reply_text(message_buffer, parse_mode=ParseMode.HTML)
                        message_buffer = ""
                    message_buffer += res_text
                
                if message_buffer:
                    await update.message.reply_text(message_buffer, parse_mode=ParseMode.HTML)
            
            # إعادة زر القائمة الرئيسية بعد البحث
            keyboard = [[InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data='main_menu')]]
            await update.message.reply_text("انتهى البحث.", reply_markup=InlineKeyboardMarkup(keyboard))
            
        except Exception as e:
            logging.error(e)
            await update.message.reply_text("حدث خطأ أثناء عملية البحث.")
        
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
        # فك تشفير اسم الفئة (تحويل %20 إلى مسافات إذا لزم الأمر، لكن هنا نستخدم النص مباشرة)
        category = data.replace('zkr_', '')
        await show_azkar_content(update, context, category)
        
    elif data == 'search_prompt':
        await search_prompt(update, context)
    elif data == 'random_ayah':
        await random_ayah(update, context)

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_search))
    
    print("البوت يعمل الآن مع التحسينات الجديدة...")
    app.run_polling()
