"""
backend/scripts/check_ai_moot_schema.py
Diagnose database schema mismatch for AI Moot Court tables.

Checks:
1. If ai_oral_sessions/turns tables exist in database
2. Actual column types (especially problem_id)
"""
import sqlite3
import sys
from pathlib import Path

db_path = Path(__file__).parent.parent.parent / "legalai.db"

if not db_path.exists():
    print(f"ERROR: Database not found at {db_path}")
    sys.exit(1)

print(f"✓ Database found: {db_path}\n")

conn = sqlite3.connect(str(db_path))
cur = conn.cursor()

# Check if tables exist
cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('ai_oral_sessions', 'ai_oral_turns')")
tables = cur.fetchall()

if not tables:
    print("✓ Tables do not exist - will be created on first use with correct schema")
else:
    print(f"✗ Tables exist: {[t[0] for t in tables]}")
    print("\nChecking ai_oral_sessions schema:")
    cur.execute("PRAGMA table_info(ai_oral_sessions)")
    columns = cur.fetchall()
    for col in columns:
        print(f"  {col[1]:20} {col[2]:10} {'NOT NULL' if col[3] else 'NULL'}")
    
    # Check problem_id type specifically
    problem_id_col = [c for c in columns if c[1] == 'problem_id']
    if problem_id_col:
        col_type = problem_id_col[0][2]
        print(f"\n✓ problem_id type: {col_type}")
        if col_type.upper() == 'TEXT':
            print("✗ PROBLEM: problem_id is TEXT (UUID) - should be INTEGER")
            print("   FIX: Run python backend/scripts/force_recreate_ai_moot_tables.py")
        elif col_type.upper() == 'INTEGER':
            print("✓ CORRECT: problem_id is INTEGER")

# Check ORM model by reading source
print("\nChecking ORM model definition (reading source file)...")
orm_path = Path(__file__).parent.parent / "orm" / "ai_oral_session.py"
if orm_path.exists():
    content = orm_path.read_text()
    if 'problem_id = Column(Integer' in content:
        print("✓ ORM model has: problem_id = Column(Integer, ...)")
        print("✓ CORRECT: ORM expects INTEGER")
    elif 'problem_id = Column(UUID' in content:
        print("✗ ORM model has: problem_id = Column(UUID, ...)")
        print("✗ PROBLEM: ORM expects UUID")
    else:
        print("? Could not determine ORM problem_id type from source")
else:
    print("✗ ORM file not found")

conn.close()

print("\n" + "="*60)
if not tables:
    print("STATUS: Tables don't exist. Restart backend to create with correct schema.")
elif problem_id_col and problem_id_col[0][2].upper() == 'TEXT':
    print("STATUS: SCHEMA MISMATCH - Run force_recreate script")
else:
    print("STATUS: Schema looks correct")
