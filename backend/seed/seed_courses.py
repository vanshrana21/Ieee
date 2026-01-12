"""
backend/seed/seed_courses.py
Seed Indian law degree programs (idempotent)
"""
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import select
from backend.database import AsyncSessionLocal, init_db
from backend.orm.course import Course

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


COURSES = [
    {
        "name": "BA LLB",
        "code": "BA_LLB",
        "duration_years": 5,
        "total_semesters": 10,
        "description": "Bachelor of Arts & Bachelor of Legislative Law - 5-year integrated program"
    },
    {
        "name": "BBA LLB",
        "code": "BBA_LLB",
        "duration_years": 5,
        "total_semesters": 10,
        "description": "Bachelor of Business Administration & Bachelor of Legislative Law - 5-year integrated program"
    },
    {
        "name": "LLB",
        "code": "LLB",
        "duration_years": 3,
        "total_semesters": 6,
        "description": "Bachelor of Legislative Law - 3-year program for graduates"
    },
]


async def seed_courses():
    """Seed courses table (idempotent)"""
    async with AsyncSessionLocal() as session:
        try:
            logger.info("=" * 60)
            logger.info("SEEDING COURSES")
            logger.info("=" * 60)
            
            created_count = 0
            existing_count = 0
            
            for course_data in COURSES:
                # Check if course already exists
                stmt = select(Course).where(Course.code == course_data["code"])
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()
                
                if existing:
                    logger.info(f"✓ Course {course_data['name']} exists")
                    existing_count += 1
                    continue
                
                # Create new course
                course = Course(**course_data)
                session.add(course)
                logger.info(f"✓ Course {course_data['name']} created")
                created_count += 1
            
            await session.commit()
            
            logger.info("=" * 60)
            logger.info(f"RESULT: {created_count} created, {existing_count} already exist")
            logger.info("=" * 60)
            
        except Exception as e:
            logger.error(f"❌ Error seeding courses: {str(e)}")
            await session.rollback()
            raise


async def main():
    """Main entry point"""
    await init_db()
    await seed_courses()
    logger.info("✅ Course seeding complete")


if __name__ == "__main__":
    asyncio.run(main())