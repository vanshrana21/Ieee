"""
backend/routes/student.py
Phase 3: Student-facing APIs for content availability and study flow
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from pydantic import BaseModel
from typing import Optional

from backend.database import get_db
from backend.orm.user import User
from backend.orm.curriculum import CourseCurriculum
from backend.orm.content_module import ContentModule, ModuleType, ModuleStatus
from backend.orm.learn_content import LearnContent
from backend.orm.case_content import CaseContent
from backend.orm.practice_question import PracticeQuestion
from backend.orm.user_notes import UserNotes
from backend.routes.auth import get_current_user

router = APIRouter(prefix="/student", tags=["Student"])


class ContentAvailabilityResponse(BaseModel):
    subject_id: int
    has_learning_content: bool
    has_cases: bool
    has_practice: bool
    has_notes: bool
    first_learning_content_id: Optional[int] = None
    first_case_id: Optional[int] = None
    first_practice_id: Optional[int] = None
    learn_count: int = 0
    cases_count: int = 0
    practice_count: int = 0
    notes_count: int = 0


@router.get("/subject/{subject_id}/availability", response_model=ContentAvailabilityResponse)
async def get_subject_availability(
    subject_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 3: Check what content exists for a subject.
    
    Returns availability flags for each study mode:
    - has_learning_content: True if LearnContent items exist
    - has_cases: True if CaseContent items exist  
    - has_practice: True if PracticeQuestion items exist
    - has_notes: True if user has notes for this subject
    
    Also returns first content IDs for direct navigation.
    """
    if not current_user.course_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User not enrolled in any course"
        )

    curriculum_stmt = select(CourseCurriculum).where(
        and_(
            CourseCurriculum.course_id == current_user.course_id,
            CourseCurriculum.subject_id == subject_id,
            CourseCurriculum.is_active == True
        )
    )
    curriculum_result = await db.execute(curriculum_stmt)
    if not curriculum_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Subject not in your curriculum"
        )

    learn_module_stmt = select(ContentModule).where(
        and_(
            ContentModule.subject_id == subject_id,
            ContentModule.module_type == ModuleType.LEARN,
            ContentModule.status == ModuleStatus.ACTIVE
        )
    )
    learn_module_result = await db.execute(learn_module_stmt)
    learn_module = learn_module_result.scalar_one_or_none()

    first_learn_id = None
    learn_count = 0
    if learn_module:
        learn_stmt = (
            select(LearnContent)
            .where(LearnContent.module_id == learn_module.id)
            .order_by(LearnContent.order_index)
        )
        learn_result = await db.execute(learn_stmt)
        learn_items = learn_result.scalars().all()
        learn_count = len(learn_items)
        if learn_items:
            first_learn_id = learn_items[0].id

    cases_module_stmt = select(ContentModule).where(
        and_(
            ContentModule.subject_id == subject_id,
            ContentModule.module_type == ModuleType.CASES,
            ContentModule.status == ModuleStatus.ACTIVE
        )
    )
    cases_module_result = await db.execute(cases_module_stmt)
    cases_module = cases_module_result.scalar_one_or_none()

    first_case_id = None
    cases_count = 0
    if cases_module:
        cases_stmt = (
            select(CaseContent)
            .where(CaseContent.module_id == cases_module.id)
            .order_by(CaseContent.year.desc())
        )
        cases_result = await db.execute(cases_stmt)
        case_items = cases_result.scalars().all()
        cases_count = len(case_items)
        if case_items:
            first_case_id = case_items[0].id

    practice_module_stmt = select(ContentModule).where(
        and_(
            ContentModule.subject_id == subject_id,
            ContentModule.module_type == ModuleType.PRACTICE,
            ContentModule.status == ModuleStatus.ACTIVE
        )
    )
    practice_module_result = await db.execute(practice_module_stmt)
    practice_module = practice_module_result.scalar_one_or_none()

    first_practice_id = None
    practice_count = 0
    if practice_module:
        practice_stmt = (
            select(PracticeQuestion)
            .where(PracticeQuestion.module_id == practice_module.id)
            .order_by(PracticeQuestion.order_index)
        )
        practice_result = await db.execute(practice_stmt)
        practice_items = practice_result.scalars().all()
        practice_count = len(practice_items)
        if practice_items:
            first_practice_id = practice_items[0].id

    notes_stmt = select(func.count(UserNotes.id)).where(
        and_(
            UserNotes.user_id == current_user.id,
            UserNotes.subject_id == subject_id
        )
    )
    notes_result = await db.execute(notes_stmt)
    notes_count = notes_result.scalar() or 0

    return ContentAvailabilityResponse(
        subject_id=subject_id,
        has_learning_content=learn_count > 0,
        has_cases=cases_count > 0,
        has_practice=practice_count > 0,
        has_notes=True,
        first_learning_content_id=first_learn_id,
        first_case_id=first_case_id,
        first_practice_id=first_practice_id,
        learn_count=learn_count,
        cases_count=cases_count,
        practice_count=practice_count,
        notes_count=notes_count
    )
