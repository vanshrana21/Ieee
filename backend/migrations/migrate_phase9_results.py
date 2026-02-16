"""
Phase 9 — Tournament Results & Ranking Engine
Migration: Create tournament_team_results, tournament_speaker_results, tournament_results_freeze

This migration creates the complete results infrastructure with PostgreSQL triggers
for immutability after freeze, and CHECK constraints for data integrity.
"""
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine
import asyncio
import os

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://moot_user:moot_pass@localhost:5432/moot_court"
)


def run_migration_sync():
    """Synchronous migration runner."""
    engine = create_engine(DATABASE_URL.replace("+asyncpg", ""))
    with engine.begin() as conn:
        _run_migration_logic(conn)


async def run_migration_async():
    """Async migration runner."""
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        # Create tables
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tournament_team_results (
                id SERIAL PRIMARY KEY,
                tournament_id INTEGER NOT NULL REFERENCES national_tournaments(id) ON DELETE RESTRICT,
                team_id INTEGER NOT NULL REFERENCES tournament_teams(id) ON DELETE RESTRICT,
                
                memorial_total NUMERIC(12,2) NOT NULL DEFAULT 0,
                oral_total NUMERIC(12,2) NOT NULL DEFAULT 0,
                total_score NUMERIC(14,2) NOT NULL DEFAULT 0,
                
                strength_of_schedule NUMERIC(12,4) NOT NULL DEFAULT 0,
                opponent_wins_total INTEGER NOT NULL DEFAULT 0,
                
                final_rank INTEGER,
                percentile NUMERIC(6,3),
                
                result_hash VARCHAR(64) NOT NULL,
                
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                
                UNIQUE(tournament_id, team_id),
                
                CHECK (total_score = memorial_total + oral_total)
            )
        """))
        
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tournament_speaker_results (
                id SERIAL PRIMARY KEY,
                tournament_id INTEGER NOT NULL REFERENCES national_tournaments(id) ON DELETE RESTRICT,
                speaker_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
                
                total_speaker_score NUMERIC(12,2) NOT NULL DEFAULT 0,
                average_score NUMERIC(12,4) NOT NULL DEFAULT 0,
                rounds_participated INTEGER NOT NULL DEFAULT 0,
                
                final_rank INTEGER,
                percentile NUMERIC(6,3),
                
                speaker_hash VARCHAR(64) NOT NULL,
                
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                
                UNIQUE(tournament_id, speaker_id)
            )
        """))
        
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tournament_results_freeze (
                id SERIAL PRIMARY KEY,
                tournament_id INTEGER NOT NULL UNIQUE REFERENCES national_tournaments(id) ON DELETE RESTRICT,
                
                team_snapshot_json JSONB NOT NULL,
                speaker_snapshot_json JSONB NOT NULL,
                
                results_checksum VARCHAR(64) NOT NULL,
                
                frozen_by INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
                frozen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        
        # Create indexes
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_team_results_tournament 
            ON tournament_team_results(tournament_id)
        """))
        
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_team_results_rank 
            ON tournament_team_results(tournament_id, final_rank)
        """))
        
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_speaker_results_tournament 
            ON tournament_speaker_results(tournament_id)
        """))
        
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_speaker_results_rank 
            ON tournament_speaker_results(tournament_id, final_rank)
        """))
        
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_results_freeze_tournament 
            ON tournament_results_freeze(tournament_id)
        """))
        
        # Create trigger function for freeze protection
        await conn.execute(text("""
            CREATE OR REPLACE FUNCTION prevent_results_modification_if_frozen()
            RETURNS TRIGGER AS $$
            DECLARE
                v_frozen BOOLEAN;
                v_tournament_id INTEGER;
            BEGIN
                -- Get tournament_id based on table
                IF TG_TABLE_NAME = 'tournament_team_results' THEN
                    v_tournament_id := NEW.tournament_id;
                ELSIF TG_TABLE_NAME = 'tournament_speaker_results' THEN
                    v_tournament_id := NEW.tournament_id;
                ELSE
                    RAISE EXCEPTION 'Unknown table: %', TG_TABLE_NAME;
                END IF;
                
                -- Check if tournament is frozen
                SELECT EXISTS(
                    SELECT 1 FROM tournament_results_freeze
                    WHERE tournament_id = v_tournament_id
                ) INTO v_frozen;
                
                IF v_frozen THEN
                    RAISE EXCEPTION 'Results frozen for tournament_id=%', v_tournament_id;
                END IF;
                
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
        """))
        
        # Create trigger function for freeze protection on DELETE
        await conn.execute(text("""
            CREATE OR REPLACE FUNCTION prevent_results_deletion_if_frozen()
            RETURNS TRIGGER AS $$
            DECLARE
                v_frozen BOOLEAN;
                v_tournament_id INTEGER;
            BEGIN
                -- Get tournament_id based on table
                IF TG_TABLE_NAME = 'tournament_team_results' THEN
                    v_tournament_id := OLD.tournament_id;
                ELSIF TG_TABLE_NAME = 'tournament_speaker_results' THEN
                    v_tournament_id := OLD.tournament_id;
                ELSE
                    RAISE EXCEPTION 'Unknown table: %', TG_TABLE_NAME;
                END IF;
                
                -- Check if tournament is frozen
                SELECT EXISTS(
                    SELECT 1 FROM tournament_results_freeze
                    WHERE tournament_id = v_tournament_id
                ) INTO v_frozen;
                
                IF v_frozen THEN
                    RAISE EXCEPTION 'Cannot delete results: tournament_id=% is frozen', v_tournament_id;
                END IF;
                
                RETURN OLD;
            END;
            $$ LANGUAGE plpgsql
        """))
        
        # Attach triggers to tournament_team_results
        await conn.execute(text("""
            DROP TRIGGER IF EXISTS team_results_update_guard ON tournament_team_results;
            CREATE TRIGGER team_results_update_guard
                BEFORE UPDATE ON tournament_team_results
                FOR EACH ROW EXECUTE FUNCTION prevent_results_modification_if_frozen()
        """))
        
        await conn.execute(text("""
            DROP TRIGGER IF EXISTS team_results_delete_guard ON tournament_team_results;
            CREATE TRIGGER team_results_delete_guard
                BEFORE DELETE ON tournament_team_results
                FOR EACH ROW EXECUTE FUNCTION prevent_results_deletion_if_frozen()
        """))
        
        # Attach triggers to tournament_speaker_results
        await conn.execute(text("""
            DROP TRIGGER IF EXISTS speaker_results_update_guard ON tournament_speaker_results;
            CREATE TRIGGER speaker_results_update_guard
                BEFORE UPDATE ON tournament_speaker_results
                FOR EACH ROW EXECUTE FUNCTION prevent_results_modification_if_frozen()
        """))
        
        await conn.execute(text("""
            DROP TRIGGER IF EXISTS speaker_results_delete_guard ON tournament_speaker_results;
            CREATE TRIGGER speaker_results_delete_guard
                BEFORE DELETE ON tournament_speaker_results
                FOR EACH ROW EXECUTE FUNCTION prevent_results_deletion_if_frozen()
        """))
        
        # Create trigger to prevent freeze table modification
        await conn.execute(text("""
            CREATE OR REPLACE FUNCTION prevent_freeze_modification()
            RETURNS TRIGGER AS $$
            BEGIN
                RAISE EXCEPTION 'Tournament results freeze is immutable';
            END;
            $$ LANGUAGE plpgsql
        """))
        
        await conn.execute(text("""
            DROP TRIGGER IF EXISTS freeze_update_guard ON tournament_results_freeze;
            CREATE TRIGGER freeze_update_guard
                BEFORE UPDATE ON tournament_results_freeze
                FOR EACH ROW EXECUTE FUNCTION prevent_freeze_modification()
        """))
        
        await conn.execute(text("""
            DROP TRIGGER IF EXISTS freeze_delete_guard ON tournament_results_freeze;
            CREATE TRIGGER freeze_delete_guard
                BEFORE DELETE ON tournament_results_freeze
                FOR EACH ROW EXECUTE FUNCTION prevent_freeze_modification()
        """))
    
    await engine.dispose()


def _run_migration_logic(conn):
    """Core migration logic for sync execution."""
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS tournament_team_results (
            id SERIAL PRIMARY KEY,
            tournament_id INTEGER NOT NULL REFERENCES national_tournaments(id) ON DELETE RESTRICT,
            team_id INTEGER NOT NULL REFERENCES tournament_teams(id) ON DELETE RESTRICT,
            
            memorial_total NUMERIC(12,2) NOT NULL DEFAULT 0,
            oral_total NUMERIC(12,2) NOT NULL DEFAULT 0,
            total_score NUMERIC(14,2) NOT NULL DEFAULT 0,
            
            strength_of_schedule NUMERIC(12,4) NOT NULL DEFAULT 0,
            opponent_wins_total INTEGER NOT NULL DEFAULT 0,
            
            final_rank INTEGER,
            percentile NUMERIC(6,3),
            
            result_hash VARCHAR(64) NOT NULL,
            
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            
            UNIQUE(tournament_id, team_id),
            
            CHECK (total_score = memorial_total + oral_total)
        )
    """))
    
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS tournament_speaker_results (
            id SERIAL PRIMARY KEY,
            tournament_id INTEGER NOT NULL REFERENCES national_tournaments(id) ON DELETE RESTRICT,
            speaker_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            
            total_speaker_score NUMERIC(12,2) NOT NULL DEFAULT 0,
            average_score NUMERIC(12,4) NOT NULL DEFAULT 0,
            rounds_participated INTEGER NOT NULL DEFAULT 0,
            
            final_rank INTEGER,
            percentile NUMERIC(6,3),
            
            speaker_hash VARCHAR(64) NOT NULL,
            
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            
            UNIQUE(tournament_id, speaker_id)
        )
    """))
    
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS tournament_results_freeze (
            id SERIAL PRIMARY KEY,
            tournament_id INTEGER NOT NULL UNIQUE REFERENCES national_tournaments(id) ON DELETE RESTRICT,
            
            team_snapshot_json JSONB NOT NULL,
            speaker_snapshot_json JSONB NOT NULL,
            
            results_checksum VARCHAR(64) NOT NULL,
            
            frozen_by INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            frozen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))
    
    # Indexes
    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_team_results_tournament 
        ON tournament_team_results(tournament_id)
    """))
    
    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_team_results_rank 
        ON tournament_team_results(tournament_id, final_rank)
    """))
    
    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_speaker_results_tournament 
        ON tournament_speaker_results(tournament_id)
    """))
    
    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_speaker_results_rank 
        ON tournament_speaker_results(tournament_id, final_rank)
    """))
    
    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_results_freeze_tournament 
        ON tournament_results_freeze(tournament_id)
    """))


if __name__ == "__main__":
    try:
        asyncio.run(run_migration_async())
        print("✅ Phase 9 migration completed successfully")
        print("   - tournament_team_results table created")
        print("   - tournament_speaker_results table created")
        print("   - tournament_results_freeze table created")
        print("   - PostgreSQL triggers installed for freeze protection")
    except Exception as e:
        print(f"Migration failed: {e}")
        raise
