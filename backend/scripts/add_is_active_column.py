#!/usr/bin/env python3
"""
Migration script to add is_active column to classroom_sessions table.
Run this script to ensure the is_active column exists.
"""
import sqlite3
import sys
import os

def add_is_active_column():
    """Add is_active column to classroom_sessions table if it doesn't exist."""
    
    # Database path
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'legalai.db')
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if table exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='classroom_sessions'
        """)
        table_exists = cursor.fetchone()
        
        if not table_exists:
            print("❌ classroom_sessions table does not exist. Run create_tables_async.py first.")
            return False
        
        # Check if is_active column exists
        cursor.execute("PRAGMA table_info(classroom_sessions)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'is_active' in columns:
            print("✓ is_active column already exists in classroom_sessions table")
            return True
        
        # Add is_active column
        print("Adding is_active column to classroom_sessions table...")
        cursor.execute("""
            ALTER TABLE classroom_sessions 
            ADD COLUMN is_active BOOLEAN DEFAULT 1 NOT NULL
        """)
        
        # Create index on is_active for performance
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_classroom_sessions_is_active 
            ON classroom_sessions(is_active)
        """)
        
        conn.commit()
        print("✓ is_active column added successfully")
        print("✓ Index created on is_active column")
        
        # Verify the column was added
        cursor.execute("PRAGMA table_info(classroom_sessions)")
        columns = [column[1] for column in cursor.fetchall()]
        if 'is_active' in columns:
            print("✓ Verification successful: is_active column exists")
            return True
        else:
            print("❌ Verification failed: is_active column not found")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    success = add_is_active_column()
    sys.exit(0 if success else 1)
