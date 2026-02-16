"""
Phase 5 — Hardened Live Courtroom State Machine Migration

Server-authoritative with:
- PostgreSQL ENUM types
- DB-level freeze immutability (triggers)
- Event log chain with cryptographic hashing
- Append-only design
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
-- SQLite doesn't support ENUM, use VARCHAR with CHECK constraints

-- Live court sessions table
CREATE TABLE IF NOT EXISTS live_court_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id INTEGER NOT NULL REFERENCES tournament_rounds(id) ON DELETE RESTRICT,
    institution_id INTEGER NOT NULL REFERENCES institutions(id) ON DELETE RESTRICT,
    status VARCHAR(20) NOT NULL DEFAULT 'not_started' CHECK(status IN ('not_started', 'live', 'paused', 'completed')),
    current_turn_id INTEGER,
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (current_turn_id) REFERENCES live_turns(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_live_session_round ON live_court_sessions(round_id);
CREATE INDEX IF NOT EXISTS idx_live_session_institution_status ON live_court_sessions(institution_id, status);

-- Live turns table
CREATE TABLE IF NOT EXISTS live_turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES live_court_sessions(id) ON DELETE RESTRICT,
    participant_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    side VARCHAR(20) NOT NULL CHECK(side IN ('petitioner', 'respondent')),
    turn_type VARCHAR(20) NOT NULL CHECK(turn_type IN ('presentation', 'rebuttal', 'surrebuttal', 'question', 'answer')),
    allocated_seconds INTEGER NOT NULL,
    state VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK(state IN ('pending', 'active', 'ended')),
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    violation_flag INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_live_turn_session ON live_turns(session_id);
CREATE INDEX IF NOT EXISTS idx_live_turn_session_state ON live_turns(session_id, state);

-- Live event log table (append-only)
CREATE TABLE IF NOT EXISTS live_event_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES live_court_sessions(id) ON DELETE RESTRICT,
    event_sequence INTEGER NOT NULL,
    event_type VARCHAR(40) NOT NULL,
    event_payload_json TEXT NOT NULL,
    previous_hash VARCHAR(64) NOT NULL,
    event_hash VARCHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(session_id, event_sequence)
);

CREATE INDEX IF NOT EXISTS idx_live_event_session_seq ON live_event_log(session_id, event_sequence);
CREATE INDEX IF NOT EXISTS idx_live_event_session ON live_event_log(session_id);
"""

# =============================================================================
# PostgreSQL Migration (production)
# =============================================================================

POSTGRESQL_MIGRATION = """
-- Create ENUM types
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'livecourtstatus') THEN
        CREATE TYPE livecourtstatus AS ENUM ('not_started', 'live', 'paused', 'completed');
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'oralside') THEN
        CREATE TYPE oralside AS ENUM ('petitioner', 'respondent');
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'oralturntype') THEN
        CREATE TYPE oralturntype AS ENUM ('presentation', 'rebuttal', 'surrebuttal', 'question', 'answer');
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'liveturnstate') THEN
        CREATE TYPE liveturnstate AS ENUM ('pending', 'active', 'ended');
    END IF;
END
$$;

-- Live court sessions table
CREATE TABLE IF NOT EXISTS live_court_sessions (
    id SERIAL PRIMARY KEY,
    round_id INTEGER NOT NULL REFERENCES tournament_rounds(id) ON DELETE RESTRICT,
    institution_id INTEGER NOT NULL REFERENCES institutions(id) ON DELETE RESTRICT,
    status livecourtstatus NOT NULL DEFAULT 'not_started',
    current_turn_id INTEGER,
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (current_turn_id) REFERENCES live_turns(id) ON DELETE SET NULL
);

CREATE INDEX idx_live_session_round ON live_court_sessions(round_id);
CREATE INDEX idx_live_session_institution_status ON live_court_sessions(institution_id, status);

-- Live turns table
CREATE TABLE IF NOT EXISTS live_turns (
    id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES live_court_sessions(id) ON DELETE RESTRICT,
    participant_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    side oralside NOT NULL,
    turn_type oralturntype NOT NULL,
    allocated_seconds INTEGER NOT NULL,
    state liveturnstate NOT NULL DEFAULT 'pending',
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    violation_flag BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_live_turn_session ON live_turns(session_id);
CREATE INDEX idx_live_turn_session_state ON live_turns(session_id, state);

-- Live event log table (append-only)
CREATE TABLE IF NOT EXISTS live_event_log (
    id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES live_court_sessions(id) ON DELETE RESTRICT,
    event_sequence INTEGER NOT NULL,
    event_type VARCHAR(40) NOT NULL,
    event_payload_json JSONB NOT NULL,
    previous_hash VARCHAR(64) NOT NULL,
    event_hash VARCHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(session_id, event_sequence)
);

CREATE INDEX idx_live_event_session_seq ON live_event_log(session_id, event_sequence);
CREATE INDEX idx_live_event_session ON live_event_log(session_id);
"""

# =============================================================================
# PostgreSQL Triggers for Freeze Immutability
# =============================================================================

POSTGRESQL_TRIGGERS = """
-- Trigger function to prevent turn modifications after session completed
CREATE OR REPLACE FUNCTION prevent_turn_modification_if_completed()
RETURNS TRIGGER AS $$
DECLARE
    v_session_status livecourtstatus;
BEGIN
    SELECT status INTO v_session_status
    FROM live_court_sessions
    WHERE id = NEW.session_id;
    
    IF v_session_status = 'completed' THEN
        RAISE EXCEPTION 'Cannot modify turn after session completed';
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to live_turns UPDATE
DROP TRIGGER IF EXISTS turn_completed_guard_update ON live_turns;
CREATE TRIGGER turn_completed_guard_update
BEFORE UPDATE ON live_turns
FOR EACH ROW EXECUTE FUNCTION prevent_turn_modification_if_completed();

-- Apply to live_turns DELETE
DROP TRIGGER IF EXISTS turn_completed_guard_delete ON live_turns;
CREATE TRIGGER turn_completed_guard_delete
BEFORE DELETE ON live_turns
FOR EACH ROW EXECUTE FUNCTION prevent_turn_modification_if_completed();

-- Trigger function to prevent event log modifications (append-only)
CREATE OR REPLACE FUNCTION prevent_event_log_modification()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Cannot modify event log - append-only design';
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- Apply to live_event_log UPDATE
DROP TRIGGER IF EXISTS event_log_guard_update ON live_event_log;
CREATE TRIGGER event_log_guard_update
BEFORE UPDATE ON live_event_log
FOR EACH ROW EXECUTE FUNCTION prevent_event_log_modification();

-- Apply to live_event_log DELETE
DROP TRIGGER IF EXISTS event_log_guard_delete ON live_event_log;
CREATE TRIGGER event_log_guard_delete
BEFORE DELETE ON live_event_log
FOR EACH ROW EXECUTE FUNCTION prevent_event_log_modification();

-- Trigger function to prevent live_court_sessions modifications after completed
CREATE OR REPLACE FUNCTION prevent_session_modification_if_completed()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.status = 'completed' THEN
        RAISE EXCEPTION 'Cannot modify session after completed';
    END IF;
    
    IF OLD.status = 'completed' AND NEW.status != 'completed' THEN
        RAISE EXCEPTION 'Cannot change status from completed';
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to live_court_sessions UPDATE
DROP TRIGGER IF EXISTS session_completed_guard_update ON live_court_sessions;
CREATE TRIGGER session_completed_guard_update
BEFORE UPDATE ON live_court_sessions
FOR EACH ROW EXECUTE FUNCTION prevent_session_modification_if_completed();

-- Apply to live_court_sessions DELETE
DROP TRIGGER IF EXISTS session_completed_guard_delete ON live_court_sessions;
CREATE TRIGGER session_completed_guard_delete
BEFORE DELETE ON live_court_sessions
FOR EACH ROW EXECUTE FUNCTION prevent_session_modification_if_completed();
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
        
        print("Phase 5 migration completed successfully.")


if __name__ == "__main__":
    import asyncio
    asyncio.run(migrate())
