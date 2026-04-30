import sqlite3
import os

DB_PATH = "products.db"
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

print("--- product_photos schema ---")
cursor.execute("PRAGMA table_info(product_photos)")
for col in cursor.fetchall():
    print(col)

print("\n--- products schema ---")
cursor.execute("PRAGMA table_info(products)")
for col in cursor.fetchall():
    print(col)

conn.close()
