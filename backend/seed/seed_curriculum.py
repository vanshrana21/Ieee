"""
backend/seed/seed_curriculum.py
Map subjects to courses and semesters (idempotent)
"""
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import select, func
from backend.database import AsyncSessionLocal, init_db
from backend.orm.course import Course
from backend.orm.subject import Subject
from backend.orm.curriculum import CourseCurriculum

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================
# BA LLB CURRICULUM (10 Semesters)
# ============================================
BA_LLB_CURRICULUM = [
    # Semester 1
    {"subject_code": "ENG101", "semester": 1, "is_elective": False, "order": 1},
    {"subject_code": "POL101", "semester": 1, "is_elective": False, "order": 2},
    {"subject_code": "ECO101", "semester": 1, "is_elective": False, "order": 3},
    {"subject_code": "SOC101", "semester": 1, "is_elective": False, "order": 4},
    
    # Semester 2
    {"subject_code": "ENG102", "semester": 2, "is_elective": False, "order": 1},
    {"subject_code": "POL102", "semester": 2, "is_elective": False, "order": 2},
    {"subject_code": "ECO102", "semester": 2, "is_elective": False, "order": 3},
    {"subject_code": "LAW201", "semester": 2, "is_elective": False, "order": 4},
    
    # Semester 3
    {"subject_code": "POL103", "semester": 3, "is_elective": False, "order": 1},
    {"subject_code": "ECO103", "semester": 3, "is_elective": False, "order": 2},
    {"subject_code": "LAW202", "semester": 3, "is_elective": False, "order": 3},
    {"subject_code": "LAW204", "semester": 3, "is_elective": False, "order": 4},
    
    # Semester 4
    {"subject_code": "POL104", "semester": 4, "is_elective": False, "order": 1},
    {"subject_code": "SOC102", "semester": 4, "is_elective": False, "order": 2},
    {"subject_code": "LAW203", "semester": 4, "is_elective": False, "order": 3},
    {"subject_code": "LAW205", "semester": 4, "is_elective": False, "order": 4},
    
    # Semester 5
    {"subject_code": "POL105", "semester": 5, "is_elective": False, "order": 1},
    {"subject_code": "LAW206", "semester": 5, "is_elective": False, "order": 2},
    {"subject_code": "LAW208", "semester": 5, "is_elective": False, "order": 3},
    {"subject_code": "LAW301", "semester": 5, "is_elective": False, "order": 4},
    
    # Semester 6
    {"subject_code": "POL106", "semester": 6, "is_elective": False, "order": 1},
    {"subject_code": "LAW207", "semester": 6, "is_elective": False, "order": 2},
    {"subject_code": "LAW209", "semester": 6, "is_elective": False, "order": 3},
    {"subject_code": "LAW302", "semester": 6, "is_elective": False, "order": 4},
    
    # Semester 7
    {"subject_code": "LAW210", "semester": 7, "is_elective": False, "order": 1},
    {"subject_code": "LAW211", "semester": 7, "is_elective": False, "order": 2},
    {"subject_code": "LAW214", "semester": 7, "is_elective": False, "order": 3},
    {"subject_code": "LAW303", "semester": 7, "is_elective": False, "order": 4},
    
    # Semester 8
    {"subject_code": "LAW212", "semester": 8, "is_elective": False, "order": 1},
    {"subject_code": "LAW213", "semester": 8, "is_elective": False, "order": 2},
    {"subject_code": "LAW402", "semester": 8, "is_elective": False, "order": 3},
    {"subject_code": "LAW501", "semester": 8, "is_elective": True, "order": 4},
    
    # Semester 9
    {"subject_code": "LAW401", "semester": 9, "is_elective": False, "order": 1},
    {"subject_code": "LAW403", "semester": 9, "is_elective": False, "order": 2},
    {"subject_code": "LAW502", "semester": 9, "is_elective": True, "order": 3},
    {"subject_code": "LAW503", "semester": 9, "is_elective": True, "order": 4},
    
    # Semester 10
    {"subject_code": "LAW404", "semester": 10, "is_elective": False, "order": 1},
    {"subject_code": "LAW505", "semester": 10, "is_elective": True, "order": 2},
    {"subject_code": "LAW506", "semester": 10, "is_elective": True, "order": 3},
]


# ============================================
# BBA LLB CURRICULUM (10 Semesters)
# ============================================
BBA_LLB_CURRICULUM = [
    # Semester 1
    {"subject_code": "ENG101", "semester": 1, "is_elective": False, "order": 1},
    {"subject_code": "ECO101", "semester": 1, "is_elective": False, "order": 2},
    {"subject_code": "MGT101", "semester": 1, "is_elective": False, "order": 3},
    {"subject_code": "ACC101", "semester": 1, "is_elective": False, "order": 4},
    
    # Semester 2
    {"subject_code": "ENG102", "semester": 2, "is_elective": False, "order": 1},
    {"subject_code": "ECO102", "semester": 2, "is_elective": False, "order": 2},
    {"subject_code": "COM101", "semester": 2, "is_elective": False, "order": 3},
    {"subject_code": "LAW201", "semester": 2, "is_elective": False, "order": 4},
    
    # Semester 3
    {"subject_code": "ECO103", "semester": 3, "is_elective": False, "order": 1},
    {"subject_code": "POL101", "semester": 3, "is_elective": False, "order": 2},
    {"subject_code": "LAW202", "semester": 3, "is_elective": False, "order": 3},
    {"subject_code": "LAW204", "semester": 3, "is_elective": False, "order": 4},
    
    # Semester 4
    {"subject_code": "POL102", "semester": 4, "is_elective": False, "order": 1},
    {"subject_code": "LAW203", "semester": 4, "is_elective": False, "order": 2},
    {"subject_code": "LAW205", "semester": 4, "is_elective": False, "order": 3},
    {"subject_code": "LAW210", "semester": 4, "is_elective": False, "order": 4},
    
    # Semester 5
    {"subject_code": "LAW206", "semester": 5, "is_elective": False, "order": 1},
    {"subject_code": "LAW208", "semester": 5, "is_elective": False, "order": 2},
    {"subject_code": "LAW301", "semester": 5, "is_elective": False, "order": 3},
    {"subject_code": "LAW504", "semester": 5, "is_elective": False, "order": 4},
    
    # Semester 6
    {"subject_code": "LAW207", "semester": 6, "is_elective": False, "order": 1},
    {"subject_code": "LAW209", "semester": 6, "is_elective": False, "order": 2},
    {"subject_code": "LAW302", "semester": 6, "is_elective": False, "order": 3},
    {"subject_code": "LAW506", "semester": 6, "is_elective": False, "order": 4},
    
    # Semester 7
    {"subject_code": "LAW211", "semester": 7, "is_elective": False, "order": 1},
    {"subject_code": "LAW214", "semester": 7, "is_elective": False, "order": 2},
    {"subject_code": "LAW303", "semester": 7, "is_elective": False, "order": 3},
    {"subject_code": "LAW507", "semester": 7, "is_elective": False, "order": 4},
    
    # Semester 8
    {"subject_code": "LAW212", "semester": 8, "is_elective": False, "order": 1},
    {"subject_code": "LAW213", "semester": 8, "is_elective": False, "order": 2},
    {"subject_code": "LAW402", "semester": 8, "is_elective": False, "order": 3},
    {"subject_code": "LAW501", "semester": 8, "is_elective": True, "order": 4},
    
    # Semester 9
    {"subject_code": "LAW401", "semester": 9, "is_elective": False, "order": 1},
    {"subject_code": "LAW403", "semester": 9, "is_elective": False, "order": 2},
    {"subject_code": "LAW502", "semester": 9, "is_elective": True, "order": 3},
    {"subject_code": "LAW503", "semester": 9, "is_elective": True, "order": 4},
    
    # Semester 10
    {"subject_code": "LAW404", "semester": 10, "is_elective": False, "order": 1},
    {"subject_code": "LAW509", "semester": 10, "is_elective": True, "order": 2},
    {"subject_code": "LAW510", "semester": 10, "is_elective": True, "order": 3},
]


# ============================================
# LLB CURRICULUM (6 Semesters)
# ============================================
LLB_CURRICULUM = [
    # Semester 1
    {"subject_code": "LAW201", "semester": 1, "is_elective": False, "order": 1},
    {"subject_code": "LAW202", "semester": 1, "is_elective": False, "order": 2},
    {"subject_code": "LAW204", "semester": 1, "is_elective": False, "order": 3},
    {"subject_code": "LAW208", "semester": 1, "is_elective": False, "order": 4},
    
    # Semester 2
    {"subject_code": "LAW203", "semester": 2, "is_elective": False, "order": 1},
    {"subject_code": "LAW205", "semester": 2, "is_elective": False, "order": 2},
    {"subject_code": "LAW214", "semester": 2, "is_elective": False, "order": 3},
    {"subject_code": "LAW301", "semester": 2, "is_elective": False, "order": 4},
    
    # Semester 3
    {"subject_code": "LAW206", "semester": 3, "is_elective": False, "order": 1},
    {"subject_code": "LAW209", "semester": 3, "is_elective": False, "order": 2},
    {"subject_code": "LAW302", "semester": 3, "is_elective": False, "order": 3},
    {"subject_code": "LAW303", "semester": 3, "is_elective": False, "order": 4},
    
    # Semester 4
    {"subject_code": "LAW207", "semester": 4, "is_elective": False, "order": 1},
    {"subject_code": "LAW210", "semester": 4, "is_elective": False, "order": 2},
    {"subject_code": "LAW211", "semester": 4, "is_elective": False, "order": 3},
    {"subject_code": "LAW402", "semester": 4, "is_elective": False, "order": 4},
    
    # Semester 5
    {"subject_code": "LAW212", "semester": 5, "is_elective": False, "order": 1},
    {"subject_code": "LAW213", "semester": 5, "is_elective": False, "order": 2},
    {"subject_code": "LAW401", "semester": 5, "is_elective": False, "order": 3},
    {"subject_code": "LAW501", "semester": 5, "is_elective": True, "order": 4},
    
    # Semester 6
    {"subject_code": "LAW403", "semester": 6, "is_elective": False, "order": 1},
    {"subject_code": "LAW404", "semester": 6, "is_elective": False, "order": 2},
    {"subject_code": "LAW502", "semester": 6, "is_elective": True, "order": 3},
    {"subject_code": "LAW503", "semester": 6, "is_elective": True, "order": 4},
]


async def get_course_by_code(session, code: str):
    """Get course by code (no hard-coded IDs)"""
    stmt = select(Course).where(Course.code == code)
    result = await session.execute(stmt)
    course = result.scalar_one_or_none()
    if not course:
        raise ValueError(f"❌ Course not found: {code}")
    return course


async def get_subject_by_code(session, code: str):
    """Get subject by code (no hard-coded IDs)"""
    stmt = select(Subject).where(Subject.code == code)
    result = await session.execute(stmt)
    subject = result.scalar_one_or_none()
    if not subject:
        raise ValueError(f"❌ Subject not found: {code}")
    return subject


async def seed_course_curriculum(session, course_code: str, curriculum_data: list):
    """Seed curriculum for a specific course (idempotent)"""
    course = await get_course_by_code(session, course_code)
    logger.info(f"\n📖 Mapping curriculum for {course.name}")
    logger.info("-" * 60)
    
    created_count = 0
    existing_count = 0
    
    for item in curriculum_data:
        try:
            subject = await get_subject_by_code(session, item["subject_code"])
        except ValueError as e:
            logger.warning(f"⚠️  Skipping: {str(e)}")
            continue
        
        # Check if mapping already exists (idempotent)
        stmt = select(CourseCurriculum).where(
            CourseCurriculum.course_id == course.id,
            CourseCurriculum.subject_id == subject.id,
            CourseCurriculum.semester_number == item["semester"]
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing:
            existing_count += 1
            continue
        
        # Create new mapping
        curriculum = CourseCurriculum(
            course_id=course.id,
            subject_id=subject.id,
            semester_number=item["semester"],
            is_elective=item["is_elective"],
            display_order=item["order"],
            is_active=True
        )
        session.add(curriculum)
        created_count += 1
        
        elective_text = " (Elective)" if item["is_elective"] else ""
        logger.info(
            f"✓ {course.name} | Semester {item['semester']} | "
            f"{subject.title}{elective_text} mapped"
        )
    
    await session.commit()
    logger.info(f"RESULT: {created_count} created, {existing_count} already exist")


async def seed_all_curriculum():
    """Seed curriculum for all courses (idempotent)"""
    async with AsyncSessionLocal() as session:
        try:
            logger.info("=" * 60)
            logger.info("SEEDING CURRICULUM")
            logger.info("=" * 60)
            
            # Seed BA LLB
            await seed_course_curriculum(session, "BA_LLB", BA_LLB_CURRICULUM)
            
            # Seed BBA LLB
            await seed_course_curriculum(session, "BBA_LLB", BBA_LLB_CURRICULUM)
            
            # Seed LLB
            await seed_course_curriculum(session, "LLB", LLB_CURRICULUM)
            
            logger.info("\n" + "=" * 60)
            logger.info("CURRICULUM SUMMARY")
            logger.info("=" * 60)
            
            # Summary for each course
            for course_code in ["BA_LLB", "BBA_LLB", "LLB"]:
                course = await get_course_by_code(session, course_code)
                
                stmt = select(func.count(CourseCurriculum.id)).where(
                    CourseCurriculum.course_id == course.id
                )
                result = await session.execute(stmt)
                total = result.scalar()
                
                stmt = select(func.count(CourseCurriculum.id)).where(
                    CourseCurriculum.course_id == course.id,
                    CourseCurriculum.is_elective == True
                )
                result = await session.execute(stmt)
                electives = result.scalar()
                
                logger.info(
                    f"{course.name}: {total} total ({total - electives} mandatory, {electives} elective)"
                )
            
        except Exception as e:
            logger.error(f"❌ Error seeding curriculum: {str(e)}")
            await session.rollback()
            raise


async def main():
    """Main entry point"""
    await init_db()
    await seed_all_curriculum()
    logger.info("\n✅ Curriculum seeding complete")


if __name__ == "__main__":
    asyncio.run(main())