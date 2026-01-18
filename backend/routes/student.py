"""
backend/routes/student.py
Phase 3 & 4: Student-facing APIs for content availability and study flow
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.orm import joinedload
from pydantic import BaseModel
from typing import Optional, List

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


class ModuleResponse(BaseModel):
    module_id: int
    title: str
    sequence_order: int
    content_count: int
    completed_count: int
    is_completed: bool


class SubjectModulesResponse(BaseModel):
    subject_id: int
    subject_title: str
    modules: List[ModuleResponse]


@router.get("/subject/{subject_id}/modules", response_model=SubjectModulesResponse)
async def get_subject_modules(
    subject_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 4: Get all modules for a subject with progress tracking.
    
    Returns modules in correct order with:
    - content_count from learn_content
    - is_completed calculated from user_content_progress
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
    curriculum = curriculum_result.scalar_one_or_none()
    if not curriculum:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Subject not in your curriculum"
        )

    from backend.orm.subject import Subject
    subject_stmt = select(Subject).where(Subject.id == subject_id)
    subject_result = await db.execute(subject_stmt)
    subject = subject_result.scalar_one_or_none()
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subject not found"
        )

    from sqlalchemy import text
    
    # Use raw SQL to bypass ORM relationship issues
    raw_result = await db.execute(
        text("SELECT id, title, order_index FROM content_modules WHERE subject_id = :sid AND module_type = 'learn' AND status = 'active' ORDER BY order_index"),
        {"sid": subject_id}
    )
    raw_modules = raw_result.fetchall()

    module_responses = []
    for row in raw_modules:
        module_id = row[0]
        module_title = row[1]
        module_order = row[2]
        
        # Count content items
        content_count_result = await db.execute(
            text("SELECT COUNT(*) FROM learn_content WHERE module_id = :mid"),
            {"mid": module_id}
        )
        content_count = content_count_result.scalar() or 0
        
        # Count completed items
        completed_result = await db.execute(
            text("""
                SELECT COUNT(*) FROM user_content_progress 
                WHERE user_id = :uid 
                AND content_type = 'learn' 
                AND content_id IN (SELECT id FROM learn_content WHERE module_id = :mid)
                AND is_completed = 1
            """),
            {"uid": current_user.id, "mid": module_id}
        )
        completed_count = completed_result.scalar() or 0
        
        is_completed = content_count > 0 and completed_count >= content_count

        module_responses.append(ModuleResponse(
            module_id=module_id,
            title=module_title,
            sequence_order=module_order,
            content_count=content_count,
            completed_count=completed_count,
            is_completed=is_completed
        ))

    return SubjectModulesResponse(
        subject_id=subject_id,
        subject_title=subject.title,
        modules=module_responses
    )


class ContentItemResponse(BaseModel):
    content_id: int
    title: str
    summary: Optional[str] = None
    sequence_order: int
    estimated_time_minutes: Optional[int] = None
    is_completed: bool


class ModuleContentResponse(BaseModel):
    module_id: int
    module_title: str
    subject_id: int
    subject_title: str
    content: List[ContentItemResponse]


@router.get("/module/{module_id}/content", response_model=ModuleContentResponse)
async def get_module_content(
    module_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 4: Get all learn content items for a module.
    
    Returns content items in correct order with completion status.
    """
    if not current_user.course_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User not enrolled in any course"
        )

    from sqlalchemy import text
    
    # Get module info using raw SQL
    module_result = await db.execute(
        text("SELECT id, title, subject_id, module_type FROM content_modules WHERE id = :mid"),
        {"mid": module_id}
    )
    module_row = module_result.fetchone()
    
    if not module_row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module not found"
        )
    
    module_title = module_row[1]
    module_subject_id = module_row[2]
    module_type = module_row[3]

    # Check curriculum
    curriculum_stmt = select(CourseCurriculum).where(
        and_(
            CourseCurriculum.course_id == current_user.course_id,
            CourseCurriculum.subject_id == module_subject_id,
            CourseCurriculum.is_active == True
        )
    )
    curriculum_result = await db.execute(curriculum_stmt)
    if not curriculum_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Subject not in your curriculum"
        )

    if module_type != "learn":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This endpoint only supports LEARN modules"
        )

    # Get subject title
    subject_result = await db.execute(
        text("SELECT title FROM subjects WHERE id = :sid"),
        {"sid": module_subject_id}
    )
    subject_row = subject_result.fetchone()
    subject_title = subject_row[0] if subject_row else "Unknown"

    # Get content items
    content_result = await db.execute(
        text("SELECT id, title, summary, order_index, estimated_time_minutes FROM learn_content WHERE module_id = :mid ORDER BY order_index"),
        {"mid": module_id}
    )
    content_rows = content_result.fetchall()

    content_responses = []
    for row in content_rows:
        content_id = row[0]
        
        # Check completion status
        progress_result = await db.execute(
            text("SELECT is_completed FROM user_content_progress WHERE user_id = :uid AND content_type = 'learn' AND content_id = :cid"),
            {"uid": current_user.id, "cid": content_id}
        )
        progress_row = progress_result.fetchone()
        is_completed = bool(progress_row[0]) if progress_row else False

        content_responses.append(ContentItemResponse(
            content_id=content_id,
            title=row[1],
            summary=row[2],
            sequence_order=row[3],
            estimated_time_minutes=row[4],
            is_completed=is_completed
        ))

    return ModuleContentResponse(
        module_id=module_id,
        module_title=module_title,
        subject_id=module_subject_id,
        subject_title=subject_title,
        content=content_responses
    )


class LearnContentDetailResponse(BaseModel):
    content_id: int
    title: str
    summary: Optional[str]
    body: str
    estimated_time_minutes: Optional[int]
    is_completed: bool
    view_count: int
    module_id: int
    module_title: str
    subject_id: int
    subject_code: str


@router.get("/learn/{content_id}", response_model=LearnContentDetailResponse)
async def get_learn_content(
    content_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 4: Get full learn content item with body and progress.
    """
    from sqlalchemy import text
    
    # Get content
    content_result = await db.execute(
        text("SELECT id, module_id, title, summary, body, estimated_time_minutes FROM learn_content WHERE id = :cid"),
        {"cid": content_id}
    )
    content_row = content_result.fetchone()
    
    if not content_row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Content not found"
        )
    
    module_id = content_row[1]
    
    # Get module and subject info
    module_result = await db.execute(
        text("SELECT cm.id, cm.title, cm.subject_id, s.code FROM content_modules cm JOIN subjects s ON cm.subject_id = s.id WHERE cm.id = :mid"),
        {"mid": module_id}
    )
    module_row = module_result.fetchone()
    
    if not module_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found")
    
    subject_id = module_row[2]
    
    # Check curriculum access
    curriculum_stmt = select(CourseCurriculum).where(
        and_(
            CourseCurriculum.course_id == current_user.course_id,
            CourseCurriculum.subject_id == subject_id,
            CourseCurriculum.is_active == True
        )
    )
    curriculum_result = await db.execute(curriculum_stmt)
    if not curriculum_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Subject not in your curriculum")
    
    # Get or create progress
    progress_result = await db.execute(
        text("SELECT id, is_completed, view_count FROM user_content_progress WHERE user_id = :uid AND content_type = 'learn' AND content_id = :cid"),
        {"uid": current_user.id, "cid": content_id}
    )
    progress_row = progress_result.fetchone()
    
    if progress_row:
        is_completed = bool(progress_row[1])
        view_count = progress_row[2] + 1
        # Update view count
        await db.execute(
            text("UPDATE user_content_progress SET view_count = :vc, last_viewed_at = datetime('now') WHERE id = :pid"),
            {"vc": view_count, "pid": progress_row[0]}
        )
        await db.commit()
    else:
        is_completed = False
        view_count = 1
        # Create progress record
        await db.execute(
            text("INSERT INTO user_content_progress (user_id, content_type, content_id, is_completed, view_count, last_viewed_at, created_at, updated_at) VALUES (:uid, 'learn', :cid, 0, 1, datetime('now'), datetime('now'), datetime('now'))"),
            {"uid": current_user.id, "cid": content_id}
        )
        await db.commit()
    
    return LearnContentDetailResponse(
        content_id=content_row[0],
        title=content_row[2],
        summary=content_row[3],
        body=content_row[4],
        estimated_time_minutes=content_row[5],
        is_completed=is_completed,
        view_count=view_count,
        module_id=module_row[0],
        module_title=module_row[1],
        subject_id=module_row[2],
        subject_code=module_row[3]
    )


class MarkCompleteRequest(BaseModel):
    time_spent_seconds: Optional[int] = None


@router.post("/learn/{content_id}/complete")
async def mark_learn_content_complete(
    content_id: int,
    request: MarkCompleteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 4: Mark learn content as completed.
    """
    from sqlalchemy import text
    
    # Verify content exists
    content_result = await db.execute(
        text("SELECT module_id FROM learn_content WHERE id = :cid"),
        {"cid": content_id}
    )
    content_row = content_result.fetchone()
    
    if not content_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content not found")
    
    module_id = content_row[0]
    
    # Get subject_id
    module_result = await db.execute(
        text("SELECT subject_id FROM content_modules WHERE id = :mid"),
        {"mid": module_id}
    )
    module_row = module_result.fetchone()
    subject_id = module_row[0] if module_row else None
    
    # Check/update progress
    progress_result = await db.execute(
        text("SELECT id, is_completed FROM user_content_progress WHERE user_id = :uid AND content_type = 'learn' AND content_id = :cid"),
        {"uid": current_user.id, "cid": content_id}
    )
    progress_row = progress_result.fetchone()
    
    if progress_row:
        if not progress_row[1]:
            await db.execute(
                text("UPDATE user_content_progress SET is_completed = 1, completed_at = datetime('now'), updated_at = datetime('now') WHERE id = :pid"),
                {"pid": progress_row[0]}
            )
    else:
        await db.execute(
            text("INSERT INTO user_content_progress (user_id, content_type, content_id, is_completed, completed_at, view_count, last_viewed_at, created_at, updated_at) VALUES (:uid, 'learn', :cid, 1, datetime('now'), 1, datetime('now'), datetime('now'), datetime('now'))"),
            {"uid": current_user.id, "cid": content_id}
        )
    
    await db.commit()
    
    return {
        "success": True,
        "message": "Content marked as complete",
        "content_id": content_id,
        "subject_id": subject_id
    }
