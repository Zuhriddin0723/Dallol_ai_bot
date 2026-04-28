import asyncio
import logging
import sqlite3
import re
import os
import anthropic
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove, InputMediaPhoto
from aiogram.exceptions import TelegramForbiddenError

# --- SOZLAMALAR ---
TELEGRAM_TOKEN = "8772049993:AAEu_UCPZLvo5tvPkzyDhuA3Hq56lNf4guc"
CLAUDE_KEY = "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"
ADMIN_IDS = [1621989960, 7611428203]  # Barcha adminlar ID raqami
MONITOR_BOT_TOKEN = "8681144550:AAH4ulohF2-JLA4RSLJzSgtlTXCVE8k8ZGI"

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
                media = [InputMediaPhoto(media=ph, caption=text if i == 0 else "") for i, ph in enumerate(photos)]
                await bot.send_media_group(user_id, media)
            else:
                await bot.send_photo(user_id, photos[0], caption=text)
        else:
            await bot.send_message(user_id, text)
        return True
    except:
        return False

client = anthropic.Anthropic(api_key=CLAUDE_KEY)
bot = Bot(token=TELEGRAM_TOKEN)
monitor_bot = Bot(token=MONITOR_BOT_TOKEN)
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
        SELECT photo_id FROM product_photos 
        WHERE product_id = (SELECT id FROM products WHERE name = ?)
    """, (name,))
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]

# --- AI PROMPT (QOIDALAR) ---
def get_system_prompt():
    products = get_all_products()
    products_text = "\n".join([f"- {p[0]}: {p[1]} - {p[2]} so'm (O'lcham: {p[3]}, Rang: {p[4]}, Material: {p[6]})" for p in products]) if products else "Hozircha mahsulot yo'q."
    return f"""SEN "Anojram" do'konining "Dallol AI" botisan. Haqiqiy O'zbek dalloli kabi chaqqon va xushmuomala bo'l.
Bizdagi mahsulotlar (FAQAT MIJOZ SO'RASA AYT):
{products_text}

QAT'IY QOIDALAR:
1. MIJOZ SO'RAMAGUNCHA MAHSULOTLARNI O'ZINGDAN TAKLIF QILMA.
2. Agar mijoz shunchaki salom bersa yoki xol-ahvol so'rasa, xushmuomala bilan alik ol va "Sizga qanday yordam bera olaman?" deb so'ra.
3. Mahsulotlar haqida mijoz so'ramagunicha gapirma.
4. Narxni doim MAXIMUMdan boshla.
5. Savdolashsa, MINIMUMdan pastga tushma.
6. HAR DOIM FAQAT BITTA SAVOL BER.
7. FAQAT BIRINCHI XABARDA SALOM BER. Ikkinchi xabardan boshlab salomlashish QAT'IYAN TAQIQLANADI.
8. Kelishuv bo'lsa xabar oxiriga [DEAL_REACHED] qo'sh.
9. Rasm ko'rsatish uchun [SEND_PHOTO: mahsulot_nomi] ishlat. Agar mijoz rasm so'rasa yoki birorta mahsulot haqida ma'lumot bersang, ALBATTA shu tagni xabaringga qo'sh.
"""

# Claude uchun xabarlar tarixi (har user uchun alohida ro'yxat)
chat_histories = {}
pending_questions = {}

def get_chat_history(user_id):
    if user_id not in chat_histories:
        chat_histories[user_id] = []
    return chat_histories[user_id]

def send_claude_message(user_id, text):
    history = get_chat_history(user_id)
    history.append({"role": "user", "content": text})

    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1024,
        system=get_system_prompt(),
        messages=history
    )

    assistant_text = response.content[0].text
    history.append({"role": "assistant", "content": assistant_text})
    return assistant_text

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

    if user_id in pending_questions:
        q = pending_questions.pop(user_id)
        p_name = q.get('product_name')

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT max_price FROM products WHERE name = ?", (p_name,))
        p_data = cursor.fetchone()
        conn.close()

        if p_data:
            price = p_data[0]
            intro = f"Assalomu alaykum! Siz bizning telegram guruhimizda shu mahsulotni narhini so'ragan ekansiz. Mahsulotning narhi {price} so'm. Sizga qaysi rangdagisi kerak?"
            
            photos = get_product_photos(p_name)
            if photos:
                media = [InputMediaPhoto(media=p, caption=intro if i == 0 else "") for i, p in enumerate(photos)]
                await bot.send_media_group(message.chat.id, media)
            else:
                await message.answer(intro)

            # AI'ga vaziyatni tushuntiramiz (salom bermasligi uchun)
            send_claude_message(user_id, f"Mijoz guruhda {p_name} mahsulotini narxini so'radi. Men unga salom berdim, narx {price} so'm ekanligini aytdim va rangini so'radim. SEN SALOM BERMASDAN, darhol muloqotni davom ettir va faqat bittadan savol ber.")
        else:
            await process_ai_message(user_id, message.chat.id, q['question'], state)
    else:
        welcome_msg = "Assalomu alaykum! Anojram do'konimizga xush kelibsiz. Sizga telegram guruhimizdagi qaysi mahsulotimiz yoqdi?"
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

        res_text = send_claude_message(user_id, text)

        # Bot javobini monitoring botga yuborish
        await log_interaction(user_id, None, res_text)

        # Rasm yuborish mantiqi
        photo_match = re.search(r"\[SEND_PHOTO:\s*(.+?)\]", res_text)
        if photo_match:
            p_name = photo_match.group(1).strip()
            await state.update_data(last_product=p_name)
            photos = get_product_photos(p_name)
            if photos:
                if len(photos) > 1:
                    media = [InputMediaPhoto(media=p) for p in photos]
                    await bot.send_media_group(chat_id, media)
                else:
                    await bot.send_photo(chat_id, photos[0])

        res_text = re.sub(r"\[SEND_PHOTO:.*?\]", "", res_text).strip()

        # Kelishuv bo'lganda
        if "[DEAL_REACHED]" in res_text:
            prices = re.findall(r"(\d[\d\s]*)\s*(?:so'm|som|sum)", res_text.lower())
            if prices:
                await state.update_data(last_price=int(prices[-1].replace(" ", "")))

            await bot.send_message(chat_id, res_text.replace("[DEAL_REACHED]", "").strip())
            await bot.send_message(chat_id, "Kelishdik! Ismingizni yozing:")
            await state.set_state(OrderState.waiting_for_name)
        else:
            await bot.send_message(chat_id, res_text)

    except Exception as e:
        logging.error(f"AI error: {e}")
        await bot.send_message(chat_id, "Kechirasiz, birozdan keyin urinib ko'ring.")

@dp.message(F.chat.type.in_({"group", "supergroup"}))
async def group_handler(message: types.Message):
    raw_text = (message.text or message.caption or "").lower()
    trigger_words = ["narx", "qancha", "necha pul", "som", "so'm", "nechi"]
    is_reply_to_photo = message.reply_to_message and message.reply_to_message.photo
    
    if any(word in raw_text for word in trigger_words):
        user_id = message.from_user.id
        me = await bot.get_me()
        markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Lichkada javob olish 💬", url=f"https://t.me/{me.username}?start=guruh")]])

        if is_reply_to_photo:
            # Rasmga reply qilingan
            replied_unique_id = message.reply_to_message.photo[-1].file_unique_id
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT name FROM products 
                WHERE id = (SELECT product_id FROM product_photos WHERE file_unique_id = ?)
            """, (replied_unique_id,))
            row = cursor.fetchone()
            conn.close()
            
            if row:
                p_name = row[0]
                success = await send_product_to_dm(user_id, p_name)
                if not success:
                    await message.reply(f"@{message.from_user.username}, narxni bilish uchun lichkamga o'ting!", reply_markup=markup)
            else:
                await message.reply("Bu mahsulot topilmadi. Iltimos, rasmga reply qilib so'rang.")
        else:
            # Shunchaki narx so'ralgan
            last_3 = get_last_3_products()
            success_count = 0
            for p in last_3:
                if await send_product_to_dm(user_id, p[1]):
                    success_count += 1
            
            if success_count == 0:
                await message.reply(f"@{message.from_user.username}, narxni bilish uchun lichkamga o'ting!", reply_markup=markup)
            else:
                await message.reply(f"@{message.from_user.username}, oxirgi mahsulotlarimizni lichkangizga yubordim!")

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