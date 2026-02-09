"""
backend/scripts/test_ai_session_insert.py
Test inserting an AI session to diagnose the exact error.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from backend.database import DATABASE_URL, Base
from backend.orm.ai_oral_session import AIOralSession, AIOralTurn

# Convert to async SQLite URL
async_db_url = DATABASE_URL.replace("sqlite://", "sqlite+aiosqlite://")

async def test_insert():
    print(f"Testing with database: {async_db_url}")
    
    engine = create_async_engine(async_db_url, echo=True)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Create test session
        test_session = AIOralSession(
            user_id="550e8400-e29b-41d4-a716-446655440000",  # Valid UUID string
            problem_id=1,  # Integer as expected
            side="petitioner",
        )
        
        print(f"Created test session: problem_id={test_session.problem_id} (type: {type(test_session.problem_id)})")
        
        try:
            session.add(test_session)
            await session.commit()
            print("✓ SUCCESS: Session inserted without error")
            print(f"Session ID: {test_session.id}")
        except Exception as e:
            print(f"✗ FAILED: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await session.close()
    
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(test_insert())
