"""
backend/scripts/fix_ai_moot_schema.py
Fix database schema mismatch for AI Moot Court Practice Mode.

PROBLEM:
- Phase 2 created ai_oral_sessions/turns tables with problem_id as UUID
- Phase 3 changed models to use Integer problem_id
- Tables were never altered → schema mismatch
- SQLAlchemy crashes converting int → UUID

SOLUTION:
- Drop problematic tables (they're empty in dev anyway)
- Restart backend → tables auto-recreate with correct schema

SAFETY:
- Only drops ai_oral_turns and ai_oral_sessions
- Leaves all other tables intact
- DEV-ONLY fix (production would use migrations)
"""
import sqlite3
import sys
from pathlib import Path

# Find database (project root)
db_path = Path(__file__).parent.parent.parent / "legalai.db"

if not db_path.exists():
    print(f"ERROR: Database not found at {db_path}")
    sys.exit(1)

print(f"✓ Database found: {db_path}")
print("Dropping AI Moot tables to fix schema mismatch...")

conn = sqlite3.connect(str(db_path))
cur = conn.cursor()

# Drop in reverse order (foreign keys)
cur.execute("DROP TABLE IF EXISTS ai_oral_turns")
print("✓ Dropped ai_oral_turns")

cur.execute("DROP TABLE IF EXISTS ai_oral_sessions")
print("✓ Dropped ai_oral_sessions")

conn.commit()
conn.close()

print("\n✓✓✓ SUCCESS: Tables dropped. Restart backend to recreate with correct schema.")
print("Next step: uvicorn backend.main:app --reload --env-file .env")
