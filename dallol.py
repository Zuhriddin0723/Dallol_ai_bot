import asyncio
import logging
import sqlite3
import httpx
import re
import os
from anthropic import AsyncAnthropic
from aiogram import Bot, Dispatcher, types, F
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove, InputMediaPhoto, BufferedInputFile
from aiogram.exceptions import TelegramForbiddenError

from dotenv import load_dotenv

# .env faylini yuklash
load_dotenv()

# --- SOZLAMALAR ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CLAUDE_KEY = os.getenv("CLAUDE_KEY", "").strip()
MONITOR_BOT_TOKEN = os.getenv("MONITOR_BOT_TOKEN")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")
ADMIN_IDS_STR = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(aid) for aid in ADMIN_IDS_STR.split(",") if aid.strip()]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PHOTOS_DIR = os.path.join(BASE_DIR, "photos")
DB_PATH = os.path.join(BASE_DIR, "products.db")
os.makedirs(PHOTOS_DIR, exist_ok=True)

def get_last_3_products():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, max_price FROM products ORDER BY id DESC LIMIT 3")
    rows = cursor.fetchall()
    conn.close()
    return rows

async def send_product_to_dm(user_id, p_name):
    # Mahsulot haqida ma'lumot olish
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name, max_price, sizes, colors, material FROM products WHERE name = ?", (p_name,))
    p = cursor.fetchone()
    conn.close()
    
    if not p: return False
    
    text = f"📦 {p[0]}\n💰 Narxi: {p[1]} so'm\n📐 O'lcham: {p[2]}\n🎨 Rang: {p[3]}\n🧵 Material: {p[4]}\n\nSavdolashish uchun narxni yozing!"
    
    photos = get_product_photos(p_name)
    try:
        if photos:
            if len(photos) > 1:
                media = []
                for i, p_tuple in enumerate(photos):
                    file_input = get_photo_input(p_tuple[0], p_tuple[1])
                    media.append(InputMediaPhoto(media=file_input, caption=text if i == 0 else ""))
                await bot.send_media_group(user_id, media)
            else:
                file_input = get_photo_input(photos[0][0], photos[0][1])
                await bot.send_photo(user_id, file_input, caption=text)
        else:
            await bot.send_message(user_id, text)
        return True
    except Exception as e:
        logging.error(f"Error sending photo to DM: {e}")
        return False

session = AiohttpSession(timeout=60.0)
client = AsyncAnthropic(api_key=CLAUDE_KEY, timeout=60.0)
bot = Bot(token=TELEGRAM_TOKEN, session=session)
monitor_bot = Bot(token=MONITOR_BOT_TOKEN, session=session)
dp = Dispatcher()
monitor_dp = Dispatcher()

class OrderState(StatesGroup):
    waiting_for_name = State()
    waiting_for_phone = State()
    waiting_for_address = State()
    waiting_for_confirmation = State()

# --- BAZA BILAN ISHLASH --- 
def get_all_products():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name, min_price, max_price, sizes, colors, photo_id, material FROM products WHERE stock > 0")
    products = cursor.fetchall()
    conn.close()
    return products

def get_product_by_photo(photo_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name, max_price FROM products WHERE photo_id = ?", (photo_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def get_product_photos(name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT photo_id, file_path, file_unique_id FROM product_photos 
        WHERE product_id = (SELECT id FROM products WHERE name = ?)
    """, (name,))
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    for photo_id, file_path, file_unique_id in rows:
        # Agar bazada file_path bo'lmasa yoki noto'g'ri bo'lsa, qidirib ko'ramiz
        if not file_path or not os.path.exists(file_path):
            # 1. file_unique_id bo'yicha (admin_bot shunday saqlaydi)
            if file_unique_id:
                p = os.path.join(PHOTOS_DIR, f"{file_unique_id}.jpg")
                if os.path.exists(p): file_path = p
            
            # 2. Mahsulot nomi bo'yicha (lowercase)
            if not file_path:
                p = os.path.join(PHOTOS_DIR, f"{name.lower()}.jpg")
                if os.path.exists(p): file_path = p
            
            # 3. Mahsulot nomi bo'yicha (aslida)
            if not file_path:
                p = os.path.join(PHOTOS_DIR, f"{name}.jpg")
                if os.path.exists(p): file_path = p
        
        results.append((photo_id, file_path))
    return results

def get_photo_input(pid, ppath):
    if ppath and os.path.exists(ppath):
        return FSInputFile(ppath)
    # Dallol bot admin_bot ning file_id sini ishlata olmaydi, shuning uchun None qaytaramiz
    return None

# --- AI PROMPT (QOIDALAR) ---
def get_system_prompt():
    products = get_all_products()
    products_text = "\n".join([f"- Nomi: {p[0]} | Boshlang'ich narxi: {p[2]} so'm | Maxfiy minimum: {p[1]} so'm | O'lchamlari: {p[3]} | Ranglari: {p[4]} | Materiali: {p[6]} | Rasm yuborish: [SEND_PHOTO: {p[0]}]" for p in products]) if products else "Hozircha mahsulot yo'q."
    return f"""SEN "Anojram" do'konining "Dallol AI" botisan. Haqiqiy O'zbek dalloli kabi chaqqon, xushmuomala va ishonchli bo'l.
Sizga hozirda Vision (ko'rish) imkoniyati berilgan, ya'ni foydalanuvchi yuborgan yoki biz senga yuborgan mahsulot rasmlarini ko'ra olasan. 
HECH QACHON "men rasm ko'ra olmayman" dema!

<products>
{products_text}
</products>

<rules>
1. MIJOZ SO'RAMAGUNCHA MAHSULOTLARNI O'ZINGDAN TAKLIF QILMA.
2. Agar mijoz shunchaki salom bersa yoki xol-ahvol so'rasa, xushmuomala bilan alik ol va "Sizga qanday yordam bera olaman?" deb so'ra.
3. Foydalanuvchi birinchi yozganida salom ber. Ikkinchi xabardan boshlab salomlashish QAT'IYAN TAQIQLANADI.
4. NARX SIYOSATI:
   - Hech qachon foydalanuvchiga narx oralig'ini (minimumdan maximumgacha) aytma.
   - FAQAT boshlang'ich Sotuv narxini (max_price) ayt.
   - Agar mijoz "qimmat" desa yoki narx tushirishni so'rasa, xushmuomalalik bilan ozgina (10-20 ming so'm) tushib ber.
   - Hech qachon Maxfiy minimumdan (min_price) pastga tushma!
5. Agar mijoz taklifingga rozi bo'lsa, xabar oxiriga kelishilgan aniq narxni va [DEAL_REACHED] belgisini qo'sh.
6. SAVOL BERISH QOIDASI: Har doim mijozga faqat va faqat bitta savol ber. Hech qachon birdaniga 2 ta yoki undan ko'p savol berma. Savollarni ketma-ket, bitta-bitta ber! Mijozni savollarga ko'mib tashlama.
7. Kelishuv bo'lsa xabar oxiriga albatta kelishilgan narxni va [DEAL_REACHED] belgisini qo'sh (Masalan: "Kelishdik, 150000 so'm. [DEAL_REACHED]").
8. RASM YUBORISH QOIDASI: 
   - Agar foydalanuvchi aniq bir mahsulot haqida so'rasa, DOIM o'sha mahsulotning rasmini yuborish uchun [SEND_PHOTO: MahsulotNomi] belgisidan foydalan. Boshqa mahsulotlarni aralashtirma, faqat so'ralgan mahsulot rasmini ko'rsat.
   - Agar senda juda zarur bo'lgan TASHQI rasm linki bo'lsa (va u bizning bazamizda bo'lmasa), [PHOTO_LINK: URL] formatidan foydalan. 
   - Hech qachon Markdown formatini (![alt](link)) ishlatma.
9. QISQA VA LONDA JAVOB:
   - MAHSULOTLAR ro'yxatida yozilgan ranglar va o'lchamlarni aniq tekshirib, shunga qarab javob yoz. O'zingdan yo'q ranglarni yoki razmerlarni umuman to'qib chiqarma!
   - Mahsulot narxini yoki rasmini so'rashganda, lirik chekinishlar qilma ("Xushmuolamiz", "Juda yaxshi", "Ko'rsataman", "Sizga bu narx mos keladimi" kabi ortiqcha gaplarni UMUMAN ishlatma).
   - Faqat rasmini yubor ([SEND_PHOTO: Nomi]) va "Narxi: ... so'm" deb aniq yoz. Va kerak bo'lsa "Sizga qanday razmerdagisi yoki qanday rangi kerak?" deb qisqacha so'ra.
10. SUHBAT DAVOMIYLIGI (KONTEKST):
   - Mijoz oldingi savolingga (masalan o'lcham yoki rang haqidagi) javob berganda, hech qachon suhbatni boshidan boshlama! "Sizga qanday yordam bera olaman?" kabi gaplarni qayta ishlatma.
   - Uning javobini (masalan "qizil") qabul qil va savdolashishni o'sha joyidan davom ettir.
</rules>
"""

# Claude uchun xabarlar tarixi (har user uchun alohida ro'yxat)
chat_histories = {}

def get_chat_history(user_id):
    if user_id not in chat_histories:
        chat_histories[user_id] = []
    return chat_histories[user_id]

import base64

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

async def send_claude_message(user_id, text, image_path=None):
    history = get_chat_history(user_id)
    
    content = [{"type": "text", "text": text}]
    if image_path and os.path.exists(image_path):
        base64_image = encode_image(image_path)
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": base64_image,
            },
        })
    
    history.append({"role": "user", "content": content})

    # Retry logic for network errors
    for attempt in range(3):
        try:
            response = await client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=1024,
                system=get_system_prompt(),
                messages=history
            )
            assistant_text = response.content[0].text
            history.append({"role": "assistant", "content": assistant_text})
            return assistant_text
        except Exception as e:
            # Agar model topilmasa (404), Haiku ga o'tamiz
            if "not_found_error" in str(e).lower() and CLAUDE_MODEL != "claude-haiku-4-5-20251001":
                logging.warning(f"Model {CLAUDE_MODEL} topilmadi, Haiku'ga o'tilmoqda...")
                try:
                    response = await client.messages.create(
                        model="claude-haiku-4-5-20251001",
                        max_tokens=1024,
                        system=get_system_prompt(),
                        messages=history
                    )
                    assistant_text = response.content[0].text
                    history.append({"role": "assistant", "content": assistant_text})
                    return assistant_text
                except Exception as e2:
                    logging.error(f"Fallback model ham xato berdi: {e2}")
            
            if attempt == 2: raise e
            logging.warning(f"AI attempt {attempt+1} failed: {e}. Retrying...")
            await asyncio.sleep(2)

def save_message_to_db(user_id, role, content):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO messages (user_id, role, content) VALUES (?,?,?)", (user_id, role, content))
    conn.commit()
    conn.close()

async def log_interaction(user_id, user_msg, bot_msg=None):
    if user_msg:
        save_message_to_db(user_id, "user", user_msg)
    if bot_msg:
        save_message_to_db(user_id, "assistant", bot_msg)
    
    # Real-time monitoring o'chirildi. Faqat bazaga saqlanadi.

def register_user(user_id, username, full_name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO users (user_id, username, full_name) VALUES (?,?,?)", (user_id, username, full_name))
    conn.commit()
    conn.close()

# --- HANDLERS ---

@dp.message(Command("start"), F.chat.type == "private")
async def start_handler(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    register_user(user_id, message.from_user.username, message.from_user.full_name)
    # Har safar start bosilganda yangi qoidalar ishlashi uchun suhbatni yangilaymiz
    chat_histories.pop(user_id, None)

    welcome_msg = "Assalomu alaykum! Anojram do'konimizga xush kelibsiz. Bizda ajoyib mahsulotlar bor. Sizga qanday yordam bera olaman?"
    await message.answer(welcome_msg)
    await log_interaction(user_id, "/start", welcome_msg)

async def process_ai_message(user_id, chat_id, text, state, show_typing=True):
    if show_typing:
        try:
            await bot.send_chat_action(chat_id, "typing")
        except: pass

    try:
        # User xabarini monitoring botga yuborish
        await log_interaction(user_id, text)

        res_text = await send_claude_message(user_id, text)

        # Bot javobini monitoring botga yuborish
        await log_interaction(user_id, None, res_text)

        # Rasm yuborish mantiqi (Local DB)
        photo_match = re.search(r"\[SEND_PHOTO:\s*(.+?)\]", res_text)
        if photo_match:
            p_name = photo_match.group(1).strip()
            await state.update_data(last_product=p_name)
            photos = get_product_photos(p_name)
            if photos:
                if len(photos) > 1:
                    media = []
                    for p_tuple in photos:
                        file_input = get_photo_input(p_tuple[0], p_tuple[1])
                        if file_input:
                            media.append(InputMediaPhoto(media=file_input))
                    if media:
                        try:
                            await bot.send_media_group(chat_id, media)
                        except Exception as e:
                            logging.error(f"Error sending local media group: {e}")
                else:
                    file_input = get_photo_input(photos[0][0], photos[0][1])
                    if file_input:
                        try:
                            await bot.send_photo(chat_id, file_input)
                        except Exception as e:
                            logging.error(f"Error sending local photo: {e}")

        res_text = re.sub(r"\[SEND_PHOTO:.*?\]", "", res_text).strip()

        # Rasm yuborish mantiqi (URL Link)
        link_match = re.search(r"\[PHOTO_LINK:\s*(https?://[^\s\]]+)\]", res_text)
        if link_match:
            photo_url = link_match.group(1).strip().rstrip(')]')
            res_text = re.sub(r"\[PHOTO_LINK:.*?\]", "", res_text).strip()
            
            caption_text = res_text if res_text else "Mana siz so'ragan rasm!"
            try:
                # 1. To'g'ridan-to'g'ri URL orqali urinib ko'ramiz
                await bot.send_photo(chat_id, photo=photo_url, caption=caption_text)
                if "[DEAL_REACHED]" not in res_text:
                    return
            except Exception as e:
                logging.warning(f"Direct URL photo sending failed, trying to download: {e}")
                try:
                    # 2. Yuklab olib yuborishga urinib ko'ramiz
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(photo_url, timeout=15.0)
                        if resp.status_code == 200:
                            photo_data = resp.content
                            file_input = BufferedInputFile(photo_data, filename="photo.jpg")
                            await bot.send_photo(chat_id, photo=file_input, caption=caption_text)
                            if "[DEAL_REACHED]" not in res_text:
                                return
                        else:
                            raise Exception(f"HTTP Status {resp.status_code}")
                except Exception as e2:
                    logging.error(f"Error downloading photo from URL: {e2}")
                    # Oxirgi chora: xato xabarini yuboramiz
                    await bot.send_message(chat_id, f"{caption_text}\n\n(Kechirasiz, rasm yuklanmadi, lekin mahsulot haqida ma'lumot yuqorida)")

        # Kelishuv bo'lganda
        if "[DEAL_REACHED]" in res_text:
            prices = re.findall(r"(\d[\d\s\.]*)\s*(?:so'm|som|sum)", res_text.lower())
            if prices:
                price_str = prices[-1].replace(" ", "").replace(".", "")
                try:
                    await state.update_data(last_price=int(price_str))
                except: pass

            await bot.send_message(chat_id, res_text.replace("[DEAL_REACHED]", "").strip())
            await bot.send_message(chat_id, "Kelishdik! Ismingizni yozing:")
            await state.set_state(OrderState.waiting_for_name)
        else:
            await bot.send_message(chat_id, res_text)

    except Exception as e:
        logging.error(f"AI error: {e}")
        await bot.send_message(chat_id, "Kechirasiz, birozdan keyin urinib ko'ring.")

@dp.message(F.chat.type.in_({"group", "supergroup"}))
async def group_handler(message: types.Message, state: FSMContext):
    raw_text = (message.text or message.caption or "").lower()
    trigger_words = ["narx", "qancha", "necha pul", "som", "so'm", "nechi", "pul", "narxi"]
    is_reply_to_photo = message.reply_to_message and message.reply_to_message.photo
    has_trigger_word = any(word in raw_text for word in trigger_words)
    
    if has_trigger_word:
        user_id = message.from_user.id
        p_name = None
        last_3 = None
        if is_reply_to_photo:
            replied_unique_id = message.reply_to_message.photo[-1].file_unique_id
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM products WHERE id = (SELECT product_id FROM product_photos WHERE file_unique_id = ?)", (replied_unique_id,))
            row = cursor.fetchone()
            conn.close()
            if row: p_name = row[0]
        else:
            last_3 = get_last_3_products()

        user_question = message.text or message.caption or "Narx so'rovi"
        try:
            if is_reply_to_photo and p_name:
                photos = get_product_photos(p_name)
                best_photo_path = photos[0][1] if photos and photos[0][1] else None
                
                ai_instruction = f"Mijoz guruhda rasmga reply qilib '{user_question}' deb so'radi. Mahsulot: {p_name}. SEN salomlashib, mahsulot haqida ma'lumot ber va savdolashishni boshla."
                res_text = await send_claude_message(user_id, ai_instruction, image_path=best_photo_path)
                
                await bot.send_message(user_id, res_text)
                if photos:
                    media = []
                    for p_tuple in photos:
                        file_input = get_photo_input(p_tuple[0], p_tuple[1])
                        if file_input:
                            media.append(InputMediaPhoto(media=file_input))
                    if media:
                        await bot.send_media_group(user_id, media)
            elif not is_reply_to_photo and last_3:
                p_list_text = "\n".join([f"{i+1}. {p[1]} - {p[2]} so'm" for i, p in enumerate(last_3)])
                ai_instruction = f"Mijoz guruhda umumiy narx so'radi. Men unga ohirgi 3 ta mahsulotni yubordim:\n{p_list_text}\n\nSEN xushmuomala bilan salomlashib 'Siz tanlagan mahsulotimiz shular orasida bormi?' deb so'ra."
                res_text = await send_claude_message(user_id, ai_instruction)
                await bot.send_message(user_id, res_text)
                
                for i, p in enumerate(last_3):
                    p_photos = get_product_photos(p[1])
                    if p_photos:
                        file_input = get_photo_input(p_photos[0][0], p_photos[0][1])
                        if file_input:
                            await bot.send_photo(user_id, file_input, caption=f"{i+1}. {p[1]}")
            else:
                dm_state = dp.fsm.resolve_context(bot, user_id, user_id)
                await process_ai_message(user_id, user_id, user_question, dm_state, show_typing=False)
        except TelegramForbiddenError:
            bot_info = await bot.get_me()
            markup = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Botga kirish", url=f"https://t.me/{bot_info.username}")]
            ])
            await message.reply("Bizdan foydalanish uchun avval botga start tugmasini bosing.", reply_markup=markup)
        except Exception as e:
            logging.error(f"Group interaction error: {e}")
        else:
            await message.reply("Sizga shaxsiy xabarda javob yubordik.")

@dp.message(OrderState.waiting_for_name)
async def get_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Telefoningiz:")
    await state.set_state(OrderState.waiting_for_phone)

@dp.message(OrderState.waiting_for_phone)
async def get_phone(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text)
    await message.answer("Manzil:")
    await state.set_state(OrderState.waiting_for_address)

@dp.message(OrderState.waiting_for_address)
async def get_address(message: types.Message, state: FSMContext):
    await state.update_data(address=message.text)
    d = await state.get_data()
    
    last_p = d.get('last_product', "Noma'lum")
    summary = (
        f"📝 Buyurtma ma'lumotlarini tekshiring:\n\n"
        f"📦 Mahsulot: {last_p}\n"
        f"💰 Kelishilgan narx: {d.get('last_price', 0)} so'm\n"
        f"👤 Ism: {d['name']}\n"
        f"📞 Telefon: {d['phone']}\n"
        f"📍 Manzil: {message.text}\n\n"
        f"Barcha ma'lumotlar to'g'rimi?"
    )
    
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Ha, to'g'ri", callback_data="confirm_yes")],
        [InlineKeyboardButton(text="❌ Yo'q, qaytadan kiritish", callback_data="confirm_no")]
    ])
    
    await message.answer(summary, reply_markup=markup)
    await state.set_state(OrderState.waiting_for_confirmation)

@dp.callback_query(OrderState.waiting_for_confirmation, F.data.startswith("confirm_"))
async def confirm_order(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "confirm_yes":
        d = await state.get_data()
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO orders (user_id, product_name, customer_name, customer_phone, customer_address, agreed_price) VALUES (?,?,?,?,?,?)",
                       (callback.from_user.id, d.get('last_product', "Noma'lum"), d['name'], d['phone'], d['address'], d.get('last_price', 0)))
        conn.commit()
        conn.close()

        await callback.message.edit_text("Rahmat! Buyurtmangiz qabul qilindi. Tez orada bog'lanamiz.")
        
        # MONITOR BOT orqali adminlarga yuborish
        order_text = (
            f"🔔 YANGI BUYURTMA!\n\n"
            f"Mahsulot: {d.get('last_product')}\n"
            f"Mijoz: {d['name']}, {d['phone']}\n"
            f"Narx: {d.get('last_price')} so'm\n"
            f"Manzil: {d['address']}"
        )
        for aid in ADMIN_IDS:
            try:
                await monitor_bot.send_message(aid, order_text)
            except: pass
            
        await state.clear()
        chat_histories.pop(callback.from_user.id, None)
    else:
        await callback.message.edit_text("Ismingizni qaytadan kiriting:")
        await state.set_state(OrderState.waiting_for_name)
    await callback.answer()

@dp.message(F.chat.type == "private")
async def private_handler(message: types.Message, state: FSMContext):
    if message.text:
        register_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
        await process_ai_message(message.from_user.id, message.chat.id, message.text, state)

# --- MONITOR BOT HANDLERS ---

@monitor_dp.message(Command("start"))
async def monitor_start(message: types.Message):
    if message.from_user.id not in ADMIN_IDS: return
    await message.answer("Assalomu alaykum! Bu monitoring boti. Suhbat tarixini ko'rish uchun `/history_ID` buyrug'idan foydalaning.", parse_mode="Markdown")

@monitor_dp.message(F.text.startswith("/history_"))
async def monitor_history(message: types.Message):
    if message.from_user.id not in ADMIN_IDS: return
    uid = message.text.replace("/history_", "").strip()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT role, content, timestamp FROM messages WHERE user_id = ? ORDER BY timestamp ASC", (uid,))
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        await message.answer(f"ID: {uid} uchun tarix topilmadi.")
        return
        
    history_text = f"📜 Foydalanuvchi {uid} suhbat tarixi:\n\n"
    for r in rows:
        role = "👤 MIJOZ" if r[0] == "user" else "🤖 BOT"
        history_text += f"[{r[2]}]\n{role}: {r[1]}\n\n"
    
    if len(history_text) > 4096:
        for x in range(0, len(history_text), 4096):
            await message.answer(history_text[x:x+4096])
    else:
        await message.answer(history_text)

async def main():
    logging.basicConfig(level=logging.INFO)
    await bot.delete_webhook(drop_pending_updates=True)
    await monitor_bot.delete_webhook(drop_pending_updates=True)
    
    # Ikkala botni ham parallel ravishda ishga tushiramiz
    await asyncio.gather(
        dp.start_polling(bot),
        monitor_dp.start_polling(monitor_bot)
    )

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())