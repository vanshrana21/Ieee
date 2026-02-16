"""
Phase 4 — Hardened Judge Panel Assignment Engine Migration

Conflict Detection + Immutability with:
- PostgreSQL ENUM types
- DB-level freeze immutability (triggers)
- Judge assignment history for repeat detection
- All foreign keys use ON DELETE RESTRICT
"""
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import engine
from sqlalchemy import text

# =============================================================================
# SQLite Migration (for development/testing)
# =============================================================================

SQLITE_MIGRATION = """
-- Judge panels table
CREATE TABLE IF NOT EXISTS judge_panels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id INTEGER NOT NULL REFERENCES tournament_rounds(id) ON DELETE RESTRICT,
    table_number INTEGER NOT NULL,
    panel_hash VARCHAR(64) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(round_id, table_number)
);

CREATE INDEX IF NOT EXISTS idx_panel_round ON judge_panels(round_id);

-- Panel members table
CREATE TABLE IF NOT EXISTS panel_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    panel_id INTEGER NOT NULL REFERENCES judge_panels(id) ON DELETE RESTRICT,
    judge_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    role VARCHAR(20) NOT NULL CHECK(role IN ('presiding', 'member')),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(panel_id, judge_id)
);

CREATE INDEX IF NOT EXISTS idx_panel_members_panel ON panel_members(panel_id);
CREATE INDEX IF NOT EXISTS idx_panel_members_judge ON panel_members(judge_id);

-- Judge assignment history for conflict detection
CREATE TABLE IF NOT EXISTS judge_assignment_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL REFERENCES national_tournaments(id) ON DELETE RESTRICT,
    judge_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    team_id INTEGER NOT NULL REFERENCES tournament_teams(id) ON DELETE RESTRICT,
    round_id INTEGER NOT NULL REFERENCES tournament_rounds(id) ON DELETE RESTRICT,
    
    UNIQUE(tournament_id, judge_id, team_id)
);

CREATE INDEX IF NOT EXISTS idx_assignment_history_tournament ON judge_assignment_history(tournament_id);
CREATE INDEX IF NOT EXISTS idx_assignment_history_judge ON judge_assignment_history(judge_id);
CREATE INDEX IF NOT EXISTS idx_assignment_history_team ON judge_assignment_history(team_id);

-- Panel freeze table
CREATE TABLE IF NOT EXISTS panel_freeze (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id INTEGER NOT NULL UNIQUE REFERENCES tournament_rounds(id) ON DELETE RESTRICT,
    panel_snapshot_json TEXT NOT NULL DEFAULT '[]',
    panel_checksum VARCHAR(64) NOT NULL,
    frozen_by INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    frozen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_panel_freeze_round ON panel_freeze(round_id);
"""

# =============================================================================
# PostgreSQL Migration (production)
# =============================================================================

POSTGRESQL_MIGRATION = """
-- Judge panels table
CREATE TABLE IF NOT EXISTS judge_panels (
    id SERIAL PRIMARY KEY,
    round_id INTEGER NOT NULL REFERENCES tournament_rounds(id) ON DELETE RESTRICT,
    table_number INTEGER NOT NULL,
    panel_hash VARCHAR(64) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(round_id, table_number)
);

CREATE INDEX IF NOT EXISTS idx_panel_round ON judge_panels(round_id);

-- Panel members table
CREATE TABLE IF NOT EXISTS panel_members (
    id SERIAL PRIMARY KEY,
    panel_id INTEGER NOT NULL REFERENCES judge_panels(id) ON DELETE RESTRICT,
    judge_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    role VARCHAR(20) NOT NULL CHECK(role IN ('presiding', 'member')),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(panel_id, judge_id)
);

CREATE INDEX IF NOT EXISTS idx_panel_members_panel ON panel_members(panel_id);
CREATE INDEX IF NOT EXISTS idx_panel_members_judge ON panel_members(judge_id);

-- Judge assignment history for conflict detection
CREATE TABLE IF NOT EXISTS judge_assignment_history (
    id SERIAL PRIMARY KEY,
    tournament_id INTEGER NOT NULL REFERENCES national_tournaments(id) ON DELETE RESTRICT,
    judge_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    team_id INTEGER NOT NULL REFERENCES tournament_teams(id) ON DELETE RESTRICT,
    round_id INTEGER NOT NULL REFERENCES tournament_rounds(id) ON DELETE RESTRICT,
    
    UNIQUE(tournament_id, judge_id, team_id)
);

CREATE INDEX IF NOT EXISTS idx_assignment_history_tournament ON judge_assignment_history(tournament_id);
CREATE INDEX IF NOT EXISTS idx_assignment_history_judge ON judge_assignment_history(judge_id);
CREATE INDEX IF NOT EXISTS idx_assignment_history_team ON judge_assignment_history(team_id);

-- Panel freeze table
CREATE TABLE IF NOT EXISTS panel_freeze (
    id SERIAL PRIMARY KEY,
    round_id INTEGER NOT NULL UNIQUE REFERENCES tournament_rounds(id) ON DELETE RESTRICT,
    panel_snapshot_json JSONB NOT NULL DEFAULT '[]',
    panel_checksum VARCHAR(64) NOT NULL,
    frozen_by INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    frozen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_panel_freeze_round ON panel_freeze(round_id);
"""

# =============================================================================
# PostgreSQL Triggers for Freeze Immutability
# =============================================================================

POSTGRESQL_TRIGGERS = """
-- Trigger function to prevent panel modifications after freeze
CREATE OR REPLACE FUNCTION prevent_panel_modification_if_frozen()
RETURNS TRIGGER AS $$
DECLARE
    v_round_id INTEGER;
BEGIN
    -- Get round_id depending on operation
    IF TG_OP = 'DELETE' THEN
        -- For DELETE on judge_panels, use OLD
        v_round_id := OLD.round_id;
    ELSIF TG_OP = 'INSERT' OR TG_OP = 'UPDATE' THEN
        -- For INSERT/UPDATE on judge_panels, use NEW
        v_round_id := NEW.round_id;
    END IF;
    
    IF EXISTS (
        SELECT 1 FROM panel_freeze f
        WHERE f.round_id = v_round_id
    ) THEN
        RAISE EXCEPTION 'Cannot modify panel after freeze';
    END IF;
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

-- Apply to judge_panels INSERT
DROP TRIGGER IF EXISTS panel_freeze_guard_insert ON judge_panels;
CREATE TRIGGER panel_freeze_guard_insert
BEFORE INSERT ON judge_panels
FOR EACH ROW EXECUTE FUNCTION prevent_panel_modification_if_frozen();

-- Apply to judge_panels UPDATE
DROP TRIGGER IF EXISTS panel_freeze_guard_update ON judge_panels;
CREATE TRIGGER panel_freeze_guard_update
BEFORE UPDATE ON judge_panels
FOR EACH ROW EXECUTE FUNCTION prevent_panel_modification_if_frozen();

-- Apply to judge_panels DELETE
DROP TRIGGER IF EXISTS panel_freeze_guard_delete ON judge_panels;
CREATE TRIGGER panel_freeze_guard_delete
BEFORE DELETE ON judge_panels
FOR EACH ROW EXECUTE FUNCTION prevent_panel_modification_if_frozen();

-- Trigger function for panel_members (need to get round_id via panel)
CREATE OR REPLACE FUNCTION prevent_panel_member_modification_if_frozen()
RETURNS TRIGGER AS $$
DECLARE
    v_round_id INTEGER;
    v_panel_id INTEGER;
BEGIN
    -- Get panel_id depending on operation
    IF TG_OP = 'DELETE' THEN
        v_panel_id := OLD.panel_id;
    ELSE
        v_panel_id := NEW.panel_id;
    END IF;
    
    -- Get round_id from judge_panels
    SELECT round_id INTO v_round_id FROM judge_panels WHERE id = v_panel_id;
    
    IF v_round_id IS NOT NULL AND EXISTS (
        SELECT 1 FROM panel_freeze f
        WHERE f.round_id = v_round_id
    ) THEN
        RAISE EXCEPTION 'Cannot modify panel members after freeze';
    END IF;
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

-- Apply to panel_members INSERT
DROP TRIGGER IF EXISTS panel_member_freeze_guard_insert ON panel_members;
CREATE TRIGGER panel_member_freeze_guard_insert
BEFORE INSERT ON panel_members
FOR EACH ROW EXECUTE FUNCTION prevent_panel_member_modification_if_frozen();

-- Apply to panel_members UPDATE
DROP TRIGGER IF EXISTS panel_member_freeze_guard_update ON panel_members;
CREATE TRIGGER panel_member_freeze_guard_update
BEFORE UPDATE ON panel_members
FOR EACH ROW EXECUTE FUNCTION prevent_panel_member_modification_if_frozen();

-- Apply to panel_members DELETE
DROP TRIGGER IF EXISTS panel_member_freeze_guard_delete ON panel_members;
CREATE TRIGGER panel_member_freeze_guard_delete
BEFORE DELETE ON panel_members
FOR EACH ROW EXECUTE FUNCTION prevent_panel_member_modification_if_frozen();

-- Trigger to prevent round status mutation after freeze (for panel rounds)
CREATE OR REPLACE FUNCTION prevent_round_panel_change_if_frozen()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.status = 'finalized' AND NEW.status != 'finalized' THEN
        RAISE EXCEPTION 'Cannot change status from finalized';
    END IF;
    
    IF EXISTS (
        SELECT 1 FROM panel_freeze f
        WHERE f.round_id = NEW.id
    ) AND OLD.status != NEW.status THEN
        RAISE EXCEPTION 'Cannot modify round after panel freeze';
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to tournament_rounds
DROP TRIGGER IF EXISTS round_panel_freeze_guard ON tournament_rounds;
CREATE TRIGGER round_panel_freeze_guard
BEFORE UPDATE ON tournament_rounds
FOR EACH ROW EXECUTE FUNCTION prevent_round_panel_change_if_frozen();
"""


async def migrate():
    """Execute migration for both SQLite and PostgreSQL."""
    async with engine.begin() as conn:
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
        
        print("Phase 4 migration completed successfully.")


if __name__ == "__main__":
    import asyncio
    asyncio.run(migrate())
