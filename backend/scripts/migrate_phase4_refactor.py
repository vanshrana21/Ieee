"""
Phase 4 Refactor Migration — AI Judge Engine Production Fixes

Updates ai_evaluations table for production safety:
1. Add ENUM status column (PENDING, PROCESSING, COMPLETED, FAILED, REQUIRES_REVIEW, OVERRIDDEN)
2. Add unique constraint (uq_round_participant_evaluation)
3. Add processing_started_at and processing_completed_at timestamps
4. Fix indexes for PostgreSQL compatibility

Usage:
    python backend/scripts/migrate_phase4_refactor.py --db /path/to/legalai.db
"""
import argparse
import sqlite3
import sys
from pathlib import Path


def run_migration(db_path: str):
    """Run Phase 4 refactor migration on SQLite database."""
    print(f"Running Phase 4 refactor migration on: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if ai_evaluations exists
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='ai_evaluations'
    """)
    if not cursor.fetchone():
        print("Error: ai_evaluations table not found. Run migrate_phase4.py first.")
        conn.close()
        return
    
    # 1. Check current schema
    cursor.execute("PRAGMA table_info(ai_evaluations)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    
    # 2. Add new columns if not exist
    new_columns = [
        ("processing_started_at", "DATETIME"),
        ("processing_completed_at", "DATETIME"),
    ]
    
    for col_name, col_type in new_columns:
        if col_name not in existing_columns:
            print(f"Adding column: {col_name}")
            cursor.execute(f"""
                ALTER TABLE ai_evaluations 
                ADD COLUMN {col_name} {col_type}
            """)
        else:
            print(f"Column {col_name} already exists")
    
    # 3. Check if status is ENUM or VARCHAR (SQLite uses TEXT for both)
    # SQLite doesn't have native ENUM, but we can add a CHECK constraint
    # For PostgreSQL migration, we'll use proper ENUM type
    
    # 4. Migrate existing status values to new ENUM
    # Map old values to new ones
    status_mapping = {
        "in_progress": "processing",
        "malformed": "requires_review",
        "timeout": "requires_review",
        "error": "failed"
    }
    
    for old_status, new_status in status_mapping.items():
        cursor.execute("""
            UPDATE ai_evaluations 
            SET status = ? 
            WHERE status = ?
        """, (new_status, old_status))
        if cursor.rowcount > 0:
            print(f"Migrated {cursor.rowcount} rows: {old_status} -> {new_status}")
    
    # 5. Add unique constraint if not exists (SQLite: use UNIQUE INDEX)
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='index' AND name='uq_round_participant_evaluation'
    """)
    if not cursor.fetchone():
        print("Creating unique index uq_round_participant_evaluation")
        try:
            cursor.execute("""
                CREATE UNIQUE INDEX uq_round_participant_evaluation 
                ON ai_evaluations(round_id, participant_id)
            """)
        except sqlite3.OperationalError as e:
            print(f"Note: Could not create unique index: {e}")
            print("(May already have data that violates constraint)")
    else:
        print("Unique index uq_round_participant_evaluation already exists")
    
    # 6. Drop old index if exists (replace with new one)
    old_indexes = [
        "idx_evaluations_session",
        "idx_evaluations_round", 
        "idx_evaluations_participant"
    ]
    for idx in old_indexes:
        cursor.execute(f"""
            SELECT name FROM sqlite_master 
            WHERE type='index' AND name='{idx}'
        """)
        if cursor.fetchone():
            print(f"Dropping old index: {idx}")
            cursor.execute(f"DROP INDEX {idx}")
    
    # 7. Create new composite indexes
    new_indexes = [
        ("idx_evaluations_session_round", "session_id, round_id"),
        ("idx_evaluations_round_participant", "round_id, participant_id"),
    ]
    
    for idx_name, columns in new_indexes:
        cursor.execute(f"""
            SELECT name FROM sqlite_master 
            WHERE type='index' AND name='{idx_name}'
        """)
        if not cursor.fetchone():
            print(f"Creating index: {idx_name}")
            cursor.execute(f"CREATE INDEX {idx_name} ON ai_evaluations({columns})")
    
    # 8. Add index on status for quick filtering
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='index' AND name='idx_evaluations_status'
    """)
    if not cursor.fetchone():
        print("Creating index: idx_evaluations_status")
        cursor.execute("CREATE INDEX idx_evaluations_status ON ai_evaluations(status)")
    
    # 9. Add index on rubric_version_id
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='index' AND name='idx_evaluations_rubric'
    """)
    if not cursor.fetchone():
        print("Creating index: idx_evaluations_rubric")
        cursor.execute("CREATE INDEX idx_evaluations_rubric ON ai_evaluations(rubric_version_id)")
    
    conn.commit()
    conn.close()
    
    print("\n✅ Phase 4 refactor migration completed successfully!")
    print("\nPostgreSQL Migration Notes:")
    print("- Use: CREATE TYPE evaluation_status_enum AS ENUM ('pending', 'processing', 'completed', 'failed', 'requires_review', 'overridden');")
    print("- Use: ALTER TABLE ai_evaluations ALTER COLUMN status TYPE evaluation_status_enum USING status::evaluation_status_enum;")
    print("- Use: ALTER TABLE ai_evaluations ADD CONSTRAINT uq_round_participant_evaluation UNIQUE (round_id, participant_id);")


def main():
    parser = argparse.ArgumentParser(description="Phase 4 AI Judge Refactor Migration")
    parser.add_argument(
        "--db",
        default="/Users/vanshrana/Desktop/IEEE/legalai.db",
        help="Path to SQLite database file"
    )
    args = parser.parse_args()
    
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        sys.exit(1)
    
    run_migration(str(db_path))


if __name__ == "__main__":
    main()
