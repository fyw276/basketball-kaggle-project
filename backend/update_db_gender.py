"""Update SQLite database for gender-inclusive system (修正版)"""

import sqlite3

db_path = "outfit_assistant.db"

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Check garments table
cursor.execute("PRAGMA table_info(garments)")
garment_cols = {col[1] for col in cursor.fetchall()}
print("[garments] Current columns:", sorted(garment_cols))

# Add gender_label and neutral_score if missing
if "gender_label" not in garment_cols:
    cursor.execute("ALTER TABLE garments ADD COLUMN gender_label VARCHAR(20) DEFAULT 'neutral'")
    print("[OK] Added gender_label column to garments")

if "neutral_score" not in garment_cols:
    cursor.execute("ALTER TABLE garments ADD COLUMN neutral_score FLOAT DEFAULT 1.0")
    print("[OK] Added neutral_score column to garments")

# Update existing garments: set neutral_score based on category
# Some categories are more gender-neutral by nature
neutral_categories = {
    "上衣": 0.6,  # T-shirts can be neutral
    "裤子": 0.5,  # Jeans can be gender-neutral
    "外套": 0.7,  # Coats can be neutral
    "鞋": 0.7,  # Sneakers are neutral
    "包": 0.8,  # Bags can be gender-neutral
    "汉服": 0.3,  # Hanfu is traditionally gendered
    "国风": 0.3,  # Chinese style can be gendered
}

cursor.execute("SELECT garment_id, category FROM garments WHERE gender_label = 'neutral'")
garments_to_update = cursor.fetchall()
for garment_id, category in garments_to_update:
    neutral_score = neutral_categories.get(category, 0.5)
    cursor.execute(
        "UPDATE garments SET neutral_score = ? WHERE garment_id = ?", (neutral_score, garment_id)
    )
print(f"[OK] Updated neutral_score for {len(garments_to_update)} garments")

# Check user_profiles table
cursor.execute("PRAGMA table_info(user_profiles)")
profile_cols = {col[1] for col in cursor.fetchall()}
print("[user_profiles] Current columns:", sorted(profile_cols))

# Add gender_expression if missing (nullable for males)
if "gender_expression" not in profile_cols:
    cursor.execute("ALTER TABLE user_profiles ADD COLUMN gender_expression FLOAT")
    print("[OK] Added nullable gender_expression column to user_profiles")

# Add explore_cross_gender if missing
if "explore_cross_gender" not in profile_cols:
    cursor.execute("ALTER TABLE user_profiles ADD COLUMN explore_cross_gender CHAR(1) DEFAULT '0'")
    print("[OK] Added explore_cross_gender column to user_profiles")

conn.commit()

# Verify final state
cursor.execute("PRAGMA table_info(garments)")
print("[garments] Final columns:", [col[1] for col in cursor.fetchall()])

cursor.execute("PRAGMA table_info(user_profiles)")
print("[user_profiles] Final columns:", [col[1] for col in cursor.fetchall()])

conn.close()
print("[DONE] Database updated for gender-inclusive system (修正版)")
