import asyncio
import logging
import sqlite3
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# Admin bot o'zining tokeni
TOKEN = "8268202573:AAFo-TuIs9hnEsNbWBsuix_Yx7InN-vkzgw"
ADMIN_IDS = [1621989960,7611428203]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PHOTOS_DIR = os.path.join(BASE_DIR, "photos")
DB_PATH = os.path.join(BASE_DIR, "products.db")
os.makedirs(PHOTOS_DIR, exist_ok=True)

bot = Bot(token=TOKEN)
monitor_bot = Bot(token="8681144550:AAH4ulohF2-JLA4RSLJzSgtlTXCVE8k8ZGI")
dp = Dispatcher()

class AddProduct(StatesGroup):
    name = State()
    min_price = State()
    max_price = State()
    sizes = State()
    colors = State()
    material = State()
    stock = State()
    photo = State()
    more_photos = State()

class EditProduct(StatesGroup):
    product_id = State()
    field = State()
    value = State()

class DeleteProduct(StatesGroup):
    product_id = State()

def is_admin(user_id):
    return user_id in ADMIN_IDS

def get_admin_keyboard():
    keyboard = [
        [KeyboardButton(text="➕ Mahsulot qo'shish"), KeyboardButton(text="📦 Mahsulotlar ro'yxati")],
        [KeyboardButton(text="📝 Tahrirlash"), KeyboardButton(text="🗑 O'chirish")],
        [KeyboardButton(text="🔔 Buyurtmalar")],
        [KeyboardButton(text="🛍 Xaridorlar"), KeyboardButton(text="👀 Qiziquvchilar")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_yes_no_keyboard():
    keyboard = [[KeyboardButton(text="✅ Ha"), KeyboardButton(text="❌ Yo'q")]]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        min_price INTEGER,
        max_price INTEGER,
        sizes TEXT,
        colors TEXT,
        material TEXT,
        stock INTEGER DEFAULT 0
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS product_photos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER,
        photo_id TEXT,
        file_unique_id TEXT
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        product_name TEXT,
        customer_name TEXT,
        customer_phone TEXT,
        customer_address TEXT,
        agreed_price INTEGER,
        status TEXT DEFAULT 'yangi'
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        role TEXT,
        content TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    # Migratsiya: yangi ustunlarni qo'shish (eski baza bo'lsa)
    cursor.execute("PRAGMA table_info(products)")
    columns = [col[1] for col in cursor.fetchall()]
    if "material" not in columns:
        cursor.execute("ALTER TABLE products ADD COLUMN material TEXT")
    if "file_unique_id" not in columns:
        cursor.execute("ALTER TABLE products ADD COLUMN file_unique_id TEXT")
    
    cursor.execute("PRAGMA table_info(orders)")
    order_columns = [col[1] for col in cursor.fetchall()]
    if "user_id" not in order_columns:
        cursor.execute("ALTER TABLE orders ADD COLUMN user_id INTEGER")

    conn.commit()
    conn.close()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("Kechirasiz lekin sizga mahsulot qo'shishga ruxsat yo'q.")
        return
    await message.answer("Xush kelibsiz, Admin! Kerakli bo'limni tanlang:", reply_markup=get_admin_keyboard())

@dp.message(F.text == "➕ Mahsulot qo'shish")
async def cmd_add(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await message.answer("Mahsulot nomini kiriting:")
    await state.set_state(AddProduct.name)

@dp.message(AddProduct.name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Minimum narxni kiriting:")
    await state.set_state(AddProduct.min_price)

@dp.message(AddProduct.min_price)
async def process_min(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Iltimos, faqat raqam yozing!")
        return
    await state.update_data(min_price=int(message.text))
    await message.answer("Maximum narxni kiriting:")
    await state.set_state(AddProduct.max_price)

@dp.message(AddProduct.max_price)
async def process_max(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Iltimos, faqat raqam yozing!")
        return
    await state.update_data(max_price=int(message.text))
    await message.answer("Razmerlari (masalan: S, M, L, XL):")
    await state.set_state(AddProduct.sizes)

@dp.message(AddProduct.sizes)
async def process_sizes(message: types.Message, state: FSMContext):
    await state.update_data(sizes=message.text)
    await message.answer("Ranglari (masalan: Qizil, Ko'k, Yashil):")
    await state.set_state(AddProduct.colors)

@dp.message(AddProduct.colors)
async def process_colors(message: types.Message, state: FSMContext):
    await state.update_data(colors=message.text)
    await message.answer("Materiali (Mato turi, masalan: Paxta, Lyukra):")
    await state.set_state(AddProduct.material)

@dp.message(AddProduct.material)
async def process_material(message: types.Message, state: FSMContext):
    await state.update_data(material=message.text)
    await message.answer("Qolgan miqdori (Stock):")
    await state.set_state(AddProduct.stock)

@dp.message(AddProduct.stock)
async def process_stock(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Iltimos, faqat raqam yozing!")
        return
    await state.update_data(stock=int(message.text), photos=[])
    await message.answer("Rasm yuboring:")
    await state.set_state(AddProduct.photo)

@dp.message(AddProduct.photo, F.photo | F.text)
async def process_photo(message: types.Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    file_unique_id = message.photo[-1].file_unique_id
    
    data = await state.get_data()
    photos = data.get('photos', [])
    photos.append({'id': photo_id, 'unique': file_unique_id})
    await state.update_data(photos=photos)
    
    await message.answer("Rasm qo'shildi. Yana rasm qo'shasizmi?", reply_markup=get_yes_no_keyboard())
    await state.set_state(AddProduct.more_photos)

@dp.message(AddProduct.more_photos)
async def process_more_photos(message: types.Message, state: FSMContext):
    if message.text == "✅ Ha":
        await message.answer("Keyingi rasmni yuboring:", reply_markup=ReplyKeyboardMarkup(keyboard=[], remove_keyboard=True))
        await state.set_state(AddProduct.photo)
    elif message.text == "❌ Yo'q":
        d = await state.get_data()
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO products (name, min_price, max_price, sizes, colors, material, stock)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (d['name'], d['min_price'], d['max_price'], d['sizes'], d['colors'], d['material'], d['stock']))
            
            product_id = cursor.lastrowid
            
            for p in d['photos']:
                cursor.execute("INSERT INTO product_photos (product_id, photo_id, file_unique_id) VALUES (?, ?, ?)",
                               (product_id, p['id'], p['unique']))
            
            conn.commit()
            await message.answer(f"✅ Mahsulot muvaffaqiyatli qo'shildi! (ID: {product_id})", reply_markup=get_admin_keyboard())
        except sqlite3.IntegrityError:
            await message.answer("❌ Xatolik: Bunday nomli mahsulot allaqachon mavjud.", reply_markup=get_admin_keyboard())
        finally:
            conn.close()
            await state.clear()
    else:
        await message.answer("Iltimos, tugmalardan birini tanlang!")

@dp.message(F.text == "📦 Mahsulotlar ro'yxati")
async def cmd_list(message: types.Message):
    if not is_admin(message.from_user.id): return
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, stock, min_price, max_price, material FROM products")
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        await message.answer("Baza bo'sh.")
        return
    unknown = "Noma'lum"
    text = "\n\n".join([f"🆔 ID: {r[0]}\n📦 {r[1]}\n💰 {r[3]} - {r[4]} so'm\n🧵 {r[5] or unknown}\n📊 Stock: {r[2]}" for r in rows])
    await message.answer(f"📦 Mahsulotlar:\n\n{text}")


@dp.message(F.text == "📝 Tahrirlash")
async def cmd_edit_start(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await message.answer("Tahrirlash uchun mahsulot ID raqamini yozing:")
    await state.set_state(EditProduct.product_id)

@dp.message(EditProduct.product_id)
async def edit_id_received(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Raqam yozing!")
        return
    await state.update_data(product_id=message.text)
    await message.answer("Nimani o'zgartiramiz? (name, stock, min_price, max_price, sizes, colors, material)")
    await state.set_state(EditProduct.field)

@dp.message(EditProduct.field)
async def edit_field(message: types.Message, state: FSMContext):
    await state.update_data(field=message.text.lower())
    await message.answer("Yangi qiymatni kiriting:")
    await state.set_state(EditProduct.value)

@dp.message(EditProduct.value)
async def edit_value(message: types.Message, state: FSMContext):
    data = await state.get_data()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # SQL injection dan himoya uchun field nomi tekshiriladi
    allowed_fields = ['name', 'stock', 'min_price', 'max_price', 'sizes', 'colors', 'material']
    if data['field'] not in allowed_fields:
        await message.answer("Bunday maydon yo'q!")
        await state.clear()
        return

    cursor.execute(f"UPDATE products SET {data['field']} = ? WHERE id = ?", (message.text, data['product_id']))
    conn.commit()
    conn.close()
    await message.answer("✅ Yangilandi.")
    await state.clear()

@dp.message(F.text == "🗑 O'chirish")
async def cmd_del_start(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await message.answer("O'chirish uchun mahsulot ID raqamini yozing:")
    await state.set_state(DeleteProduct.product_id)

@dp.message(DeleteProduct.product_id)
async def process_delete(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Iltimos, faqat raqam yozing!")
        return

    pid = message.text
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM products WHERE id = ?", (pid,))
    conn.commit()
    conn.close()
    await message.answer(f"✅ Mahsulot #{pid} o'chirildi.")
    await state.clear()

@dp.message(F.text == "🔔 Buyurtmalar")
async def cmd_orders(message: types.Message):
    if not is_admin(message.from_user.id): return
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE status = 'yangi'")
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        await message.answer("Yangi buyurtmalar yo'q.")
        return
    for r in rows:
        await message.answer(f"🆕 Buyurtma #{r[0]}\nMahsulot: {r[2]}\nMijoz: {r[3]}, {r[4]}\nManzil: {r[5]}\nNarx: {r[6]} so'm\n\n/done_{r[0]}")

@dp.message(F.text == "🛍 Xaridorlar")
async def cmd_buyers(message: types.Message):
    if not is_admin(message.from_user.id): return
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT user_id, customer_name, '' FROM orders WHERE user_id IS NOT NULL
    """)
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        await message.answer("Xaridorlar hali yo'q.")
        return
        
    text = "🛍 Mahsulot sotib olganlar:\n\n"
    for r in rows:
        text += f"👤 Ism: {r[1]}\n📜 Tarix: /history_{r[0]}\n\n"
    await message.answer(text)

@dp.message(F.text == "👀 Qiziquvchilar")
async def cmd_visitors(message: types.Message):
    if not is_admin(message.from_user.id): return
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT user_id, username, full_name 
        FROM users 
        WHERE user_id NOT IN (SELECT DISTINCT user_id FROM orders WHERE user_id IS NOT NULL)
    """)
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        await message.answer("Qiziquvchilar yo'q.")
        return
        
    text = "👀 Mahsulot sotib olmaganlar:\n\n"
    unknown = "Yo'q"
    for r in rows:
        text += f"👤 Ism: {r[2]}\n🔗 User: @{r[1] or unknown}\n📜 Tarix: /history_{r[0]}\n\n"
    await message.answer(text)

@dp.message(F.text.startswith("/history_"))
async def cmd_history(message: types.Message):
    if not is_admin(message.from_user.id): return
    uid = message.text.replace("/history_", "")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT role, content, timestamp FROM messages WHERE user_id = ? ORDER BY timestamp ASC", (uid,))
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        await message.answer("Suhbat tarixi topilmadi.")
        return
        
    history_text = f"📜 Foydalanuvchi {uid} suhbat tarixi:\n\n"
    for r in rows:
        role = "👤 MIJOZ" if r[0] == "user" else "🤖 BOT"
        history_text += f"[{r[2]}]\n{role}: {r[1]}\n\n"
    
    # Monitoring botga yuborish
    try:
        await monitor_bot.send_message(message.from_user.id, history_text)
        await message.answer("Tarix monitoring botga yuborildi.")
    except Exception as e:
        await message.answer(f"Xatolik: {e}. Monitoring botga start bosganingizni tekshiring.")

@dp.message(F.text.startswith("/done_"))
async def cmd_done(message: types.Message):
    oid = message.text.replace("/done_", "")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE orders SET status = 'yopildi' WHERE id = ?", (oid,))
    conn.commit()
    conn.close()
    await message.answer(f"✅ Buyurtma #{oid} yopildi.")

async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
