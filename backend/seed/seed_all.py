"""
backend/seed/seed_all.py
Master seeding script - runs all seeders in correct order (idempotent)
"""
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.database import init_db
from backend.seed.seed_courses import seed_courses
from backend.seed.seed_subjects import seed_subjects
from backend.seed.seed_curriculum import seed_all_curriculum

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def seed_database():
    """Run all seeders in correct order (idempotent)"""
    try:
        logger.info("\n" + "🚀 " * 20)
        logger.info("STARTING DATABASE SEEDING")
        logger.info("🚀 " * 20 + "\n")
        
        # Step 1: Initialize database
        logger.info("[1/4] Initializing database...")
        await init_db()
        logger.info("✓ Database initialized\n")
        
        # Step 2: Seed courses (foundation)
        logger.info("[2/4] Seeding courses...")
        await seed_courses()
        logger.info("✓ Courses seeded\n")
        
        # Step 3: Seed subjects (foundation)
        logger.info("[3/4] Seeding subjects...")
        await seed_subjects()
        logger.info("✓ Subjects seeded\n")
        
        # Step 4: Seed curriculum (mappings)
        logger.info("[4/4] Seeding curriculum...")
        await seed_all_curriculum()
        logger.info("✓ Curriculum seeded\n")
        
        logger.info("=" * 60)
        logger.info("✅ DATABASE SEEDING COMPLETE!")
        logger.info("=" * 60)
        logger.info("\nNext steps:")
        logger.info("1. Start FastAPI server: uvicorn backend.main:app --reload")
        logger.info("2. Register users via /api/auth/register")
        logger.info("3. Assign course_id and current_semester to users")
        logger.info("4. Query curriculum: GET /api/curriculum/active")
        
    except Exception as e:
        logger.error(f"\n❌ Seeding failed: {str(e)}", exc_info=True)
        raise


if __name__ == "__main__":
    asyncio.run(seed_database())