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
            result = await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            )
            table_exists = result.fetchone() is not None
            
            if not table_exists:
                logger.info("Users table doesn't exist yet - will be created fresh")
                return
            
            result = await conn.execute(text("PRAGMA table_info(users)"))
            columns = [row[1] for row in result.fetchall()]
            
            if 'role' not in columns:
                logger.warning("Role column missing - performing migration")
                
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
                
                await conn.execute(text("DROP TABLE users"))
                await conn.execute(text("ALTER TABLE users_new RENAME TO users"))
                
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
        from backend.orm import (
            User, Course, Subject, CourseCurriculum,
            ContentModule, LearnContent, CaseContent, PracticeQuestion,
            UserContentProgress, PracticeAttempt, SubjectProgress, UserNotes,
            ExamSession, ExamAnswer, ExamAnswerEvaluation, ExamSessionEvaluation,
            Bookmark, SavedSearch
        )
        from backend.orm.user_progress import UserProgress
        from backend.orm.smart_note import SmartNote 
        from backend.orm.semantic_embedding import SemanticEmbedding
        from backend.orm.tutor_session import TutorSession 
        from backend.orm.tutor_message import TutorMessage 
        from backend.orm.topic_mastery import TopicMastery 
        from backend.orm.study_plan import StudyPlan
        from backend.orm.study_plan_item import StudyPlanItem
        
        await check_and_migrate_role_column()
        
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