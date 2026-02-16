"""
Phase 2 Database Migration Script — Oral Rounds Engine

Creates all tables for Hardened Oral Rounds Engine:
- oral_round_templates
- oral_sessions
- oral_turns
- oral_evaluations
- oral_session_freeze

Security Features:
- PostgreSQL triggers for freeze immutability
- Check constraint for total_score
- No CASCADE deletes (ON DELETE RESTRICT everywhere)
- Institution-scoped with proper indexing

Supports:
- SQLite (for development)
- PostgreSQL (for production, with triggers)

Usage:
    python -m backend.migrations.migrate_phase2_oral

Or import and call:
    from backend.migrations.migrate_phase2_oral import run_migration
    await run_migration(db_engine)
"""
import logging
from typing import Dict, Any, List

from sqlalchemy import text, inspect
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)


# =============================================================================
# Migration SQL Statements
# =============================================================================

# SQLite Migration SQL (no triggers, application-level guards)
SQLITE_MIGRATION = """
-- =====================================================
-- Phase 2: Hardened Oral Rounds Engine
-- =====================================================

-- 1. Create ENUM types as TEXT CHECK constraints
-- OralSessionStatus
-- OralSide
-- OralTurnType

-- 2. Create oral_round_templates table
CREATE TABLE IF NOT EXISTS oral_round_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    institution_id INTEGER NOT NULL REFERENCES institutions(id) ON DELETE RESTRICT,
    name VARCHAR(100) NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    structure_json TEXT NOT NULL DEFAULT '[]',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for oral_round_templates
CREATE INDEX IF NOT EXISTS idx_templates_institution ON oral_round_templates(institution_id, name);
CREATE UNIQUE INDEX IF NOT EXISTS idx_templates_unique 
ON oral_round_templates(institution_id, name, version);

-- 3. Create oral_sessions table
CREATE TABLE IF NOT EXISTS oral_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    institution_id INTEGER NOT NULL REFERENCES institutions(id) ON DELETE RESTRICT,
    petitioner_team_id INTEGER NOT NULL REFERENCES tournament_teams(id) ON DELETE RESTRICT,
    respondent_team_id INTEGER NOT NULL REFERENCES tournament_teams(id) ON DELETE RESTRICT,
    round_template_id INTEGER NOT NULL REFERENCES oral_round_templates(id) ON DELETE RESTRICT,
    status VARCHAR(20) NOT NULL CHECK(status IN ('draft', 'active', 'finalized')) DEFAULT 'draft',
    finalized_at TIMESTAMP NULL,
    finalized_by INTEGER NULL REFERENCES users(id) ON DELETE RESTRICT,
    session_hash VARCHAR(64) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for oral_sessions
CREATE INDEX IF NOT EXISTS idx_oral_sessions_institution ON oral_sessions(institution_id, status);
CREATE INDEX IF NOT EXISTS idx_oral_sessions_teams ON oral_sessions(petitioner_team_id, respondent_team_id);
CREATE INDEX IF NOT EXISTS idx_oral_sessions_template ON oral_sessions(round_template_id);

-- 4. Create oral_turns table
CREATE TABLE IF NOT EXISTS oral_turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES oral_sessions(id) ON DELETE RESTRICT,
    participant_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    side VARCHAR(20) NOT NULL CHECK(side IN ('petitioner', 'respondent')),
    turn_type VARCHAR(20) NOT NULL CHECK(turn_type IN ('opening', 'argument', 'rebuttal', 'sur_rebuttal')),
    allocated_seconds INTEGER NOT NULL,
    order_index INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for oral_turns
CREATE UNIQUE INDEX IF NOT EXISTS idx_turns_session_order 
ON oral_turns(session_id, order_index);
CREATE INDEX IF NOT EXISTS idx_turns_session ON oral_turns(session_id, order_index);
CREATE INDEX IF NOT EXISTS idx_turns_participant ON oral_turns(participant_id);

-- 5. Create oral_evaluations table
CREATE TABLE IF NOT EXISTS oral_evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES oral_sessions(id) ON DELETE RESTRICT,
    judge_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    speaker_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    legal_reasoning_score NUMERIC(5,2) NOT NULL,
    structure_score NUMERIC(5,2) NOT NULL,
    responsiveness_score NUMERIC(5,2) NOT NULL,
    courtroom_control_score NUMERIC(5,2) NOT NULL,
    total_score NUMERIC(6,2) NOT NULL,
    evaluation_hash VARCHAR(64) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for oral_evaluations
CREATE UNIQUE INDEX IF NOT EXISTS idx_evaluations_unique 
ON oral_evaluations(session_id, judge_id, speaker_id);
CREATE INDEX IF NOT EXISTS idx_oral_evaluations_session ON oral_evaluations(session_id, judge_id);
CREATE INDEX IF NOT EXISTS idx_oral_evaluations_scores ON oral_evaluations(total_score, created_at);

-- 6. Create oral_session_freeze table
CREATE TABLE IF NOT EXISTS oral_session_freeze (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL UNIQUE REFERENCES oral_sessions(id) ON DELETE RESTRICT,
    evaluation_snapshot_json TEXT NOT NULL DEFAULT '[]',
    session_checksum VARCHAR(64) NOT NULL,
    frozen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    frozen_by INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for oral_session_freeze
CREATE INDEX IF NOT EXISTS idx_freeze_session ON oral_session_freeze(session_id, frozen_at);
CREATE INDEX IF NOT EXISTS idx_freeze_checksum ON oral_session_freeze(session_checksum);
"""

# PostgreSQL Migration SQL (with triggers for freeze immutability)
POSTGRESQL_MIGRATION = """
-- =====================================================
-- Phase 2: Hardened Oral Rounds Engine (PostgreSQL)
-- =====================================================

-- 1. Create ENUM types
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'oralsessionstatus') THEN
        CREATE TYPE oralsessionstatus AS ENUM ('draft', 'active', 'finalized');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'oralside') THEN
        CREATE TYPE oralside AS ENUM ('petitioner', 'respondent');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'oralturntype') THEN
        CREATE TYPE oralturntype AS ENUM ('opening', 'argument', 'rebuttal', 'sur_rebuttal');
    END IF;
END$$;

-- 2. Create oral_round_templates table
CREATE TABLE IF NOT EXISTS oral_round_templates (
    id SERIAL PRIMARY KEY,
    institution_id INTEGER NOT NULL REFERENCES institutions(id) ON DELETE RESTRICT,
    name VARCHAR(100) NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    structure_json JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for oral_round_templates
CREATE INDEX IF NOT EXISTS idx_templates_institution ON oral_round_templates(institution_id, name);
CREATE UNIQUE INDEX IF NOT EXISTS idx_templates_unique 
ON oral_round_templates(institution_id, name, version);

-- 3. Create oral_sessions table
CREATE TABLE IF NOT EXISTS oral_sessions (
    id SERIAL PRIMARY KEY,
    institution_id INTEGER NOT NULL REFERENCES institutions(id) ON DELETE RESTRICT,
    petitioner_team_id INTEGER NOT NULL REFERENCES tournament_teams(id) ON DELETE RESTRICT,
    respondent_team_id INTEGER NOT NULL REFERENCES tournament_teams(id) ON DELETE RESTRICT,
    round_template_id INTEGER NOT NULL REFERENCES oral_round_templates(id) ON DELETE RESTRICT,
    status oralsessionstatus NOT NULL DEFAULT 'draft',
    finalized_at TIMESTAMP NULL,
    finalized_by INTEGER NULL REFERENCES users(id) ON DELETE RESTRICT,
    session_hash VARCHAR(64) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for oral_sessions
CREATE INDEX IF NOT EXISTS idx_oral_sessions_institution ON oral_sessions(institution_id, status);
CREATE INDEX IF NOT EXISTS idx_oral_sessions_teams ON oral_sessions(petitioner_team_id, respondent_team_id);
CREATE INDEX IF NOT EXISTS idx_oral_sessions_template ON oral_sessions(round_template_id);

-- 4. Create oral_turns table
CREATE TABLE IF NOT EXISTS oral_turns (
    id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES oral_sessions(id) ON DELETE RESTRICT,
    participant_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    side oralside NOT NULL,
    turn_type oralturntype NOT NULL,
    allocated_seconds INTEGER NOT NULL,
    order_index INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for oral_turns
CREATE UNIQUE INDEX IF NOT EXISTS idx_turns_session_order 
ON oral_turns(session_id, order_index);
CREATE INDEX IF NOT EXISTS idx_turns_session ON oral_turns(session_id, order_index);
CREATE INDEX IF NOT EXISTS idx_turns_participant ON oral_turns(participant_id);

-- 5. Create oral_evaluations table
CREATE TABLE IF NOT EXISTS oral_evaluations (
    id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES oral_sessions(id) ON DELETE RESTRICT,
    judge_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    speaker_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    legal_reasoning_score NUMERIC(5,2) NOT NULL,
    structure_score NUMERIC(5,2) NOT NULL,
    responsiveness_score NUMERIC(5,2) NOT NULL,
    courtroom_control_score NUMERIC(5,2) NOT NULL,
    total_score NUMERIC(6,2) NOT NULL,
    evaluation_hash VARCHAR(64) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for oral_evaluations
CREATE UNIQUE INDEX IF NOT EXISTS idx_evaluations_unique 
ON oral_evaluations(session_id, judge_id, speaker_id);
CREATE INDEX IF NOT EXISTS idx_oral_evaluations_session ON oral_evaluations(session_id, judge_id);
CREATE INDEX IF NOT EXISTS idx_oral_evaluations_scores ON oral_evaluations(total_score, created_at);

-- 6. Create oral_session_freeze table
CREATE TABLE IF NOT EXISTS oral_session_freeze (
    id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL UNIQUE REFERENCES oral_sessions(id) ON DELETE RESTRICT,
    evaluation_snapshot_json JSONB NOT NULL DEFAULT '[]',
    session_checksum VARCHAR(64) NOT NULL,
    frozen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    frozen_by INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for oral_session_freeze
CREATE INDEX IF NOT EXISTS idx_freeze_session ON oral_session_freeze(session_id, frozen_at);
CREATE INDEX IF NOT EXISTS idx_freeze_checksum ON oral_session_freeze(session_checksum);

-- =====================================================
-- PostgreSQL Triggers for Freeze Immutability
-- =====================================================

-- 7. Add check constraint for total_score (PostgreSQL only)
ALTER TABLE oral_evaluations
DROP CONSTRAINT IF EXISTS check_total_score_oral;

ALTER TABLE oral_evaluations
ADD CONSTRAINT check_total_score_oral
CHECK (
    total_score =
    legal_reasoning_score +
    structure_score +
    responsiveness_score +
    courtroom_control_score
);

-- 8. Create function to prevent evaluation UPDATE after freeze
CREATE OR REPLACE FUNCTION prevent_oral_eval_update_if_frozen()
RETURNS TRIGGER AS $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM oral_session_freeze f
    WHERE f.session_id = NEW.session_id
  ) THEN
    RAISE EXCEPTION 'Cannot modify oral evaluation after session is frozen';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 9. Create trigger to block UPDATE on oral_evaluations after freeze
DROP TRIGGER IF EXISTS oral_freeze_guard_update ON oral_evaluations;
CREATE TRIGGER oral_freeze_guard_update
BEFORE UPDATE ON oral_evaluations
FOR EACH ROW EXECUTE FUNCTION prevent_oral_eval_update_if_frozen();

-- 10. Create trigger to block DELETE on oral_evaluations after freeze
DROP TRIGGER IF EXISTS oral_freeze_guard_delete ON oral_evaluations;
CREATE TRIGGER oral_freeze_guard_delete
BEFORE DELETE ON oral_evaluations
FOR EACH ROW EXECUTE FUNCTION prevent_oral_eval_update_if_frozen();

-- 11. Create function to prevent evaluation INSERT after freeze
CREATE OR REPLACE FUNCTION prevent_oral_eval_insert_if_frozen()
RETURNS TRIGGER AS $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM oral_session_freeze f
    WHERE f.session_id = NEW.session_id
  ) THEN
    RAISE EXCEPTION 'Cannot create oral evaluation after session is frozen';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 12. Create trigger to block INSERT on oral_evaluations after freeze
DROP TRIGGER IF EXISTS oral_freeze_guard_insert ON oral_evaluations;
CREATE TRIGGER oral_freeze_guard_insert
BEFORE INSERT ON oral_evaluations
FOR EACH ROW EXECUTE FUNCTION prevent_oral_eval_insert_if_frozen();
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
    Run Phase 2 migration on the database.
    
    Args:
        engine: SQLAlchemy async engine
    """
    dialect = await detect_dialect(engine)
    
    logger.info(f"Starting Phase 2 migration for {dialect} database")
    
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
    
    logger.info("Phase 2 migration completed successfully")


async def verify_migration(engine: AsyncEngine) -> Dict[str, Any]:
    """
    Verify that all Phase 2 tables exist.
    
    Returns:
        Dict with verification results
    """
    expected_tables = [
        'oral_round_templates',
        'oral_sessions',
        'oral_turns',
        'oral_evaluations',
        'oral_session_freeze'
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
            print("Phase 2 Migration Verification")
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
                print("\n✅ Phase 2 migration completed successfully!")
                print("\nOral Rounds Engine is ready for use.")
                print("\nNext steps:")
                print("  1. Create templates: POST /oral/templates")
                print("  2. Create sessions: POST /oral/sessions")
                print("  3. Activate: POST /oral/sessions/{id}/activate")
                print("  4. Evaluate: POST /oral/sessions/{id}/evaluate")
                print("  5. Finalize: POST /oral/sessions/{id}/finalize")
                sys.exit(0)
            else:
                print("\n⚠️  Phase 2 migration partially completed. Check logs.")
                sys.exit(1)
                
        except Exception as e:
            logger.exception("Migration failed")
            print(f"\n❌ Migration failed: {e}")
            sys.exit(1)
    
    asyncio.run(main())
