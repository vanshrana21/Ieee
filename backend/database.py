"""
backend/database.py
Database configuration with automatic migration support
"""
import os
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import text
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./legalai.db")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set")

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

from backend.orm.base import Base


async def get_db():
    """Dependency for getting async database session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def check_and_migrate_role_column():
    """
    Check if the 'role' column exists in users table and add it if missing.
    This handles migration for existing databases.
    """
    async with engine.begin() as conn:
        try:
            # Check if users table exists
            result = await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            )
            table_exists = result.fetchone() is not None
            
            if not table_exists:
                logger.info("Users table doesn't exist yet - will be created fresh")
                return
            
            # Check if role column exists
            result = await conn.execute(text("PRAGMA table_info(users)"))
            columns = [row[1] for row in result.fetchall()]
            
            if 'role' not in columns:
                logger.warning("Role column missing - performing migration")
                
                # SQLite doesn't support ALTER COLUMN, so we need to:
                # 1. Create new table with role column
                # 2. Copy data with default role
                # 3. Drop old table
                # 4. Rename new table
                
                await conn.execute(text("""
                    CREATE TABLE users_new (
                        id INTEGER PRIMARY KEY,
                        email VARCHAR NOT NULL UNIQUE,
                        full_name VARCHAR NOT NULL,
                        password_hash VARCHAR NOT NULL,
                        role VARCHAR NOT NULL,
                        course_id INTEGER,
                        current_semester INTEGER,
                        is_active BOOLEAN DEFAULT 1,
                        is_premium BOOLEAN DEFAULT 0,
                        credits_remaining INTEGER DEFAULT 500,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (course_id) REFERENCES courses(id)
                    )
                """))
                
                # Copy existing data with default role as 'student'
                await conn.execute(text("""
                    INSERT INTO users_new (
                        id, email, full_name, password_hash, role,
                        is_active, is_premium, credits_remaining,
                        created_at, updated_at
                    )
                    SELECT 
                        id, email, full_name, password_hash, 'student',
                        is_active, is_premium, credits_remaining,
                        created_at, updated_at
                    FROM users
                """))
                
                # Drop old table and rename
                await conn.execute(text("DROP TABLE users"))
                await conn.execute(text("ALTER TABLE users_new RENAME TO users"))
                
                # Recreate indexes
                await conn.execute(text("CREATE INDEX ix_users_id ON users (id)"))
                await conn.execute(text("CREATE INDEX ix_users_email ON users (email)"))
                await conn.execute(text("CREATE INDEX ix_users_role ON users (role)"))
                await conn.execute(text("CREATE INDEX ix_users_course_id ON users (course_id)"))
                await conn.execute(text("CREATE INDEX ix_users_current_semester ON users (current_semester)"))
                
                logger.info("✓ Successfully migrated users table with role column")
            else:
                logger.info("✓ Role column already exists - no migration needed")
                
        except Exception as e:
            logger.error(f"Migration error: {str(e)}")
            raise


async def init_db():
    """
    Initialize database:
    1. Check and migrate existing tables
    2. Create new tables if they don't exist
    """
    logger.info("Initializing database...")
    
    try:
        # Import all models to register them with Base
        from backend.orm.user import User
        from backend.orm.course import Course
        from backend.orm.subject import Subject
        from backend.orm.curriculum import CourseCurriculum
        from backend.orm.content_module import ContentModule  # PHASE 6
        from backend.orm.learn_content import LearnContent    # PHASE 6
        from backend.orm.case_content import CaseContent      # PHASE 6
        from backend.orm.practice_question import PracticeQuestion  # PHASE 6
        from backend.orm.user_notes import UserNotes          # PHASE 6
        from backend.orm.user_progress import UserProgress
        
        # ⭐ PHASE 8: Import progress tracking models
        from backend.orm.user_content_progress import UserContentProgress
        from backend.orm.practice_attempt import PracticeAttempt
        from backend.orm.subject_progress import SubjectProgress
        
        # First, handle migration for existing database
        await check_and_migrate_role_column()
        
        # Then create all tables (this will only create missing tables)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        logger.info("✓ Database initialization complete")
        
    except Exception as e:
        logger.error(f"Database initialization failed: {str(e)}")
        raise



async def close_db():
    """Close database connection"""
    await engine.dispose()
    logger.info("Database connection closed")