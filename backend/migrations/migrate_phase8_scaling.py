"""
Phase 8 — Real-Time Integrity Hardening & Scaling Layer
Migration: Add integrity_last_checked_at to live_court_sessions

This migration adds optional timestamp tracking for global integrity verification.
No schema changes to core functionality - purely additive.
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
        await conn.execute(text("""
            ALTER TABLE live_court_sessions
            ADD COLUMN IF NOT EXISTS integrity_last_checked_at TIMESTAMP NULL
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_session_integrity_check
            ON live_court_sessions(integrity_last_checked_at)
            WHERE integrity_last_checked_at IS NOT NULL
        """))
    await engine.dispose()


def _run_migration_logic(conn):
    """Core migration logic."""
    conn.execute(text("""
        ALTER TABLE live_court_sessions
        ADD COLUMN IF NOT EXISTS integrity_last_checked_at TIMESTAMP NULL
    """))
    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_session_integrity_check
        ON live_court_sessions(integrity_last_checked_at)
        WHERE integrity_last_checked_at IS NOT NULL
    """))


if __name__ == "__main__":
    try:
        asyncio.run(run_migration_async())
        print("✅ Phase 8 migration completed successfully")
    except Exception as e:
        print(f"Migration failed: {e}")
        raise
