"""
backend/routes/modules.py
Module Content Delivery - Phase 4.2

Endpoints:
- GET /api/modules/{module_id}/content - Fetch content items for a module
"""
import logging
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from backend.database import get_db
from backend.orm.user import User
from backend.orm.content_module import ContentModule, ModuleType, ModuleStatus
from backend.orm.subject import Subject
from backend.orm.curriculum import CourseCurriculum
from backend.orm.learn_content import LearnContent
from backend.orm.case_content import CaseContent
from backend.orm.practice_question import PracticeQuestion
from backend.orm.user_content_progress import UserContentProgress, ContentType
from backend.routes.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/modules", tags=["Modules"])


# ================= HELPER FUNCTIONS =================

def calculate_module_lock_status(module: ContentModule, user: User) -> tuple[bool, str]:
    """
    Determine if a module should be locked for the user.
    
    Lock Rules:
    1. LOCKED status → Always locked
    2. COMING_SOON status → Always locked
    3. ACTIVE + not free + not premium → Locked (paywall)
    4. ACTIVE + (free OR premium) → Unlocked
    
    Args:
        module: ContentModule to check
        user: Current user with premium status
    
    Returns:
        (is_locked: bool, reason: str)
    """
    if module.status == ModuleStatus.LOCKED:
        return True, "This module is currently locked"
    
    if module.status == ModuleStatus.COMING_SOON:
        return True, "Content coming soon"
    
    if not module.is_free and not user.is_premium:
        return True, "Premium subscription required"
    
    return False, "Access granted"


async def verify_module_access(
    db: AsyncSession,
    module_id: int,
    user: User
) -> tuple[ContentModule, Subject]:
    """
    Verify user can access a module.
    
    Checks:
    1. Module exists
    2. User's course includes subject
    3. Semester access (current or past only)
    4. Module not locked
    
    Args:
        db: Database session
        module_id: Module to verify
        user: Current user
    
    Returns:
        (module, subject) if access granted
    
    Raises:
        HTTPException: 400/403/404 for various access violations
    """
    # Validate user enrollment
    if not user.course_id or not user.current_semester:
        logger.warning(f"User {user.email} has incomplete enrollment")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User enrollment incomplete. Please complete course enrollment."
        )
    
    # Fetch module with subject relationship
    module_stmt = (
        select(ContentModule)
        .options(joinedload(ContentModule.subject))
        .where(ContentModule.id == module_id)
    )
    module_result = await db.execute(module_stmt)
    module = module_result.scalar_one_or_none()
    
    if not module:
        logger.warning(f"Module {module_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module not found"
        )
    
    subject = module.subject
    if not subject:
        logger.error(f"Module {module_id} has no subject relationship")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Module configuration error"
        )
    
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
        logger.warning(
            f"Subject {subject.id} not found in course {user.course_id} "
            f"for user {user.email}"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This subject is not in your enrolled course"
        )
    
    # Check semester access (future semesters are locked)
    if curriculum_item.semester_number > user.current_semester:
        logger.warning(
            f"User {user.email} attempted to access future semester content: "
            f"subject_semester={curriculum_item.semester_number}, "
            f"user_semester={user.current_semester}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This subject is locked. Available in Semester {curriculum_item.semester_number}."
        )
    
    # Check module lock status
    is_locked, lock_reason = calculate_module_lock_status(module, user)
    if is_locked:
        logger.info(
            f"User {user.email} attempted to access locked module {module_id}: {lock_reason}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=lock_reason
        )
    
    return module, subject


async def get_learn_content_with_progress(
    db: AsyncSession,
    module_id: int,
    user_id: int
) -> List[Dict[str, Any]]:
    """
    Fetch LearnContent items with user progress.
    
    Args:
        db: Database session
        module_id: Module ID
        user_id: User ID for progress lookup
    
    Returns:
        List of learn content dictionaries with completion status
    """
    # Fetch learn content items
    content_stmt = (
        select(LearnContent)
        .where(LearnContent.module_id == module_id)
        .order_by(LearnContent.order_index)
    )
    content_result = await db.execute(content_stmt)
    content_items = content_result.scalars().all()
    
    if not content_items:
        return []
    
    # Fetch progress for these items
    content_ids = [item.id for item in content_items]
    progress_stmt = (
        select(UserContentProgress)
        .where(
            UserContentProgress.user_id == user_id,
            UserContentProgress.content_type == ContentType.LEARN,
            UserContentProgress.content_id.in_(content_ids)
        )
    )
    progress_result = await db.execute(progress_stmt)
    progress_records = progress_result.scalars().all()
    
    # Map progress by content_id
    progress_map = {p.content_id: p for p in progress_records}
    
    # Build response
    result = []
    for item in content_items:
        progress = progress_map.get(item.id)
        
        result.append({
            "id": item.id,
            "content_type": "learn",
            "title": item.title,
            "summary": item.summary,
            "order_index": item.order_index,
            "estimated_time_minutes": item.estimated_time_minutes,
            "is_completed": progress.is_completed if progress else False,
            "last_viewed_at": progress.last_viewed_at.isoformat() if progress and progress.last_viewed_at else None,
            "created_at": item.created_at.isoformat() if item.created_at else None,
        })
    
    return result


async def get_case_content_with_progress(
    db: AsyncSession,
    module_id: int,
    user_id: int
) -> List[Dict[str, Any]]:
    """
    Fetch CaseContent items with user progress.
    
    Args:
        db: Database session
        module_id: Module ID
        user_id: User ID for progress lookup
    
    Returns:
        List of case content dictionaries with completion status
    """
    # Fetch case content items (ordered by case name alphabetically)
    content_stmt = (
        select(CaseContent)
        .where(CaseContent.module_id == module_id)
        .order_by(CaseContent.case_name)
    )
    content_result = await db.execute(content_stmt)
    content_items = content_result.scalars().all()
    
    if not content_items:
        return []
    
    # Fetch progress for these items
    content_ids = [item.id for item in content_items]
    progress_stmt = (
        select(UserContentProgress)
        .where(
            UserContentProgress.user_id == user_id,
            UserContentProgress.content_type == ContentType.CASE,
            UserContentProgress.content_id.in_(content_ids)
        )
    )
    progress_result = await db.execute(progress_stmt)
    progress_records = progress_result.scalars().all()
    
    # Map progress by content_id
    progress_map = {p.content_id: p for p in progress_records}
    
    # Build response
    result = []
    for item in content_items:
        progress = progress_map.get(item.id)
        
        result.append({
            "id": item.id,
            "content_type": "case",
            "case_name": item.case_name,
            "citation": item.citation,
            "year": item.year,
            "court": item.court,
            "exam_importance": item.exam_importance.value if item.exam_importance else None,
            "tags": item.get_tag_list(),
            "is_completed": progress.is_completed if progress else False,
            "last_viewed_at": progress.last_viewed_at.isoformat() if progress and progress.last_viewed_at else None,
            "created_at": item.created_at.isoformat() if item.created_at else None,
        })
    
    return result


async def get_practice_content_with_progress(
    db: AsyncSession,
    module_id: int,
    user_id: int
) -> List[Dict[str, Any]]:
    """
    Fetch PracticeQuestion items with user progress.
    
    Args:
        db: Database session
        module_id: Module ID
        user_id: User ID for progress lookup
    
    Returns:
        List of practice question dictionaries with completion status
    """
    # Fetch practice questions
    content_stmt = (
        select(PracticeQuestion)
        .where(PracticeQuestion.module_id == module_id)
        .order_by(PracticeQuestion.order_index)
    )
    content_result = await db.execute(content_stmt)
    content_items = content_result.scalars().all()
    
    if not content_items:
        return []
    
    # Fetch progress for these items
    content_ids = [item.id for item in content_items]
    progress_stmt = (
        select(UserContentProgress)
        .where(
            UserContentProgress.user_id == user_id,
            UserContentProgress.content_type == ContentType.PRACTICE,
            UserContentProgress.content_id.in_(content_ids)
        )
    )
    progress_result = await db.execute(progress_stmt)
    progress_records = progress_result.scalars().all()
    
    # Map progress by content_id
    progress_map = {p.content_id: p for p in progress_records}
    
    # Build response
    result = []
    for item in content_items:
        progress = progress_map.get(item.id)
        
        # Base data (no answers included)
        question_data = {
            "id": item.id,
            "content_type": "practice",
            "question_type": item.question_type.value if item.question_type else None,
            "question": item.question,
            "marks": item.marks,
            "difficulty": item.difficulty.value if item.difficulty else None,
            "order_index": item.order_index,
            "tags": [tag.strip() for tag in item.tags.split(",")] if item.tags else [],
            "is_completed": progress.is_completed if progress else False,
            "last_viewed_at": progress.last_viewed_at.isoformat() if progress and progress.last_viewed_at else None,
            "created_at": item.created_at.isoformat() if item.created_at else None,
        }
        
        # Include MCQ options if applicable (but NOT the answer)
        if item.question_type.value == "mcq":
            question_data.update({
                "option_a": item.option_a,
                "option_b": item.option_b,
                "option_c": item.option_c,
                "option_d": item.option_d,
            })
        
        result.append(question_data)
    
    return result


# ================= API ROUTES =================

@router.get("/{module_id}/content")
async def get_module_content(
    module_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get content items for a specific module.
    
    PHASE 4.2: Module Content Delivery
    
    Security:
    - JWT authentication required
    - User must be enrolled in course containing this module's subject
    - Semester access control enforced (no future semesters)
    - Module lock status checked (locked/premium/coming_soon)
    
    Content Delivery:
    - Returns different content types based on module_type:
      * LEARN → LearnContent items (title, summary, estimated time)
      * CASES → CaseContent items (case name, citation, year, importance)
      * PRACTICE → PracticeQuestion items (question, difficulty, marks)
    - Each item includes is_completed from user_content_progress
    - Ordered by order_index (learn/practice) or case_name (cases)
    - Read-only: no progress mutation
    
    Args:
        module_id: Module ID to fetch content for
    
    Returns:
        {
            "module": {
                "id": 1,
                "title": "Learn Contract Law",
                "module_type": "learn",
                "description": "Theory and concepts"
            },
            "subject": {
                "id": 1,
                "title": "Contract Law",
                "code": "LAW101"
            },
            "content": [
                {
                    "id": 1,
                    "content_type": "learn",
                    "title": "What is a Contract?",
                    "summary": "Introduction to contracts",
                    "is_completed": false,
                    "order_index": 0
                }
            ],
            "total_items": 10,
            "completed_items": 3
        }
    
    Raises:
        400: User enrollment incomplete
        403: Module locked or future semester
        404: Module not found or not in user's course
    """
    logger.info(f"Module content request: module_id={module_id}, user={current_user.email}")
    
    # ========== VERIFY ACCESS ==========
    
    module, subject = await verify_module_access(db, module_id, current_user)
    
    logger.info(
        f"Access granted for user {current_user.email} to module {module_id} "
        f"(subject: {subject.title}, type: {module.module_type})"
    )
    
    # ========== FETCH CONTENT BASED ON MODULE TYPE ==========
    
    content_items = []
    
    if module.module_type == ModuleType.LEARN:
        content_items = await get_learn_content_with_progress(
            db, module_id, current_user.id
        )
    elif module.module_type == ModuleType.CASES:
        content_items = await get_case_content_with_progress(
            db, module_id, current_user.id
        )
    elif module.module_type == ModuleType.PRACTICE:
        content_items = await get_practice_content_with_progress(
            db, module_id, current_user.id
        )
    else:
        # NOTES type has no content (user-generated)
        content_items = []
    
    # ========== CALCULATE PROGRESS STATS ==========
    
    total_items = len(content_items)
    completed_items = sum(1 for item in content_items if item.get("is_completed", False))
    
    logger.info(
        f"Module {module_id} content prepared: {total_items} items, "
        f"{completed_items} completed"
    )
    
    # ========== RETURN RESPONSE ==========
    
    return {
        "module": {
            "id": module.id,
            "title": module.title,
            "module_type": module.module_type.value,
            "description": module.description,
            "status": module.status.value,
            "is_free": module.is_free,
        },
        "subject": {
            "id": subject.id,
            "title": subject.title,
            "code": subject.code,
            "category": subject.category.value if subject.category else None,
        },
        "content": content_items,
        "total_items": total_items,
        "completed_items": completed_items,
        "completion_percentage": round((completed_items / total_items * 100), 1) if total_items > 0 else 0.0,
    }