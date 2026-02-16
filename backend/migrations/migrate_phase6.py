"""
Phase 6 Database Migration Script

Creates all tables, columns, and indexes for the Institutional Governance Layer.

Supports:
- SQLite (for development)
- PostgreSQL (for production)

Usage:
    python -m backend.migrations.migrate_phase6

Or import and call:
    from backend.migrations.migrate_phase6 import run_migration
    await run_migration(db_engine)
"""
import logging
from typing import Optional

from sqlalchemy import text, inspect
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)


# =============================================================================
# Migration SQL Statements
# =============================================================================

# SQLite Migration SQL
SQLITE_MIGRATION = """
-- =====================================================
-- Phase 6: Institutional Governance Layer
-- =====================================================

-- 1. Create institutions table
CREATE TABLE IF NOT EXISTS institutions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(200) NOT NULL UNIQUE,
    slug VARCHAR(50) NOT NULL UNIQUE,
    accreditation_body VARCHAR(200),
    accreditation_number VARCHAR(100),
    compliance_mode VARCHAR(20) NOT NULL DEFAULT 'standard',
    settings_json TEXT,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deactivated_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_institutions_slug ON institutions(slug);
CREATE INDEX IF NOT EXISTS idx_institutions_compliance ON institutions(compliance_mode);
CREATE INDEX IF NOT EXISTS idx_institutions_active ON institutions(is_active);

-- 2. Create academic_years table
CREATE TABLE IF NOT EXISTS academic_years (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    institution_id INTEGER NOT NULL REFERENCES institutions(id) ON DELETE RESTRICT,
    label VARCHAR(50) NOT NULL,
    start_date TIMESTAMP NOT NULL,
    end_date TIMESTAMP NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(institution_id, label)
);

CREATE INDEX IF NOT EXISTS idx_academic_years_institution ON academic_years(institution_id);
CREATE INDEX IF NOT EXISTS idx_academic_years_dates ON academic_years(start_date, end_date);

-- 3. Create session_policy_profiles table
CREATE TABLE IF NOT EXISTS session_policy_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    institution_id INTEGER NOT NULL REFERENCES institutions(id) ON DELETE RESTRICT,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    allow_overrides_after_freeze BOOLEAN NOT NULL DEFAULT 0,
    require_dual_faculty_validation BOOLEAN NOT NULL DEFAULT 0,
    require_external_examiner BOOLEAN NOT NULL DEFAULT 0,
    freeze_requires_all_rounds BOOLEAN NOT NULL DEFAULT 1,
    auto_freeze_enabled BOOLEAN NOT NULL DEFAULT 0,
    ranking_visibility_mode VARCHAR(20) NOT NULL DEFAULT 'faculty_only',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(institution_id, name)
);

CREATE INDEX IF NOT EXISTS idx_policy_profiles_institution ON session_policy_profiles(institution_id);

-- 4. Create course_instances table
CREATE TABLE IF NOT EXISTS course_instances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    academic_year_id INTEGER NOT NULL REFERENCES academic_years(id) ON DELETE RESTRICT,
    subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE RESTRICT,
    faculty_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    policy_profile_id INTEGER NOT NULL REFERENCES session_policy_profiles(id) ON DELETE RESTRICT,
    section VARCHAR(20),
    capacity INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(academic_year_id, subject_id, section)
);

CREATE INDEX IF NOT EXISTS idx_course_instances_year ON course_instances(academic_year_id);
CREATE INDEX IF NOT EXISTS idx_course_instances_faculty ON course_instances(faculty_id);
CREATE INDEX IF NOT EXISTS idx_course_instances_policy ON course_instances(policy_profile_id);

-- 5. Create session_approvals table
CREATE TABLE IF NOT EXISTS session_approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES classroom_sessions(id) ON DELETE RESTRICT,
    required_role VARCHAR(20) NOT NULL,
    approved_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    approved_at TIMESTAMP,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    notes TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_session_approvals_session ON session_approvals(session_id, status);
CREATE INDEX IF NOT EXISTS idx_session_approvals_required_role ON session_approvals(session_id, required_role, status);
CREATE INDEX IF NOT EXISTS idx_session_approvals_approved_by ON session_approvals(approved_by);

-- 6. Create evaluation_reviews table
CREATE TABLE IF NOT EXISTS evaluation_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    evaluation_id INTEGER NOT NULL REFERENCES ai_evaluations(id) ON DELETE RESTRICT,
    reviewer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    reviewer_role VARCHAR(20) NOT NULL,
    decision VARCHAR(20) NOT NULL,
    notes TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_evaluation_reviews_evaluation ON evaluation_reviews(evaluation_id, decision);
CREATE INDEX IF NOT EXISTS idx_evaluation_reviews_reviewer ON evaluation_reviews(reviewer_id);
CREATE INDEX IF NOT EXISTS idx_evaluation_reviews_role ON evaluation_reviews(evaluation_id, reviewer_role);

-- 7. Create institutional_ledger_entries table
CREATE TABLE IF NOT EXISTS institutional_ledger_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    institution_id INTEGER NOT NULL REFERENCES institutions(id) ON DELETE RESTRICT,
    entity_type VARCHAR(20) NOT NULL,
    entity_id INTEGER NOT NULL,
    event_type VARCHAR(30) NOT NULL,
    event_data_json TEXT,
    event_hash VARCHAR(64) NOT NULL,
    previous_hash VARCHAR(64) NOT NULL,
    actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(event_hash)
);

CREATE INDEX IF NOT EXISTS idx_ledger_institution ON institutional_ledger_entries(institution_id, created_at);
CREATE INDEX IF NOT EXISTS idx_ledger_entity ON institutional_ledger_entries(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_ledger_event_type ON institutional_ledger_entries(event_type);
CREATE INDEX IF NOT EXISTS idx_ledger_previous_hash ON institutional_ledger_entries(previous_hash);

-- 8. Create institution_metrics table
CREATE TABLE IF NOT EXISTS institution_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    institution_id INTEGER NOT NULL REFERENCES institutions(id) ON DELETE RESTRICT,
    metric_date TIMESTAMP NOT NULL,
    freeze_attempts INTEGER NOT NULL DEFAULT 0,
    freeze_successes INTEGER NOT NULL DEFAULT 0,
    freeze_failures INTEGER NOT NULL DEFAULT 0,
    integrity_failures INTEGER NOT NULL DEFAULT 0,
    override_count INTEGER NOT NULL DEFAULT 0,
    concurrency_conflicts INTEGER NOT NULL DEFAULT 0,
    review_approvals INTEGER NOT NULL DEFAULT 0,
    review_rejections INTEGER NOT NULL DEFAULT 0,
    review_modifications INTEGER NOT NULL DEFAULT 0,
    approval_grants INTEGER NOT NULL DEFAULT 0,
    approval_rejections INTEGER NOT NULL DEFAULT 0,
    publications INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(institution_id, metric_date)
);

CREATE INDEX IF NOT EXISTS idx_metrics_institution ON institution_metrics(institution_id, metric_date);

-- 9. Add new columns to session_leaderboard_snapshots
ALTER TABLE session_leaderboard_snapshots ADD COLUMN is_pending_approval BOOLEAN NOT NULL DEFAULT 0;
ALTER TABLE session_leaderboard_snapshots ADD COLUMN is_finalized BOOLEAN NOT NULL DEFAULT 0;
ALTER TABLE session_leaderboard_snapshots ADD COLUMN finalized_at TIMESTAMP;

ALTER TABLE session_leaderboard_snapshots ADD COLUMN publication_mode VARCHAR(20) NOT NULL DEFAULT 'draft';
ALTER TABLE session_leaderboard_snapshots ADD COLUMN publication_date TIMESTAMP;
ALTER TABLE session_leaderboard_snapshots ADD COLUMN is_published BOOLEAN NOT NULL DEFAULT 0;
ALTER TABLE session_leaderboard_snapshots ADD COLUMN published_at TIMESTAMP;
ALTER TABLE session_leaderboard_snapshots ADD COLUMN published_by INTEGER REFERENCES users(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_snapshots_finalized ON session_leaderboard_snapshots(is_finalized);
CREATE INDEX IF NOT EXISTS idx_snapshots_published ON session_leaderboard_snapshots(is_published);
CREATE INDEX IF NOT EXISTS idx_snapshots_pub_mode ON session_leaderboard_snapshots(publication_mode);

-- 10. Add evaluation_epoch to ai_evaluations
ALTER TABLE ai_evaluations ADD COLUMN evaluation_epoch INTEGER NOT NULL DEFAULT 0;
CREATE INDEX IF NOT EXISTS idx_evaluations_epoch ON ai_evaluations(evaluation_epoch);
"""

# PostgreSQL Migration SQL
POSTGRESQL_MIGRATION = """
-- =====================================================
-- Phase 6: Institutional Governance Layer
-- =====================================================

-- 1. Create institutions table
CREATE TABLE IF NOT EXISTS institutions (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL UNIQUE,
    slug VARCHAR(50) NOT NULL UNIQUE,
    accreditation_body VARCHAR(200),
    accreditation_number VARCHAR(100),
    compliance_mode VARCHAR(20) NOT NULL DEFAULT 'standard',
    settings_json TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deactivated_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_institutions_slug ON institutions(slug);
CREATE INDEX IF NOT EXISTS idx_institutions_compliance ON institutions(compliance_mode);
CREATE INDEX IF NOT EXISTS idx_institutions_active ON institutions(is_active);

-- 2. Create academic_years table
CREATE TABLE IF NOT EXISTS academic_years (
    id SERIAL PRIMARY KEY,
    institution_id INTEGER NOT NULL REFERENCES institutions(id) ON DELETE RESTRICT,
    label VARCHAR(50) NOT NULL,
    start_date TIMESTAMP NOT NULL,
    end_date TIMESTAMP NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(institution_id, label)
);

CREATE INDEX IF NOT EXISTS idx_academic_years_institution ON academic_years(institution_id);
CREATE INDEX IF NOT EXISTS idx_academic_years_dates ON academic_years(start_date, end_date);

-- 3. Create session_policy_profiles table
CREATE TABLE IF NOT EXISTS session_policy_profiles (
    id SERIAL PRIMARY KEY,
    institution_id INTEGER NOT NULL REFERENCES institutions(id) ON DELETE RESTRICT,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    allow_overrides_after_freeze BOOLEAN NOT NULL DEFAULT FALSE,
    require_dual_faculty_validation BOOLEAN NOT NULL DEFAULT FALSE,
    require_external_examiner BOOLEAN NOT NULL DEFAULT FALSE,
    freeze_requires_all_rounds BOOLEAN NOT NULL DEFAULT TRUE,
    auto_freeze_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    ranking_visibility_mode VARCHAR(20) NOT NULL DEFAULT 'faculty_only',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(institution_id, name)
);

CREATE INDEX IF NOT EXISTS idx_policy_profiles_institution ON session_policy_profiles(institution_id);

-- 4. Create course_instances table
CREATE TABLE IF NOT EXISTS course_instances (
    id SERIAL PRIMARY KEY,
    academic_year_id INTEGER NOT NULL REFERENCES academic_years(id) ON DELETE RESTRICT,
    subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE RESTRICT,
    faculty_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    policy_profile_id INTEGER NOT NULL REFERENCES session_policy_profiles(id) ON DELETE RESTRICT,
    section VARCHAR(20),
    capacity INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(academic_year_id, subject_id, section)
);

CREATE INDEX IF NOT EXISTS idx_course_instances_year ON course_instances(academic_year_id);
CREATE INDEX IF NOT EXISTS idx_course_instances_faculty ON course_instances(faculty_id);
CREATE INDEX IF NOT EXISTS idx_course_instances_policy ON course_instances(policy_profile_id);

-- 5. Create session_approvals table
CREATE TABLE IF NOT EXISTS session_approvals (
    id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES classroom_sessions(id) ON DELETE RESTRICT,
    required_role VARCHAR(20) NOT NULL,
    approved_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    approved_at TIMESTAMP,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    notes TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_session_approvals_session ON session_approvals(session_id, status);
CREATE INDEX IF NOT EXISTS idx_session_approvals_required_role ON session_approvals(session_id, required_role, status);
CREATE INDEX IF NOT EXISTS idx_session_approvals_approved_by ON session_approvals(approved_by);

-- 6. Create evaluation_reviews table
CREATE TABLE IF NOT EXISTS evaluation_reviews (
    id SERIAL PRIMARY KEY,
    evaluation_id INTEGER NOT NULL REFERENCES ai_evaluations(id) ON DELETE RESTRICT,
    reviewer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    reviewer_role VARCHAR(20) NOT NULL,
    decision VARCHAR(20) NOT NULL,
    notes TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_evaluation_reviews_evaluation ON evaluation_reviews(evaluation_id, decision);
CREATE INDEX IF NOT EXISTS idx_evaluation_reviews_reviewer ON evaluation_reviews(reviewer_id);
CREATE INDEX IF NOT EXISTS idx_evaluation_reviews_role ON evaluation_reviews(evaluation_id, reviewer_role);

-- 7. Create institutional_ledger_entries table
CREATE TABLE IF NOT EXISTS institutional_ledger_entries (
    id SERIAL PRIMARY KEY,
    institution_id INTEGER NOT NULL REFERENCES institutions(id) ON DELETE RESTRICT,
    entity_type VARCHAR(20) NOT NULL,
    entity_id INTEGER NOT NULL,
    event_type VARCHAR(30) NOT NULL,
    event_data_json TEXT,
    event_hash VARCHAR(64) NOT NULL UNIQUE,
    previous_hash VARCHAR(64) NOT NULL,
    actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ledger_institution ON institutional_ledger_entries(institution_id, created_at);
CREATE INDEX IF NOT EXISTS idx_ledger_entity ON institutional_ledger_entries(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_ledger_event_type ON institutional_ledger_entries(event_type);
CREATE INDEX IF NOT EXISTS idx_ledger_previous_hash ON institutional_ledger_entries(previous_hash);

-- 8. Create institution_metrics table
CREATE TABLE IF NOT EXISTS institution_metrics (
    id SERIAL PRIMARY KEY,
    institution_id INTEGER NOT NULL REFERENCES institutions(id) ON DELETE RESTRICT,
    metric_date TIMESTAMP NOT NULL,
    freeze_attempts INTEGER NOT NULL DEFAULT 0,
    freeze_successes INTEGER NOT NULL DEFAULT 0,
    freeze_failures INTEGER NOT NULL DEFAULT 0,
    integrity_failures INTEGER NOT NULL DEFAULT 0,
    override_count INTEGER NOT NULL DEFAULT 0,
    concurrency_conflicts INTEGER NOT NULL DEFAULT 0,
    review_approvals INTEGER NOT NULL DEFAULT 0,
    review_rejections INTEGER NOT NULL DEFAULT 0,
    review_modifications INTEGER NOT NULL DEFAULT 0,
    approval_grants INTEGER NOT NULL DEFAULT 0,
    approval_rejections INTEGER NOT NULL DEFAULT 0,
    publications INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(institution_id, metric_date)
);

CREATE INDEX IF NOT EXISTS idx_metrics_institution ON institution_metrics(institution_id, metric_date);

-- 9. Add new columns to session_leaderboard_snapshots
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='session_leaderboard_snapshots' AND column_name='is_pending_approval') THEN
        ALTER TABLE session_leaderboard_snapshots ADD COLUMN is_pending_approval BOOLEAN NOT NULL DEFAULT FALSE;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='session_leaderboard_snapshots' AND column_name='is_finalized') THEN
        ALTER TABLE session_leaderboard_snapshots ADD COLUMN is_finalized BOOLEAN NOT NULL DEFAULT FALSE;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='session_leaderboard_snapshots' AND column_name='finalized_at') THEN
        ALTER TABLE session_leaderboard_snapshots ADD COLUMN finalized_at TIMESTAMP;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='session_leaderboard_snapshots' AND column_name='publication_mode') THEN
        ALTER TABLE session_leaderboard_snapshots ADD COLUMN publication_mode VARCHAR(20) NOT NULL DEFAULT 'draft';
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='session_leaderboard_snapshots' AND column_name='publication_date') THEN
        ALTER TABLE session_leaderboard_snapshots ADD COLUMN publication_date TIMESTAMP;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='session_leaderboard_snapshots' AND column_name='is_published') THEN
        ALTER TABLE session_leaderboard_snapshots ADD COLUMN is_published BOOLEAN NOT NULL DEFAULT FALSE;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='session_leaderboard_snapshots' AND column_name='published_at') THEN
        ALTER TABLE session_leaderboard_snapshots ADD COLUMN published_at TIMESTAMP;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='session_leaderboard_snapshots' AND column_name='published_by') THEN
        ALTER TABLE session_leaderboard_snapshots ADD COLUMN published_by INTEGER REFERENCES users(id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_snapshots_finalized ON session_leaderboard_snapshots(is_finalized);
CREATE INDEX IF NOT EXISTS idx_snapshots_published ON session_leaderboard_snapshots(is_published);
CREATE INDEX IF NOT EXISTS idx_snapshots_pub_mode ON session_leaderboard_snapshots(publication_mode);

-- 10. Add evaluation_epoch to ai_evaluations
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='ai_evaluations' AND column_name='evaluation_epoch') THEN
        ALTER TABLE ai_evaluations ADD COLUMN evaluation_epoch INTEGER NOT NULL DEFAULT 0;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_evaluations_epoch ON ai_evaluations(evaluation_epoch);

-- 11. Add rank integrity constraint if not exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_snapshot_rank_participant'
    ) THEN
        ALTER TABLE session_leaderboard_entries 
        ADD CONSTRAINT uq_snapshot_rank_participant 
        UNIQUE (snapshot_id, rank, participant_id);
    END IF;
END $$;
"""


# =============================================================================
# Migration Runner
# =============================================================================

async def detect_dialect(engine: AsyncEngine) -> str:
    """Detect database dialect (sqlite or postgresql)."""
    async with engine.connect() as conn:
        # Get the dialect name from the connection
        dialect = conn.dialect.name
        return dialect


async def run_migration(engine: AsyncEngine) -> None:
    """
    Run Phase 6 migration on the database.
    
    Args:
        engine: SQLAlchemy async engine
    """
    dialect = await detect_dialect(engine)
    
    logger.info(f"Starting Phase 6 migration for {dialect} database")
    
    # Select appropriate SQL
    if dialect == "sqlite":
        migration_sql = SQLITE_MIGRATION
    elif dialect == "postgresql":
        migration_sql = POSTGRESQL_MIGRATION
    else:
        raise ValueError(f"Unsupported database dialect: {dialect}")
    
    # Execute migration
    async with engine.begin() as conn:
        # Split and execute statements
        statements = [s.strip() for s in migration_sql.split(';') if s.strip()]
        
        for statement in statements:
            # Skip empty statements and DO blocks (for PostgreSQL)
            if not statement or statement.startswith('--'):
                continue
                
            try:
                await conn.execute(text(statement))
                logger.debug(f"Executed: {statement[:50]}...")
            except Exception as e:
                # Log but don't fail on index creation errors (may already exist)
                if "CREATE INDEX" in statement:
                    logger.warning(f"Index may already exist: {e}")
                else:
                    logger.error(f"Migration error: {e}")
                    raise
    
    logger.info("Phase 6 migration completed successfully")


async def verify_migration(engine: AsyncEngine) -> dict:
    """
    Verify that all Phase 6 tables and columns exist.
    
    Returns:
        Dict with verification results
    """
    expected_tables = [
        'institutions',
        'academic_years',
        'session_policy_profiles',
        'course_instances',
        'session_approvals',
        'evaluation_reviews',
        'institutional_ledger_entries',
        'institution_metrics'
    ]
    
    results = {
        'tables_created': [],
        'tables_missing': [],
        'new_columns_added': [],
        'status': 'unknown'
    }
    
    async with engine.connect() as conn:
        # Get list of existing tables
        if engine.dialect.name == "sqlite":
            result = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
            existing_tables = {row[0] for row in result.fetchall()}
        else:  # postgresql
            result = await conn.execute(text(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
            ))
            existing_tables = {row[0] for row in result.fetchall()}
        
        # Check each expected table
        for table in expected_tables:
            if table in existing_tables:
                results['tables_created'].append(table)
            else:
                results['tables_missing'].append(table)
        
        # Check for new columns in session_leaderboard_snapshots
        snapshot_columns = ['is_pending_approval', 'is_finalized', 'publication_mode', 'is_published']
        
        for col in snapshot_columns:
            if engine.dialect.name == "sqlite":
                try:
                    result = await conn.execute(text(
                        f"SELECT {col} FROM session_leaderboard_snapshots LIMIT 1"
                    ))
                    results['new_columns_added'].append(col)
                except Exception:
                    pass
            else:  # postgresql
                result = await conn.execute(text(
                    f"SELECT 1 FROM information_schema.columns WHERE table_name='session_leaderboard_snapshots' AND column_name='{col}'"
                ))
                if result.scalar():
                    results['new_columns_added'].append(col)
        
        # Check evaluation_epoch column
        if engine.dialect.name == "sqlite":
            try:
                result = await conn.execute(text(
                    "SELECT evaluation_epoch FROM ai_evaluations LIMIT 1"
                ))
                results['new_columns_added'].append('evaluation_epoch')
            except Exception:
                pass
        else:  # postgresql
            result = await conn.execute(text(
                "SELECT 1 FROM information_schema.columns WHERE table_name='ai_evaluations' AND column_name='evaluation_epoch'"
            ))
            if result.scalar():
                results['new_columns_added'].append('evaluation_epoch')
    
    # Determine overall status
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
            print("Phase 6 Migration Verification")
            print(f"{'='*60}")
            print(f"Status: {results['status'].upper()}")
            print(f"\nTables Created: {len(results['tables_created'])}")
            for table in results['tables_created']:
                print(f"  ✓ {table}")
            
            if results['tables_missing']:
                print(f"\nTables Missing: {len(results['tables_missing'])}")
                for table in results['tables_missing']:
                    print(f"  ✗ {table}")
            
            print(f"\nNew Columns Added: {len(results['new_columns_added'])}")
            for col in results['new_columns_added']:
                print(f"  ✓ {col}")
            
            print(f"{'='*60}")
            
            if results['status'] == 'success':
                print("\n✅ Phase 6 migration completed successfully!")
                sys.exit(0)
            else:
                print("\n⚠️  Phase 6 migration partially completed. Check logs.")
                sys.exit(1)
                
        except Exception as e:
            logger.exception("Migration failed")
            print(f"\n❌ Migration failed: {e}")
            sys.exit(1)
    
    asyncio.run(main())
