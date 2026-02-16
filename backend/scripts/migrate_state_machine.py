"""
Manual migration script for Session State Machine tables

This script uses async SQLAlchemy to create the necessary tables and columns
for the strict state machine implementation.
"""
import asyncio
import logging
from sqlalchemy import text, inspect
from sqlalchemy.exc import OperationalError

from backend.database import AsyncSessionLocal, init_db
from backend.orm.base import Base
from backend.orm.session_state_transition import SessionStateTransition
from backend.orm.classroom_session_state_log import ClassroomSessionStateLog
from backend.orm.classroom_session import ClassroomSession

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def add_state_updated_at_column():
    """Add state_updated_at column to classroom_sessions if it doesn't exist."""
    async with AsyncSessionLocal() as session:
        try:
            # Check if column exists
            result = await session.execute(
                text("SELECT name FROM pragma_table_info('classroom_sessions') WHERE name='state_updated_at'")
            )
            column_exists = result.fetchone() is not None
            
            if not column_exists:
                logger.info("Adding state_updated_at column to classroom_sessions...")
                await session.execute(
                    text("ALTER TABLE classroom_sessions ADD COLUMN state_updated_at DATETIME")
                )
                await session.commit()
                logger.info("✓ Added state_updated_at column")
            else:
                logger.info("✓ state_updated_at column already exists")
                
        except Exception as e:
            logger.error(f"Error adding state_updated_at column: {e}")
            await session.rollback()


async def create_session_state_transitions_table():
    """Create the session_state_transitions table if it doesn't exist."""
    async with AsyncSessionLocal() as session:
        try:
            # Check if table exists
            result = await session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='session_state_transitions'")
            )
            table_exists = result.fetchone() is not None
            
            if not table_exists:
                logger.info("Creating session_state_transitions table...")
                await session.execute(text("""
                    CREATE TABLE session_state_transitions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        from_state VARCHAR(50) NOT NULL,
                        to_state VARCHAR(50) NOT NULL,
                        trigger_type VARCHAR(50),
                        requires_all_rounds_complete BOOLEAN DEFAULT 0,
                        requires_faculty BOOLEAN DEFAULT 0,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(from_state, to_state)
                    )
                """))
                await session.execute(text("""
                    CREATE INDEX ix_session_state_transitions_from_state 
                    ON session_state_transitions(from_state)
                """))
                await session.commit()
                logger.info("✓ Created session_state_transitions table")
                
                # Seed default transitions
                await seed_default_transitions(session)
            else:
                logger.info("✓ session_state_transitions table already exists")
                
        except Exception as e:
            logger.error(f"Error creating session_state_transitions table: {e}")
            await session.rollback()


async def create_classroom_session_state_log_table():
    """Create the classroom_session_state_log table if it doesn't exist."""
    async with AsyncSessionLocal() as session:
        try:
            # Check if table exists
            result = await session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='classroom_session_state_log'")
            )
            table_exists = result.fetchone() is not None
            
            if not table_exists:
                logger.info("Creating classroom_session_state_log table...")
                await session.execute(text("""
                    CREATE TABLE classroom_session_state_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id INTEGER NOT NULL,
                        from_state VARCHAR(50) NOT NULL,
                        to_state VARCHAR(50) NOT NULL,
                        triggered_by_user_id INTEGER,
                        trigger_type VARCHAR(50),
                        reason TEXT,
                        is_successful BOOLEAN DEFAULT 1,
                        error_message TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (session_id) REFERENCES classroom_sessions(id) ON DELETE CASCADE,
                        FOREIGN KEY (triggered_by_user_id) REFERENCES users(id)
                    )
                """))
                await session.execute(text("""
                    CREATE INDEX ix_classroom_session_state_log_session_id 
                    ON classroom_session_state_log(session_id)
                """))
                await session.execute(text("""
                    CREATE INDEX ix_classroom_session_state_log_created_at 
                    ON classroom_session_state_log(created_at)
                """))
                await session.commit()
                logger.info("✓ Created classroom_session_state_log table")
            else:
                logger.info("✓ classroom_session_state_log table already exists")
                
        except Exception as e:
            logger.error(f"Error creating classroom_session_state_log table: {e}")
            await session.rollback()


async def seed_default_transitions(session):
    """Seed the default state transitions."""
    logger.info("Seeding default state transitions...")
    
    transitions = [
        # Standard flow
        ("CREATED", "PREPARING", "faculty_action", False, True),
        ("PREPARING", "ARGUING_PETITIONER", "faculty_action", False, True),
        ("ARGUING_PETITIONER", "ARGUING_RESPONDENT", "round_completed", False, False),
        ("ARGUING_RESPONDENT", "REBUTTAL", "round_completed", False, False),
        ("REBUTTAL", "JUDGING", "faculty_action", False, True),
        ("JUDGING", "COMPLETED", "all_evaluations_complete", True, True),
        # Cancel transitions
        ("CREATED", "CANCELLED", "faculty_action", False, True),
        ("PREPARING", "CANCELLED", "faculty_action", False, True),
        ("ARGUING_PETITIONER", "CANCELLED", "faculty_action", False, True),
        ("ARGUING_RESPONDENT", "CANCELLED", "faculty_action", False, True),
        ("REBUTTAL", "CANCELLED", "faculty_action", False, True),
        ("JUDGING", "CANCELLED", "faculty_action", False, True),
    ]
    
    for from_state, to_state, trigger_type, requires_rounds, requires_faculty in transitions:
        await session.execute(text("""
            INSERT OR IGNORE INTO session_state_transitions 
            (from_state, to_state, trigger_type, requires_all_rounds_complete, requires_faculty)
            VALUES (:from_state, :to_state, :trigger_type, :requires_rounds, :requires_faculty)
        """), {
            "from_state": from_state,
            "to_state": to_state,
            "trigger_type": trigger_type,
            "requires_rounds": requires_rounds,
            "requires_faculty": requires_faculty
        })
    
    await session.commit()
    logger.info(f"✓ Seeded {len(transitions)} default transitions")


async def run_migration():
    """Run all migration steps."""
    logger.info("=" * 60)
    logger.info("Session State Machine Migration")
    logger.info("=" * 60)
    
    try:
        # Initialize database connection
        await init_db()
        
        # Run migrations
        await add_state_updated_at_column()
        await create_session_state_transitions_table()
        await create_classroom_session_state_log_table()
        
        logger.info("=" * 60)
        logger.info("✅ Migration completed successfully!")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(run_migration())
