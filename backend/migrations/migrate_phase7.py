"""
Phase 7 Database Migration Script

Creates all tables, columns, and indexes for the National Moot Network Layer.

Supports:
- SQLite (for development)
- PostgreSQL (for production)

Usage:
    python -m backend.migrations.migrate_phase7

Or import and call:
    from backend.migrations.migrate_phase7 import run_migration
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
-- Phase 7: National Moot Network Layer
-- =====================================================

-- 1. Create national_tournaments table
CREATE TABLE IF NOT EXISTS national_tournaments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    host_institution_id INTEGER NOT NULL REFERENCES institutions(id) ON DELETE RESTRICT,
    name VARCHAR(200) NOT NULL,
    slug VARCHAR(50) NOT NULL UNIQUE,
    description TEXT,
    format VARCHAR(20) NOT NULL DEFAULT 'swiss',
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    registration_opens_at TIMESTAMP NOT NULL,
    registration_closes_at TIMESTAMP NOT NULL,
    tournament_starts_at TIMESTAMP NOT NULL,
    tournament_ends_at TIMESTAMP,
    max_teams_per_institution INTEGER NOT NULL DEFAULT 2,
    total_rounds INTEGER NOT NULL DEFAULT 5,
    teams_advance_to_knockout INTEGER NOT NULL DEFAULT 8,
    preliminary_round_weight NUMERIC(5,4) NOT NULL DEFAULT 1.0,
    knockout_round_weight NUMERIC(5,4) NOT NULL DEFAULT 1.5,
    created_by INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tournaments_slug ON national_tournaments(slug);
CREATE INDEX IF NOT EXISTS idx_tournaments_host ON national_tournaments(host_institution_id, status);
CREATE INDEX IF NOT EXISTS idx_tournaments_status ON national_tournaments(status, tournament_starts_at);

-- 2. Create tournament_institutions table
CREATE TABLE IF NOT EXISTS tournament_institutions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL REFERENCES national_tournaments(id) ON DELETE RESTRICT,
    institution_id INTEGER NOT NULL REFERENCES institutions(id) ON DELETE RESTRICT,
    is_invited BOOLEAN NOT NULL DEFAULT 1,
    invited_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    invited_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    is_accepted BOOLEAN NOT NULL DEFAULT 0,
    accepted_at TIMESTAMP,
    accepted_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    max_teams_allowed INTEGER NOT NULL DEFAULT 2,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tournament_id, institution_id)
);

CREATE INDEX IF NOT EXISTS idx_tournament_institutions_tournament ON tournament_institutions(tournament_id);
CREATE INDEX IF NOT EXISTS idx_tournament_institutions_institution ON tournament_institutions(institution_id);
CREATE INDEX IF NOT EXISTS idx_tournament_institutions_accepted ON tournament_institutions(tournament_id, is_accepted);

-- 3. Create tournament_teams table
CREATE TABLE IF NOT EXISTS tournament_teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL REFERENCES national_tournaments(id) ON DELETE RESTRICT,
    institution_id INTEGER NOT NULL REFERENCES institutions(id) ON DELETE RESTRICT,
    team_name VARCHAR(200) NOT NULL,
    members_json TEXT,
    seed_number INTEGER,
    wins INTEGER NOT NULL DEFAULT 0,
    losses INTEGER NOT NULL DEFAULT 0,
    draws INTEGER NOT NULL DEFAULT 0,
    total_score NUMERIC(10,4) NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    is_eliminated BOOLEAN NOT NULL DEFAULT 0,
    bracket_position INTEGER,
    registered_by INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    registered_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tournament_id, team_name)
);

CREATE INDEX IF NOT EXISTS idx_tournament_teams_tournament ON tournament_teams(tournament_id, is_active);
CREATE INDEX IF NOT EXISTS idx_tournament_teams_institution ON tournament_teams(institution_id);
CREATE INDEX IF NOT EXISTS idx_tournament_teams_ranking ON tournament_teams(tournament_id, total_score);

-- 4. Create tournament_rounds table
CREATE TABLE IF NOT EXISTS tournament_rounds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL REFERENCES national_tournaments(id) ON DELETE RESTRICT,
    round_number INTEGER NOT NULL,
    round_name VARCHAR(100) NOT NULL,
    is_knockout BOOLEAN NOT NULL DEFAULT 0,
    is_preliminary BOOLEAN NOT NULL DEFAULT 1,
    scheduled_at TIMESTAMP NOT NULL,
    is_finalized BOOLEAN NOT NULL DEFAULT 0,
    finalized_at TIMESTAMP,
    finalized_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tournament_id, round_number)
);

CREATE INDEX IF NOT EXISTS idx_tournament_rounds_tournament ON tournament_rounds(tournament_id, round_number);
CREATE INDEX IF NOT EXISTS idx_tournament_rounds_finalized ON tournament_rounds(tournament_id, is_finalized);

-- 5. Create tournament_matches table
CREATE TABLE IF NOT EXISTS tournament_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id INTEGER NOT NULL REFERENCES tournament_rounds(id) ON DELETE RESTRICT,
    tournament_id INTEGER NOT NULL REFERENCES national_tournaments(id) ON DELETE RESTRICT,
    petitioner_team_id INTEGER NOT NULL REFERENCES tournament_teams(id) ON DELETE RESTRICT,
    respondent_team_id INTEGER NOT NULL REFERENCES tournament_teams(id) ON DELETE RESTRICT,
    winner_team_id INTEGER REFERENCES tournament_teams(id) ON DELETE RESTRICT,
    is_draw BOOLEAN NOT NULL DEFAULT 0,
    petitioner_score NUMERIC(10,4),
    respondent_score NUMERIC(10,4),
    panel_id INTEGER REFERENCES cross_institution_panels(id) ON DELETE RESTRICT,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    scheduled_at TIMESTAMP,
    venue VARCHAR(200),
    submission_idempotency_key VARCHAR(64) UNIQUE,
    submitted_at TIMESTAMP,
    submitted_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    finalized_at TIMESTAMP,
    finalized_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    notes TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tournament_matches_round ON tournament_matches(round_id, status);
CREATE INDEX IF NOT EXISTS idx_tournament_matches_tournament ON tournament_matches(tournament_id, status);
CREATE INDEX IF NOT EXISTS idx_tournament_matches_petitioner ON tournament_matches(petitioner_team_id);
CREATE INDEX IF NOT EXISTS idx_tournament_matches_respondent ON tournament_matches(respondent_team_id);
CREATE INDEX IF NOT EXISTS idx_tournament_matches_panel ON tournament_matches(panel_id);
CREATE INDEX IF NOT EXISTS idx_tournament_matches_winner ON tournament_matches(winner_team_id);
CREATE INDEX IF NOT EXISTS idx_tournament_matches_idempotency ON tournament_matches(submission_idempotency_key);

-- 6. Create cross_institution_panels table
CREATE TABLE IF NOT EXISTS cross_institution_panels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL REFERENCES national_tournaments(id) ON DELETE RESTRICT,
    panel_name VARCHAR(100) NOT NULL,
    require_mixed_institutions BOOLEAN NOT NULL DEFAULT 1,
    min_institutions_represented INTEGER NOT NULL DEFAULT 2,
    created_by INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cross_institution_panels_tournament ON cross_institution_panels(tournament_id);

-- 7. Create panel_judges table
CREATE TABLE IF NOT EXISTS panel_judges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    panel_id INTEGER NOT NULL REFERENCES cross_institution_panels(id) ON DELETE RESTRICT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    institution_id INTEGER NOT NULL REFERENCES institutions(id) ON DELETE RESTRICT,
    role VARCHAR(20) NOT NULL DEFAULT 'member',
    is_available BOOLEAN NOT NULL DEFAULT 1,
    assigned_matches_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(panel_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_panel_judges_panel ON panel_judges(panel_id, role);
CREATE INDEX IF NOT EXISTS idx_panel_judges_user ON panel_judges(user_id);
CREATE INDEX IF NOT EXISTS idx_panel_judges_institution ON panel_judges(institution_id);

-- 8. Create tournament_evaluations table
CREATE TABLE IF NOT EXISTS tournament_evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL REFERENCES tournament_matches(id) ON DELETE RESTRICT,
    tournament_id INTEGER NOT NULL REFERENCES national_tournaments(id) ON DELETE RESTRICT,
    judge_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    judge_institution_id INTEGER NOT NULL REFERENCES institutions(id) ON DELETE RESTRICT,
    team_id INTEGER NOT NULL REFERENCES tournament_teams(id) ON DELETE RESTRICT,
    side VARCHAR(20) NOT NULL,
    legal_argument_score NUMERIC(5,4) NOT NULL,
    presentation_score NUMERIC(5,4) NOT NULL,
    rebuttal_score NUMERIC(5,4) NOT NULL,
    procedural_compliance_score NUMERIC(5,4) NOT NULL,
    total_score NUMERIC(10,4) NOT NULL,
    weighted_contribution NUMERIC(10,4) NOT NULL,
    ai_evaluation_id INTEGER REFERENCES ai_evaluations(id) ON DELETE RESTRICT,
    comments TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tournament_evaluations_match ON tournament_evaluations(match_id, team_id);
CREATE INDEX IF NOT EXISTS idx_tournament_evaluations_judge ON tournament_evaluations(judge_id);
CREATE INDEX IF NOT EXISTS idx_tournament_evaluations_team ON tournament_evaluations(team_id);
CREATE INDEX IF NOT EXISTS idx_tournament_evaluations_tournament ON tournament_evaluations(tournament_id);

-- 9. Create national_team_rankings table
CREATE TABLE IF NOT EXISTS national_team_rankings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL REFERENCES national_tournaments(id) ON DELETE RESTRICT,
    round_id INTEGER REFERENCES tournament_rounds(id) ON DELETE RESTRICT,
    is_final BOOLEAN NOT NULL DEFAULT 0,
    computed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    computed_by INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    rankings_json TEXT NOT NULL,
    checksum VARCHAR(64) NOT NULL,
    is_finalized BOOLEAN NOT NULL DEFAULT 0,
    finalized_at TIMESTAMP,
    finalized_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_national_rankings_tournament ON national_team_rankings(tournament_id, is_final);
CREATE INDEX IF NOT EXISTS idx_national_rankings_round ON national_team_rankings(round_id);
CREATE INDEX IF NOT EXISTS idx_national_rankings_finalized ON national_team_rankings(tournament_id, is_finalized);

-- 10. Create national_ledger_entries table
CREATE TABLE IF NOT EXISTS national_ledger_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL REFERENCES national_tournaments(id) ON DELETE RESTRICT,
    event_type VARCHAR(30) NOT NULL,
    entity_type VARCHAR(30) NOT NULL,
    entity_id INTEGER NOT NULL,
    event_data_json TEXT,
    event_hash VARCHAR(64) NOT NULL UNIQUE,
    previous_hash VARCHAR(64) NOT NULL,
    actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    institution_id INTEGER NOT NULL REFERENCES institutions(id) ON DELETE RESTRICT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_national_ledger_tournament ON national_ledger_entries(tournament_id, created_at);
CREATE INDEX IF NOT EXISTS idx_national_ledger_entity ON national_ledger_entries(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_national_ledger_event_type ON national_ledger_entries(event_type);
CREATE INDEX IF NOT EXISTS idx_national_ledger_previous_hash ON national_ledger_entries(previous_hash);
CREATE INDEX IF NOT EXISTS idx_national_ledger_institution ON national_ledger_entries(institution_id);
"""

# PostgreSQL Migration SQL
POSTGRESQL_MIGRATION = """
-- =====================================================
-- Phase 7: National Moot Network Layer
-- =====================================================

-- 1. Create national_tournaments table
CREATE TABLE IF NOT EXISTS national_tournaments (
    id SERIAL PRIMARY KEY,
    host_institution_id INTEGER NOT NULL REFERENCES institutions(id) ON DELETE RESTRICT,
    name VARCHAR(200) NOT NULL,
    slug VARCHAR(50) NOT NULL UNIQUE,
    description TEXT,
    format VARCHAR(20) NOT NULL DEFAULT 'swiss',
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    registration_opens_at TIMESTAMP NOT NULL,
    registration_closes_at TIMESTAMP NOT NULL,
    tournament_starts_at TIMESTAMP NOT NULL,
    tournament_ends_at TIMESTAMP,
    max_teams_per_institution INTEGER NOT NULL DEFAULT 2,
    total_rounds INTEGER NOT NULL DEFAULT 5,
    teams_advance_to_knockout INTEGER NOT NULL DEFAULT 8,
    preliminary_round_weight NUMERIC(5,4) NOT NULL DEFAULT 1.0,
    knockout_round_weight NUMERIC(5,4) NOT NULL DEFAULT 1.5,
    created_by INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tournaments_slug ON national_tournaments(slug);
CREATE INDEX IF NOT EXISTS idx_tournaments_host ON national_tournaments(host_institution_id, status);
CREATE INDEX IF NOT EXISTS idx_tournaments_status ON national_tournaments(status, tournament_starts_at);

-- 2. Create tournament_institutions table
CREATE TABLE IF NOT EXISTS tournament_institutions (
    id SERIAL PRIMARY KEY,
    tournament_id INTEGER NOT NULL REFERENCES national_tournaments(id) ON DELETE RESTRICT,
    institution_id INTEGER NOT NULL REFERENCES institutions(id) ON DELETE RESTRICT,
    is_invited BOOLEAN NOT NULL DEFAULT TRUE,
    invited_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    invited_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    is_accepted BOOLEAN NOT NULL DEFAULT FALSE,
    accepted_at TIMESTAMP,
    accepted_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    max_teams_allowed INTEGER NOT NULL DEFAULT 2,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tournament_id, institution_id)
);

CREATE INDEX IF NOT EXISTS idx_tournament_institutions_tournament ON tournament_institutions(tournament_id);
CREATE INDEX IF NOT EXISTS idx_tournament_institutions_institution ON tournament_institutions(institution_id);
CREATE INDEX IF NOT EXISTS idx_tournament_institutions_accepted ON tournament_institutions(tournament_id, is_accepted);

-- 3. Create tournament_teams table
CREATE TABLE IF NOT EXISTS tournament_teams (
    id SERIAL PRIMARY KEY,
    tournament_id INTEGER NOT NULL REFERENCES national_tournaments(id) ON DELETE RESTRICT,
    institution_id INTEGER NOT NULL REFERENCES institutions(id) ON DELETE RESTRICT,
    team_name VARCHAR(200) NOT NULL,
    members_json TEXT,
    seed_number INTEGER,
    wins INTEGER NOT NULL DEFAULT 0,
    losses INTEGER NOT NULL DEFAULT 0,
    draws INTEGER NOT NULL DEFAULT 0,
    total_score NUMERIC(10,4) NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_eliminated BOOLEAN NOT NULL DEFAULT FALSE,
    bracket_position INTEGER,
    registered_by INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    registered_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tournament_id, team_name)
);

CREATE INDEX IF NOT EXISTS idx_tournament_teams_tournament ON tournament_teams(tournament_id, is_active);
CREATE INDEX IF NOT EXISTS idx_tournament_teams_institution ON tournament_teams(institution_id);
CREATE INDEX IF NOT EXISTS idx_tournament_teams_ranking ON tournament_teams(tournament_id, total_score);

-- 4. Create tournament_rounds table
CREATE TABLE IF NOT EXISTS tournament_rounds (
    id SERIAL PRIMARY KEY,
    tournament_id INTEGER NOT NULL REFERENCES national_tournaments(id) ON DELETE RESTRICT,
    round_number INTEGER NOT NULL,
    round_name VARCHAR(100) NOT NULL,
    is_knockout BOOLEAN NOT NULL DEFAULT FALSE,
    is_preliminary BOOLEAN NOT NULL DEFAULT TRUE,
    scheduled_at TIMESTAMP NOT NULL,
    is_finalized BOOLEAN NOT NULL DEFAULT FALSE,
    finalized_at TIMESTAMP,
    finalized_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tournament_id, round_number)
);

CREATE INDEX IF NOT EXISTS idx_tournament_rounds_tournament ON tournament_rounds(tournament_id, round_number);
CREATE INDEX IF NOT EXISTS idx_tournament_rounds_finalized ON tournament_rounds(tournament_id, is_finalized);

-- 5. Create tournament_matches table
CREATE TABLE IF NOT EXISTS tournament_matches (
    id SERIAL PRIMARY KEY,
    round_id INTEGER NOT NULL REFERENCES tournament_rounds(id) ON DELETE RESTRICT,
    tournament_id INTEGER NOT NULL REFERENCES national_tournaments(id) ON DELETE RESTRICT,
    petitioner_team_id INTEGER NOT NULL REFERENCES tournament_teams(id) ON DELETE RESTRICT,
    respondent_team_id INTEGER NOT NULL REFERENCES tournament_teams(id) ON DELETE RESTRICT,
    winner_team_id INTEGER REFERENCES tournament_teams(id) ON DELETE RESTRICT,
    is_draw BOOLEAN NOT NULL DEFAULT FALSE,
    petitioner_score NUMERIC(10,4),
    respondent_score NUMERIC(10,4),
    panel_id INTEGER REFERENCES cross_institution_panels(id) ON DELETE RESTRICT,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    scheduled_at TIMESTAMP,
    venue VARCHAR(200),
    submission_idempotency_key VARCHAR(64) UNIQUE,
    submitted_at TIMESTAMP,
    submitted_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    finalized_at TIMESTAMP,
    finalized_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    notes TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tournament_matches_round ON tournament_matches(round_id, status);
CREATE INDEX IF NOT EXISTS idx_tournament_matches_tournament ON tournament_matches(tournament_id, status);
CREATE INDEX IF NOT EXISTS idx_tournament_matches_petitioner ON tournament_matches(petitioner_team_id);
CREATE INDEX IF NOT EXISTS idx_tournament_matches_respondent ON tournament_matches(respondent_team_id);
CREATE INDEX IF NOT EXISTS idx_tournament_matches_panel ON tournament_matches(panel_id);
CREATE INDEX IF NOT EXISTS idx_tournament_matches_winner ON tournament_matches(winner_team_id);
CREATE INDEX IF NOT EXISTS idx_tournament_matches_idempotency ON tournament_matches(submission_idempotency_key);

-- 6. Create cross_institution_panels table
CREATE TABLE IF NOT EXISTS cross_institution_panels (
    id SERIAL PRIMARY KEY,
    tournament_id INTEGER NOT NULL REFERENCES national_tournaments(id) ON DELETE RESTRICT,
    panel_name VARCHAR(100) NOT NULL,
    require_mixed_institutions BOOLEAN NOT NULL DEFAULT TRUE,
    min_institutions_represented INTEGER NOT NULL DEFAULT 2,
    created_by INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cross_institution_panels_tournament ON cross_institution_panels(tournament_id);

-- 7. Create panel_judges table
CREATE TABLE IF NOT EXISTS panel_judges (
    id SERIAL PRIMARY KEY,
    panel_id INTEGER NOT NULL REFERENCES cross_institution_panels(id) ON DELETE RESTRICT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    institution_id INTEGER NOT NULL REFERENCES institutions(id) ON DELETE RESTRICT,
    role VARCHAR(20) NOT NULL DEFAULT 'member',
    is_available BOOLEAN NOT NULL DEFAULT TRUE,
    assigned_matches_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(panel_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_panel_judges_panel ON panel_judges(panel_id, role);
CREATE INDEX IF NOT EXISTS idx_panel_judges_user ON panel_judges(user_id);
CREATE INDEX IF NOT EXISTS idx_panel_judges_institution ON panel_judges(institution_id);

-- 8. Create tournament_evaluations table
CREATE TABLE IF NOT EXISTS tournament_evaluations (
    id SERIAL PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES tournament_matches(id) ON DELETE RESTRICT,
    tournament_id INTEGER NOT NULL REFERENCES national_tournaments(id) ON DELETE RESTRICT,
    judge_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    judge_institution_id INTEGER NOT NULL REFERENCES institutions(id) ON DELETE RESTRICT,
    team_id INTEGER NOT NULL REFERENCES tournament_teams(id) ON DELETE RESTRICT,
    side VARCHAR(20) NOT NULL,
    legal_argument_score NUMERIC(5,4) NOT NULL,
    presentation_score NUMERIC(5,4) NOT NULL,
    rebuttal_score NUMERIC(5,4) NOT NULL,
    procedural_compliance_score NUMERIC(5,4) NOT NULL,
    total_score NUMERIC(10,4) NOT NULL,
    weighted_contribution NUMERIC(10,4) NOT NULL,
    ai_evaluation_id INTEGER REFERENCES ai_evaluations(id) ON DELETE RESTRICT,
    comments TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tournament_evaluations_match ON tournament_evaluations(match_id, team_id);
CREATE INDEX IF NOT EXISTS idx_tournament_evaluations_judge ON tournament_evaluations(judge_id);
CREATE INDEX IF NOT EXISTS idx_tournament_evaluations_team ON tournament_evaluations(team_id);
CREATE INDEX IF NOT EXISTS idx_tournament_evaluations_tournament ON tournament_evaluations(tournament_id);

-- 9. Create national_team_rankings table
CREATE TABLE IF NOT EXISTS national_team_rankings (
    id SERIAL PRIMARY KEY,
    tournament_id INTEGER NOT NULL REFERENCES national_tournaments(id) ON DELETE RESTRICT,
    round_id INTEGER REFERENCES tournament_rounds(id) ON DELETE RESTRICT,
    is_final BOOLEAN NOT NULL DEFAULT FALSE,
    computed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    computed_by INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    rankings_json TEXT NOT NULL,
    checksum VARCHAR(64) NOT NULL,
    is_finalized BOOLEAN NOT NULL DEFAULT FALSE,
    finalized_at TIMESTAMP,
    finalized_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_national_rankings_tournament ON national_team_rankings(tournament_id, is_final);
CREATE INDEX IF NOT EXISTS idx_national_rankings_round ON national_team_rankings(round_id);
CREATE INDEX IF NOT EXISTS idx_national_rankings_finalized ON national_team_rankings(tournament_id, is_finalized);

-- 10. Create national_ledger_entries table
CREATE TABLE IF NOT EXISTS national_ledger_entries (
    id SERIAL PRIMARY KEY,
    tournament_id INTEGER NOT NULL REFERENCES national_tournaments(id) ON DELETE RESTRICT,
    event_type VARCHAR(30) NOT NULL,
    entity_type VARCHAR(30) NOT NULL,
    entity_id INTEGER NOT NULL,
    event_data_json TEXT,
    event_hash VARCHAR(64) NOT NULL UNIQUE,
    previous_hash VARCHAR(64) NOT NULL,
    actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    institution_id INTEGER NOT NULL REFERENCES institutions(id) ON DELETE RESTRICT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_national_ledger_tournament ON national_ledger_entries(tournament_id, created_at);
CREATE INDEX IF NOT EXISTS idx_national_ledger_entity ON national_ledger_entries(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_national_ledger_event_type ON national_ledger_entries(event_type);
CREATE INDEX IF NOT EXISTS idx_national_ledger_previous_hash ON national_ledger_entries(previous_hash);
CREATE INDEX IF NOT EXISTS idx_national_ledger_institution ON national_ledger_entries(institution_id);
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
    Run Phase 7 migration on the database.
    
    Args:
        engine: SQLAlchemy async engine
    """
    dialect = await detect_dialect(engine)
    
    logger.info(f"Starting Phase 7 migration for {dialect} database")
    
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
                if "CREATE INDEX" in statement:
                    logger.warning(f"Index may already exist: {e}")
                else:
                    logger.error(f"Migration error: {e}")
                    raise
    
    logger.info("Phase 7 migration completed successfully")


async def verify_migration(engine: AsyncEngine) -> dict:
    """
    Verify that all Phase 7 tables exist.
    
    Returns:
        Dict with verification results
    """
    expected_tables = [
        'national_tournaments',
        'tournament_institutions',
        'tournament_teams',
        'tournament_rounds',
        'tournament_matches',
        'cross_institution_panels',
        'panel_judges',
        'tournament_evaluations',
        'national_team_rankings',
        'national_ledger_entries'
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
            print("Phase 7 Migration Verification")
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
                print("\n✅ Phase 7 migration completed successfully!")
                sys.exit(0)
            else:
                print("\n⚠️  Phase 7 migration partially completed. Check logs.")
                sys.exit(1)
                
        except Exception as e:
            logger.exception("Migration failed")
            print(f"\n❌ Migration failed: {e}")
            sys.exit(1)
    
    asyncio.run(main())
