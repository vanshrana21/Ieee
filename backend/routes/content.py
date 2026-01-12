"""
backend/routes/content.py
Content access routes - Read-only APIs for learning content

PHASE 6 SCOPE:
- Get modules for a subject
- Get content items for a module
- Access control (semester lock + premium check)
- User notes CRUD

IMPORTANT:
- All routes enforce semester-based access control
- Premium content requires is_premium flag
- No content generation or AI integration yet (Phase 7+)
"""
import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from backend.database import get_db
from backend.orm.user import User
from backend.orm.subject import Subject
from backend.orm.curriculum import CourseCurriculum
from backend.orm.content_module import ContentModule, ModuleStatus, ModuleType
from backend.orm.learn_content import LearnContent
from backend.orm.case_content import CaseContent
from backend.orm.practice_question import PracticeQuestion
from backend.orm.user_notes import UserNotes
from backend.routes.auth import get_current_user
from backend.schemas.content import (
    ContentModuleResponse,
    SubjectModulesResponse,
    LearnContentSummary,
    LearnContentFull,
    CaseContentSummary,
    CaseContentFull,
    PracticeQuestionSummary,
    UserNoteResponse,
    UserNoteCreate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/content", tags=["Content"])


# ================= HELPER FUNCTIONS =================

async def verify_subject_access(
    db: AsyncSession,
    user: User,
    subject_id: int
) -> tuple[Subject, CourseCurriculum]:
    """
    Verify user can access a subject.
    
    Checks:
    1. User is enrolled in a course
    2. Subject exists in user's course
    3. Subject is not from future semester (semester lock)
    
    Returns:
        (subject, curriculum_item)
    
    Raises:
        HTTPException if access denied
    """
    # Check enrollment
    if not user.course_id or not user.current_semester:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User not enrolled in any course"
        )
    
    # Find subject in user's course
    stmt = (
        select(CourseCurriculum)
        .options(joinedload(CourseCurriculum.subject))
        .where(
            CourseCurriculum.course_id == user.course_id,
            CourseCurriculum.subject_id == subject_id,
            CourseCurriculum.is_active == True
        )
    )
    
    result = await db.execute(stmt)
    curriculum_item = result.scalar_one_or_none()
    
    if not curriculum_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subject not found in your course"
        )
    
    # Check semester lock
    if curriculum_item.semester_number > user.current_semester:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Subject locked. Available in Semester {curriculum_item.semester_number}"
        )
    
    return curriculum_item.subject, curriculum_item


async def verify_module_access(
    db: AsyncSession,
    user: User,
    module_id: int
) -> ContentModule:
    """
    Verify user can access a content module.
    
    Checks:
    1. Module exists
    2. User can access parent subject
    3. Module status (locked/coming_soon/active)
    4. Premium requirement
    
    Returns:
        module
    
    Raises:
        HTTPException if access denied
    """
    # Fetch module with subject
    stmt = (
        select(ContentModule)
        .options(joinedload(ContentModule.subject))
        .where(ContentModule.id == module_id)
    )
    
    result = await db.execute(stmt)
    module = result.scalar_one_or_none()
    
    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module not found"
        )
    
    # Verify subject access (includes semester lock)
    await verify_subject_access(db, user, module.subject_id)
    
    # Check module access
    can_access, reason = module.can_user_access(user)
    
    if not can_access:
        if module.status == ModuleStatus.LOCKED:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=reason
            )
        elif module.status == ModuleStatus.COMING_SOON:
            raise HTTPException(
                status_code=status.HTTP_200_OK,
                detail={"message": reason, "module": module.to_dict()}
            )
        elif not module.is_free and not user.is_premium:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=reason
            )
    
    return module


# ================= SUBJECT MODULES =================

@router.get("/subjects/{subject_id}/modules")
async def get_subject_modules(
    subject_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all content modules for a subject.
    
    Returns:
    - Module metadata (type, status, title, item count)
    - Does NOT return actual content items
    - Respects semester lock and premium status
    
    Security:
    - User must be enrolled in course
    - Subject must be from current or past semester
    - Premium content flagged but not blocked
    """
    logger.info(f"Get modules: subject_id={subject_id}, user={current_user.email}")
    
    # Verify subject access
    subject, _ = await verify_subject_access(db, current_user, subject_id)
    
    # Fetch all modules for subject
    stmt = (
        select(ContentModule)
        .where(ContentModule.subject_id == subject_id)
        .order_by(ContentModule.order_index)
    )
    
    result = await db.execute(stmt)
    modules = result.scalars().all()
    
    # Transform to response
    module_responses = []
    for module in modules:
        module_dict = module.to_dict()
        module_dict["item_count"] = module.get_item_count()
        
        # Add access metadata
        can_access, reason = module.can_user_access(current_user)
        module_dict["can_access"] = can_access
        module_dict["access_message"] = reason if not can_access else None
        
        module_responses.append(module_dict)
    
    return {
        "subject_id": subject.id,
        "subject_title": subject.title,
        "modules": module_responses
    }


# ================= LEARN CONTENT =================

@router.get("/modules/{module_id}/learn", response_model=List[LearnContentSummary])
async def get_learn_content_list(
    module_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get list of learn content items (without full body).
    
    Returns:
    - Title, summary, order, estimated time
    - Full content fetched via separate endpoint
    """
    logger.info(f"Get learn list: module_id={module_id}, user={current_user.email}")
    
    # Verify access
    module = await verify_module_access(db, current_user, module_id)
    
    if module.module_type != ModuleType.LEARN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This module is not a LEARN module"
        )
    
    # Return items (already loaded via relationship)
    return [item.to_dict(include_body=False) for item in module.learn_items]


@router.get("/learn/{content_id}", response_model=LearnContentFull)
async def get_learn_content_detail(
    content_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get full learn content item with body"""
    stmt = (
        select(LearnContent)
        .options(joinedload(LearnContent.module))
        .where(LearnContent.id == content_id)
    )
    
    result = await db.execute(stmt)
    content = result.scalar_one_or_none()
    
    if not content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Content not found"
        )
    
    # Verify module access
    await verify_module_access(db, current_user, content.module_id)
    
    return content.to_dict(include_body=True)


# ================= CASE CONTENT =================

@router.get("/modules/{module_id}/cases", response_model=List[CaseContentSummary])
async def get_case_content_list(
    module_id: int,
    importance: str = None,  # Filter: high/medium/low
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get list of case content items.
    
    Query params:
    - importance: Filter by exam importance (high/medium/low)
    """
    logger.info(f"Get cases: module_id={module_id}, user={current_user.email}")
    
    # Verify access
    module = await verify_module_access(db, current_user, module_id)
    
    if module.module_type != ModuleType.CASES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This module is not a CASES module"
        )
    
    # Filter by importance if provided
    cases = module.case_items
    if importance:
        cases = [c for c in cases if c.exam_importance.value == importance.lower()]
    
    return [item.to_dict(include_full_content=False) for item in cases]


@router.get("/cases/{case_id}", response_model=CaseContentFull)
async def get_case_content_detail(
    case_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get full case content with facts, judgment, ratio"""
    stmt = (
        select(CaseContent)
        .options(joinedload(CaseContent.module))
        .where(CaseContent.id == case_id)
    )
    
    result = await db.execute(stmt)
    case = result.scalar_one_or_none()
    
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found"
        )
    
    # Verify module access
    await verify_module_access(db, current_user, case.module_id)
    
    return case.to_dict(include_full_content=True)


# ================= PRACTICE QUESTIONS =================

@router.get("/modules/{module_id}/practice", response_model=List[PracticeQuestionSummary])
async def get_practice_questions(
    module_id: int,
    difficulty: str = None,  # Filter: easy/medium/hard
    question_type: str = None,  # Filter: mcq/short_answer/essay
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get practice questions (without answers).
    
    Query params:
    - difficulty: Filter by difficulty
    - question_type: Filter by type
    
    Note: Answers not included (use submit endpoint)
    """
    logger.info(f"Get practice: module_id={module_id}, user={current_user.email}")
    
    # Verify access
    module = await verify_module_access(db, current_user, module_id)
    
    if module.module_type != ModuleType.PRACTICE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This module is not a PRACTICE module"
        )
    
    # Filter questions
    questions = module.practice_items
    
    if difficulty:
        questions = [q for q in questions if q.difficulty.value == difficulty.lower()]
    
    if question_type:
        questions = [q for q in questions if q.question_type.value == question_type.lower()]
    
    return [q.to_dict(include_answer=False) for q in questions]


# ================= USER NOTES =================

@router.get("/subjects/{subject_id}/notes", response_model=UserNoteResponse)
async def get_user_note(
    subject_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get user's personal note for a subject.
    
    Returns:
    - 200 + note if exists
    - 404 if no note found
    """
    # Verify subject access
    await verify_subject_access(db, current_user, subject_id)
    
    # Find user's note
    stmt = select(UserNotes).where(
        UserNotes.user_id == current_user.id,
        UserNotes.subject_id == subject_id
    )
    
    result = await db.execute(stmt)
    note = result.scalar_one_or_none()
    
    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No note found for this subject"
        )
    
    return note.to_dict()


@router.post("/subjects/{subject_id}/notes", response_model=UserNoteResponse, status_code=201)
async def create_or_update_note(
    subject_id: int,
    note_data: UserNoteCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create or update user's note for a subject.
    
    Behavior:
    - If note exists → Update
    - If note doesn't exist → Create
    """
    # Verify subject access
    await verify_subject_access(db, current_user, subject_id)
    
    # Check if note exists
    stmt = select(UserNotes).where(
        UserNotes.user_id == current_user.id,
        UserNotes.subject_id == subject_id
    )
    
    result = await db.execute(stmt)
    note = result.scalar_one_or_none()
    
    if note:
        # Update existing note
        note.title = note_data.title
        note.content = note_data.content
        note.is_pinned = 1 if note_data.is_pinned else 0
        logger.info(f"Updated note for subject {subject_id} by user {current_user.email}")
    else:
        # Create new note
        note = UserNotes(
            user_id=current_user.id,
            subject_id=subject_id,
            title=note_data.title,
            content=note_data.content,
            is_pinned=1 if note_data.is_pinned else 0
        )
        db.add(note)
        logger.info(f"Created note for subject {subject_id} by user {current_user.email}")
    
    await db.commit()
    await db.refresh(note)
    
    return note.to_dict()


@router.delete("/subjects/{subject_id}/notes", status_code=204)
async def delete_user_note(
    subject_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete user's note for a subject"""
    # Verify subject access
    await verify_subject_access(db, current_user, subject_id)
    
    # Find and delete note
    stmt = select(UserNotes).where(
        UserNotes.user_id == current_user.id,
        UserNotes.subject_id == subject_id
    )
    
    result = await db.execute(stmt)
    note = result.scalar_one_or_none()
    
    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No note found to delete"
        )
    
    await db.delete(note)
    await db.commit()
    
    logger.info(f"Deleted note for subject {subject_id} by user {current_user.email}")
    return None