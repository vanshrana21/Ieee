"""
Phase 8 Database Migration Script

Creates all tables, columns, and indexes for the Live Courtroom Engine.

Supports:
- SQLite (for development)
- PostgreSQL (for production)

Usage:
    python -m backend.migrations.migrate_phase8

Or import and call:
    from backend.migrations.migrate_phase8 import run_migration
    await run_migration(db_engine)
"""
import logging
from typing import Optional, Dict, Any, List

from sqlalchemy import text, inspect
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)


# =============================================================================
# Migration SQL Statements
# =============================================================================

# SQLite Migration SQL
SQLITE_MIGRATION = """
-- =====================================================
-- Phase 8: Live Courtroom Engine
-- =====================================================

-- 1. Create live_court_sessions table
CREATE TABLE IF NOT EXISTS live_court_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER REFERENCES classroom_sessions(id) ON DELETE RESTRICT,
    tournament_match_id INTEGER REFERENCES tournament_matches(id) ON DELETE RESTRICT,
    institution_id INTEGER NOT NULL REFERENCES institutions(id) ON DELETE RESTRICT,
    status VARCHAR(20) NOT NULL DEFAULT 'not_started',
    current_turn_id INTEGER REFERENCES live_turns(id) ON DELETE SET NULL,
    current_speaker_id INTEGER REFERENCES classroom_participants(id) ON DELETE SET NULL,
    current_side VARCHAR(20),
    visibility_mode VARCHAR(20) NOT NULL DEFAULT 'institution',
    score_visibility VARCHAR(20) NOT NULL DEFAULT 'after_completion',
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for live_court_sessions
CREATE INDEX IF NOT EXISTS idx_live_sessions_session ON live_court_sessions(session_id, status);
CREATE INDEX IF NOT EXISTS idx_live_sessions_match ON live_court_sessions(tournament_match_id, status);
CREATE INDEX IF NOT EXISTS idx_live_sessions_institution ON live_court_sessions(institution_id, status);
CREATE INDEX IF NOT EXISTS idx_live_sessions_status ON live_court_sessions(status, created_at);

-- 2. Create live_turns table
CREATE TABLE IF NOT EXISTS live_turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    live_session_id INTEGER NOT NULL REFERENCES live_court_sessions(id) ON DELETE RESTRICT,
    participant_id INTEGER NOT NULL REFERENCES classroom_participants(id) ON DELETE RESTRICT,
    side VARCHAR(20) NOT NULL,
    turn_type VARCHAR(20) NOT NULL DEFAULT 'argument',
    allocated_seconds INTEGER NOT NULL DEFAULT 300,
    actual_seconds INTEGER DEFAULT 0,
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    is_interrupted BOOLEAN NOT NULL DEFAULT 0,
    violation_flag BOOLEAN NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for live_turns
CREATE INDEX IF NOT EXISTS idx_live_turns_session_started ON live_turns(live_session_id, started_at);
CREATE INDEX IF NOT EXISTS idx_live_turns_participant ON live_turns(participant_id, live_session_id);
CREATE INDEX IF NOT EXISTS idx_live_turns_active ON live_turns(live_session_id, ended_at) WHERE ended_at IS NULL;

-- 3. Create live_objections table
CREATE TABLE IF NOT EXISTS live_objections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    live_turn_id INTEGER NOT NULL REFERENCES live_turns(id) ON DELETE RESTRICT,
    raised_by_participant_id INTEGER NOT NULL REFERENCES classroom_participants(id) ON DELETE RESTRICT,
    objection_type VARCHAR(30) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    resolved_by_judge_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    resolved_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for live_objections
CREATE INDEX IF NOT EXISTS idx_live_objections_turn ON live_objections(live_turn_id, status);
CREATE INDEX IF NOT EXISTS idx_live_objections_judge ON live_objections(resolved_by_judge_id, status);
CREATE INDEX IF NOT EXISTS idx_live_objections_pending ON live_objections(status, created_at) WHERE status = 'pending';

-- 4. Create live_judge_scores table
CREATE TABLE IF NOT EXISTS live_judge_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    live_session_id INTEGER NOT NULL REFERENCES live_court_sessions(id) ON DELETE RESTRICT,
    judge_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    participant_id INTEGER NOT NULL REFERENCES classroom_participants(id) ON DELETE RESTRICT,
    score_type VARCHAR(30) NOT NULL,
    provisional_score NUMERIC(10,2) NOT NULL,
    comment TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(live_session_id, judge_id, participant_id, score_type)
);

-- Indexes for live_judge_scores
CREATE INDEX IF NOT EXISTS idx_live_scores_session ON live_judge_scores(live_session_id, participant_id);
CREATE INDEX IF NOT EXISTS idx_live_scores_judge ON live_judge_scores(judge_id, created_at);
CREATE INDEX IF NOT EXISTS idx_live_scores_type ON live_judge_scores(live_session_id, score_type);

-- 5. Create live_session_events table (Hash-Chained Event Log)
-- Elite Hardening: Includes event_sequence for deterministic ordering
CREATE TABLE IF NOT EXISTS live_session_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    live_session_id INTEGER NOT NULL REFERENCES live_court_sessions(id) ON DELETE RESTRICT,
    event_sequence INTEGER NOT NULL,
    event_type VARCHAR(40) NOT NULL,
    event_payload_json TEXT,
    event_hash VARCHAR(64) NOT NULL UNIQUE,
    previous_hash VARCHAR(64) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(live_session_id, event_sequence)
);

-- Indexes for live_session_events
CREATE INDEX IF NOT EXISTS idx_live_events_chain ON live_session_events(live_session_id, event_sequence);
CREATE INDEX IF NOT EXISTS idx_live_events_type ON live_session_events(live_session_id, event_type);
CREATE INDEX IF NOT EXISTS idx_live_events_previous_hash ON live_session_events(previous_hash);
CREATE INDEX IF NOT EXISTS idx_live_events_created ON live_session_events(live_session_id, created_at);
"""

# PostgreSQL Migration SQL
POSTGRESQL_MIGRATION = """
-- =====================================================
-- Phase 8: Live Courtroom Engine
-- =====================================================

-- 1. Create live_court_sessions table
CREATE TABLE IF NOT EXISTS live_court_sessions (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES classroom_sessions(id) ON DELETE RESTRICT,
    tournament_match_id INTEGER REFERENCES tournament_matches(id) ON DELETE RESTRICT,
    institution_id INTEGER NOT NULL REFERENCES institutions(id) ON DELETE RESTRICT,
    status VARCHAR(20) NOT NULL DEFAULT 'not_started',
    current_turn_id INTEGER REFERENCES live_turns(id) ON DELETE SET NULL,
    current_speaker_id INTEGER REFERENCES classroom_participants(id) ON DELETE SET NULL,
    current_side VARCHAR(20),
    visibility_mode VARCHAR(20) NOT NULL DEFAULT 'institution',
    score_visibility VARCHAR(20) NOT NULL DEFAULT 'after_completion',
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for live_court_sessions
CREATE INDEX IF NOT EXISTS idx_live_sessions_session ON live_court_sessions(session_id, status);
CREATE INDEX IF NOT EXISTS idx_live_sessions_match ON live_court_sessions(tournament_match_id, status);
CREATE INDEX IF NOT EXISTS idx_live_sessions_institution ON live_court_sessions(institution_id, status);
CREATE INDEX IF NOT EXISTS idx_live_sessions_status ON live_court_sessions(status, created_at);

-- Partial unique index: Only one LIVE session per tournament match
CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_live_per_match 
ON live_court_sessions (tournament_match_id) 
WHERE status = 'live' AND tournament_match_id IS NOT NULL;

-- 2. Create live_turns table
CREATE TABLE IF NOT EXISTS live_turns (
    id SERIAL PRIMARY KEY,
    live_session_id INTEGER NOT NULL REFERENCES live_court_sessions(id) ON DELETE RESTRICT,
    participant_id INTEGER NOT NULL REFERENCES classroom_participants(id) ON DELETE RESTRICT,
    side VARCHAR(20) NOT NULL,
    turn_type VARCHAR(20) NOT NULL DEFAULT 'argument',
    allocated_seconds INTEGER NOT NULL DEFAULT 300,
    actual_seconds INTEGER DEFAULT 0,
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    is_interrupted BOOLEAN NOT NULL DEFAULT FALSE,
    violation_flag BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for live_turns
CREATE INDEX IF NOT EXISTS idx_live_turns_session_started ON live_turns(live_session_id, started_at);
CREATE INDEX IF NOT EXISTS idx_live_turns_participant ON live_turns(participant_id, live_session_id);
CREATE INDEX IF NOT EXISTS idx_live_turns_active ON live_turns(live_session_id, ended_at) WHERE ended_at IS NULL;

-- 3. Create live_objections table
CREATE TABLE IF NOT EXISTS live_objections (
    id SERIAL PRIMARY KEY,
    live_turn_id INTEGER NOT NULL REFERENCES live_turns(id) ON DELETE RESTRICT,
    raised_by_participant_id INTEGER NOT NULL REFERENCES classroom_participants(id) ON DELETE RESTRICT,
    objection_type VARCHAR(30) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    resolved_by_judge_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    resolved_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for live_objections
CREATE INDEX IF NOT EXISTS idx_live_objections_turn ON live_objections(live_turn_id, status);
CREATE INDEX IF NOT EXISTS idx_live_objections_judge ON live_objections(resolved_by_judge_id, status);
CREATE INDEX IF NOT EXISTS idx_live_objections_pending ON live_objections(status, created_at) WHERE status = 'pending';

-- 4. Create live_judge_scores table
CREATE TABLE IF NOT EXISTS live_judge_scores (
    id SERIAL PRIMARY KEY,
    live_session_id INTEGER NOT NULL REFERENCES live_court_sessions(id) ON DELETE RESTRICT,
    judge_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    participant_id INTEGER NOT NULL REFERENCES classroom_participants(id) ON DELETE RESTRICT,
    score_type VARCHAR(30) NOT NULL,
    provisional_score NUMERIC(10,2) NOT NULL,
    comment TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(live_session_id, judge_id, participant_id, score_type)
);

-- Indexes for live_judge_scores
CREATE INDEX IF NOT EXISTS idx_live_scores_session ON live_judge_scores(live_session_id, participant_id);
CREATE INDEX IF NOT EXISTS idx_live_scores_judge ON live_judge_scores(judge_id, created_at);
CREATE INDEX IF NOT EXISTS idx_live_scores_type ON live_judge_scores(live_session_id, score_type);

-- 5. Create live_session_events table (Hash-Chained Event Log)
-- Elite Hardening: Includes event_sequence for deterministic ordering
CREATE TABLE IF NOT EXISTS live_session_events (
    id SERIAL PRIMARY KEY,
    live_session_id INTEGER NOT NULL REFERENCES live_court_sessions(id) ON DELETE RESTRICT,
    event_sequence INTEGER NOT NULL,
    event_type VARCHAR(40) NOT NULL,
    event_payload_json TEXT,
    event_hash VARCHAR(64) NOT NULL UNIQUE,
    previous_hash VARCHAR(64) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(live_session_id, event_sequence)
);

-- Indexes for live_session_events
CREATE INDEX IF NOT EXISTS idx_live_events_chain ON live_session_events(live_session_id, event_sequence);
CREATE INDEX IF NOT EXISTS idx_live_events_type ON live_session_events(live_session_id, event_type);
CREATE INDEX IF NOT EXISTS idx_live_events_previous_hash ON live_session_events(previous_hash);
CREATE INDEX IF NOT EXISTS idx_live_events_created ON live_session_events(live_session_id, created_at);
"""


# =============================================================================
# Migration Runner
# =============================================================================

async def detect_dialect(engine: AsyncEngine) -> str:
    """Detect database dialect (sqlite or postgresql)."""
    async with engine.connect() as conn:
        dialect = conn.dialect.name
        return dialect


async def run_migration(engine: AsyncEngine) -> None:
    """
    Run Phase 8 migration on the database.
    
    Args:
        engine: SQLAlchemy async engine
    """
    dialect = await detect_dialect(engine)
    
    logger.info(f"Starting Phase 8 migration for {dialect} database")
    
    # Select appropriate SQL
    if dialect == "sqlite":
        migration_sql = SQLITE_MIGRATION
    elif dialect == "postgresql":
        migration_sql = POSTGRESQL_MIGRATION
    else:
        raise ValueError(f"Unsupported database dialect: {dialect}")
    
    # Execute migration
    async with engine.begin() as conn:
        statements = [s.strip() for s in migration_sql.split(';') if s.strip()]
        
        for statement in statements:
            if not statement or statement.startswith('--'):
                continue
                
            try:
                await conn.execute(text(statement))
                logger.debug(f"Executed: {statement[:50]}...")
            except Exception as e:
                if "CREATE INDEX" in statement or "UNIQUE INDEX" in statement:
                    logger.warning(f"Index may already exist: {e}")
                elif "already exists" in str(e).lower():
                    logger.warning(f"Table/index already exists: {e}")
                else:
                    logger.error(f"Migration error: {e}")
                    raise
    
    logger.info("Phase 8 migration completed successfully")


async def verify_migration(engine: AsyncEngine) -> dict:
    """
    Verify that all Phase 8 tables exist.
    
    Returns:
        Dict with verification results
    """
    expected_tables = [
        'live_court_sessions',
        'live_turns',
        'live_objections',
        'live_judge_scores',
        'live_session_events'
    ]
    
    results = {
        'tables_created': [],
        'tables_missing': [],
        'status': 'unknown'
    }
    
    async with engine.connect() as conn:
        if engine.dialect.name == "sqlite":
            result = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
            existing_tables = {row[0] for row in result.fetchall()}
        else:  # postgresql
            result = await conn.execute(text(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
            ))
            existing_tables = {row[0] for row in result.fetchall()}
        
        for table in expected_tables:
            if table in existing_tables:
                results['tables_created'].append(table)
            else:
                results['tables_missing'].append(table)
        
        if len(results['tables_missing']) == 0:
            results['status'] = 'success'
        else:
            results['status'] = 'partial'
    
    return results


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    import asyncio
    import sys
    from backend.database import engine
    
    async def main():
        try:
            await run_migration(engine)
            
            # Verify migration
            results = await verify_migration(engine)
            
            print(f"\n{'='*60}")
            print("Phase 8 Migration Verification")
            print(f"{'='*60}")
            print(f"Status: {results['status'].upper()}")
            print(f"\nTables Created: {len(results['tables_created'])}")
            for table in results['tables_created']:
                print(f"  ✓ {table}")
            
            if results['tables_missing']:
                print(f"\nTables Missing: {len(results['tables_missing'])}")
                for table in results['tables_missing']:
                    print(f"  ✗ {table}")
            
            print(f"{'='*60}")
            
            if results['status'] == 'success':
                print("\n✅ Phase 8 migration completed successfully!")
                print("\nLive Courtroom Engine is ready for use.")
                sys.exit(0)
            else:
                print("\n⚠️  Phase 8 migration partially completed. Check logs.")
                sys.exit(1)
                
        except Exception as e:
            logger.exception("Migration failed")
            print(f"\n❌ Migration failed: {e}")
            sys.exit(1)
    
    asyncio.run(main())
