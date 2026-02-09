"""
backend/scripts/verify_schema.py
Verify database schema has correct types for UUID and Integer columns.
"""
import sqlite3
from pathlib import Path

db_path = Path(__file__).parent.parent.parent / "legalai.db"

if not db_path.exists():
    print(f"ERROR: Database not found at {db_path}")
    exit(1)

print(f"✓ Database: {db_path}\n")
conn = sqlite3.connect(str(db_path))
cur = conn.cursor()

# Check users table
print("users table schema:")
cur.execute("PRAGMA table_info(users)")
for row in cur.fetchall():
    print(f"  {row[1]:20} {row[2]:10}")
    if row[1] == 'id':
        if row[2].upper() == 'TEXT':
            print("    ✓ users.id is TEXT (UUID stored as TEXT)")
        elif row[2].upper() == 'INTEGER':
            print("    ✗ ERROR: users.id is INTEGER - should be TEXT for UUID!")

# Check ai_oral_sessions table
print("\nai_oral_sessions schema:")
cur.execute("PRAGMA table_info(ai_oral_sessions)")
for row in cur.fetchall():
    print(f"  {row[1]:20} {row[2]:10}")
    if row[1] == 'user_id':
        if row[2].upper() == 'TEXT':
            print("    ✓ user_id is TEXT (matches users.id UUID)")
        elif row[2].upper() == 'INTEGER':
            print("    ✗ ERROR: user_id is INTEGER - should be TEXT!")
    if row[1] == 'problem_id':
        if row[2].upper() == 'INTEGER':
            print("    ✓ problem_id is INTEGER (matches MootProject.id)")
        else:
            print(f"    ✗ ERROR: problem_id is {row[2]} - should be INTEGER!")

# Check ai_oral_turns table
print("\nai_oral_turns schema:")
cur.execute("PRAGMA table_info(ai_oral_turns)")
for row in cur.fetchall():
    print(f"  {row[1]:20} {row[2]:10}")
    if row[1] == 'session_id':
        if row[2].upper() == 'TEXT':
            print("    ✓ session_id is TEXT (matches ai_oral_sessions.id UUID)")
        elif row[2].upper() == 'INTEGER':
            print("    ✗ ERROR: session_id is INTEGER - should be TEXT!")

conn.close()
print("\n" + "="*60)
print("Schema check complete. All UUID columns should be TEXT.")
