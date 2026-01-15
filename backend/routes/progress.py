"""
backend/routes/progress.py
Progress tracking and content completion endpoints - Phase 4.3

This module handles:
- Individual content item completion
- Subject-level progress recalculation
- Content detail delivery with progress state
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload
from pydantic import BaseModel

from backend.database import get_db
from backend.orm.user import User
from backend.orm.learn_content import LearnContent
from backend.orm.case_content import CaseContent
from backend.orm.practice_question import PracticeQuestion
from backend.orm.content_module import ContentModule, ModuleType
from backend.orm.subject import Subject
from backend.orm.curriculum import CourseCurriculum
from backend.orm.user_content_progress import UserContentProgress, ContentType
from backend.orm.subject_progress import SubjectProgress
from backend.routes.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/content", tags=["Content Progress"])


# ================= SCHEMAS =================

class ContentCompleteRequest(BaseModel):
    """Request body for marking content complete"""
    time_spent_seconds: Optional[int] = None


# ================= HELPER FUNCTIONS =================

async def verify_content_access(
    db: AsyncSession,
    user: User,
    content_type: ContentType,
    content_id: int
) -> tuple[ContentModule, Subject]:
    """
    Verify user can access content and return module + subject.
    
    Args:
        db: Database session
        user: Current user
        content_type: Type of content (learn/case/practice)
        content_id: Content item ID
    
    Returns:
        (module, subject) if access granted
    
    Raises:
        HTTPException: 400/403/404 for access violations
    """
    # Validate user enrollment
    if not user.course_id or not user.current_semester:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User enrollment incomplete"
        )
    
    # Fetch content with module relationship
    if content_type == ContentType.LEARN:
        stmt = (
            select(LearnContent)
            .options(joinedload(LearnContent.module).joinedload(ContentModule.subject))
            .where(LearnContent.id == content_id)
        )
        result = await db.execute(stmt)
        content = result.scalar_one_or_none()
    elif content_type == ContentType.CASE:
        stmt = (
            select(CaseContent)
            .options(joinedload(CaseContent.module).joinedload(ContentModule.subject))
            .where(CaseContent.id == content_id)
        )
        result = await db.execute(stmt)
        content = result.scalar_one_or_none()
    elif content_type == ContentType.PRACTICE:
        stmt = (
            select(PracticeQuestion)
            .options(joinedload(PracticeQuestion.module).joinedload(ContentModule.subject))
            .where(PracticeQuestion.id == content_id)
        )
        result = await db.execute(stmt)
        content = result.scalar_one_or_none()
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid content type"
        )
    
    if not content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Content not found"
        )
    
    module = content.module
    if not module or not module.subject:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Content configuration error"
        )
    
    subject = module.subject
    
    # Check if subject is in user's course curriculum
    curriculum_stmt = (
        select(CourseCurriculum)
        .where(
            CourseCurriculum.course_id == user.course_id,
            CourseCurriculum.subject_id == subject.id,
            CourseCurriculum.is_active == True
        )
    )
    curriculum_result = await db.execute(curriculum_stmt)
    curriculum_item = curriculum_result.scalar_one_or_none()
    
    if not curriculum_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This subject is not in your enrolled course"
        )
    
    # Check semester access (future semesters are locked)
    if curriculum_item.semester_number > user.current_semester:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This subject is locked. Available in Semester {curriculum_item.semester_number}."
        )
    
    # Check module lock status
    if module.status.value == "locked":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This module is currently locked"
        )
    
    if module.status.value == "coming_soon":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Content coming soon"
        )
    
    if not module.is_free and not user.is_premium:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Premium subscription required"
        )
    
    return module, subject


async def recalculate_subject_progress(
    db: AsyncSession,
    user_id: int,
    subject_id: int
):
    """
    Recalculate subject progress percentage.
    
    Args:
        db: Database session
        user_id: User ID
        subject_id: Subject ID
    
    Process:
        1. Count total content items in subject (all modules)
        2. Count completed items from user_content_progress
        3. Update subject_progress record
    """
    # Get all modules for subject
    modules_stmt = (
        select(ContentModule)
        .where(ContentModule.subject_id == subject_id)
    )
    modules_result = await db.execute(modules_stmt)
    modules = modules_result.scalars().all()
    
    if not modules:
        return
    
    module_ids = [m.id for m in modules]
    
    # Count total items across all modules
    total_items = 0
    
    # Count Learn items
    learn_stmt = (
        select(func.count(LearnContent.id))
        .where(LearnContent.module_id.in_(module_ids))
    )
    learn_result = await db.execute(learn_stmt)
    total_items += learn_result.scalar() or 0
    
    # Count Case items
    case_stmt = (
        select(func.count(CaseContent.id))
        .where(CaseContent.module_id.in_(module_ids))
    )
    case_result = await db.execute(case_stmt)
    total_items += case_result.scalar() or 0
    
    # Count Practice items
    practice_stmt = (
        select(func.count(PracticeQuestion.id))
        .where(PracticeQuestion.module_id.in_(module_ids))
    )
    practice_result = await db.execute(practice_stmt)
    total_items += practice_result.scalar() or 0
    
    # Count completed items from user_content_progress
    # Need to count across all content types for this subject's modules
    completed_learn_stmt = (
        select(func.count(UserContentProgress.id))
        .join(LearnContent, 
              (UserContentProgress.content_type == ContentType.LEARN) & 
              (UserContentProgress.content_id == LearnContent.id))
        .where(
            UserContentProgress.user_id == user_id,
            UserContentProgress.is_completed == True,
            LearnContent.module_id.in_(module_ids)
        )
    )
    completed_learn_result = await db.execute(completed_learn_stmt)
    completed_items = completed_learn_result.scalar() or 0
    
    completed_case_stmt = (
        select(func.count(UserContentProgress.id))
        .join(CaseContent,
              (UserContentProgress.content_type == ContentType.CASE) &
              (UserContentProgress.content_id == CaseContent.id))
        .where(
            UserContentProgress.user_id == user_id,
            UserContentProgress.is_completed == True,
            CaseContent.module_id.in_(module_ids)
        )
    )
    completed_case_result = await db.execute(completed_case_stmt)
    completed_items += completed_case_result.scalar() or 0
    
    completed_practice_stmt = (
        select(func.count(UserContentProgress.id))
        .join(PracticeQuestion,
              (UserContentProgress.content_type == ContentType.PRACTICE) &
              (UserContentProgress.content_id == PracticeQuestion.id))
        .where(
            UserContentProgress.user_id == user_id,
            UserContentProgress.is_completed == True,
            PracticeQuestion.module_id.in_(module_ids)
        )
    )
    completed_practice_result = await db.execute(completed_practice_stmt)
    completed_items += completed_practice_result.scalar() or 0
    
    # Get or create subject_progress record
    progress_stmt = (
        select(SubjectProgress)
        .where(
            SubjectProgress.user_id == user_id,
            SubjectProgress.subject_id == subject_id
        )
    )
    progress_result = await db.execute(progress_stmt)
    subject_progress = progress_result.scalar_one_or_none()
    
    if not subject_progress:
        # Create new record
        subject_progress = SubjectProgress(
            user_id=user_id,
            subject_id=subject_id
        )
        db.add(subject_progress)
    
    # Update progress
    subject_progress.recalculate_progress(completed_items, total_items)
    subject_progress.update_activity()
    
    await db.commit()
    
    logger.info(
        f"Subject progress updated: user={user_id}, subject={subject_id}, "
        f"completed={completed_items}/{total_items} ({subject_progress.completion_percentage}%)"
    )


# ================= CONTENT DETAIL ENDPOINTS =================

@router.get("/learn/{content_id}")
async def get_learn_content_detail(
    content_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get full learn content item with body.
    
    Returns:
        - Full content (title, summary, body, metadata)
        - User's progress (is_completed, view_count, etc.)
        - Module and subject context
    """
    logger.info(f"Learn content detail: id={content_id}, user={current_user.email}")
    
    # Verify access
    module, subject = await verify_content_access(
        db, current_user, ContentType.LEARN, content_id
    )
    
    # Fetch content
    stmt = (
        select(LearnContent)
        .where(LearnContent.id == content_id)
    )
    result = await db.execute(stmt)
    content = result.scalar_one()
    
    # Fetch user progress
    progress_stmt = (
        select(UserContentProgress)
        .where(
            UserContentProgress.user_id == current_user.id,
            UserContentProgress.content_type == ContentType.LEARN,
            UserContentProgress.content_id == content_id
        )
    )
    progress_result = await db.execute(progress_stmt)
    progress = progress_result.scalar_one_or_none()
    
    # Record view if progress exists, create if not
    if progress:
        progress.record_view()
    else:
        progress = UserContentProgress(
            user_id=current_user.id,
            content_type=ContentType.LEARN,
            content_id=content_id
        )
        db.add(progress)
    
    await db.commit()
    await db.refresh(progress)
    
    return {
        "content": content.to_dict(include_body=True),
        "progress": progress.to_dict(),
        "module": {
            "id": module.id,
            "title": module.title,
            "module_type": module.module_type.value
        },
        "subject": {
            "id": subject.id,
            "title": subject.title,
            "code": subject.code
        }
    }


@router.get("/case/{content_id}")
async def get_case_content_detail(
    content_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get full case content with facts, judgment, ratio.
    
    Returns:
        - Full case details
        - User's progress
        - Module and subject context
    """
    logger.info(f"Case content detail: id={content_id}, user={current_user.email}")
    
    # Verify access
    module, subject = await verify_content_access(
        db, current_user, ContentType.CASE, content_id
    )
    
    # Fetch content
    stmt = (
        select(CaseContent)
        .where(CaseContent.id == content_id)
    )
    result = await db.execute(stmt)
    content = result.scalar_one()
    
    # Fetch/create user progress
    progress_stmt = (
        select(UserContentProgress)
        .where(
            UserContentProgress.user_id == current_user.id,
            UserContentProgress.content_type == ContentType.CASE,
            UserContentProgress.content_id == content_id
        )
    )
    progress_result = await db.execute(progress_stmt)
    progress = progress_result.scalar_one_or_none()
    
    if progress:
        progress.record_view()
    else:
        progress = UserContentProgress(
            user_id=current_user.id,
            content_type=ContentType.CASE,
            content_id=content_id
        )
        db.add(progress)
    
    await db.commit()
    await db.refresh(progress)
    
    return {
        "content": content.to_dict(include_full_content=True),
        "progress": progress.to_dict(),
        "module": {
            "id": module.id,
            "title": module.title,
            "module_type": module.module_type.value
        },
        "subject": {
            "id": subject.id,
            "title": subject.title,
            "code": subject.code
        }
    }


@router.get("/practice/{content_id}")
async def get_practice_content_detail(
    content_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get practice question details.
    
    Note: Answer is NOT included (use attempt endpoint to submit answer)
    
    Returns:
        - Question details (without answer)
        - User's progress
        - Module and subject context
    """
    logger.info(f"Practice content detail: id={content_id}, user={current_user.email}")
    
    # Verify access
    module, subject = await verify_content_access(
        db, current_user, ContentType.PRACTICE, content_id
    )
    
    # Fetch content
    stmt = (
        select(PracticeQuestion)
        .where(PracticeQuestion.id == content_id)
    )
    result = await db.execute(stmt)
    content = result.scalar_one()
    
    # Fetch/create user progress
    progress_stmt = (
        select(UserContentProgress)
        .where(
            UserContentProgress.user_id == current_user.id,
            UserContentProgress.content_type == ContentType.PRACTICE,
            UserContentProgress.content_id == content_id
        )
    )
    progress_result = await db.execute(progress_stmt)
    progress = progress_result.scalar_one_or_none()
    
    if progress:
        progress.record_view()
    else:
        progress = UserContentProgress(
            user_id=current_user.id,
            content_type=ContentType.PRACTICE,
            content_id=content_id
        )
        db.add(progress)
    
    await db.commit()
    await db.refresh(progress)
    
    return {
        "content": content.to_dict(include_answer=False),  # No answer
        "progress": progress.to_dict(),
        "module": {
            "id": module.id,
            "title": module.title,
            "module_type": module.module_type.value
        },
        "subject": {
            "id": subject.id,
            "title": subject.title,
            "code": subject.code
        }
    }


# ================= COMPLETION ENDPOINT =================

@router.post("/{content_type}/{content_id}/complete")
async def mark_content_complete(
    content_type: str,
    content_id: int,
    request: ContentCompleteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Mark content as completed.
    
    Process:
        1. Verify content access
        2. Update UserContentProgress (idempotent)
        3. Recalculate SubjectProgress
        4. Return updated progress
    
    Args:
        content_type: "learn", "case", or "practice"
        content_id: Content item ID
        request: Optional time spent
    
    Returns:
        Updated progress data
    """
    logger.info(
        f"Mark complete: type={content_type}, id={content_id}, user={current_user.email}"
    )
    
    # Convert string to ContentType enum
    try:
        content_type_enum = ContentType(content_type.lower())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid content type. Must be 'learn', 'case', or 'practice'"
        )
    
    # Verify access
    module, subject = await verify_content_access(
        db, current_user, content_type_enum, content_id
    )
    
    # Get or create progress record
    progress_stmt = (
        select(UserContentProgress)
        .where(
            UserContentProgress.user_id == current_user.id,
            UserContentProgress.content_type == content_type_enum,
            UserContentProgress.content_id == content_id
        )
    )
    progress_result = await db.execute(progress_stmt)
    progress = progress_result.scalar_one_or_none()
    
    if not progress:
        # Create new progress record
        progress = UserContentProgress(
            user_id=current_user.id,
            content_type=content_type_enum,
            content_id=content_id
        )
        db.add(progress)
    
    # Mark complete (idempotent)
    progress.mark_complete()
    
    # Record time spent if provided
    if request.time_spent_seconds:
        progress.record_view(time_spent=request.time_spent_seconds)
    
    await db.commit()
    await db.refresh(progress)
    
    # Recalculate subject progress
    await recalculate_subject_progress(db, current_user.id, subject.id)
    
    logger.info(
        f"Content completed: user={current_user.email}, type={content_type}, "
        f"id={content_id}, subject={subject.id}"
    )
    
    return {
        "success": True,
        "message": "Content marked as complete",
        "progress": progress.to_dict()
    }