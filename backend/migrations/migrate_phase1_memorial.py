"""
Phase 1 Database Migration Script — Memorial Infrastructure

Creates all tables for Moot Problem & Memorial Infrastructure:
- moot_problems
- moot_clarifications
- memorial_submissions
- memorial_evaluations
- memorial_score_freeze

Supports:
- SQLite (for development)
- PostgreSQL (for production)

Usage:
    python -m backend.migrations.migrate_phase1_memorial

Or import and call:
    from backend.migrations.migrate_phase1_memorial import run_migration
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

# SQLite Migration SQL
SQLITE_MIGRATION = """
-- =====================================================
-- Phase 1: Moot Problem & Memorial Infrastructure
-- =====================================================

-- 1. Create moot_problems table
CREATE TABLE IF NOT EXISTS moot_problems (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    institution_id INTEGER NOT NULL REFERENCES institutions(id) ON DELETE RESTRICT,
    tournament_id INTEGER REFERENCES national_tournaments(id) ON DELETE RESTRICT,
    title VARCHAR(200) NOT NULL,
    description TEXT NOT NULL,
    official_release_at TIMESTAMP NOT NULL,
    version_number INTEGER NOT NULL DEFAULT 1,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    blind_review BOOLEAN NOT NULL DEFAULT 1,
    created_by INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for moot_problems
CREATE INDEX IF NOT EXISTS idx_moot_problems_institution ON moot_problems(institution_id, is_active);
CREATE INDEX IF NOT EXISTS idx_moot_problems_release ON moot_problems(official_release_at);
CREATE INDEX IF NOT EXISTS idx_moot_problems_tournament ON moot_problems(tournament_id, version_number);

-- Unique constraint: one version per tournament
CREATE UNIQUE INDEX IF NOT EXISTS idx_moot_problems_version 
ON moot_problems(tournament_id, version_number) WHERE tournament_id IS NOT NULL;

-- 2. Create moot_clarifications table
CREATE TABLE IF NOT EXISTS moot_clarifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    moot_problem_id INTEGER NOT NULL REFERENCES moot_problems(id) ON DELETE RESTRICT,
    question_text TEXT NOT NULL,
    official_response TEXT NOT NULL,
    released_at TIMESTAMP NOT NULL,
    release_sequence INTEGER NOT NULL,
    created_by INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for moot_clarifications
CREATE INDEX IF NOT EXISTS idx_clarifications_problem ON moot_clarifications(moot_problem_id, release_sequence);
CREATE UNIQUE INDEX IF NOT EXISTS idx_clarifications_sequence 
ON moot_clarifications(moot_problem_id, release_sequence);

-- 3. Create memorial_submissions table
CREATE TABLE IF NOT EXISTS memorial_submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_team_id INTEGER NOT NULL REFERENCES tournament_teams(id) ON DELETE RESTRICT,
    moot_problem_id INTEGER NOT NULL REFERENCES moot_problems(id) ON DELETE RESTRICT,
    side VARCHAR(20) NOT NULL CHECK(side IN ('petitioner', 'respondent')),
    file_path VARCHAR(500) NOT NULL,
    file_hash_sha256 VARCHAR(64) NOT NULL,
    file_size_bytes INTEGER NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    internal_filename VARCHAR(100) NOT NULL,
    submitted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deadline_at TIMESTAMP NOT NULL,
    is_late BOOLEAN NOT NULL DEFAULT 0,
    resubmission_number INTEGER NOT NULL DEFAULT 1,
    is_locked BOOLEAN NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for memorial_submissions
CREATE INDEX IF NOT EXISTS idx_memorials_team ON memorial_submissions(tournament_team_id, moot_problem_id);
CREATE INDEX IF NOT EXISTS idx_memorials_deadline ON memorial_submissions(deadline_at, is_late);
CREATE INDEX IF NOT EXISTS idx_memorials_problem ON memorial_submissions(moot_problem_id, side);

-- Unique constraint: one resubmission per team/side/number
CREATE UNIQUE INDEX IF NOT EXISTS idx_memorials_resubmission 
ON memorial_submissions(tournament_team_id, side, resubmission_number);

-- 4. Create memorial_evaluations table
CREATE TABLE IF NOT EXISTS memorial_evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    memorial_submission_id INTEGER NOT NULL REFERENCES memorial_submissions(id) ON DELETE RESTRICT,
    judge_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    rubric_version_id INTEGER REFERENCES ai_rubric_versions(id) ON DELETE RESTRICT,
    legal_analysis_score NUMERIC(5,2) NOT NULL,
    research_depth_score NUMERIC(5,2) NOT NULL,
    clarity_score NUMERIC(5,2) NOT NULL,
    citation_format_score NUMERIC(5,2) NOT NULL,
    total_score NUMERIC(6,2) NOT NULL,
    evaluation_hash VARCHAR(64) NOT NULL,
    evaluated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for memorial_evaluations
CREATE INDEX IF NOT EXISTS idx_evaluations_submission ON memorial_evaluations(memorial_submission_id, judge_id);
CREATE INDEX IF NOT EXISTS idx_evaluations_judge ON memorial_evaluations(judge_id, evaluated_at);
CREATE INDEX IF NOT EXISTS idx_evaluations_scores ON memorial_evaluations(total_score, evaluated_at);

-- Unique constraint: one evaluation per submission per judge
CREATE UNIQUE INDEX IF NOT EXISTS idx_evaluations_unique 
ON memorial_evaluations(memorial_submission_id, judge_id);

-- 5. Create memorial_score_freeze table
CREATE TABLE IF NOT EXISTS memorial_score_freeze (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    moot_problem_id INTEGER NOT NULL UNIQUE REFERENCES moot_problems(id) ON DELETE RESTRICT,
    frozen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    frozen_by INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    checksum VARCHAR(64) NOT NULL,
    is_final BOOLEAN NOT NULL DEFAULT 1,
    total_evaluations INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for memorial_score_freeze
CREATE INDEX IF NOT EXISTS idx_freeze_problem ON memorial_score_freeze(moot_problem_id, frozen_at);
CREATE INDEX IF NOT EXISTS idx_freeze_checksum ON memorial_score_freeze(checksum);
"""

# PostgreSQL Migration SQL
POSTGRESQL_MIGRATION = """
-- =====================================================
-- Phase 1: Moot Problem & Memorial Infrastructure
-- =====================================================

-- 1. Create ENUM type for memorial side
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'memorialside') THEN
        CREATE TYPE memorialside AS ENUM ('petitioner', 'respondent');
    END IF;
END$$;

-- 2. Create moot_problems table
CREATE TABLE IF NOT EXISTS moot_problems (
    id SERIAL PRIMARY KEY,
    institution_id INTEGER NOT NULL REFERENCES institutions(id) ON DELETE RESTRICT,
    tournament_id INTEGER REFERENCES national_tournaments(id) ON DELETE RESTRICT,
    title VARCHAR(200) NOT NULL,
    description TEXT NOT NULL,
    official_release_at TIMESTAMP NOT NULL,
    version_number INTEGER NOT NULL DEFAULT 1,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    blind_review BOOLEAN NOT NULL DEFAULT TRUE,
    created_by INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for moot_problems
CREATE INDEX IF NOT EXISTS idx_moot_problems_institution ON moot_problems(institution_id, is_active);
CREATE INDEX IF NOT EXISTS idx_moot_problems_release ON moot_problems(official_release_at);
CREATE INDEX IF NOT EXISTS idx_moot_problems_tournament ON moot_problems(tournament_id, version_number);

-- Unique constraint: one version per tournament
CREATE UNIQUE INDEX IF NOT EXISTS idx_moot_problems_version 
ON moot_problems(tournament_id, version_number) WHERE tournament_id IS NOT NULL;

-- 3. Create moot_clarifications table
CREATE TABLE IF NOT EXISTS moot_clarifications (
    id SERIAL PRIMARY KEY,
    moot_problem_id INTEGER NOT NULL REFERENCES moot_problems(id) ON DELETE RESTRICT,
    question_text TEXT NOT NULL,
    official_response TEXT NOT NULL,
    released_at TIMESTAMP NOT NULL,
    release_sequence INTEGER NOT NULL,
    created_by INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for moot_clarifications
CREATE INDEX IF NOT EXISTS idx_clarifications_problem ON moot_clarifications(moot_problem_id, release_sequence);
CREATE UNIQUE INDEX IF NOT EXISTS idx_clarifications_sequence 
ON moot_clarifications(moot_problem_id, release_sequence);

-- 4. Create memorial_submissions table
CREATE TABLE IF NOT EXISTS memorial_submissions (
    id SERIAL PRIMARY KEY,
    tournament_team_id INTEGER NOT NULL REFERENCES tournament_teams(id) ON DELETE RESTRICT,
    moot_problem_id INTEGER NOT NULL REFERENCES moot_problems(id) ON DELETE RESTRICT,
    side memorialside NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    file_hash_sha256 VARCHAR(64) NOT NULL,
    file_size_bytes INTEGER NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    internal_filename VARCHAR(100) NOT NULL,
    submitted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deadline_at TIMESTAMP NOT NULL,
    is_late BOOLEAN NOT NULL DEFAULT FALSE,
    resubmission_number INTEGER NOT NULL DEFAULT 1,
    is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for memorial_submissions
CREATE INDEX IF NOT EXISTS idx_memorials_team ON memorial_submissions(tournament_team_id, moot_problem_id);
CREATE INDEX IF NOT EXISTS idx_memorials_deadline ON memorial_submissions(deadline_at, is_late);
CREATE INDEX IF NOT EXISTS idx_memorials_problem ON memorial_submissions(moot_problem_id, side);

-- Unique constraint: one resubmission per team/side/number
CREATE UNIQUE INDEX IF NOT EXISTS idx_memorials_resubmission 
ON memorial_submissions(tournament_team_id, side, resubmission_number);

-- 5. Create memorial_evaluations table
CREATE TABLE IF NOT EXISTS memorial_evaluations (
    id SERIAL PRIMARY KEY,
    memorial_submission_id INTEGER NOT NULL REFERENCES memorial_submissions(id) ON DELETE RESTRICT,
    judge_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    rubric_version_id INTEGER REFERENCES ai_rubric_versions(id) ON DELETE RESTRICT,
    legal_analysis_score NUMERIC(5,2) NOT NULL,
    research_depth_score NUMERIC(5,2) NOT NULL,
    clarity_score NUMERIC(5,2) NOT NULL,
    citation_format_score NUMERIC(5,2) NOT NULL,
    total_score NUMERIC(6,2) NOT NULL,
    evaluation_hash VARCHAR(64) NOT NULL,
    evaluated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for memorial_evaluations
CREATE INDEX IF NOT EXISTS idx_evaluations_submission ON memorial_evaluations(memorial_submission_id, judge_id);
CREATE INDEX IF NOT EXISTS idx_evaluations_judge ON memorial_evaluations(judge_id, evaluated_at);
CREATE INDEX IF NOT EXISTS idx_evaluations_scores ON memorial_evaluations(total_score, evaluated_at);

-- Unique constraint: one evaluation per submission per judge
CREATE UNIQUE INDEX IF NOT EXISTS idx_evaluations_unique 
ON memorial_evaluations(memorial_submission_id, judge_id);

-- 6. Create memorial_score_freeze table
CREATE TABLE IF NOT EXISTS memorial_score_freeze (
    id SERIAL PRIMARY KEY,
    moot_problem_id INTEGER NOT NULL UNIQUE REFERENCES moot_problems(id) ON DELETE RESTRICT,
    frozen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    frozen_by INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    checksum VARCHAR(64) NOT NULL,
    is_final BOOLEAN NOT NULL DEFAULT TRUE,
    total_evaluations INTEGER NOT NULL,
    evaluation_snapshot_json JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for memorial_score_freeze
CREATE INDEX IF NOT EXISTS idx_freeze_problem ON memorial_score_freeze(moot_problem_id, frozen_at);
CREATE INDEX IF NOT EXISTS idx_freeze_checksum ON memorial_score_freeze(checksum);

-- 7. Add check constraint for total_score calculation
ALTER TABLE memorial_evaluations
ADD CONSTRAINT check_total_score
CHECK (
    total_score =
    legal_analysis_score +
    research_depth_score +
    clarity_score +
    citation_format_score
);

-- 8. Create function to prevent evaluation updates after freeze
CREATE OR REPLACE FUNCTION prevent_eval_update_if_frozen()
RETURNS TRIGGER AS $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM memorial_score_freeze f
    JOIN memorial_submissions s
      ON s.moot_problem_id = f.moot_problem_id
    WHERE s.id = NEW.memorial_submission_id
  ) THEN
    RAISE EXCEPTION 'Cannot modify evaluation after scores are frozen';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 9. Create triggers to enforce freeze immutability
DROP TRIGGER IF EXISTS freeze_guard_update ON memorial_evaluations;
CREATE TRIGGER freeze_guard_update
BEFORE UPDATE ON memorial_evaluations
FOR EACH ROW EXECUTE FUNCTION prevent_eval_update_if_frozen();

DROP TRIGGER IF EXISTS freeze_guard_delete ON memorial_evaluations;
CREATE TRIGGER freeze_guard_delete
BEFORE DELETE ON memorial_evaluations
FOR EACH ROW EXECUTE FUNCTION prevent_eval_update_if_frozen();

-- 10. Create function to prevent evaluation insert after freeze
CREATE OR REPLACE FUNCTION prevent_eval_insert_if_frozen()
RETURNS TRIGGER AS $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM memorial_score_freeze f
    JOIN memorial_submissions s
      ON s.moot_problem_id = f.moot_problem_id
    WHERE s.id = NEW.memorial_submission_id
  ) THEN
    RAISE EXCEPTION 'Cannot create evaluation after scores are frozen';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS freeze_guard_insert ON memorial_evaluations;
CREATE TRIGGER freeze_guard_insert
BEFORE INSERT ON memorial_evaluations
FOR EACH ROW EXECUTE FUNCTION prevent_eval_insert_if_frozen();
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
    Run Phase 1 migration on the database.
    
    Args:
        engine: SQLAlchemy async engine
    """
    dialect = await detect_dialect(engine)
    
    logger.info(f"Starting Phase 1 migration for {dialect} database")
    
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
    
    logger.info("Phase 1 migration completed successfully")


async def verify_migration(engine: AsyncEngine) -> Dict[str, Any]:
    """
    Verify that all Phase 1 tables exist.
    
    Returns:
        Dict with verification results
    """
    expected_tables = [
        'moot_problems',
        'moot_clarifications',
        'memorial_submissions',
        'memorial_evaluations',
        'memorial_score_freeze'
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
            print("Phase 1 Migration Verification")
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
                print("\n✅ Phase 1 migration completed successfully!")
                print("\nMemorial Infrastructure is ready for use.")
                print("\nNext steps:")
                print("  1. Create moot problems: POST /admin/moot-problems")
                print("  2. Release clarifications: POST /moot-problems/{id}/clarifications")
                print("  3. Accept submissions: POST /teams/{id}/memorial")
                print("  4. Judges evaluate: POST /judges/memorial/{id}/evaluate")
                print("  5. Freeze scores: POST /admin/moot-problems/{id}/memorial-freeze")
                sys.exit(0)
            else:
                print("\n⚠️  Phase 1 migration partially completed. Check logs.")
                sys.exit(1)
                
        except Exception as e:
            logger.exception("Migration failed")
            print(f"\n❌ Migration failed: {e}")
            sys.exit(1)
    
    asyncio.run(main())
