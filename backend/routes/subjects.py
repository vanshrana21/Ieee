"""
backend/routes/subjects.py
Phase 9.1: Subject Context & Navigation
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import List
from pydantic import BaseModel

from backend.database import get_db
from backend.orm.user import User
from backend.orm.subject import Subject, SubjectCategory
from backend.orm.curriculum import CourseCurriculum
from backend.routes.auth import get_current_user

from backend.orm.content_module import ContentModule, ModuleType
from backend.orm.user_content_progress import UserContentProgress, ContentType
from backend.orm.learn_content import LearnContent
from backend.orm.case_content import CaseContent
from backend.orm.practice_question import PracticeQuestion

router = APIRouter(prefix="/subjects", tags=["Subjects"])

# ================= SCHEMAS =================

class ResumeResponse(BaseModel):
    type: str  # "learn", "case", "practice", "revision"
    content_id: int | None = None
    subject_id: int
    module_id: int | None = None
    message: str

class SubjectResponse(BaseModel):
    id: int
    title: str
    code: str
    description: str | None
    category: SubjectCategory
    semester: int
    is_elective: bool

    class Config:
        from_attributes = True

# ================= ENDPOINTS =================

@router.get("", response_model=List[SubjectResponse])
async def get_my_subjects(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Fetch subjects for the student's enrolled course and current/previous semesters.
    """
    if not current_user.course_id or not current_user.current_semester:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User enrollment incomplete"
        )

    # Fetch subjects from curriculum mapping
    stmt = (
        select(Subject, CourseCurriculum.semester_number, CourseCurriculum.is_elective)
        .join(CourseCurriculum, Subject.id == CourseCurriculum.subject_id)
        .where(
            and_(
                CourseCurriculum.course_id == current_user.course_id,
                CourseCurriculum.semester_number <= current_user.current_semester,
                CourseCurriculum.is_active == True
            )
        )
        .order_by(CourseCurriculum.semester_number, CourseCurriculum.display_order)
    )
    
    result = await db.execute(stmt)
    rows = result.all()
    
    subjects = []
    for subject, semester, is_elective in rows:
        subjects.append(SubjectResponse(
            id=subject.id,
            title=subject.title,
            code=subject.code,
            description=subject.description,
            category=subject.category,
            semester=semester,
            is_elective=is_elective
        ))
        
    return subjects

@router.get("/{subject_id}/resume", response_model=ResumeResponse)
async def resume_subject(
    subject_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 9.2: Resume Learning Engine
    Determines the exact next destination for a student.
    """
    # 1. Validate subject ownership
    curriculum_stmt = select(CourseCurriculum).where(
        and_(
            CourseCurriculum.course_id == current_user.course_id,
            CourseCurriculum.subject_id == subject_id,
            CourseCurriculum.is_active == True
        )
    )
    curriculum_result = await db.execute(curriculum_stmt)
    if not curriculum_result.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Subject not in your curriculum")

    # 2. Check for unfinished LEARN content
    # Get all LEARN items for this subject
    learn_stmt = (
        select(LearnContent)
        .join(ContentModule, LearnContent.module_id == ContentModule.id)
        .where(and_(
            ContentModule.subject_id == subject_id,
            ContentModule.module_type == ModuleType.LEARN
        ))
        .order_by(LearnContent.order_index)
    )
    learn_result = await db.execute(learn_stmt)
    learn_items = learn_result.scalars().all()

    for item in learn_items:
        progress_stmt = select(UserContentProgress).where(and_(
            UserContentProgress.user_id == current_user.id,
            UserContentProgress.content_type == ContentType.LEARN,
            UserContentProgress.content_id == item.id,
            UserContentProgress.is_completed == True
        ))
        p_res = await db.execute(progress_stmt)
        if not p_res.scalar_one_or_none():
            return ResumeResponse(
                type="learn",
                content_id=item.id,
                subject_id=subject_id,
                module_id=item.module_id,
                message="Resuming unfinished learn content"
            )

    # 3. Check for unfinished CASES content
    case_stmt = (
        select(CaseContent)
        .join(ContentModule, CaseContent.module_id == ContentModule.id)
        .where(and_(
            ContentModule.subject_id == subject_id,
            ContentModule.module_type == ModuleType.CASES
        ))
        .order_by(CaseContent.order_index if hasattr(CaseContent, 'order_index') else CaseContent.id)
    )
    case_result = await db.execute(case_stmt)
    case_items = case_result.scalars().all()

    for item in case_items:
        progress_stmt = select(UserContentProgress).where(and_(
            UserContentProgress.user_id == current_user.id,
            UserContentProgress.content_type == ContentType.CASE,
            UserContentProgress.content_id == item.id,
            UserContentProgress.is_completed == True
        ))
        p_res = await db.execute(progress_stmt)
        if not p_res.scalar_one_or_none():
            return ResumeResponse(
                type="case",
                content_id=item.id,
                subject_id=subject_id,
                module_id=item.module_id,
                message="Resuming unfinished case content"
            )

    # 4. Check for PRACTICE attempts
    practice_stmt = (
        select(PracticeQuestion)
        .join(ContentModule, PracticeQuestion.module_id == ContentModule.id)
        .where(and_(
            ContentModule.subject_id == subject_id,
            ContentModule.module_type == ModuleType.PRACTICE
        ))
        .order_by(PracticeQuestion.order_index)
    )
    practice_result = await db.execute(practice_stmt)
    practice_items = practice_result.scalars().all()

    if practice_items:
        # If any practice question is not completed, redirect to the first incomplete one
        for item in practice_items:
            progress_stmt = select(UserContentProgress).where(and_(
                UserContentProgress.user_id == current_user.id,
                UserContentProgress.content_type == ContentType.PRACTICE,
                UserContentProgress.content_id == item.id,
                UserContentProgress.is_completed == True
            ))
            p_res = await db.execute(progress_stmt)
            if not p_res.scalar_one_or_none():
                return ResumeResponse(
                    type="practice",
                    content_id=item.id,
                    subject_id=subject_id,
                    module_id=item.module_id,
                    message="Resuming practice"
                )

    # 5. Everything complete
    return ResumeResponse(
        type="revision",
        subject_id=subject_id,
        message="Subject complete! Time for revision."
    )

@router.post("/{subject_id}/select")
async def select_subject(
    subject_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Validate that a subject belongs to the student's course.
    Phase 9.1: Ensures subject context is valid.
    """
    if not current_user.course_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User not enrolled in any course"
        )

    stmt = (
        select(CourseCurriculum)
        .where(
            and_(
                CourseCurriculum.course_id == current_user.course_id,
                CourseCurriculum.subject_id == subject_id,
                CourseCurriculum.is_active == True
            )
        )
    )
    
    result = await db.execute(stmt)
    curriculum = result.scalar_one_or_none()
    
    if not curriculum:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This subject is not part of your curriculum"
        )
        
    return {"success": True, "subject_id": subject_id, "message": "Subject context validated"}
