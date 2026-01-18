"""
backend/routes/student.py
Phase 3 & 4: Student-facing APIs for content availability, modules, and learning content
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from backend.database import get_db
from backend.orm.user import User
from backend.orm.curriculum import CourseCurriculum
from backend.orm.content_module import ContentModule, ModuleType, ModuleStatus
from backend.orm.learn_content import LearnContent
from backend.orm.case_content import CaseContent
from backend.orm.practice_question import PracticeQuestion
from backend.orm.user_notes import UserNotes
from backend.orm.user_content_progress import UserContentProgress, ContentType
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


class ModuleListItem(BaseModel):
    module_id: int
    title: str
    sequence_order: int
    content_count: int
    is_completed: bool


class SubjectModulesResponse(BaseModel):
    subject_id: int
    modules: List[ModuleListItem]


class ContentListItem(BaseModel):
    content_id: int
    title: str
    sequence_order: int
    is_completed: bool


class ModuleContentResponse(BaseModel):
    module_id: int
    content: List[ContentListItem]


class LearnContentDetailResponse(BaseModel):
    content_id: int
    module_id: int
    title: str
    body: str
    sequence_order: int
    is_completed: bool


@router.get("/subject/{subject_id}/availability", response_model=ContentAvailabilityResponse)
async def get_subject_availability(
    subject_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Check what content exists for a subject.
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
    learn_modules = learn_module_result.scalars().all()

    first_learn_id = None
    total_learn_count = 0
    if learn_modules:
        for module in learn_modules:
            learn_stmt = select(func.count(LearnContent.id)).where(LearnContent.module_id == module.id)
            learn_result = await db.execute(learn_stmt)
            total_learn_count += (learn_result.scalar() or 0)
            
            if first_learn_id is None:
                first_item_stmt = select(LearnContent.id).where(LearnContent.module_id == module.id).order_by(LearnContent.order_index).limit(1)
                first_item_result = await db.execute(first_item_stmt)
                first_learn_id = first_item_result.scalar()

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
        has_learning_content=total_learn_count > 0,
        has_cases=cases_count > 0,
        has_practice=practice_count > 0,
        has_notes=True,
        first_learning_content_id=first_learn_id,
        first_case_id=first_case_id,
        first_practice_id=first_practice_id,
        learn_count=total_learn_count,
        cases_count=cases_count,
        practice_count=practice_count,
        notes_count=notes_count
    )


@router.get("/subject/{subject_id}/modules", response_model=SubjectModulesResponse)
async def get_subject_modules(
    subject_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all LEARN modules for a subject in correct order.
    """
    modules_stmt = select(ContentModule).where(
        and_(
            ContentModule.subject_id == subject_id,
            ContentModule.module_type == ModuleType.LEARN,
            ContentModule.status == ModuleStatus.ACTIVE
        )
    ).order_by(ContentModule.order_index)
    
    modules_result = await db.execute(modules_stmt)
    modules = modules_result.scalars().all()
    
    module_list = []
    for module in modules:
        content_count_stmt = select(func.count(LearnContent.id)).where(
            LearnContent.module_id == module.id
        )
        content_count_result = await db.execute(content_count_stmt)
        content_count = content_count_result.scalar() or 0
        
        content_ids_stmt = select(LearnContent.id).where(LearnContent.module_id == module.id)
        content_ids_result = await db.execute(content_ids_stmt)
        content_ids = content_ids_result.scalars().all()
        
        is_completed = False
        if content_ids:
            completed_count_stmt = select(func.count(UserContentProgress.id)).where(
                and_(
                    UserContentProgress.user_id == current_user.id,
                    UserContentProgress.content_type == ContentType.LEARN,
                    UserContentProgress.content_id.in_(content_ids),
                    UserContentProgress.is_completed == True
                )
            )
            completed_count_result = await db.execute(completed_count_stmt)
            completed_count = completed_count_result.scalar() or 0
            
            is_completed = (completed_count == len(content_ids))
        
        module_list.append(ModuleListItem(
            module_id=module.id,
            title=module.title,
            sequence_order=module.order_index,
            content_count=content_count,
            is_completed=is_completed
        ))
    
    return SubjectModulesResponse(
        subject_id=subject_id,
        modules=module_list
    )


@router.get("/module/{module_id}/content", response_model=ModuleContentResponse)
async def get_module_content(
    module_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all learning content for a module in correct order.
    """
    content_stmt = select(LearnContent).where(
        LearnContent.module_id == module_id
    ).order_by(LearnContent.order_index)
    
    content_result = await db.execute(content_stmt)
    contents = content_result.scalars().all()
    
    content_list = []
    for content in contents:
        progress_stmt = select(UserContentProgress).where(
            and_(
                UserContentProgress.user_id == current_user.id,
                UserContentProgress.content_type == ContentType.LEARN,
                UserContentProgress.content_id == content.id
            )
        )
        progress_result = await db.execute(progress_stmt)
        progress = progress_result.scalar_one_or_none()
        
        content_list.append(ContentListItem(
            content_id=content.id,
            title=content.title,
            sequence_order=content.order_index,
            is_completed=progress.is_completed if progress else False
        ))
    
    return ModuleContentResponse(
        module_id=module_id,
        content=content_list
    )


@router.get("/content/{content_id}", response_model=LearnContentDetailResponse)
async def get_content_detail(
    content_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed learning content.
    """
    content_stmt = select(LearnContent).where(LearnContent.id == content_id)
    content_result = await db.execute(content_stmt)
    content = content_result.scalar_one_or_none()
    
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
    
    progress_stmt = select(UserContentProgress).where(
        and_(
            UserContentProgress.user_id == current_user.id,
            UserContentProgress.content_type == ContentType.LEARN,
            UserContentProgress.content_id == content.id
        )
    )
    progress_result = await db.execute(progress_stmt)
    progress = progress_result.scalar_one_or_none()
    
    if not progress:
        progress = UserContentProgress(
            user_id=current_user.id,
            content_type=ContentType.LEARN,
            content_id=content.id,
            is_completed=False,
            last_viewed_at=datetime.utcnow()
        )
        db.add(progress)
    else:
        progress.last_viewed_at = datetime.utcnow()
        progress.view_count += 1
    
    await db.commit()
    
    return LearnContentDetailResponse(
        content_id=content.id,
        module_id=content.module_id,
        title=content.title,
        body=content.body,
        sequence_order=content.order_index,
        is_completed=progress.is_completed if progress else False
    )


@router.post("/content/{content_id}/complete")
async def mark_content_complete(
    content_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Mark a learning content as completed.
    """
    progress_stmt = select(UserContentProgress).where(
        and_(
            UserContentProgress.user_id == current_user.id,
            UserContentProgress.content_type == ContentType.LEARN,
            UserContentProgress.content_id == content_id
        )
    )
    progress_result = await db.execute(progress_stmt)
    progress = progress_result.scalar_one_or_none()
    
    if not progress:
        progress = UserContentProgress(
            user_id=current_user.id,
            content_type=ContentType.LEARN,
            content_id=content_id,
            is_completed=True,
            completed_at=datetime.utcnow(),
            last_viewed_at=datetime.utcnow()
        )
        db.add(progress)
    else:
        progress.is_completed = True
        progress.completed_at = datetime.utcnow()
    
    await db.commit()
    return {"status": "success", "message": "Content marked as completed"}
