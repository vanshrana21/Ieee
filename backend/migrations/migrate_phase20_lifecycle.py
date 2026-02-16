"""
Phase 20 — Tournament Lifecycle Migration.

Safe migration for tournament_lifecycle table.
"""
from sqlalchemy import text
from backend.database import engine


async def migrate():
    """
    Create tournament_lifecycle table and indexes.
    Safe to re-run - uses IF NOT EXISTS.
    """
    async with engine.begin() as conn:
        # Create tournament_lifecycle table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tournament_lifecycle (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tournament_id UUID NOT NULL UNIQUE REFERENCES tournaments(id) ON DELETE CASCADE,
                status VARCHAR(30) NOT NULL DEFAULT 'draft',
                final_standings_hash VARCHAR(64),
                archived_at TIMESTAMP,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                
                CONSTRAINT ck_lifecycle_status_valid 
                    CHECK (status IN ('draft', 'registration_open', 'registration_closed', 
                                     'scheduling', 'rounds_running', 'scoring_locked', 
                                     'completed', 'archived')),
                CONSTRAINT ck_archived_has_timestamp 
                    CHECK (status != 'archived' OR archived_at IS NOT NULL)
            )
        """))
        
        # Create indexes
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_lifecycle_tournament 
            ON tournament_lifecycle(tournament_id)
        """))
        
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_lifecycle_status 
            ON tournament_lifecycle(status)
        """))
        
        # Create trigger for updated_at
        await conn.execute(text("""
            CREATE OR REPLACE FUNCTION update_updated_at_column()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.updated_at = NOW();
                RETURN NEW;
            END;
            $$ language 'plpgsql';
        """))
        
        await conn.execute(text("""
            DROP TRIGGER IF EXISTS update_tournament_lifecycle_updated_at 
            ON tournament_lifecycle;
            
            CREATE TRIGGER update_tournament_lifecycle_updated_at
                BEFORE UPDATE ON tournament_lifecycle
                FOR EACH ROW
                EXECUTE FUNCTION update_updated_at_column();
        """))
        
        print("✅ Phase 20 migration completed successfully")


if __name__ == "__main__":
    import asyncio
    asyncio.run(migrate())
