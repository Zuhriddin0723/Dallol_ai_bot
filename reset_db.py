import sqlite3
import os
import shutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "products.db")
PHOTOS_DIR = os.path.join(BASE_DIR, "photos")

def reset_database():
    if not os.path.exists(DB_PATH):
        print("Database topilmadi.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    tables = ["products", "product_photos", "orders", "users", "messages"]
    
    print("Bazani tozalash boshlandi...")
    for table in tables:
        try:
            cursor.execute(f"DELETE FROM {table}")
            print(f"✅ {table} jadvali tozalandi.")
        except sqlite3.OperationalError:
            print(f"⚠️ {table} jadvali mavjud emas.")

    conn.commit()
    conn.close()

    # Rasmlarni o'chirish
    if os.path.exists(PHOTOS_DIR):
        print("Rasmlarni o'chirish boshlandi...")
        for filename in os.listdir(PHOTOS_DIR):
            file_path = os.path.join(PHOTOS_DIR, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print(f'❌ {file_path} ni o\'chirib bo\'lmadi. Sabab: {e}')
        print("✅ Photos papkasi tozalandi.")

    print("\nBaza butunlay tozalandi!")

if __name__ == "__main__":
    confirm = input("DIQQAT! Barcha ma'lumotlar o'chib ketadi. Rozimisiz? (ha/yo'q): ")
    if confirm.lower() == "ha":
        reset_database()
    else:
        print("Amal bekor qilindi.")
