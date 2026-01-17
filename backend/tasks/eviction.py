"""
backend/tasks/eviction.py
Phase 4.4: TTL eviction task for expired tutor sessions
"""

import logging
import asyncio
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from backend.services.tutor_session_service import evict_expired_sessions

logger = logging.getLogger(__name__)

async def run_eviction_once(database_url: str) -> int:
    """Run a single eviction cycle."""
    engine = create_async_engine(database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as db:
        try:
            count = await evict_expired_sessions(db)
            logger.info(f"Eviction completed: {count} sessions removed")
            return count
        except Exception as e:
            logger.error(f"Eviction failed: {str(e)}")
            return 0
        finally:
            await engine.dispose()

async def eviction_loop(database_url: str, interval_seconds: int = 3600):
    """
    Background eviction loop.
    Runs every interval_seconds (default 1 hour).
    """
    logger.info(f"Starting eviction loop with interval {interval_seconds}s")
    
    while True:
        try:
            await run_eviction_once(database_url)
        except Exception as e:
            logger.error(f"Eviction loop error: {str(e)}")
            
        await asyncio.sleep(interval_seconds)

def start_eviction_task(database_url: str, interval_seconds: int = 3600):
    """Start the eviction task as a background coroutine."""
    return asyncio.create_task(eviction_loop(database_url, interval_seconds))

if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./legalai.db")
    
    logging.basicConfig(level=logging.INFO)
    
    asyncio.run(run_eviction_once(DATABASE_URL))
