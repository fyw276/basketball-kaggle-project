"""Add gender column to user_profiles table"""
import sqlite3

db_path = "outfit_assistant.db"

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Check user_profiles table structure
cursor.execute("PRAGMA table_info(user_profiles)")
columns = cursor.fetchall()
print("[OK] user_profiles columns:")
for col in columns:
    print(f"  - {col[1]} ({col[2]})")

has_gender = any(col[1] == "gender" for col in columns)
if not has_gender:
    # Use ASCII-compatible DEFAULT value
    cursor.execute("ALTER TABLE user_profiles ADD COLUMN gender VARCHAR(10) DEFAULT 'other'")
    conn.commit()
    print("[OK] Added gender column")
else:
    print("[OK] gender column already exists")

conn.close()
print("[DONE]")
