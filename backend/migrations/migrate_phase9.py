"""
Phase 9 Database Migration Script

Creates all tables for AI Performance Intelligence & Recruiter Signal Layer.

Supports:
- SQLite (for development)
- PostgreSQL (for production)

Usage:
    python -m backend.migrations.migrate_phase9

Or import and call:
    from backend.migrations.migrate_phase9 import run_migration
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
-- Phase 9: AI Performance Intelligence & Recruiter Signal Layer
-- =====================================================

-- 1. Create candidate_skill_vectors table
CREATE TABLE IF NOT EXISTS candidate_skill_vectors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    institution_id INTEGER NOT NULL REFERENCES institutions(id) ON DELETE RESTRICT,
    
    oral_advocacy_score NUMERIC(5,2) NOT NULL,
    statutory_interpretation_score NUMERIC(5,2) NOT NULL,
    case_law_application_score NUMERIC(5,2) NOT NULL,
    procedural_compliance_score NUMERIC(5,2) NOT NULL,
    rebuttal_responsiveness_score NUMERIC(5,2) NOT NULL,
    courtroom_etiquette_score NUMERIC(5,2) NOT NULL,
    
    consistency_factor NUMERIC(5,2) NOT NULL,
    confidence_index NUMERIC(5,2) NOT NULL,
    total_sessions_analyzed INTEGER NOT NULL,
    
    last_updated_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(user_id)
);

-- Indexes for candidate_skill_vectors
CREATE INDEX IF NOT EXISTS idx_candidate_skill_institution ON candidate_skill_vectors(institution_id);
CREATE INDEX IF NOT EXISTS idx_candidate_skill_composite ON candidate_skill_vectors(oral_advocacy_score, statutory_interpretation_score);

-- 2. Create performance_normalization_stats table
CREATE TABLE IF NOT EXISTS performance_normalization_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    institution_id INTEGER NOT NULL REFERENCES institutions(id) ON DELETE RESTRICT,
    metric_name VARCHAR(100) NOT NULL,
    mean_value NUMERIC(10,4) NOT NULL,
    std_deviation NUMERIC(10,4) NOT NULL,
    sample_size INTEGER NOT NULL,
    computed_at TIMESTAMP NOT NULL,
    
    UNIQUE(institution_id, metric_name)
);

-- Indexes for performance_normalization_stats
CREATE INDEX IF NOT EXISTS idx_normalization_institution ON performance_normalization_stats(institution_id, computed_at);

-- 3. Create national_candidate_rankings table
CREATE TABLE IF NOT EXISTS national_candidate_rankings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    academic_year_id INTEGER NOT NULL REFERENCES academic_years(id) ON DELETE RESTRICT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    
    composite_score NUMERIC(10,4) NOT NULL,
    national_rank INTEGER NOT NULL,
    percentile NUMERIC(6,3) NOT NULL,
    
    tournaments_participated INTEGER NOT NULL DEFAULT 0,
    checksum VARCHAR(64) NOT NULL,
    
    computed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_final BOOLEAN NOT NULL DEFAULT 0,
    
    UNIQUE(academic_year_id, user_id)
);

-- Indexes for national_candidate_rankings
CREATE INDEX IF NOT EXISTS idx_national_rank ON national_candidate_rankings(academic_year_id, national_rank);
CREATE INDEX IF NOT EXISTS idx_national_ranking_user ON national_candidate_rankings(user_id, academic_year_id);

-- 4. Create recruiter_access_logs table
CREATE TABLE IF NOT EXISTS recruiter_access_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recruiter_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    candidate_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    access_type VARCHAR(40) NOT NULL,
    accessed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for recruiter_access_logs
CREATE INDEX IF NOT EXISTS idx_recruiter_access_recruiter ON recruiter_access_logs(recruiter_user_id, accessed_at);
CREATE INDEX IF NOT EXISTS idx_recruiter_access_candidate ON recruiter_access_logs(candidate_user_id, accessed_at);
CREATE INDEX IF NOT EXISTS idx_recruiter_access_type ON recruiter_access_logs(access_type, accessed_at);

-- 5. Create fairness_audit_logs table
CREATE TABLE IF NOT EXISTS fairness_audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    institution_id INTEGER NOT NULL REFERENCES institutions(id) ON DELETE RESTRICT,
    metric_name VARCHAR(100),
    anomaly_score NUMERIC(6,3),
    flagged BOOLEAN NOT NULL DEFAULT 0,
    details_json TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for fairness_audit_logs
CREATE INDEX IF NOT EXISTS idx_fairness_audit_institution ON fairness_audit_logs(institution_id, created_at);
CREATE INDEX IF NOT EXISTS idx_fairness_audit_flagged ON fairness_audit_logs(flagged, anomaly_score);
"""

# PostgreSQL Migration SQL
POSTGRESQL_MIGRATION = """
-- =====================================================
-- Phase 9: AI Performance Intelligence & Recruiter Signal Layer
-- =====================================================

-- 1. Create candidate_skill_vectors table
CREATE TABLE IF NOT EXISTS candidate_skill_vectors (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    institution_id INTEGER NOT NULL REFERENCES institutions(id) ON DELETE RESTRICT,
    
    oral_advocacy_score NUMERIC(5,2) NOT NULL,
    statutory_interpretation_score NUMERIC(5,2) NOT NULL,
    case_law_application_score NUMERIC(5,2) NOT NULL,
    procedural_compliance_score NUMERIC(5,2) NOT NULL,
    rebuttal_responsiveness_score NUMERIC(5,2) NOT NULL,
    courtroom_etiquette_score NUMERIC(5,2) NOT NULL,
    
    consistency_factor NUMERIC(5,2) NOT NULL,
    confidence_index NUMERIC(5,2) NOT NULL,
    total_sessions_analyzed INTEGER NOT NULL,
    
    last_updated_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(user_id)
);

-- Indexes for candidate_skill_vectors
CREATE INDEX IF NOT EXISTS idx_candidate_skill_institution ON candidate_skill_vectors(institution_id);
CREATE INDEX IF NOT EXISTS idx_candidate_skill_composite ON candidate_skill_vectors(oral_advocacy_score, statutory_interpretation_score);

-- 2. Create performance_normalization_stats table
CREATE TABLE IF NOT EXISTS performance_normalization_stats (
    id SERIAL PRIMARY KEY,
    institution_id INTEGER NOT NULL REFERENCES institutions(id) ON DELETE RESTRICT,
    metric_name VARCHAR(100) NOT NULL,
    mean_value NUMERIC(10,4) NOT NULL,
    std_deviation NUMERIC(10,4) NOT NULL,
    sample_size INTEGER NOT NULL,
    computed_at TIMESTAMP NOT NULL,
    
    UNIQUE(institution_id, metric_name)
);

-- Indexes for performance_normalization_stats
CREATE INDEX IF NOT EXISTS idx_normalization_institution ON performance_normalization_stats(institution_id, computed_at);

-- 3. Create national_candidate_rankings table
CREATE TABLE IF NOT EXISTS national_candidate_rankings (
    id SERIAL PRIMARY KEY,
    academic_year_id INTEGER NOT NULL REFERENCES academic_years(id) ON DELETE RESTRICT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    
    composite_score NUMERIC(10,4) NOT NULL,
    national_rank INTEGER NOT NULL,
    percentile NUMERIC(6,3) NOT NULL,
    
    tournaments_participated INTEGER NOT NULL DEFAULT 0,
    checksum VARCHAR(64) NOT NULL,
    
    computed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_final BOOLEAN NOT NULL DEFAULT FALSE,
    
    UNIQUE(academic_year_id, user_id)
);

-- Indexes for national_candidate_rankings
CREATE INDEX IF NOT EXISTS idx_national_rank ON national_candidate_rankings(academic_year_id, national_rank);
CREATE INDEX IF NOT EXISTS idx_national_ranking_user ON national_candidate_rankings(user_id, academic_year_id);

-- 4. Create recruiter_access_logs table
CREATE TABLE IF NOT EXISTS recruiter_access_logs (
    id SERIAL PRIMARY KEY,
    recruiter_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    candidate_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    access_type VARCHAR(40) NOT NULL,
    accessed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for recruiter_access_logs
CREATE INDEX IF NOT EXISTS idx_recruiter_access_recruiter ON recruiter_access_logs(recruiter_user_id, accessed_at);
CREATE INDEX IF NOT EXISTS idx_recruiter_access_candidate ON recruiter_access_logs(candidate_user_id, accessed_at);
CREATE INDEX IF NOT EXISTS idx_recruiter_access_type ON recruiter_access_logs(access_type, accessed_at);

-- 5. Create fairness_audit_logs table
CREATE TABLE IF NOT EXISTS fairness_audit_logs (
    id SERIAL PRIMARY KEY,
    institution_id INTEGER NOT NULL REFERENCES institutions(id) ON DELETE RESTRICT,
    metric_name VARCHAR(100),
    anomaly_score NUMERIC(6,3),
    flagged BOOLEAN NOT NULL DEFAULT FALSE,
    details_json JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for fairness_audit_logs
CREATE INDEX IF NOT EXISTS idx_fairness_audit_institution ON fairness_audit_logs(institution_id, created_at);
CREATE INDEX IF NOT EXISTS idx_fairness_audit_flagged ON fairness_audit_logs(flagged, anomaly_score);
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
    Run Phase 9 migration on the database.
    
    Args:
        engine: SQLAlchemy async engine
    """
    dialect = await detect_dialect(engine)
    
    logger.info(f"Starting Phase 9 migration for {dialect} database")
    
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
                if "CREATE INDEX" in statement or "UNIQUE" in statement:
                    logger.warning(f"Index/constraint may already exist: {e}")
                elif "already exists" in str(e).lower():
                    logger.warning(f"Table already exists: {e}")
                else:
                    logger.error(f"Migration error: {e}")
                    raise
    
    logger.info("Phase 9 migration completed successfully")


async def verify_migration(engine: AsyncEngine) -> Dict[str, Any]:
    """
    Verify that all Phase 9 tables exist.
    
    Returns:
        Dict with verification results
    """
    expected_tables = [
        'candidate_skill_vectors',
        'performance_normalization_stats',
        'national_candidate_rankings',
        'recruiter_access_logs',
        'fairness_audit_logs'
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
            print("Phase 9 Migration Verification")
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
                print("\n✅ Phase 9 migration completed successfully!")
                print("\nAI Performance Intelligence Layer is ready for use.")
                print("\nNext steps:")
                print("  1. Compute skill vectors: compute_candidate_skill_vector()")
                print("  2. Compute normalization: compute_normalization_stats()")
                print("  3. Compute rankings: compute_national_rankings()")
                sys.exit(0)
            else:
                print("\n⚠️  Phase 9 migration partially completed. Check logs.")
                sys.exit(1)
                
        except Exception as e:
            logger.exception("Migration failed")
            print(f"\n❌ Migration failed: {e}")
            sys.exit(1)
    
    asyncio.run(main())
