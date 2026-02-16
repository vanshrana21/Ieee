"""
Migration Script — Phase 5: Immutable Leaderboard Engine

Creates tables for session leaderboard snapshots with full immutability support.

Tables created:
- session_leaderboard_snapshots
- session_leaderboard_entries

Features:
- SQLite-compatible (uses Text for JSON)
- PostgreSQL-ready (JSONB upgrade path)
- ON DELETE RESTRICT for referential integrity
- Unique constraints for idempotency
- Indexes for common queries
"""
import asyncio
import logging
import os
import sys
from pathlib import Path

# Setup path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from backend.orm.base import Base

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./legalai.db")


async def create_tables_with_raw_sql():
    """
    Create Phase 5 tables using raw SQL for maximum compatibility.
    """
    engine = create_async_engine(DATABASE_URL, echo=False)
    
    async with engine.begin() as conn:
        # Detect database type
        dialect = conn.dialect.name
        logger.info(f"Detected dialect: {dialect}")
        
        # Table: session_leaderboard_snapshots
        create_snapshots_table = """
        CREATE TABLE IF NOT EXISTS session_leaderboard_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            frozen_by_faculty_id INTEGER NOT NULL,
            rubric_version_id INTEGER NOT NULL,
            frozen_at TIMESTAMP NOT NULL,
            ai_model_version VARCHAR(100),
            total_participants INTEGER NOT NULL,
            checksum_hash VARCHAR(64) NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            
            UNIQUE(session_id),
            FOREIGN KEY (session_id) REFERENCES classroom_sessions(id) ON DELETE RESTRICT,
            FOREIGN KEY (frozen_by_faculty_id) REFERENCES users(id) ON DELETE RESTRICT,
            FOREIGN KEY (rubric_version_id) REFERENCES ai_rubric_versions(id) ON DELETE RESTRICT
        )
        """
        
        if dialect == "postgresql":
            # PostgreSQL uses SERIAL and different syntax
            create_snapshots_table = create_snapshots_table.replace(
                "id INTEGER PRIMARY KEY AUTOINCREMENT",
                "id SERIAL PRIMARY KEY"
            )
            create_snapshots_table = create_snapshots_table.replace(
                "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
                "TIMESTAMP NOT NULL DEFAULT NOW()"
            )
        
        await conn.execute(text(create_snapshots_table))
        logger.info("✓ Created session_leaderboard_snapshots table")
        
        # Table: session_leaderboard_entries
        create_entries_table = """
        CREATE TABLE IF NOT EXISTS session_leaderboard_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id INTEGER NOT NULL,
            participant_id INTEGER NOT NULL,
            side VARCHAR(20) NOT NULL,
            speaker_number INTEGER,
            total_score NUMERIC(10, 2) NOT NULL,
            tie_breaker_score NUMERIC(10, 4) NOT NULL DEFAULT 0,
            rank INTEGER NOT NULL,
            score_breakdown_json TEXT,
            evaluation_ids_json TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            
            UNIQUE(snapshot_id, participant_id),
            FOREIGN KEY (snapshot_id) REFERENCES session_leaderboard_snapshots(id) ON DELETE RESTRICT,
            FOREIGN KEY (participant_id) REFERENCES classroom_participants(id) ON DELETE RESTRICT
        )
        """
        
        if dialect == "postgresql":
            create_entries_table = create_entries_table.replace(
                "id INTEGER PRIMARY KEY AUTOINCREMENT",
                "id SERIAL PRIMARY KEY"
            )
            create_entries_table = create_entries_table.replace(
                "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
                "TIMESTAMP NOT NULL DEFAULT NOW()"
            )
            # Use JSONB for PostgreSQL
            create_entries_table = create_entries_table.replace(
                "score_breakdown_json TEXT",
                "score_breakdown_json JSONB"
            )
            create_entries_table = create_entries_table.replace(
                "evaluation_ids_json TEXT",
                "evaluation_ids_json JSONB"
            )
        
        await conn.execute(text(create_entries_table))
        logger.info("✓ Created session_leaderboard_entries table")
        
        # Table: session_leaderboard_audit
        create_audit_table = """
        CREATE TABLE IF NOT EXISTS session_leaderboard_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id INTEGER NOT NULL,
            action VARCHAR(50) NOT NULL,
            actor_user_id INTEGER,
            payload_json TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            
            FOREIGN KEY (snapshot_id) REFERENCES session_leaderboard_snapshots(id) ON DELETE RESTRICT,
            FOREIGN KEY (actor_user_id) REFERENCES users(id) ON DELETE SET NULL
        )
        """
        
        if dialect == "postgresql":
            create_audit_table = create_audit_table.replace(
                "id INTEGER PRIMARY KEY AUTOINCREMENT",
                "id SERIAL PRIMARY KEY"
            )
            create_audit_table = create_audit_table.replace(
                "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
                "TIMESTAMP NOT NULL DEFAULT NOW()"
            )
            create_audit_table = create_audit_table.replace(
                "payload_json TEXT",
                "payload_json JSONB"
            )
        
        await conn.execute(text(create_audit_table))
        logger.info("✓ Created session_leaderboard_audit table")
        
        # Create indexes
        indexes = [
            ("idx_snapshots_session", "session_leaderboard_snapshots", "session_id"),
            ("idx_snapshots_faculty", "session_leaderboard_snapshots", "frozen_by_faculty_id"),
            ("idx_snapshots_frozen_at", "session_leaderboard_snapshots", "frozen_at"),
            ("idx_entries_snapshot", "session_leaderboard_entries", "snapshot_id"),
            ("idx_entries_snapshot_rank", "session_leaderboard_entries", "snapshot_id, rank"),
            ("idx_entries_snapshot_score", "session_leaderboard_entries", "snapshot_id, total_score"),
            ("idx_entries_participant", "session_leaderboard_entries", "participant_id"),
            ("idx_audit_snapshot", "session_leaderboard_audit", "snapshot_id"),
            ("idx_audit_action", "session_leaderboard_audit", "action"),
            ("idx_audit_actor", "session_leaderboard_audit", "actor_user_id"),
            ("idx_audit_created", "session_leaderboard_audit", "created_at"),
        ]
        
        for idx_name, table, columns in indexes:
            try:
                await conn.execute(text(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}({columns})"))
                logger.info(f"✓ Created index {idx_name}")
            except Exception as e:
                logger.warning(f"Index {idx_name} may already exist: {e}")
        
        logger.info("✓ All Phase 5 tables and indexes created successfully")
    
    await engine.dispose()


async def verify_tables():
    """
    Verify that tables were created correctly.
    """
    engine = create_async_engine(DATABASE_URL, echo=False)
    
    async with engine.begin() as conn:
        # Check tables exist
        tables_to_check = [
            "session_leaderboard_snapshots",
            "session_leaderboard_entries",
            "session_leaderboard_audit"
        ]
        
        for table in tables_to_check:
            result = await conn.execute(text(
                f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'"
            ))
            if result.scalar_one_or_none():
                logger.info(f"✓ Verified table exists: {table}")
            else:
                logger.error(f"✗ Table missing: {table}")
    
    await engine.dispose()


async def add_foreign_key_relationships_to_orm():
    """
    Update ORM models to add back-references from related tables.
    
    Note: This is a documentation function - the actual relationships
    should be added to the ORM model files manually.
    """
    logger.info("""
    REMINDER: Add the following to these ORM files:
    
    1. classroom_session.py (ClassroomSession class):
       leaderboard_snapshots = relationship("SessionLeaderboardSnapshot", back_populates="session")
    
    2. classroom_session.py (ClassroomParticipant class):
       leaderboard_entries = relationship("SessionLeaderboardEntry", back_populates="participant")
    
    3. ai_evaluations.py (AIEvaluationAudit class):
       leaderboard_snapshot = relationship("SessionLeaderboardSnapshot", back_populates="audit_entries")
    
    4. user.py (User class):
       frozen_leaderboards = relationship("SessionLeaderboardSnapshot", back_populates="frozen_by")
    """)


async def main():
    """
    Main migration runner.
    """
    logger.info("=" * 60)
    logger.info("Phase 5 Migration: Immutable Leaderboard Engine")
    logger.info("=" * 60)
    logger.info(f"Database: {DATABASE_URL}")
    
    try:
        # Create tables
        await create_tables_with_raw_sql()
        
        # Verify
        if "sqlite" in DATABASE_URL:
            await verify_tables()
        
        # Print reminders
        await add_foreign_key_relationships_to_orm()
        
        logger.info("=" * 60)
        logger.info("✅ Phase 5 migration completed successfully")
        logger.info("=" * 60)
        
        return 0
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
