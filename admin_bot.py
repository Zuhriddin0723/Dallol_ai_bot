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
ADMIN_IDS = [1621989960]

bot = Bot(token=TOKEN)
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
        [KeyboardButton(text="🔔 Buyurtmalar")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def init_db():
    conn = sqlite3.connect("products.db")
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        min_price INTEGER,
        max_price INTEGER,
        sizes TEXT,
        colors TEXT,
        material TEXT,
        stock INTEGER DEFAULT 0,
        photo_id TEXT,
        file_unique_id TEXT
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_name TEXT,
        customer_name TEXT,
        customer_phone TEXT,
        customer_address TEXT,
        agreed_price INTEGER,
        status TEXT DEFAULT 'yangi'
    )''')

    # Migratsiya: yangi ustunlarni qo'shish (eski baza bo'lsa)
    cursor.execute("PRAGMA table_info(products)")
    columns = [col[1] for col in cursor.fetchall()]
    if "material" not in columns:
        cursor.execute("ALTER TABLE products ADD COLUMN material TEXT")
    if "file_unique_id" not in columns:
        cursor.execute("ALTER TABLE products ADD COLUMN file_unique_id TEXT")

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
    await state.update_data(min_price=int(message.text))
    await message.answer("Maximum narxni kiriting:")
    await state.set_state(AddProduct.max_price)

@dp.message(AddProduct.max_price)
async def process_max(message: types.Message, state: FSMContext):
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
    await state.update_data(stock=int(message.text))
    await message.answer("Rasm yuboring:")
    await state.set_state(AddProduct.photo)

@dp.message(AddProduct.photo, F.photo | F.text)
async def process_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    photo_name = f"{data['name']}.jpg"
    file_unique_id = None

    if not os.path.exists("photos"):
        os.makedirs("photos")

    if message.photo:
        # Rasmni kompyuterga yuklab olish va file_unique_id ni saqlash
        photo = message.photo[-1]
        file_unique_id = photo.file_unique_id
        file = await bot.get_file(photo.file_id)
        await bot.download_file(file.file_path, f"photos/{photo_name}")

    conn = sqlite3.connect("products.db")
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO products (name, min_price, max_price, sizes, colors, material, stock, photo_id, file_unique_id) VALUES (?,?,?,?,?,?,?,?,?)",
            (data['name'], data['min_price'], data['max_price'], data['sizes'], data['colors'], data['material'], data['stock'], photo_name, file_unique_id)
        )
        conn.commit()
        await message.answer(f"✅ Mahsulot muvaffaqiyatli saqlandi!\n\n📦 {data['name']}\n💰 {data['min_price']} - {data['max_price']} so'm\n📐 {data['sizes']}\n🎨 {data['colors']}\n🧵 {data['material']}\n📊 Stock: {data['stock']}")
    except Exception as e:
        await message.answer(f"Xatolik: {e}")
    conn.close()
    await state.clear()

@dp.message(F.text == "📦 Mahsulotlar ro'yxati")
async def cmd_list(message: types.Message):
    if not is_admin(message.from_user.id): return
    conn = sqlite3.connect("products.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, stock, min_price, max_price, material FROM products")
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        await message.answer("Baza bo'sh.")
        return
    text = "\n\n".join([f"🆔 ID: {r[0]}\n📦 {r[1]}\n💰 {r[3]} - {r[4]} so'm\n🧵 {r[5] or 'Noma\\'lum'}\n📊 Stock: {r[2]}" for r in rows])
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
    conn = sqlite3.connect("products.db")
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
    conn = sqlite3.connect("products.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM products WHERE id = ?", (pid,))
    conn.commit()
    conn.close()
    await message.answer(f"✅ Mahsulot #{pid} o'chirildi.")
    await state.clear()

@dp.message(F.text == "🔔 Buyurtmalar")
async def cmd_orders(message: types.Message):
    if not is_admin(message.from_user.id): return
    conn = sqlite3.connect("products.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE status = 'yangi'")
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        await message.answer("Yangi buyurtmalar yo'q.")
        return
    for r in rows:
        await message.answer(f"🆕 Buyurtma #{r[0]}\nMahsulot: {r[1]}\nMijoz: {r[2]}, {r[3]}\nManzil: {r[4]}\nNarx: {r[5]} so'm\n\n/done_{r[0]}")

@dp.message(F.text.startswith("/done_"))
async def cmd_done(message: types.Message):
    oid = message.text.replace("/done_", "")
    conn = sqlite3.connect("products.db")
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
