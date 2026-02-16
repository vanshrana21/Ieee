"""
Layer 2 Migration Script - Deterministic Participant Assignment

This migration:
1. Adds new columns to classroom_participants (side, speaker_number, is_active)
2. Creates classroom_participant_audit_log table
3. Adds database constraints for deterministic assignment
"""
import asyncio
import logging
from sqlalchemy import text

from backend.database import AsyncSessionLocal, init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate_classroom_participants():
    """Migrate classroom_participants table with new columns."""
    async with AsyncSessionLocal() as session:
        try:
            # Check if side column exists
            result = await session.execute(
                text("SELECT name FROM pragma_table_info('classroom_participants') WHERE name='side'")
            )
            side_exists = result.fetchone() is not None
            
            if not side_exists:
                logger.info("Adding 'side' column to classroom_participants...")
                await session.execute(
                    text("ALTER TABLE classroom_participants ADD COLUMN side VARCHAR(20)")
                )
                logger.info("✓ Added 'side' column")
            else:
                logger.info("✓ 'side' column already exists")
            
            # Check if speaker_number column exists
            result = await session.execute(
                text("SELECT name FROM pragma_table_info('classroom_participants') WHERE name='speaker_number'")
            )
            speaker_exists = result.fetchone() is not None
            
            if not speaker_exists:
                logger.info("Adding 'speaker_number' column to classroom_participants...")
                await session.execute(
                    text("ALTER TABLE classroom_participants ADD COLUMN speaker_number INTEGER")
                )
                logger.info("✓ Added 'speaker_number' column")
            else:
                logger.info("✓ 'speaker_number' column already exists")
            
            # Check if is_active column exists
            result = await session.execute(
                text("SELECT name FROM pragma_table_info('classroom_participants') WHERE name='is_active'")
            )
            is_active_exists = result.fetchone() is not None
            
            if not is_active_exists:
                logger.info("Adding 'is_active' column to classroom_participants...")
                await session.execute(
                    text("ALTER TABLE classroom_participants ADD COLUMN is_active BOOLEAN DEFAULT 1")
                )
                logger.info("✓ Added 'is_active' column")
            else:
                logger.info("✓ 'is_active' column already exists")
            
            await session.commit()
            
        except Exception as e:
            logger.error(f"Error migrating classroom_participants: {e}")
            await session.rollback()
            raise


async def create_audit_log_table():
    """Create classroom_participant_audit_log table."""
    async with AsyncSessionLocal() as session:
        try:
            # Check if table exists
            result = await session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='classroom_participant_audit_log'")
            )
            table_exists = result.fetchone() is not None
            
            if not table_exists:
                logger.info("Creating classroom_participant_audit_log table...")
                await session.execute(text("""
                    CREATE TABLE classroom_participant_audit_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        side VARCHAR(20),
                        speaker_number INTEGER,
                        position INTEGER,
                        is_successful BOOLEAN DEFAULT 1,
                        error_message VARCHAR(255),
                        ip_address VARCHAR(45),
                        user_agent VARCHAR(255),
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (session_id) REFERENCES classroom_sessions(id) ON DELETE CASCADE,
                        FOREIGN KEY (user_id) REFERENCES users(id)
                    )
                """))
                
                # Create indexes
                await session.execute(text("""
                    CREATE INDEX idx_audit_session ON classroom_participant_audit_log(session_id, created_at)
                """))
                await session.execute(text("""
                    CREATE INDEX idx_audit_user ON classroom_participant_audit_log(user_id, created_at)
                """))
                await session.execute(text("""
                    CREATE INDEX idx_audit_session_user ON classroom_participant_audit_log(session_id, user_id)
                """))
                
                await session.commit()
                logger.info("✓ Created classroom_participant_audit_log table with indexes")
            else:
                logger.info("✓ classroom_participant_audit_log table already exists")
                
        except Exception as e:
            logger.error(f"Error creating audit log table: {e}")
            await session.rollback()
            raise


async def add_constraints():
    """Add database constraints for deterministic assignment."""
    async with AsyncSessionLocal() as session:
        try:
            # SQLite doesn't support adding constraints to existing tables easily
            # So we check if our unique constraints are already working
            logger.info("Checking constraints...")
            
            # Test that the unique constraints would work by attempting to create
            # a temp table with the constraints and seeing if it works
            try:
                await session.execute(text("""
                    CREATE UNIQUE INDEX IF NOT EXISTS uq_participant_session_user 
                    ON classroom_participants(session_id, user_id)
                """))
                logger.info("✓ Unique constraint on (session_id, user_id) ensured")
            except Exception as e:
                logger.warning(f"Could not create session_user unique index: {e}")
            
            try:
                await session.execute(text("""
                    CREATE UNIQUE INDEX IF NOT EXISTS uq_participant_session_side_speaker 
                    ON classroom_participants(session_id, side, speaker_number)
                    WHERE side IS NOT NULL AND speaker_number IS NOT NULL
                """))
                logger.info("✓ Unique constraint on (session_id, side, speaker_number) ensured")
            except Exception as e:
                logger.warning(f"Could not create side_speaker unique index: {e}")
            
            try:
                await session.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_participant_session 
                    ON classroom_participants(session_id, is_active)
                """))
                logger.info("✓ Index on (session_id, is_active) ensured")
            except Exception as e:
                logger.warning(f"Could not create participant index: {e}")
            
            await session.commit()
                
        except Exception as e:
            logger.error(f"Error adding constraints: {e}")
            await session.rollback()
            raise


async def migrate_existing_participants():
    """Migrate existing participants to new schema with deterministic assignment."""
    async with AsyncSessionLocal() as session:
        try:
            # Get all participants without side assignment
            result = await session.execute(
                text("""
                    SELECT id, session_id, user_id, role, joined_at
                    FROM classroom_participants
                    WHERE side IS NULL AND is_active = 1
                    ORDER BY session_id, joined_at
                """)
            )
            participants = result.fetchall()
            
            if not participants:
                logger.info("✓ No existing participants to migrate")
                return
            
            logger.info(f"Migrating {len(participants)} existing participants...")
            
            # Track position per session
            session_positions = {}
            
            for p in participants:
                session_id = p.session_id
                
                # Get position for this session
                if session_id not in session_positions:
                    session_positions[session_id] = 0
                
                session_positions[session_id] += 1
                position = session_positions[session_id]
                
                # Determine assignment based on position
                if position == 1:
                    side = "PETITIONER"
                    speaker = 1
                elif position == 2:
                    side = "RESPONDENT"
                    speaker = 1
                elif position == 3:
                    side = "PETITIONER"
                    speaker = 2
                elif position == 4:
                    side = "RESPONDENT"
                    speaker = 2
                else:
                    # More than 4 - mark as observer
                    side = "OBSERVER"
                    speaker = None
                
                # Update participant
                await session.execute(
                    text("""
                        UPDATE classroom_participants
                        SET side = :side, speaker_number = :speaker, is_active = 1
                        WHERE id = :id
                    """),
                    {"side": side, "speaker": speaker, "id": p.id}
                )
                
                logger.info(f"  Migrated participant {p.id}: {side} #{speaker}")
            
            await session.commit()
            logger.info(f"✓ Migrated {len(participants)} participants")
            
        except Exception as e:
            logger.error(f"Error migrating participants: {e}")
            await session.rollback()
            raise


async def run_migration():
    """Run all Layer 2 migrations."""
    logger.info("=" * 60)
    logger.info("Layer 2 Migration - Deterministic Participant Assignment")
    logger.info("=" * 60)
    
    try:
        # Initialize database connection
        await init_db()
        
        # Run migrations
        await migrate_classroom_participants()
        await create_audit_log_table()
        await add_constraints()
        await migrate_existing_participants()
        
        logger.info("=" * 60)
        logger.info("✅ Layer 2 Migration completed successfully!")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(run_migration())
