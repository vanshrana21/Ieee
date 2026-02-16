"""
Phase 3 Migration Script - Classroom Round Engine

Creates tables for the Round Engine:
- classroom_rounds (with Phase 3 fields)
- classroom_turns
- classroom_turn_audit

Usage:
    python backend/scripts/migrate_phase3.py --db /path/to/legalai.db
"""
import argparse
import asyncio
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


def run_migration(db_path: str):
    """Run Phase 3 migration on SQLite database."""
    print(f"Running Phase 3 migration on: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if migration already run
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='classroom_turns'
    """)
    if cursor.fetchone():
        print("Migration already applied (classroom_turns exists). Skipping.")
        conn.close()
        return
    
    print("Creating classroom_turns table...")
    cursor.execute("""
        CREATE TABLE classroom_turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            round_id INTEGER NOT NULL REFERENCES classroom_rounds(id) ON DELETE CASCADE,
            participant_id INTEGER NOT NULL REFERENCES classroom_participants(id) ON DELETE CASCADE,
            turn_order INTEGER NOT NULL,
            allowed_seconds INTEGER NOT NULL,
            started_at DATETIME,
            submitted_at DATETIME,
            transcript TEXT,
            word_count INTEGER,
            is_submitted BOOLEAN NOT NULL DEFAULT 0,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME,
            UNIQUE(round_id, turn_order),
            UNIQUE(round_id, participant_id)
        )
    """)
    
    print("Creating indexes for classroom_turns...")
    cursor.execute("""
        CREATE INDEX idx_turns_round ON classroom_turns(round_id)
    """)
    cursor.execute("""
        CREATE INDEX idx_turns_participant ON classroom_turns(participant_id)
    """)
    
    print("Creating classroom_turn_audit table...")
    cursor.execute("""
        CREATE TABLE classroom_turn_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            turn_id INTEGER NOT NULL REFERENCES classroom_turns(id) ON DELETE CASCADE,
            action VARCHAR(32) NOT NULL,
            actor_user_id INTEGER NOT NULL,
            payload_json TEXT,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    print("Creating indexes for classroom_turn_audit...")
    cursor.execute("""
        CREATE INDEX idx_turn_audit_turn ON classroom_turn_audit(turn_id)
    """)
    cursor.execute("""
        CREATE INDEX idx_turn_audit_created ON classroom_turn_audit(created_at)
    """)
    
    # Check if classroom_rounds exists with Phase 3 fields
    cursor.execute("""
        PRAGMA table_info(classroom_rounds)
    """)
    existing_columns = {row[1] for row in cursor.fetchall()}
    
    phase3_columns = {
        'round_index', 'round_type', 'status', 'current_speaker_participant_id', 
        'created_at', 'updated_at'
    }
    
    if 'round_index' not in existing_columns:
        print("Adding Phase 3 columns to classroom_rounds...")
        # Add Phase 3 columns if not exist
        additions = [
            ("round_index", "INTEGER"),
            ("round_type", "VARCHAR(32)"),
            ("status", "VARCHAR(20) DEFAULT 'PENDING'"),
            ("current_speaker_participant_id", "INTEGER REFERENCES classroom_participants(id)"),
            ("created_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
            ("updated_at", "DATETIME")
        ]
        
        for col_name, col_type in additions:
            if col_name not in existing_columns:
                try:
                    cursor.execute(f"""
                        ALTER TABLE classroom_rounds 
                        ADD COLUMN {col_name} {col_type}
                    """)
                    print(f"  Added column: {col_name}")
                except sqlite3.OperationalError as e:
                    print(f"  Note: Could not add {col_name}: {e}")
    
    # Create index on round status for efficient queries
    print("Creating indexes for classroom_rounds...")
    try:
        cursor.execute("""
            CREATE INDEX idx_rounds_session ON classroom_rounds(session_id)
        """)
    except sqlite3.OperationalError:
        print("  Index idx_rounds_session may already exist")
    
    try:
        cursor.execute("""
            CREATE INDEX idx_rounds_status ON classroom_rounds(status)
        """)
    except sqlite3.OperationalError:
        print("  Index idx_rounds_status may already exist")
    
    # Create unique constraint on session_id + round_index
    try:
        cursor.execute("""
            CREATE UNIQUE INDEX uq_round_session_index ON classroom_rounds(session_id, round_index)
        """)
    except sqlite3.OperationalError:
        print("  Unique constraint uq_round_session_index may already exist")
    
    conn.commit()
    conn.close()
    
    print("✅ Phase 3 migration completed successfully!")


def main():
    parser = argparse.ArgumentParser(description="Phase 3 Round Engine Migration")
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
