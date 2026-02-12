#!/usr/bin/env python3
"""Apply migration to add is_active column to classroom_sessions table"""
import sqlite3
import os

DB_PATH = "/Users/vanshrana/Desktop/IEEE/backend/legalai.db"

def apply_migration():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if is_active column already exists
    cursor.execute("PRAGMA table_info(classroom_sessions)")
    columns = cursor.fetchall()
    column_names = [col[1] for col in columns]
    
    if 'is_active' in column_names:
        print("✓ is_active column already exists")
    else:
        # Add is_active column
        cursor.execute("""
            ALTER TABLE classroom_sessions 
            ADD COLUMN is_active BOOLEAN DEFAULT 1
        """)
        conn.commit()
        print("✓ Added is_active column to classroom_sessions table")
    
    # Verify the column was added
    cursor.execute("PRAGMA table_info(classroom_sessions)")
    columns = cursor.fetchall()
    print("\nCurrent classroom_sessions columns:")
    for col in columns:
        print(f"  - {col[1]} ({col[2]})")
    
    conn.close()

if __name__ == "__main__":
    apply_migration()
