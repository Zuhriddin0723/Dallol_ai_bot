import asyncio
import logging
import sqlite3
import re
import os
from google import genai
from google.genai import types as genai_types
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import FSInputFile
from aiogram.exceptions import TelegramForbiddenError

# --- SOZLAMALAR ---
TELEGRAM_TOKEN = "8772049993:AAEu_UCPZLvo5tvPkzyDhuA3Hq56lNf4guc"
GEMINI_KEY = "AIzaSyC2io4kDJ5q8NJLwPu0OICYK4C2V1MBDr8"
ADMIN_IDS = [1621989960] # Barcha adminlar ID raqami

client = genai.Client(api_key=GEMINI_KEY)
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

class OrderState(StatesGroup):
    waiting_for_name = State()
    waiting_for_phone = State()
    waiting_for_address = State()

# --- BAZA BILAN ISHLASH ---
def get_all_products():
    conn = sqlite3.connect("products.db")
    cursor = conn.cursor()
    cursor.execute("SELECT name, min_price, max_price, sizes, colors, photo_id, material FROM products WHERE stock > 0")
    products = cursor.fetchall()
    conn.close()
    return products

def get_product_by_photo(photo_id):
    conn = sqlite3.connect("products.db")
    cursor = conn.cursor()
    cursor.execute("SELECT name, max_price FROM products WHERE photo_id = ?", (photo_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def get_product_photo(name):
    conn = sqlite3.connect("products.db")
    cursor = conn.cursor()
    cursor.execute("SELECT photo_id FROM products WHERE name = ?", (name,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

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
9. Rasm ko'rsatish uchun [SEND_PHOTO: mahsulot_nomi] ishlat.
"""

chat_sessions = {}
pending_questions = {}

def get_chat_session(user_id):
    if user_id not in chat_sessions:
        chat_sessions[user_id] = client.chats.create(
            model='gemini-2.5-flash', 
            config=genai_types.GenerateContentConfig(system_instruction=get_system_prompt())
        )
    return chat_sessions[user_id]

# --- HANDLERS ---

@dp.message(Command("start"), F.chat.type == "private")
async def start_handler(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    # Har safar start bosilganda yangi qoidalar ishlashi uchun suhbatni yangilaymiz
    chat_sessions.pop(user_id, None)
    
    if user_id in pending_questions:
        q = pending_questions.pop(user_id)
        p_name = q.get('product_name')
        
        conn = sqlite3.connect("products.db")
        cursor = conn.cursor()
        cursor.execute("SELECT max_price, photo_id FROM products WHERE name = ?", (p_name,))
        p_data = cursor.fetchone()
        conn.close()
        
        if p_data:
            price, photo_file = p_data
            intro = f"Assalomu alaykum! Siz bizning telegram guruhimizda shu mahsulotni narhini so'ragan ekansiz. Mahsulotning narhi {price} so'm. Sizga qaysi rangdagisi kerak?"
            
            if photo_file and os.path.exists(f"photos/{photo_file}"):
                await bot.send_photo(message.chat.id, FSInputFile(f"photos/{photo_file}"), caption=intro)
            else:
                await message.answer(intro)
                
            # AI'ga vaziyatni tushuntiramiz (salom bermasligi uchun)
            chat = get_chat_session(user_id)
            chat.send_message(f"Mijoz guruhda {p_name} mahsulotini narxini so'radi. Men unga salom berdim, narx {price} so'm ekanligini aytdim va rangini so'radim. SEN SALOM BERMASDAN, darhol muloqotni davom ettir va faqat bittadan savol ber.")
        else:
            await process_ai_message(user_id, message.chat.id, q['question'], state)
    else:
        await message.answer("Assalomu alaykum! Anojram do'konimizga xush kelibsiz. Sizga telegram guruhimizdagi qaysi mahsulotimiz yoqdi?")

async def process_ai_message(user_id, chat_id, text, state, show_typing=True):
    chat = get_chat_session(user_id)
    if show_typing:
        try:
            await bot.send_chat_action(chat_id, "typing")
        except: pass
        
    try:
        response = chat.send_message(text)
        res_text = response.text
        
        # Rasm yuborish mantiqi
        photo_match = re.search(r"\[SEND_PHOTO:\s*(.+?)\]", res_text)
        if photo_match:
            p_name = photo_match.group(1).strip()
            await state.update_data(last_product=p_name)
            p_photo_file = get_product_photo(p_name)
            if p_photo_file and os.path.exists(f"photos/{p_photo_file}"):
                await bot.send_photo(chat_id, FSInputFile(f"photos/{p_photo_file}"))
        
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
    trigger_words = ["narx", "qancha", "necha pul", "som", "so'm"]
    is_reply_to_photo = message.reply_to_message and message.reply_to_message.photo

    if is_reply_to_photo or any(word in raw_text for word in trigger_words):
        user_id = message.from_user.id
        p_name = None

        if is_reply_to_photo:
            # file_unique_id orqali aniq mahsulotni topamiz
            replied_unique_id = message.reply_to_message.photo[-1].file_unique_id
            conn = sqlite3.connect("products.db")
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM products WHERE file_unique_id = ?", (replied_unique_id,))
            row = cursor.fetchone()
            if row:
                p_name = row[0]
            else:
                # Agar topilmasa, caption orqali qidiramiz
                caption = (message.reply_to_message.caption or "").lower()
                cursor.execute("SELECT name FROM products")
                all_p = cursor.fetchall()
                for p in all_p:
                    if p[0].lower() in caption:
                        p_name = p[0]
                        break
            conn.close()

        question = f"{p_name} haqida narx so'rayapman" if p_name else raw_text

        # Shaxsiy chat state-ini olish
        user_state = dp.fsm.get_context(bot, user_id, user_id)
        
        try:
            # Lichkaga yozishga harakat qilamiz
            await process_ai_message(user_id, user_id, question, user_state)
            # Agar muvaffaqiyatli bo'lsa, guruhda hech narsa demaymiz (foydalanuvchi so'raganidek)
        except (TelegramForbiddenError, Exception):
            # Agar lichkaga yozib bo'lmasa (bot start qilinmagan bo'lsa)
            pending_questions[user_id] = {"question": question, "product_name": p_name}
            me = await bot.get_me()
            markup = types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="Lichkada javob olish 💬", url=f"https://t.me/{me.username}?start=guruh")]])
            await message.reply(f"@{message.from_user.username}, narxni bilish uchun lichkamga o'ting!", reply_markup=markup)

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
    d = await state.get_data()
    conn = sqlite3.connect("products.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO orders (product_name, customer_name, customer_phone, customer_address, agreed_price) VALUES (?,?,?,?,?)",
                   (d.get('last_product', "Noma'lum"), d['name'], d['phone'], message.text, d.get('last_price', 0)))
    conn.commit()
    conn.close()
    
    await message.answer("Rahmat! Buyurtmangiz qabul qilindi. Tez orada bog'lanamiz.")
    for aid in ADMIN_IDS:
        try:
            await bot.send_message(aid, f"🔔 YANGI BUYURTMA!\n\nMahsulot: {d.get('last_product')}\nMijoz: {d['name']}, {d['phone']}\nManzil: {message.text}")
        except: pass
    await state.clear()
    chat_sessions.pop(message.from_user.id, None)

@dp.message(F.chat.type == "private")
async def private_handler(message: types.Message, state: FSMContext):
    if message.text: await process_ai_message(message.from_user.id, message.chat.id, message.text, state)

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())