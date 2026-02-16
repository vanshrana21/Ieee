"""
backend/database.py
Database configuration with automatic migration support
"""
import os
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text
from dotenv import load_dotenv

# Import Base from orm.base to avoid circular imports
from backend.orm.base import Base
import backend.orm  # force load all models


# Import all ORM models to ensure registry is complete
import backend.orm  # ensures all models are registered

load_dotenv()

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./legalai.db")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set")

# Connection pool configuration for high concurrency
# SQLite has different pool needs than PostgreSQL
if "sqlite" in DATABASE_URL.lower():
    # SQLite: Use QueuePool with proper settings for concurrent access
    # Connect arguments for SQLite to handle concurrent writes
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        future=True,
        pool_pre_ping=True,
        pool_size=10,           # Keep some connections ready
        max_overflow=20,        # Allow more connections under load
        pool_timeout=30,        # Wait up to 30s for connection
        connect_args={
            "timeout": 30.0,   # SQLite busy timeout in seconds
        }
    )
else:
    # PostgreSQL/MySQL: Use standard pool with larger size
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        future=True,
        pool_pre_ping=True,
        pool_size=20,           # Base pool size
        max_overflow=30,        # Additional connections under load
        pool_timeout=30,        # Wait up to 30s for connection
        pool_recycle=3600,      # Recycle connections after 1 hour
    )

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db():
    """Dependency for getting async database session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def check_and_migrate_institution_column():
    """
    Check if the 'institution_id' column exists in users table and add it if missing.
    Also adds refresh_token and refresh_token_expires columns from Phase 5A.
    Idempotent: safe to run multiple times.
    """
    async with engine.begin() as conn:
        try:
            # Check if users table exists
            result = await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            )
            table_exists = result.fetchone() is not None
            
            if not table_exists:
                logger.info("Users table doesn't exist yet - skipping column migrations")
                return
            
            # Check existing columns
            result = await conn.execute(text("PRAGMA table_info(users)"))
            columns = [row[1] for row in result.fetchall()]
            
            # Add institution_id if missing
            if 'institution_id' not in columns:
                logger.warning("institution_id column missing - adding column")
                await conn.execute(text("ALTER TABLE users ADD COLUMN institution_id INTEGER"))
                logger.info("✓ Successfully added institution_id column")
            else:
                logger.info("✓ institution_id column already exists")
            
            # Add refresh_token if missing (Phase 5A)
            if 'refresh_token' not in columns:
                logger.warning("refresh_token column missing - adding column")
                await conn.execute(text("ALTER TABLE users ADD COLUMN refresh_token VARCHAR"))
                logger.info("✓ Successfully added refresh_token column")
            else:
                logger.info("✓ refresh_token column already exists")
            
            # Add refresh_token_expires if missing (Phase 5A)
            if 'refresh_token_expires' not in columns:
                logger.warning("refresh_token_expires column missing - adding column")
                await conn.execute(text("ALTER TABLE users ADD COLUMN refresh_token_expires TIMESTAMP"))
                logger.info("✓ Successfully added refresh_token_expires column")
            else:
                logger.info("✓ refresh_token_expires column already exists")
                
        except Exception as e:
            logger.error(f"Column migration error: {str(e)}")
            raise


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


async def check_and_migrate_moot_cases_columns():
    """
    PHASE: Case Library Upgrade
    Check and add new columns to moot_cases table if missing.
    Safe ALTER TABLE ADD COLUMN for SQLite.
    """
    from sqlalchemy import text
    
    # New columns to add: (column_name, column_type, default_value)
    new_columns = [
        ("external_case_code", "VARCHAR(50)", None),
        ("topic", "VARCHAR(100)", None),
        ("citation", "VARCHAR(255)", None),
        ("short_proposition", "TEXT", None),
        ("constitutional_articles", "JSON", None),
        ("key_issues", "JSON", None),
        ("landmark_cases_expected", "JSON", None),
        ("complexity_level", "INTEGER", "3"),
    ]
    
    try:
        async with engine.begin() as conn:
            # Check if moot_cases table exists
            result = await conn.execute(text("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='moot_cases'
            """))
            table_exists = result.fetchone()
            
            if not table_exists:
                logger.info("Moot cases table doesn't exist yet - skipping migration")
                return
            
            # Get existing columns
            result = await conn.execute(text("PRAGMA table_info(moot_cases)"))
            existing_columns = {row[1] for row in result.fetchall()}
            
            # Add missing columns
            columns_added = 0
            for col_name, col_type, default in new_columns:
                if col_name not in existing_columns:
                    if default:
                        sql = f"ALTER TABLE moot_cases ADD COLUMN {col_name} {col_type} DEFAULT {default}"
                    else:
                        sql = f"ALTER TABLE moot_cases ADD COLUMN {col_name} {col_type}"
                    
                    logger.info(f"Adding column {col_name} to moot_cases")
                    await conn.execute(text(sql))
                    columns_added += 1
            
            if columns_added > 0:
                logger.info(f"✓ Successfully added {columns_added} columns to moot_cases table")
            else:
                logger.info("✓ All moot_cases columns already exist - no migration needed")
                
    except Exception as e:
        logger.error(f"Moot cases migration error: {str(e)}")
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
        # PHASE 1/2: Core models
        from backend.orm.user import User
        from backend.orm.course import Course
        from backend.orm.subject import Subject
        
        # PHASE 2: Competition Infrastructure
        from backend.orm.competition import Competition
        from backend.orm.team import Team, TeamMember
        from backend.orm.memorial import MemorialSubmission
        from backend.orm.oral_round import OralRound
        
        # PHASE 5/6: Moot court and submissions
        from backend.orm.moot_case import MootCase
        from backend.orm.moot_project import MootProject
        from backend.orm.submission import Submission
        from backend.orm.team_activity import TeamActivityLog
        
        # PHASE 3: Curriculum
        from backend.orm.curriculum import CourseCurriculum
        from backend.orm.content_module import ContentModule
        from backend.orm.learn_content import LearnContent
        from backend.orm.case_content import CaseContent
        from backend.orm.practice_question import PracticeQuestion
        from backend.orm.user_notes import UserNotes
        from backend.orm.user_progress import UserProgress
        
        # PHASE 6C: Bookmarks and saved items
        from backend.orm.bookmark import Bookmark
        from backend.orm.saved_search import SavedSearch
        from backend.orm.smart_note import SmartNote
        from backend.orm.semantic_embedding import SemanticEmbedding
        
        # PHASE 8: AI tutoring and progress
        from backend.orm.tutor_session import TutorSession
        from backend.orm.tutor_message import TutorMessage
        from backend.orm.topic_mastery import TopicMastery
        from backend.orm.study_plan import StudyPlan
        from backend.orm.study_plan_item import StudyPlanItem
        from backend.orm.ba_llb_curriculum import BALLBSemester, BALLBSubject, BALLBModule
        
        # PHASE 2: AI Moot Court Practice Mode
        from backend.orm.ai_oral_session import AIOralSession, AIOralTurn
        
        # PHASE 8: Progress tracking
        from backend.orm.user_content_progress import UserContentProgress
        from backend.orm.practice_attempt import PracticeAttempt
        from backend.orm.subject_progress import SubjectProgress
        
        # First, handle migration for existing database
        await check_and_migrate_role_column()
        await check_and_migrate_institution_column()
        await check_and_migrate_moot_cases_columns()  # NEW: Phase Case Library migration
        
        # Log database dialect
        logger.info(f"Database dialect: {engine.url.get_backend_name()}")
        if engine.url.get_backend_name() == "sqlite":
            logger.warning("Running on SQLite — JSONB downgraded to JSON.")
        
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


async def seed_moot_cases(db: AsyncSession):
    """
    Seed default moot cases if none exist.
    Called during startup after DB initialization.
    """
    from sqlalchemy import select, func
    from backend.orm.moot_case import MootCase
    
    try:
        # Check if any MootCase exists
        result = await db.execute(select(func.count()).select_from(MootCase))
        count = result.scalar()
        
        if count == 0:
            logger.info("No moot cases found - seeding default case")
            
            default_case = MootCase(
                title="Justice K.S. Puttaswamy vs Union of India",
                description="Landmark judgment establishing Right to Privacy as Fundamental Right",
                legal_domain="constitutional",
                difficulty_level="advanced"
            )
            
            db.add(default_case)
            await db.commit()
            
            logger.info("✓ Successfully seeded default moot case (ID: %s)", default_case.id)
        else:
            logger.info("✓ Moot cases already exist (%d cases) - skipping seed", count)
            
    except Exception as e:
        logger.error(f"Failed to seed moot cases: {str(e)}")
        await db.rollback()
        raise