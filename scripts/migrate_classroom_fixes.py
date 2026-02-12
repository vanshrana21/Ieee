"""
Classroom Mode Production Fixes Migration

FIXES:
- FIX 1: Session code validation (regex, existence, state, capacity, duplicates)
- FIX 2: DB-authoritative state machine (row locking, commit-before-broadcast)
- FIX 3: Server-calculated timer (phase_start_timestamp, phase_duration_seconds)
- FIX 4: UNIQUE constraints for concurrency protection
- FIX 5: Frontend JS backend-enforced join flow
- FIX 6: Timer persistence fields

Run: python scripts/migrate_classroom_fixes.py
"""
import sqlite3
import os
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database path
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'legalai.db')


def run_migration():
    """Execute all classroom mode production fixes."""
    logger.info("=" * 60)
    logger.info("CLASSROOM MODE PRODUCTION FIXES MIGRATION")
    logger.info("=" * 60)
    logger.info(f"Database: {DB_PATH}")
    logger.info(f"Started at: {datetime.utcnow().isoformat()}")
    logger.info("")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # =========================================================================
        # FIX 3 & 6: Add timer persistence fields to classroom_sessions
        # =========================================================================
        logger.info("[FIX 3 & 6] Adding timer persistence fields...")
        
        # Check if columns exist
        cursor.execute("PRAGMA table_info(classroom_sessions)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'phase_start_timestamp' not in columns:
            cursor.execute("""
                ALTER TABLE classroom_sessions 
                ADD COLUMN phase_start_timestamp TIMESTAMP
            """)
            logger.info("  ✓ Added phase_start_timestamp column")
        else:
            logger.info("  - phase_start_timestamp already exists")
        
        if 'phase_duration_seconds' not in columns:
            cursor.execute("""
                ALTER TABLE classroom_sessions 
                ADD COLUMN phase_duration_seconds INTEGER
            """)
            logger.info("  ✓ Added phase_duration_seconds column")
        else:
            logger.info("  - phase_duration_seconds already exists")
        
        conn.commit()
        logger.info("  ✓ Timer persistence fields ready")
        logger.info("")
        
        # =========================================================================
        # FIX 4: Add UNIQUE constraint for unique participant per session
        # =========================================================================
        logger.info("[FIX 4] Adding UNIQUE constraint for duplicate join prevention...")
        
        # SQLite doesn't support adding UNIQUE to existing columns directly
        # We need to check if a unique index already exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='index' AND name='idx_unique_participant'
        """)
        if not cursor.fetchone():
            cursor.execute("""
                CREATE UNIQUE INDEX idx_unique_participant 
                ON classroom_participants(session_id, user_id)
            """)
            logger.info("  ✓ Created UNIQUE index on (session_id, user_id)")
        else:
            logger.info("  - UNIQUE index already exists")
        
        conn.commit()
        logger.info("  ✓ Duplicate join prevention constraint ready")
        logger.info("")
        
        # =========================================================================
        # FIX 4: Add index for active session per teacher (partial index simulation)
        # =========================================================================
        logger.info("[FIX 4] Adding index for one active session per teacher...")
        
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='index' AND name='idx_teacher_active_session'
        """)
        if not cursor.fetchone():
            # SQLite doesn't support partial indexes in older versions
            # We create a regular index and enforce in application code
            cursor.execute("""
                CREATE INDEX idx_teacher_active_session 
                ON classroom_sessions(teacher_id, current_state)
            """)
            logger.info("  ✓ Created index on (teacher_id, current_state)")
        else:
            logger.info("  - Index already exists")
        
        conn.commit()
        logger.info("  ✓ Active session index ready (enforced in application code)")
        logger.info("")
        
        # =========================================================================
        # Additional indexes for performance
        # =========================================================================
        logger.info("[PERFORMANCE] Adding additional indexes...")
        
        # Index for session code lookups (join endpoint)
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='index' AND name='idx_session_code'
        """)
        if not cursor.fetchone():
            cursor.execute("""
                CREATE UNIQUE INDEX idx_session_code 
                ON classroom_sessions(session_code)
            """)
            logger.info("  ✓ Created index on session_code")
        
        # Index for participant lookups
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='index' AND name='idx_participant_session'
        """)
        if not cursor.fetchone():
            cursor.execute("""
                CREATE INDEX idx_participant_session 
                ON classroom_participants(session_id)
            """)
            logger.info("  ✓ Created index on classroom_participants(session_id)")
        
        conn.commit()
        logger.info("  ✓ Performance indexes ready")
        logger.info("")
        
        logger.info("=" * 60)
        logger.info("MIGRATION COMPLETED SUCCESSFULLY")
        logger.info("=" * 60)
        logger.info("")
        logger.info("Summary of fixes applied:")
        logger.info("  • FIX 3 & 6: Timer persistence fields added")
        logger.info("  • FIX 4: UNIQUE constraint for duplicate join prevention")
        logger.info("  • FIX 4: Index for one active session per teacher")
        logger.info("  • PERFORMANCE: Additional indexes for join/lookup operations")
        logger.info("")
        logger.info("Verification tests:")
        logger.info("  1. Try joining with invalid code format → Should fail")
        logger.info("  2. Try joining non-existent session → Should fail")
        logger.info("  3. Try joining completed session → Should fail")
        logger.info("  4. Try joining full session (40+) → Should fail")
        logger.info("  5. Try duplicate join → Should fail with 'already joined'")
        logger.info("  6. Refresh during timer → Timer continues from correct value")
        logger.info("")
        logger.info("Jai Hind! 🇮🇳⚖️")
        
    except Exception as e:
        conn.rollback()
        logger.error(f"MIGRATION FAILED: {str(e)}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run_migration()
