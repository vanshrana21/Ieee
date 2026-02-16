"""
Phase 3 — Hardened Round Pairing Engine Migration

Swiss + Knockout Pairing with:
- PostgreSQL ENUM types
- DB-level freeze immutability (triggers)
- Rematch protection (pairing_history table)
- All foreign keys use ON DELETE RESTRICT
"""
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import engine, Base, get_db
from sqlalchemy import text

# =============================================================================
# SQLite Migration (for development/testing)
# =============================================================================

SQLITE_MIGRATION = """
-- ENUMs as CHECK constraints in SQLite
CREATE TABLE IF NOT EXISTS tournament_rounds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL REFERENCES national_tournaments(id) ON DELETE RESTRICT,
    round_number INTEGER NOT NULL,
    round_type VARCHAR(10) NOT NULL CHECK(round_type IN ('swiss', 'knockout')),
    status VARCHAR(10) NOT NULL DEFAULT 'draft' CHECK(status IN ('draft', 'published', 'finalized')),
    pairing_checksum VARCHAR(64),
    published_at TIMESTAMP NULL,
    finalized_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(tournament_id, round_number)
);

CREATE INDEX IF NOT EXISTS idx_rounds_tournament ON tournament_rounds(tournament_id, status);

-- Round pairings
CREATE TABLE IF NOT EXISTS round_pairings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id INTEGER NOT NULL REFERENCES tournament_rounds(id) ON DELETE RESTRICT,
    petitioner_team_id INTEGER NOT NULL REFERENCES tournament_teams(id) ON DELETE RESTRICT,
    respondent_team_id INTEGER NOT NULL REFERENCES tournament_teams(id) ON DELETE RESTRICT,
    table_number INTEGER NOT NULL,
    pairing_hash VARCHAR(64) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(round_id, petitioner_team_id),
    UNIQUE(round_id, respondent_team_id),
    UNIQUE(round_id, table_number)
);

CREATE INDEX IF NOT EXISTS idx_pairings_round ON round_pairings(round_id);

-- Pairing history for rematch prevention
CREATE TABLE IF NOT EXISTS pairing_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL REFERENCES national_tournaments(id) ON DELETE RESTRICT,
    team_a_id INTEGER NOT NULL REFERENCES tournament_teams(id) ON DELETE RESTRICT,
    team_b_id INTEGER NOT NULL REFERENCES tournament_teams(id) ON DELETE RESTRICT,
    round_id INTEGER NOT NULL REFERENCES tournament_rounds(id) ON DELETE RESTRICT,
    
    UNIQUE(tournament_id, team_a_id, team_b_id)
);

-- Freeze table
CREATE TABLE IF NOT EXISTS round_freeze (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id INTEGER NOT NULL UNIQUE REFERENCES tournament_rounds(id) ON DELETE RESTRICT,
    pairing_snapshot_json TEXT NOT NULL DEFAULT '[]',
    round_checksum VARCHAR(64) NOT NULL,
    frozen_by INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    frozen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_freeze_round ON round_freeze(round_id);
"""

# =============================================================================
# PostgreSQL Migration (production)
# =============================================================================

POSTGRESQL_MIGRATION = """
-- ENUM types
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'roundtype') THEN
        CREATE TYPE roundtype AS ENUM ('swiss', 'knockout');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'roundstatus') THEN
        CREATE TYPE roundstatus AS ENUM ('draft', 'published', 'finalized');
    END IF;
END $$;

-- Tournament rounds table
CREATE TABLE IF NOT EXISTS tournament_rounds (
    id SERIAL PRIMARY KEY,
    tournament_id INTEGER NOT NULL REFERENCES national_tournaments(id) ON DELETE RESTRICT,
    round_number INTEGER NOT NULL,
    round_type roundtype NOT NULL,
    status roundstatus NOT NULL DEFAULT 'draft',
    pairing_checksum VARCHAR(64),
    published_at TIMESTAMP NULL,
    finalized_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(tournament_id, round_number)
);

CREATE INDEX IF NOT EXISTS idx_rounds_tournament ON tournament_rounds(tournament_id, status);

-- Round pairings table
CREATE TABLE IF NOT EXISTS round_pairings (
    id SERIAL PRIMARY KEY,
    round_id INTEGER NOT NULL REFERENCES tournament_rounds(id) ON DELETE RESTRICT,
    petitioner_team_id INTEGER NOT NULL REFERENCES tournament_teams(id) ON DELETE RESTRICT,
    respondent_team_id INTEGER NOT NULL REFERENCES tournament_teams(id) ON DELETE RESTRICT,
    table_number INTEGER NOT NULL,
    pairing_hash VARCHAR(64) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(round_id, petitioner_team_id),
    UNIQUE(round_id, respondent_team_id),
    UNIQUE(round_id, table_number)
);

CREATE INDEX IF NOT EXISTS idx_pairings_round ON round_pairings(round_id);

-- Pairing history for rematch prevention
CREATE TABLE IF NOT EXISTS pairing_history (
    id SERIAL PRIMARY KEY,
    tournament_id INTEGER NOT NULL REFERENCES national_tournaments(id) ON DELETE RESTRICT,
    team_a_id INTEGER NOT NULL REFERENCES tournament_teams(id) ON DELETE RESTRICT,
    team_b_id INTEGER NOT NULL REFERENCES tournament_teams(id) ON DELETE RESTRICT,
    round_id INTEGER NOT NULL REFERENCES tournament_rounds(id) ON DELETE RESTRICT,
    
    UNIQUE(tournament_id, team_a_id, team_b_id)
);

CREATE INDEX IF NOT EXISTS idx_history_tournament ON pairing_history(tournament_id);
CREATE INDEX IF NOT EXISTS idx_history_teams ON pairing_history(team_a_id, team_b_id);

-- Round freeze table
CREATE TABLE IF NOT EXISTS round_freeze (
    id SERIAL PRIMARY KEY,
    round_id INTEGER NOT NULL UNIQUE REFERENCES tournament_rounds(id) ON DELETE RESTRICT,
    pairing_snapshot_json JSONB NOT NULL DEFAULT '[]',
    round_checksum VARCHAR(64) NOT NULL,
    frozen_by INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    frozen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_freeze_round ON round_freeze(round_id);
"""

# =============================================================================
# PostgreSQL Triggers for Freeze Immutability
# =============================================================================

POSTGRESQL_TRIGGERS = """
-- Trigger function to prevent pairing modifications after freeze
CREATE OR REPLACE FUNCTION prevent_pairing_modification_if_frozen()
RETURNS TRIGGER AS $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM round_freeze f
    WHERE f.round_id = NEW.round_id
  ) THEN
    RAISE EXCEPTION 'Cannot modify pairings after freeze';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to INSERT
DROP TRIGGER IF EXISTS pairing_freeze_guard_insert ON round_pairings;
CREATE TRIGGER pairing_freeze_guard_insert
BEFORE INSERT ON round_pairings
FOR EACH ROW EXECUTE FUNCTION prevent_pairing_modification_if_frozen();

-- Apply to UPDATE
DROP TRIGGER IF EXISTS pairing_freeze_guard_update ON round_pairings;
CREATE TRIGGER pairing_freeze_guard_update
BEFORE UPDATE ON round_pairings
FOR EACH ROW EXECUTE FUNCTION prevent_pairing_modification_if_frozen();

-- Trigger function for DELETE (uses OLD not NEW)
CREATE OR REPLACE FUNCTION prevent_pairing_delete_if_frozen()
RETURNS TRIGGER AS $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM round_freeze f
    WHERE f.round_id = OLD.round_id
  ) THEN
    RAISE EXCEPTION 'Cannot delete pairings after freeze';
  END IF;
  RETURN OLD;
END;
$$ LANGUAGE plpgsql;

-- Apply to DELETE
DROP TRIGGER IF EXISTS pairing_freeze_guard_delete ON round_pairings;
CREATE TRIGGER pairing_freeze_guard_delete
BEFORE DELETE ON round_pairings
FOR EACH ROW EXECUTE FUNCTION prevent_pairing_delete_if_frozen();

-- Trigger to prevent round status mutation after freeze
CREATE OR REPLACE FUNCTION prevent_round_status_change_if_frozen()
RETURNS TRIGGER AS $$
BEGIN
  IF OLD.status = 'finalized' AND NEW.status != 'finalized' THEN
    RAISE EXCEPTION 'Cannot change status from finalized';
  END IF;
  
  -- If freeze exists, block status changes
  IF EXISTS (
    SELECT 1 FROM round_freeze f
    WHERE f.round_id = NEW.id
  ) AND OLD.status != NEW.status THEN
    RAISE EXCEPTION 'Cannot modify round after freeze';
  END IF;
  
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to round updates
DROP TRIGGER IF EXISTS round_freeze_guard_status ON tournament_rounds;
CREATE TRIGGER round_freeze_guard_status
BEFORE UPDATE ON tournament_rounds
FOR EACH ROW EXECUTE FUNCTION prevent_round_status_change_if_frozen();
"""


async def migrate():
    """Execute migration for both SQLite and PostgreSQL."""
    from sqlalchemy.ext.asyncio import AsyncSession
    
    async with engine.begin() as conn:
        # Detect dialect
        dialect = conn.dialect.name
        print(f"Detected dialect: {dialect}")
        
        if dialect == "postgresql":
            print("Applying PostgreSQL migration...")
            await conn.execute(text(POSTGRESQL_MIGRATION))
            await conn.execute(text(POSTGRESQL_TRIGGERS))
            print("PostgreSQL triggers installed.")
        else:
            print("Applying SQLite migration...")
            await conn.execute(text(SQLITE_MIGRATION))
            print("SQLite migration complete (triggers not supported).")
        
        print("Phase 3 migration completed successfully.")


if __name__ == "__main__":
    import asyncio
    asyncio.run(migrate())
