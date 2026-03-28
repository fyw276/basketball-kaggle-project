"""
Fix SQLite database schema - Add missing columns
"""

import sqlite3
import sys

def fix_database():
    db_path = "outfit_assistant.db"

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if garments table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='garments'")
        if not cursor.fetchone():
            print("[ERROR] garments table does not exist. Please run database init first.")
            return False

        # Check current table structure
        cursor.execute("PRAGMA table_info(garments)")
        columns = {col[1]: col[2] for col in cursor.fetchall()}
        print(f"[OK] Current garments table has {len(columns)} columns")
        for name, col_type in columns.items():
            print(f"  - {name}: {col_type}")

        # Columns to add
        patches = [
            ("name", "ALTER TABLE garments ADD COLUMN name VARCHAR(100)"),
            ("is_favorite", "ALTER TABLE garments ADD COLUMN is_favorite CHAR(1) DEFAULT '0'"),
            ("wearing_count", "ALTER TABLE garments ADD COLUMN wearing_count VARCHAR(10) DEFAULT '0'"),
        ]

        added = []
        for col_name, ddl in patches:
            if col_name in columns:
                print(f"[OK] Column '{col_name}' already exists, skip")
            else:
                try:
                    cursor.execute(ddl)
                    conn.commit()
                    print(f"[OK] Added column '{col_name}'")
                    added.append(col_name)
                except sqlite3.Error as e:
                    print(f"[ERROR] Failed to add column '{col_name}': {e}")
                    return False

        conn.close()

        if added:
            print(f"\n[DONE] Database fixed! Added {len(added)} columns: {', '.join(added)}")
        else:
            print("\n[DONE] Database is up to date, no changes needed")

        return True

    except Exception as e:
        print(f"[ERROR] Fix failed: {e}")
        return False

if __name__ == "__main__":
    success = fix_database()
    sys.exit(0 if success else 1)
