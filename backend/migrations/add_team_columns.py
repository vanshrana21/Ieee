"""
Migration: Add missing columns to teams and team_members tables
Fixes: no such column: teams.is_active
"""
import sqlite3
import os

def migrate():
    # Find the database file
    db_path = os.path.join(os.path.dirname(__file__), '..', '..', 'legalai.db')
    
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if is_active column exists in teams table
    cursor.execute("PRAGMA table_info(teams)")
    teams_columns = [col[1] for col in cursor.fetchall()]
    
    if 'is_active' not in teams_columns:
        print("Adding is_active column to teams table...")
        cursor.execute("ALTER TABLE teams ADD COLUMN is_active BOOLEAN DEFAULT 1")
        print("✓ Added is_active to teams")
    else:
        print("✓ is_active column already exists in teams")
    
    # Check if status column exists in team_members table
    cursor.execute("PRAGMA table_info(team_members)")
    members_columns = [col[1] for col in cursor.fetchall()]
    
    if 'status' not in members_columns:
        print("Adding status column to team_members table...")
        cursor.execute("ALTER TABLE team_members ADD COLUMN status VARCHAR(20) DEFAULT 'active'")
        print("✓ Added status to team_members")
    else:
        print("✓ status column already exists in team_members")
    
    conn.commit()
    conn.close()
    print("\n✅ Migration complete! Restart the backend server.")

if __name__ == "__main__":
    migrate()
