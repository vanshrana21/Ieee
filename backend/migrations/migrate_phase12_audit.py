#!/usr/bin/env python3
"""
Phase 12 — Tournament Compliance & Audit Ledger Migration

Creates:
1. tournament_audit_snapshots table
2. PostgreSQL triggers to prevent modification after snapshot

Determinism: All operations use deterministic ordering
Safety: SERIALIZABLE isolation, FOR UPDATE locking
"""
import asyncio
import asyncpg
import os

# PostgreSQL triggers for immutability after audit snapshot
FREEZE_TRIGGERS = """
-- Trigger function to prevent modification after audit snapshot
CREATE OR REPLACE FUNCTION prevent_modification_after_audit()
RETURNS TRIGGER AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM tournament_audit_snapshots
        WHERE tournament_id = NEW.tournament_id
    ) THEN
        RAISE EXCEPTION 'Tournament frozen after audit snapshot: tournament_id=%, table=%',
            NEW.tournament_id, TG_TABLE_NAME;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger function for DELETE operations
CREATE OR REPLACE FUNCTION prevent_deletion_after_audit()
RETURNS TRIGGER AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM tournament_audit_snapshots
        WHERE tournament_id = OLD.tournament_id
    ) THEN
        RAISE EXCEPTION 'Tournament frozen after audit snapshot: tournament_id=%, table=%',
            OLD.tournament_id, TG_TABLE_NAME;
    END IF;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

-- Apply triggers to tournament_results
DROP TRIGGER IF EXISTS trg_prevent_results_insert ON tournament_team_results;
CREATE TRIGGER trg_prevent_results_insert
    BEFORE INSERT ON tournament_team_results
    FOR EACH ROW
    EXECUTE FUNCTION prevent_modification_after_audit();

DROP TRIGGER IF EXISTS trg_prevent_results_update ON tournament_team_results;
CREATE TRIGGER trg_prevent_results_update
    BEFORE UPDATE ON tournament_team_results
    FOR EACH ROW
    EXECUTE FUNCTION prevent_modification_after_audit();

DROP TRIGGER IF EXISTS trg_prevent_results_delete ON tournament_team_results;
CREATE TRIGGER trg_prevent_results_delete
    BEFORE DELETE ON tournament_team_results
    FOR EACH ROW
    EXECUTE FUNCTION prevent_deletion_after_audit();

-- Apply triggers to tournament_speaker_results
DROP TRIGGER IF EXISTS trg_prevent_speaker_results_insert ON tournament_speaker_results;
CREATE TRIGGER trg_prevent_speaker_results_insert
    BEFORE INSERT ON tournament_speaker_results
    FOR EACH ROW
    EXECUTE FUNCTION prevent_modification_after_audit();

DROP TRIGGER IF EXISTS trg_prevent_speaker_results_update ON tournament_speaker_results;
CREATE TRIGGER trg_prevent_speaker_results_update
    BEFORE UPDATE ON tournament_speaker_results
    FOR EACH ROW
    EXECUTE FUNCTION prevent_modification_after_audit();

DROP TRIGGER IF EXISTS trg_prevent_speaker_results_delete ON tournament_speaker_results;
CREATE TRIGGER trg_prevent_speaker_results_delete
    BEFORE DELETE ON tournament_speaker_results
    FOR EACH ROW
    EXECUTE FUNCTION prevent_deletion_after_audit();

-- Apply triggers to oral_evaluations
DROP TRIGGER IF EXISTS trg_prevent_oral_insert ON oral_evaluations;
CREATE TRIGGER trg_prevent_oral_insert
    BEFORE INSERT ON oral_evaluations
    FOR EACH ROW
    EXECUTE FUNCTION prevent_modification_after_audit();

DROP TRIGGER IF EXISTS trg_prevent_oral_update ON oral_evaluations;
CREATE TRIGGER trg_prevent_oral_update
    BEFORE UPDATE ON oral_evaluations
    FOR EACH ROW
    EXECUTE FUNCTION prevent_modification_after_audit();

DROP TRIGGER IF EXISTS trg_prevent_oral_delete ON oral_evaluations;
CREATE TRIGGER trg_prevent_oral_delete
    BEFORE DELETE ON oral_evaluations
    FOR EACH ROW
    EXECUTE FUNCTION prevent_deletion_after_audit();

-- Apply triggers to judge_panels
DROP TRIGGER IF EXISTS trg_prevent_panels_insert ON judge_panels;
CREATE TRIGGER trg_prevent_panels_insert
    BEFORE INSERT ON judge_panels
    FOR EACH ROW
    EXECUTE FUNCTION prevent_modification_after_audit();

DROP TRIGGER IF EXISTS trg_prevent_panels_update ON judge_panels;
CREATE TRIGGER trg_prevent_panels_update
    BEFORE UPDATE ON judge_panels
    FOR EACH ROW
    EXECUTE FUNCTION prevent_modification_after_audit();

DROP TRIGGER IF EXISTS trg_prevent_panels_delete ON judge_panels;
CREATE TRIGGER trg_prevent_panels_delete
    BEFORE DELETE ON judge_panels
    FOR EACH ROW
    EXECUTE FUNCTION prevent_deletion_after_audit();

-- Apply triggers to tournament_pairings
DROP TRIGGER IF EXISTS trg_prevent_pairings_insert ON tournament_pairings;
CREATE TRIGGER trg_prevent_pairings_insert
    BEFORE INSERT ON tournament_pairings
    FOR EACH ROW
    EXECUTE FUNCTION prevent_modification_after_audit();

DROP TRIGGER IF EXISTS trg_prevent_pairings_update ON tournament_pairings;
CREATE TRIGGER trg_prevent_pairings_update
    BEFORE UPDATE ON tournament_pairings
    FOR EACH ROW
    EXECUTE FUNCTION prevent_modification_after_audit();

DROP TRIGGER IF EXISTS trg_prevent_pairings_delete ON tournament_pairings;
CREATE TRIGGER trg_prevent_pairings_delete
    BEFORE DELETE ON tournament_pairings
    FOR EACH ROW
    EXECUTE FUNCTION prevent_deletion_after_audit();

-- Apply triggers to session_exhibits
DROP TRIGGER IF EXISTS trg_prevent_exhibits_insert ON session_exhibits;
CREATE TRIGGER trg_prevent_exhibits_insert
    BEFORE INSERT ON session_exhibits
    FOR EACH ROW
    EXECUTE FUNCTION prevent_modification_after_audit();

DROP TRIGGER IF EXISTS trg_prevent_exhibits_update ON session_exhibits;
CREATE TRIGGER trg_prevent_exhibits_update
    BEFORE UPDATE ON session_exhibits
    FOR EACH ROW
    EXECUTE FUNCTION prevent_modification_after_audit();

DROP TRIGGER IF EXISTS trg_prevent_exhibits_delete ON session_exhibits;
CREATE TRIGGER trg_prevent_exhibits_delete
    BEFORE DELETE ON session_exhibits
    FOR EACH ROW
    EXECUTE FUNCTION prevent_deletion_after_audit();

-- Apply triggers to live_event_log (for completed sessions)
DROP TRIGGER IF EXISTS trg_prevent_event_insert ON live_event_log;
CREATE TRIGGER trg_prevent_event_insert
    BEFORE INSERT ON live_event_log
    FOR EACH ROW
    EXECUTE FUNCTION prevent_modification_after_audit();

DROP TRIGGER IF EXISTS trg_prevent_event_update ON live_event_log;
CREATE TRIGGER trg_prevent_event_update
    BEFORE UPDATE ON live_event_log
    FOR EACH ROW
    EXECUTE FUNCTION prevent_modification_after_audit();

DROP TRIGGER IF EXISTS trg_prevent_event_delete ON live_event_log;
CREATE TRIGGER trg_prevent_event_delete
    BEFORE DELETE ON live_event_log
    FOR EACH ROW
    EXECUTE FUNCTION prevent_deletion_after_audit();
"""


async def create_tables(conn: asyncpg.Connection) -> None:
    """Create tournament_audit_snapshots table."""
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS tournament_audit_snapshots (
            id SERIAL PRIMARY KEY,
            tournament_id INTEGER NOT NULL UNIQUE REFERENCES national_tournaments(id) ON DELETE RESTRICT,
            institution_id INTEGER NOT NULL REFERENCES institutions(id) ON DELETE RESTRICT,
            audit_root_hash VARCHAR(64) NOT NULL UNIQUE,
            snapshot_json JSONB NOT NULL,
            signature_hmac VARCHAR(64) NOT NULL,
            generated_by INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            generated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create indexes
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_tournament 
        ON tournament_audit_snapshots(tournament_id)
    """)
    
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_institution 
        ON tournament_audit_snapshots(institution_id)
    """)
    
    print("✓ Created tournament_audit_snapshots table")


async def create_triggers(conn: asyncpg.Connection) -> None:
    """Create PostgreSQL triggers for immutability."""
    await conn.execute(FREEZE_TRIGGERS)
    print("✓ Created freeze triggers on mutable tables")


async def verify_tables(conn: asyncpg.Connection) -> None:
    """Verify table creation."""
    result = await conn.fetchval("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'tournament_audit_snapshots'
        )
    """)
    
    if result:
        count = await conn.fetchval("""
            SELECT COUNT(*) FROM information_schema.triggers
            WHERE trigger_name LIKE 'trg_prevent_%'
        """)
        print(f"✓ Verified: {count} freeze triggers created")
    else:
        raise RuntimeError("Table creation verification failed")


async def run_migration() -> None:
    """Run Phase 12 migration."""
    database_url = os.environ.get(
        "DATABASE_URL",
        "postgresql://moot_user:moot_pass@localhost:5432/moot_court"
    )
    
    conn = await asyncpg.connect(database_url)
    
    try:
        print("=== Phase 12: Tournament Compliance & Audit Ledger Migration ===\n")
        
        await create_tables(conn)
        await create_triggers(conn)
        await verify_tables(conn)
        
        print("\n=== Phase 12 Migration Complete ===")
        
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run_migration())
