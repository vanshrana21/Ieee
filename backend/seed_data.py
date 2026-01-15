"""
Seed initial data for LegalAI Research
Run once: python -m backend.seed_data
"""
import asyncio
from backend.database import AsyncSessionLocal

# ⭐ CRITICAL: Import ALL models first to configure relationships
from backend.orm.base import Base
from backend.orm.user import User
from backend.orm.course import Course
from backend.orm.subject import Subject
from backend.orm.curriculum import CourseCurriculum
from backend.orm.content_module import ContentModule
from backend.orm.learn_content import LearnContent
from backend.orm.case_content import CaseContent
from backend.orm.practice_question import PracticeQuestion
from backend.orm.user_notes import UserNotes
from backend.orm.user_progress import UserProgress
from backend.orm.user_content_progress import UserContentProgress
from backend.orm.practice_attempt import PracticeAttempt
from backend.orm.subject_progress import SubjectProgress


async def seed_courses():
    """Seed the 3 law courses"""
    from sqlalchemy import select
    
    async with AsyncSessionLocal() as session:
        # Check if courses already exist
        result = await session.execute(select(Course))
        existing = result.scalars().all()
        
        if existing:
            print(f"✓ Courses already seeded ({len(existing)} found)")
            return
        
        courses = [
            Course(
                id=1,
                name="BA LLB",
                code="BA_LLB",
                duration_years=5,
                total_semesters=10,
                description="5 Year Integrated BA LLB Program"
            ),
            Course(
                id=2,
                name="BBA LLB",
                code="BBA_LLB",
                duration_years=5,
                total_semesters=10,
                description="5 Year Integrated BBA LLB Program"
            ),
            Course(
                id=3,
                name="LLB",
                code="LLB",
                duration_years=3,
                total_semesters=6,
                description="3 Year LLB Program"
            )
        ]
        
        session.add_all(courses)
        await session.commit()
        print(f"✓ Successfully seeded {len(courses)} courses")


if __name__ == "__main__":
    print("Starting database seed...")
    asyncio.run(seed_courses())
    print("✓ Seed complete!")