"""
backend/routes/progress.py
Progress tracking and learning analytics routes

PHASE 8 SCOPE:
- Mark content as completed
- Submit practice question attempts
- View subject progress
- Resume learning
- Basic statistics

IMPORTANT RULES:
- All routes enforce semester lock (cannot access future content)
- Cannot complete content from locked subjects
- Practice answers revealed only after submission
- Completion is permanent (cannot uncomplete)
"""
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import joinedload
from datetime import datetime

from backend.database import get_db
from backend.orm.user import User
from backend.orm.subject import Subject
from backend.orm.curriculum import CourseCurriculum
from backend.orm.content_module import ContentModule, ModuleType
from backend.orm.learn_content import LearnContent
from backend.orm.case_content import CaseContent
from backend.orm.practice_question import PracticeQuestion, QuestionType
from backend.orm.user_content_progress import UserContentProgress, ContentType
from backend.orm.practice_attempt import PracticeAttempt
from backend.orm.subject_progress import SubjectProgress
from backend.routes.auth import get_current_user
from backend.schemas.progress import (
    ContentCompleteRequest,
    ContentProgressResponse,
    PracticeAttemptRequest,
    PracticeAttemptResponse,
    PracticeAttemptSummary,
    SubjectProgressResponse,
    SubjectProgressDetail,
    ResumeLearningResponse,
    ResumeItemResponse,
    UserStatisticsResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/progress", tags=["Progress"])


# ================= HELPER FUNCTIONS =================

async def verify_content_access(
    db: AsyncSession,
    user: User,
    content_type: ContentType,
    content_id: int
) -> tuple[int, int]:
    """
    Verify user can access content and return subject_id, module_id.
    
    Checks:
    1. Content exists
    2. Content belongs to accessible subject (semester lock)
    3. Module is not locked
    
    Returns:
        (subject_id, module_id)
    
    Raises:
        HTTPException if access denied
    """
    # Fetch content based on type
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
    
    if not content or not content.module or not content.module.subject:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Content not found"
        )
    
    module = content.module
    subject = module.subject
    
    # Check user enrollment
    if not user.course_id or not user.current_semester:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User not enrolled in any course"
        )
    
    # Verify subject is in user's course
    stmt = (
        select(CourseCurriculum)
        .where(
            CourseCurriculum.course_id == user.course_id,
            CourseCurriculum.subject_id == subject.id,
            CourseCurriculum.is_active == True
        )
    )
    result = await db.execute(stmt)
    curriculum_item = result.scalar_one_or_none()
    
    if not curriculum_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Content not found in your course"
        )
    
    # Check semester lock
    if curriculum_item.semester_number > user.current_semester:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Content locked. Available in Semester {curriculum_item.semester_number}"
        )
    
    # Check module access
    can_access, reason = module.can_user_access(user)
    if not can_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=reason
        )
    
    return subject.id, module.id


async def get_or_create_subject_progress(
    db: AsyncSession,
    user_id: int,
    subject_id: int
) -> SubjectProgress:
    """
    Get existing subject progress or create new one.
    
    Args:
        db: Database session
        user_id: User ID
        subject_id: Subject ID
    
    Returns:
        SubjectProgress instance
    """
    stmt = select(SubjectProgress).where(
        SubjectProgress.user_id == user_id,
        SubjectProgress.subject_id == subject_id
    )
    result = await db.execute(stmt)
    progress = result.scalar_one_or_none()
    
    if not progress:
        progress = SubjectProgress(
            user_id=user_id,
            subject_id=subject_id,
            completion_percentage=0.0,
            total_items=0,
            completed_items=0,
            last_activity_at=datetime.utcnow()
        )
        db.add(progress)
        await db.flush()
    
    return progress


async def recalculate_subject_progress(
    db: AsyncSession,
    user_id: int,
    subject_id: int
):
    """
    Recalculate subject progress from scratch.
    
    Steps:
    1. Count total content items in subject
    2. Count completed items for user
    3. Update SubjectProgress record
    
    Args:
        db: Database session
        user_id: User ID
        subject_id: Subject ID
    """
    # Get all modules for subject
    modules_stmt = select(ContentModule.id).where(
        ContentModule.subject_id == subject_id
    )
    modules_result = await db.execute(modules_stmt)
    module_ids = [row[0] for row in modules_result.fetchall()]
    
    if not module_ids:
        # No modules = 0% progress
        progress = await get_or_create_subject_progress(db, user_id, subject_id)
        progress.recalculate_progress(0, 0)
        return
    
    # Count total items across all modules
    learn_count_stmt = select(func.count(LearnContent.id)).where(
        LearnContent.module_id.in_(module_ids)
    )
    case_count_stmt = select(func.count(CaseContent.id)).where(
        CaseContent.module_id.in_(module_ids)
    )
    practice_count_stmt = select(func.count(PracticeQuestion.id)).where(
        PracticeQuestion.module_id.in_(module_ids)
    )
    
    learn_count = (await db.execute(learn_count_stmt)).scalar() or 0
    case_count = (await db.execute(case_count_stmt)).scalar() or 0
    practice_count = (await db.execute(practice_count_stmt)).scalar() or 0
    
    total_items = learn_count + case_count + practice_count
    
    # Count completed items for user
    completed_stmt = (
        select(func.count(UserContentProgress.id))
        .where(
            UserContentProgress.user_id == user_id,
            UserContentProgress.is_completed == True
        )
    )
    
    # Filter by content that belongs to this subject
    # We need to join based on content_type
    learn_ids_stmt = select(LearnContent.id).where(LearnContent.module_id.in_(module_ids))
    case_ids_stmt = select(CaseContent.id).where(CaseContent.module_id.in_(module_ids))
    practice_ids_stmt = select(PracticeQuestion.id).where(PracticeQuestion.module_id.in_(module_ids))
    
    learn_ids = [row[0] for row in (await db.execute(learn_ids_stmt)).fetchall()]
    case_ids = [row[0] for row in (await db.execute(case_ids_stmt)).fetchall()]
    practice_ids = [row[0] for row in (await db.execute(practice_ids_stmt)).fetchall()]
    
    # Count completed by content type
    completed_count = 0
    
    if learn_ids:
        learn_completed = await db.execute(
            select(func.count(UserContentProgress.id)).where(
                UserContentProgress.user_id == user_id,
                UserContentProgress.content_type == ContentType.LEARN,
                UserContentProgress.content_id.in_(learn_ids),
                UserContentProgress.is_completed == True
            )
        )
        completed_count += learn_completed.scalar() or 0
    
    if case_ids:
        case_completed = await db.execute(
            select(func.count(UserContentProgress.id)).where(
                UserContentProgress.user_id == user_id,
                UserContentProgress.content_type == ContentType.CASE,
                UserContentProgress.content_id.in_(case_ids),
                UserContentProgress.is_completed == True
            )
        )
        completed_count += case_completed.scalar() or 0
    
    if practice_ids:
        practice_completed = await db.execute(
            select(func.count(UserContentProgress.id)).where(
                UserContentProgress.user_id == user_id,
                UserContentProgress.content_type == ContentType.PRACTICE,
                UserContentProgress.content_id.in_(practice_ids),
                UserContentProgress.is_completed == True
            )
        )
        completed_count += practice_completed.scalar() or 0
    
    # Update subject progress
    progress = await get_or_create_subject_progress(db, user_id, subject_id)
    progress.recalculate_progress(completed_count, total_items)
    progress.update_activity()


# ================= CONTENT COMPLETION =================

@router.post("/content/complete", response_model=ContentProgressResponse)
async def mark_content_complete(
    request: ContentCompleteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Mark content as completed.
    
    Behavior:
    - First time → Creates progress record + marks complete
    - Already exists → Updates to completed (idempotent)
    - Updates subject progress automatically
    
    Security:
    - User must have access to content (semester lock applies)
    - Cannot complete locked/premium content
    
    Request:
        {
            "content_type": "learn",
            "content_id": 42,
            "time_spent_seconds": 180
        }
    
    Returns:
        Progress record with completion status
    """
    logger.info(
        f"Complete content: type={request.content_type}, "
        f"id={request.content_id}, user={current_user.email}"
    )
    
    # Validate content type
    try:
        content_type_enum = ContentType(request.content_type.lower())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid content_type. Must be: learn, case, or practice"
        )
    
    # Verify access
    subject_id, module_id = await verify_content_access(
        db, current_user, content_type_enum, request.content_id
    )
    
    # Get or create progress record
    stmt = select(UserContentProgress).where(
        UserContentProgress.user_id == current_user.id,
        UserContentProgress.content_type == content_type_enum,
        UserContentProgress.content_id == request.content_id
    )
    result = await db.execute(stmt)
    progress = result.scalar_one_or_none()
    
    if progress:
        # Update existing record
        progress.mark_complete()
        if request.time_spent_seconds:
            progress.record_view(request.time_spent_seconds)
        logger.info(f"Updated existing progress record: {progress.id}")
    else:
        # Create new record
        progress = UserContentProgress(
            user_id=current_user.id,
            content_type=content_type_enum,
            content_id=request.content_id,
            is_completed=True,
            completed_at=datetime.utcnow(),
            last_viewed_at=datetime.utcnow(),
            view_count=1,
            time_spent_seconds=request.time_spent_seconds
        )
        db.add(progress)
        logger.info(f"Created new progress record")
    
    # Recalculate subject progress
    await recalculate_subject_progress(db, current_user.id, subject_id)
    
    await db.commit()
    await db.refresh(progress)
    
    return progress.to_dict()


# ================= PRACTICE ATTEMPTS =================

@router.post("/practice/{question_id}/attempt", response_model=PracticeAttemptResponse)
async def submit_practice_attempt(
    question_id: int,
    request: PracticeAttemptRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Submit answer to practice question.
    
    Behavior:
    - MCQs: Auto-graded immediately
    - Essays/Short answers: Stored for future grading (is_correct=NULL)
    - Multiple attempts allowed (attempt_number increments)
    - Returns correct answer and explanation after submission
    
    Security:
    - User must have access to question (semester lock applies)
    
    Request:
        {
            "selected_option": "B",
            "time_taken_seconds": 45
        }
    
    Returns:
        Attempt record + full question with correct answer
    """
    logger.info(
        f"Practice attempt: question_id={question_id}, user={current_user.email}"
    )
    
    # Verify access
    subject_id, module_id = await verify_content_access(
        db, current_user, ContentType.PRACTICE, question_id
    )
    
    # Fetch question
    stmt = (
        select(PracticeQuestion)
        .where(PracticeQuestion.id == question_id)
    )
    result = await db.execute(stmt)
    question = result.scalar_one_or_none()
    
    if not question:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question not found"
        )
    
    # Calculate attempt number
    attempt_count_stmt = select(func.count(PracticeAttempt.id)).where(
        PracticeAttempt.user_id == current_user.id,
        PracticeAttempt.practice_question_id == question_id
    )
    attempt_count = (await db.execute(attempt_count_stmt)).scalar() or 0
    attempt_number = attempt_count + 1
    
    # Auto-grade if MCQ
    is_correct = None
    if question.question_type == QuestionType.MCQ:
        is_correct = question.check_mcq_answer(request.selected_option)
    
    # Create attempt record
    attempt = PracticeAttempt(
        user_id=current_user.id,
        practice_question_id=question_id,
        selected_option=request.selected_option,
        is_correct=is_correct,
        attempt_number=attempt_number,
        time_taken_seconds=request.time_taken_seconds,
        attempted_at=datetime.utcnow()
    )
    db.add(attempt)
    
    # Mark question as attempted in progress (if not already)
    progress_stmt = select(UserContentProgress).where(
        UserContentProgress.user_id == current_user.id,
        UserContentProgress.content_type == ContentType.PRACTICE,
        UserContentProgress.content_id == question_id
    )
    progress_result = await db.execute(progress_stmt)
    progress = progress_result.scalar_one_or_none()
    
    if not progress:
        progress = UserContentProgress(
            user_id=current_user.id,
            content_type=ContentType.PRACTICE,
            content_id=question_id,
            is_completed=False,  # Practice questions don't auto-complete
            last_viewed_at=datetime.utcnow(),
            view_count=1
        )
        db.add(progress)
    else:
        progress.record_view()
    
    # Update subject progress activity
    subject_progress = await get_or_create_subject_progress(
        db, current_user.id, subject_id
    )
    subject_progress.update_activity()
    
    await db.commit()
    await db.refresh(attempt)
    
    # Return attempt with question details
    return attempt.to_dict_with_question()


@router.get("/practice/{question_id}/attempts", response_model=List[PracticeAttemptSummary])
async def get_practice_attempts(
    question_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get user's attempt history for a question.
    
    Returns:
    - List of attempts (most recent first)
    - Shows attempt number and correctness
    - Does NOT reveal selected answers (use for stats only)
    """
    # Verify access
    await verify_content_access(db, current_user, ContentType.PRACTICE, question_id)
    
    # Fetch attempts
    stmt = (
        select(PracticeAttempt)
        .where(
            PracticeAttempt.user_id == current_user.id,
            PracticeAttempt.practice_question_id == question_id
        )
        .order_by(PracticeAttempt.attempted_at.desc())
    )
    result = await db.execute(stmt)
    attempts = result.scalars().all()
    
    return [attempt.to_dict(include_answer=False) for attempt in attempts]


# ================= SUBJECT PROGRESS =================

@router.get("/subject/{subject_id}", response_model=SubjectProgressDetail)
async def get_subject_progress(
    subject_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed progress for a subject.
    
    Returns:
    - Overall completion percentage
    - Module-wise breakdown (learn/cases/practice)
    - Recently accessed items
    - Completion status per item type
    
    Security:
    - User must have access to subject (semester lock applies)
    """
    logger.info(f"Get subject progress: subject_id={subject_id}, user={current_user.email}")
    
    # Verify subject access
    if not current_user.course_id or not current_user.current_semester:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User not enrolled in any course"
        )
    
    stmt = (
        select(CourseCurriculum)
        .options(joinedload(CourseCurriculum.subject))
        .where(
            CourseCurriculum.course_id == current_user.course_id,
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
    
    if curriculum_item.semester_number > current_user.current_semester:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Subject locked. Available in Semester {curriculum_item.semester_number}"
        )
    
    subject = curriculum_item.subject
    
    # Get or create subject progress
    progress = await get_or_create_subject_progress(db, current_user.id, subject_id)
    
    # Recalculate to ensure accuracy
    await recalculate_subject_progress(db, current_user.id, subject_id)
    await db.commit()
    await db.refresh(progress)
    
    # Get module-wise breakdown
    modules_stmt = (
        select(ContentModule)
        .where(ContentModule.subject_id == subject_id)
        .order_by(ContentModule.order_index)
    )
    modules_result = await db.execute(modules_stmt)
    modules = modules_result.scalars().all()
    
    # Calculate per-module progress
    module_progress = {
        "learn": {"total": 0, "completed": 0, "percentage": 0.0},
        "cases": {"total": 0, "completed": 0, "percentage": 0.0},
        "practice": {"total": 0, "completed": 0, "percentage": 0.0},
    }
    
    for module in modules:
        module_type_key = module.module_type.value
        
        if module.module_type == ModuleType.LEARN:
            total = len(module.learn_items) if module.learn_items else 0
            content_ids = [item.id for item in module.learn_items] if module.learn_items else []
        elif module.module_type == ModuleType.CASES:
            total = len(module.case_items) if module.case_items else 0
            content_ids = [item.id for item in module.case_items] if module.case_items else []
        elif module.module_type == ModuleType.PRACTICE:
            total = len(module.practice_items) if module.practice_items else 0
            content_ids = [item.id for item in module.practice_items] if module.practice_items else []
        else:
            continue
        
        module_progress[module_type_key]["total"] += total
        
        if content_ids:
            completed_stmt = select(func.count(UserContentProgress.id)).where(
                UserContentProgress.user_id == current_user.id,
                UserContentProgress.content_type == ContentType(module_type_key),
                UserContentProgress.content_id.in_(content_ids),
                UserContentProgress.is_completed == True
            )
            completed = (await db.execute(completed_stmt)).scalar() or 0
            module_progress[module_type_key]["completed"] += completed
    
    # Calculate percentages
    for key in module_progress:
        total = module_progress[key]["total"]
        completed = module_progress[key]["completed"]
        if total > 0:
            module_progress[key]["percentage"] = round((completed / total) * 100, 2)
    
    # Get recent items
    recent_stmt = (
        select(UserContentProgress)
        .where(UserContentProgress.user_id == current_user.id)
        .order_by(UserContentProgress.last_viewed_at.desc())
        .limit(5)
    )
    recent_result = await db.execute(recent_stmt)
    recent_items = recent_result.scalars().all()
    
    recent_items_data = [item.to_dict() for item in recent_items]
    
    # Build response
    return {
        "subject_id": subject.id,
        "subject_title": subject.title,
        "overall_progress": {
            **progress.to_dict(),
            "status_label": progress.get_status_label()
        },
        "learn_progress": module_progress["learn"],
        "cases_progress": module_progress["cases"],
        "practice_progress": module_progress["practice"],
        "recent_items": recent_items_data
    }


# ================= RESUME LEARNING =================

@router.get("/resume", response_model=ResumeLearningResponse)
async def get_resume_learning(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get resume learning recommendations.
    
    Returns:
    - Most recently accessed content item
    - Recently active subjects
    - Overall completion percentage
    
    Algorithm:
    1. Find most recent UserContentProgress record
    2. Fetch that content's details
    3. Get subject progress for context
    4. List recently active subjects
    """
    logger.info(f"Resume learning: user={current_user.email}")
    
    # Get most recent activity
    recent_stmt = (
        select(UserContentProgress)
        .where(UserContentProgress.user_id == current_user.id)
        .order_by(UserContentProgress.last_viewed_at.desc())
        .limit(1)
    )
    recent_result = await db.execute(recent_stmt)
    last_activity_record = recent_result.scalar_one_or_none()
    
    last_activity = None
    if last_activity_record:
        # Fetch content details based on type
        content_type = last_activity_record.content_type
        content_id = last_activity_record.content_id
        
        content_title = "Unknown"
        subject_id = None
        module_id = None
        
        if content_type == ContentType.LEARN:
            content_stmt = (
                select(LearnContent)
                .options(joinedload(LearnContent.module).joinedload(ContentModule.subject))
                .where(LearnContent.id == content_id)
            )
            content_result = await db.execute(content_stmt)
            content = content_result.scalar_one_or_none()
            if content:
                content_title = content.title
                subject_id = content.module.subject_id
                module_id = content.module_id
                
        elif content_type == ContentType.CASE:
            content_stmt = (
                select(CaseContent)
                .options(joinedload(CaseContent.module).joinedload(ContentModule.subject))
                .where(CaseContent.id == content_id)
            )
            content_result = await db.execute(content_stmt)
            content = content_result.scalar_one_or_none()
            if content:
                content_title = content.case_name
                subject_id = content.module.subject_id
                module_id = content.module_id
                
        elif content_type == ContentType.PRACTICE:
            content_stmt = (
                select(PracticeQuestion)
                .options(joinedload(PracticeQuestion.module).joinedload(ContentModule.subject))
                .where(PracticeQuestion.id == content_id)
            )
            content_result = await db.execute(content_stmt)
            content = content_result.scalar_one_or_none()
            if content:
                content_title = content.question[:100]  # Truncate
                subject_id = content.module.subject_id
                module_id = content.module_id
        
        # Get subject name
        subject_title = "Unknown Subject"
        if subject_id:
            subject_stmt = select(Subject).where(Subject.id == subject_id)
            subject_result = await db.execute(subject_stmt)
            subject = subject_result.scalar_one_or_none()
            if subject:
                subject_title = subject.title
        
        last_activity = {
            "content_type": content_type.value,
            "content_id": content_id,
            "content_title": content_title,
            "subject_id": subject_id,
            "subject_title": subject_title,
            "module_id": module_id,
            "last_viewed_at": last_activity_record.last_viewed_at.isoformat(),
            "is_completed": last_activity_record.is_completed
        }
    
    # Get recently active subjects
    recent_subjects_stmt = (
        select(SubjectProgress)
        .options(joinedload(SubjectProgress.subject))
        .where(SubjectProgress.user_id == current_user.id)
        .order_by(SubjectProgress.last_activity_at.desc())
        .limit(5)
    )
    recent_subjects_result = await db.execute(recent_subjects_stmt)
    recent_subjects_records = recent_subjects_result.scalars().all()
    
    recent_subjects = []
    for record in recent_subjects_records:
        recent_subjects.append({
            "subject_id": record.subject_id,
            "subject_title": record.subject.title if record.subject else "Unknown",
            "completion": record.completion_percentage,
            "last_activity_at": record.last_activity_at.isoformat()
        })
    
    # Calculate overall completion
    all_progress_stmt = select(SubjectProgress).where(
        SubjectProgress.user_id == current_user.id
    )
    all_progress_result = await db.execute(all_progress_stmt)
    all_progress = all_progress_result.scalars().all()
    
    if all_progress:
        total_completion = sum(p.completion_percentage for p in all_progress) / len(all_progress)
    else:
        total_completion = 0.0
    
    return {
        "last_activity": last_activity,
        "recent_subjects": recent_subjects,
        "total_completion_percentage": round(total_completion, 2)
    }


# ================= STATISTICS =================

@router.get("/statistics", response_model=UserStatisticsResponse)
async def get_user_statistics(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get overall user statistics across all subjects.
    
    Returns:
    - Subject completion counts
    - Content completion metrics
    - Practice attempt accuracy
    - Time tracking data
    
    Foundation for Phase 9+ analytics dashboard.
    """
    logger.info(f"Get statistics: user={current_user.email}")
    
    # Subject statistics
    all_progress_stmt = select(SubjectProgress).where(
        SubjectProgress.user_id == current_user.id
    )
    all_progress_result = await db.execute(all_progress_stmt)
    all_progress = all_progress_result.scalars().all()
    
    total_subjects = len(all_progress)
    completed_subjects = sum(1 for p in all_progress if p.completion_percentage >= 100)
    in_progress_subjects = sum(1 for p in all_progress if 0 < p.completion_percentage < 100)
    
    # Content statistics
    total_items = sum(p.total_items for p in all_progress)
    completed_items = sum(p.completed_items for p in all_progress)
    overall_completion = round(
        (completed_items / total_items * 100) if total_items > 0 else 0.0,
        2
    )
    
    # Practice attempt statistics
    attempts_stmt = select(PracticeAttempt).where(
        PracticeAttempt.user_id == current_user.id
    )
    attempts_result = await db.execute(attempts_stmt)
    attempts = attempts_result.scalars().all()
    
    total_attempts = len(attempts)
    correct_attempts = sum(1 for a in attempts if a.is_correct is True)
    practice_accuracy = round(
        (correct_attempts / total_attempts * 100) if total_attempts > 0 else None,
        2
    )
    
    # Time tracking
    time_stmt = select(func.sum(UserContentProgress.time_spent_seconds)).where(
        UserContentProgress.user_id == current_user.id
    )
    time_result = await db.execute(time_stmt)
    total_time_seconds = time_result.scalar() or 0
    total_time_hours = round(total_time_seconds / 3600, 2)
    
    # Last active date
    last_activity_stmt = (
        select(func.max(UserContentProgress.last_viewed_at))
        .where(UserContentProgress.user_id == current_user.id)
    )
    last_activity_result = await db.execute(last_activity_stmt)
    last_active = last_activity_result.scalar()
    
    return {
        "total_subjects": total_subjects,
        "completed_subjects": completed_subjects,
        "in_progress_subjects": in_progress_subjects,
        "total_content_items": total_items,
        "completed_content_items": completed_items,
        "overall_completion_percentage": overall_completion,
        "total_practice_attempts": total_attempts,
        "correct_practice_attempts": correct_attempts,
        "practice_accuracy_percentage": practice_accuracy,
        "total_time_spent_seconds": total_time_seconds,
        "total_time_spent_hours": total_time_hours,
        "streak_days": 0,  # Future feature
        "last_active_date": last_active.isoformat() if last_active else None
    }