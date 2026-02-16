"""
Phase 4 Migration Script — AI Judge Engine

Creates tables for AI evaluation with full audit trail and immutability.

Usage:
    python backend/scripts/migrate_phase4.py --db /path/to/legalai.db
"""
import argparse
import sqlite3
import sys
from pathlib import Path


def run_migration(db_path: str):
    """Run Phase 4 migration on SQLite database."""
    print(f"Running Phase 4 migration on: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if migration already run
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='ai_evaluations'
    """)
    if cursor.fetchone():
        print("Migration already applied (ai_evaluations exists). Skipping.")
        conn.close()
        return
    
    print("Creating ai_rubrics table...")
    cursor.execute("""
        CREATE TABLE ai_rubrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            rubric_type VARCHAR(32) NOT NULL DEFAULT 'oral_argument',
            definition_json TEXT NOT NULL,
            current_version INTEGER NOT NULL DEFAULT 1,
            created_by_faculty_id INTEGER NOT NULL REFERENCES users(id),
            institution_id INTEGER REFERENCES institutions(id),
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME,
            is_active INTEGER DEFAULT 1
        )
    """)
    
    print("Creating indexes for ai_rubrics...")
    cursor.execute("CREATE INDEX idx_rubrics_faculty ON ai_rubrics(created_by_faculty_id)")
    cursor.execute("CREATE INDEX idx_rubrics_institution ON ai_rubrics(institution_id)")
    cursor.execute("CREATE INDEX idx_rubrics_type ON ai_rubrics(rubric_type)")
    
    print("Creating ai_rubric_versions table...")
    cursor.execute("""
        CREATE TABLE ai_rubric_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rubric_id INTEGER NOT NULL REFERENCES ai_rubrics(id) ON DELETE RESTRICT,
            version_number INTEGER NOT NULL,
            name VARCHAR(255) NOT NULL,
            frozen_json TEXT NOT NULL,
            criteria_summary VARCHAR(500),
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(rubric_id, version_number)
        )
    """)
    
    print("Creating indexes for ai_rubric_versions...")
    cursor.execute("CREATE INDEX idx_rubric_versions_rubric ON ai_rubric_versions(rubric_id)")
    
    print("Creating ai_evaluations table...")
    cursor.execute("""
        CREATE TABLE ai_evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL REFERENCES classroom_sessions(id) ON DELETE RESTRICT,
            round_id INTEGER NOT NULL REFERENCES classroom_rounds(id) ON DELETE RESTRICT,
            participant_id INTEGER NOT NULL REFERENCES classroom_participants(id) ON DELETE RESTRICT,
            turn_id INTEGER REFERENCES classroom_turns(id) ON DELETE RESTRICT,
            rubric_version_id INTEGER NOT NULL REFERENCES ai_rubric_versions(id) ON DELETE RESTRICT,
            final_score DECIMAL(5,2),
            score_breakdown TEXT,
            weights_used TEXT,
            ai_model VARCHAR(100) NOT NULL,
            ai_model_version VARCHAR(100),
            status VARCHAR(32) NOT NULL DEFAULT 'pending',
            canonical_attempt_id INTEGER REFERENCES ai_evaluation_attempts(id),
            finalized_by_faculty_id INTEGER REFERENCES users(id),
            finalized_at DATETIME,
            evaluation_timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME,
            UNIQUE(round_id, participant_id)
        )
    """)
    
    print("Creating indexes for ai_evaluations...")
    cursor.execute("CREATE INDEX idx_evaluations_session ON ai_evaluations(session_id)")
    cursor.execute("CREATE INDEX idx_evaluations_round ON ai_evaluations(round_id)")
    cursor.execute("CREATE INDEX idx_evaluations_participant ON ai_evaluations(participant_id)")
    cursor.execute("CREATE INDEX idx_evaluations_status ON ai_evaluations(status)")
    cursor.execute("CREATE INDEX idx_evaluations_rubric ON ai_evaluations(rubric_version_id)")
    
    print("Creating ai_evaluation_attempts table...")
    cursor.execute("""
        CREATE TABLE ai_evaluation_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            evaluation_id INTEGER REFERENCES ai_evaluations(id) ON DELETE SET NULL,
            attempt_number INTEGER NOT NULL DEFAULT 1,
            prompt_sent TEXT NOT NULL,
            prompt_hash VARCHAR(64) NOT NULL,
            llm_raw_response TEXT,
            parsed_json TEXT,
            parse_status VARCHAR(32) NOT NULL DEFAULT 'ok',
            parse_errors TEXT,
            ai_model VARCHAR(100) NOT NULL,
            ai_model_version VARCHAR(100),
            llm_latency_ms INTEGER,
            llm_token_usage_input INTEGER,
            llm_token_usage_output INTEGER,
            is_canonical INTEGER DEFAULT 0,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME
        )
    """)
    
    print("Creating indexes for ai_evaluation_attempts...")
    cursor.execute("CREATE INDEX idx_attempts_evaluation ON ai_evaluation_attempts(evaluation_id)")
    cursor.execute("CREATE INDEX idx_attempts_status ON ai_evaluation_attempts(parse_status)")
    cursor.execute("CREATE INDEX idx_attempts_prompt_hash ON ai_evaluation_attempts(prompt_hash)")
    
    print("Creating faculty_overrides table...")
    cursor.execute("""
        CREATE TABLE faculty_overrides (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ai_evaluation_id INTEGER NOT NULL REFERENCES ai_evaluations(id) ON DELETE RESTRICT,
            previous_score DECIMAL(5,2) NOT NULL,
            new_score DECIMAL(5,2) NOT NULL,
            previous_breakdown TEXT,
            new_breakdown TEXT,
            faculty_id INTEGER NOT NULL REFERENCES users(id),
            reason TEXT NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    print("Creating indexes for faculty_overrides...")
    cursor.execute("CREATE INDEX idx_overrides_evaluation ON faculty_overrides(ai_evaluation_id)")
    cursor.execute("CREATE INDEX idx_overrides_faculty ON faculty_overrides(faculty_id)")
    
    print("Creating ai_evaluation_audit table...")
    cursor.execute("""
        CREATE TABLE ai_evaluation_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            evaluation_id INTEGER NOT NULL REFERENCES ai_evaluations(id) ON DELETE CASCADE,
            attempt_id INTEGER REFERENCES ai_evaluation_attempts(id) ON DELETE SET NULL,
            action VARCHAR(32) NOT NULL,
            actor_user_id INTEGER REFERENCES users(id),
            payload_json TEXT,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    print("Creating indexes for ai_evaluation_audit...")
    cursor.execute("CREATE INDEX idx_audit_evaluation ON ai_evaluation_audit(evaluation_id)")
    cursor.execute("CREATE INDEX idx_audit_action ON ai_evaluation_audit(action)")
    cursor.execute("CREATE INDEX idx_audit_created ON ai_evaluation_audit(created_at)")
    
    # Seed default rubric
    print("Seeding default oral argument rubric...")
    import json
    default_rubric = {
        "name": "Standard Oral Argument v1",
        "version": 1,
        "criteria": [
            {"id": "substance", "label": "Substance & Law", "weight": 0.4, "type": "numeric", "scale": [0, 100]},
            {"id": "structure", "label": "Structure & Flow", "weight": 0.2, "type": "numeric", "scale": [0, 100]},
            {"id": "citations", "label": "Use of Authorities", "weight": 0.2, "type": "numeric", "scale": [0, 100]},
            {"id": "delivery", "label": "Delivery & Demeanour", "weight": 0.2, "type": "numeric", "scale": [0, 100]}
        ],
        "instructions_for_llm": "Return ONLY JSON matching the schema: {scores: {substance: int, structure: int, citations: int, delivery: int}, comments: {substance: string, structure: string, citations: string, delivery: string}, pass_fail: boolean, meta: {confidence: float}}. Scores must be integers between 0-100."
    }
    
    # Insert default rubric (created_by_faculty_id = 1 as placeholder)
    try:
        cursor.execute("""
            INSERT INTO ai_rubrics (name, description, rubric_type, definition_json, current_version, created_by_faculty_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("Standard Oral Argument", "Default rubric for oral argument evaluation", "oral_argument", 
              json.dumps(default_rubric), 1, 1))
        
        rubric_id = cursor.lastrowid
        
        # Create frozen version
        cursor.execute("""
            INSERT INTO ai_rubric_versions (rubric_id, version_number, name, frozen_json, criteria_summary)
            VALUES (?, ?, ?, ?, ?)
        """, (rubric_id, 1, "Standard Oral Argument v1", json.dumps(default_rubric), 
              "substance(0.4), structure(0.2), citations(0.2), delivery(0.2)"))
        
        print(f"✓ Seeded default rubric (ID: {rubric_id})")
    except Exception as e:
        print(f"⚠️ Could not seed default rubric: {e}")
    
    conn.commit()
    conn.close()
    
    print("✅ Phase 4 migration completed successfully!")


def main():
    parser = argparse.ArgumentParser(description="Phase 4 AI Judge Engine Migration")
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
