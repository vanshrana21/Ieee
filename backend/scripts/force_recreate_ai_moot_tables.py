"""
backend/scripts/force_recreate_ai_moot_tables.py
Force recreate AI Moot tables with correct schema using direct SQLite.
"""
import sqlite3
import sys
from pathlib import Path

db_path = Path(__file__).parent.parent.parent / "legalai.db"

if not db_path.exists():
    print(f"ERROR: Database not found at {db_path}")
    sys.exit(1)

print(f"Force recreating AI Moot tables...")
print(f"Database: {db_path}")

conn = sqlite3.connect(str(db_path))
cur = conn.cursor()

# Drop existing tables
cur.execute("DROP TABLE IF EXISTS ai_oral_turns")
print("✓ Dropped ai_oral_turns")

cur.execute("DROP TABLE IF EXISTS ai_oral_sessions")
print("✓ Dropped ai_oral_sessions")

# Create ai_oral_sessions with correct schema (INTEGER problem_id)
cur.execute("""
    CREATE TABLE ai_oral_sessions (
        id VARCHAR(36) PRIMARY KEY,
        user_id VARCHAR(36) NOT NULL,
        problem_id INTEGER NOT NULL,
        side VARCHAR(20) NOT NULL,
        created_at TIMESTAMP NOT NULL,
        completed_at TIMESTAMP
    )
""")
print("✓ Created ai_oral_sessions (problem_id is INTEGER)")

# Create index on problem_id
cur.execute("CREATE INDEX ix_ai_oral_sessions_problem_id ON ai_oral_sessions (problem_id)")
print("✓ Created index on problem_id")

# Create ai_oral_turns
cur.execute("""
    CREATE TABLE ai_oral_turns (
        id VARCHAR(36) PRIMARY KEY,
        session_id VARCHAR(36) NOT NULL,
        turn_number INTEGER NOT NULL,
        user_argument TEXT NOT NULL,
        ai_feedback TEXT NOT NULL,
        legal_accuracy_score INTEGER NOT NULL DEFAULT 0,
        citation_score INTEGER NOT NULL DEFAULT 0,
        etiquette_score INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP NOT NULL,
        FOREIGN KEY (session_id) REFERENCES ai_oral_sessions(id) ON DELETE CASCADE
    )
""")
print("✓ Created ai_oral_turns")

# Create index on session_id
cur.execute("CREATE INDEX ix_ai_oral_turns_session_id ON ai_oral_turns (session_id)")
print("✓ Created index on session_id")

conn.commit()
conn.close()

print("\n✓✓✓ SUCCESS: Tables recreated with correct INTEGER problem_id schema!")
print("\nNext steps:")
print("1. Restart backend: uvicorn backend.main:app --reload --env-file .env")
print("2. Test session creation with validation problem")
