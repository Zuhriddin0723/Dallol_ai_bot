import sqlite3
import os

DB_PATH = "products.db"

def check_db():
    if not os.path.exists(DB_PATH):
        print("Database not found")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("--- PRODUCTS ---")
    cursor.execute("SELECT * FROM products")
    for row in cursor.fetchall():
        print(row)
        
    print("\n--- PRODUCT PHOTOS ---")
    cursor.execute("SELECT * FROM product_photos")
    for row in cursor.fetchall():
        print(row)
        
    conn.close()

if __name__ == "__main__":
    check_db()
