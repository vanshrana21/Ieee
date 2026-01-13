"""
backend/routes/progress.py
PHASE 9: User Learning Actions (Submissions, Attempts, Completions)

This builds on Phase 8's database tables with enhanced API responses
and standardized format for all user learning actions.

KEY FEATURES:
- Standardized response format: {success, message, data}
- Multiple attempt tracking (no overwrite)
- Server-side answer validation
- Comprehensive access control
- Production-grade logging

DATABASE TABLES (ALREADY EXISTS - NO CHANGES):
- practice_attempts
- user_content_progress
- subject_progress
"""
import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import joinedload
from datetime import datetime

from backend.database import get_db
from backend.orm.user import User
from backend.orm.subject import Subject
from backend.orm.curriculum import CourseCurriculum
from backend.orm.content_module import ContentModule, ModuleType, ModuleStatus
from backend.orm.learn_content import LearnContent
from backend.orm.case_content import CaseContent
from backend.orm.practice_question import PracticeQuestion, QuestionType
from backend.orm.user_content_progress import UserContentProgress, ContentType
from backend.orm.practice_attempt import PracticeAttempt
from backend.orm.subject_progress import SubjectProgress
from backend.routes.auth import get_current_user
from backend.schemas.progress import (
    ContentCompleteRequest,
    PracticeAttemptRequest,
    StandardResponse,
    AnswerSubmissionResponse,
    ContentCompletionResponse,
    UserProgressSummary,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/progress", tags=["Progress - Phase 9"])


# ================= HELPER FUNCTIONS =================

async def verify_content_access(
    db: AsyncSession,
    user: User,
    content_type: ContentType,
    content_id: int
) -> tuple[int, int, Any]:
    """
    Verify user can access content.
    
    VALIDATION CHECKS:
    1. User is enrolled in a course
    2. Content exists
    3. Content belongs to user's course
    4. Semester lock (cannot access future content)
    5. Module status (not locked)
    6. Premium access (if required)
    
    Args:
        db: Database session
        user: Current authenticated user
        content_type: Type of content (learn/case/practice)
        content_id: ID of the content item
    
    Returns:
        (subject_id, module_id, content_object)
    
    Raises:
        HTTPException with appropriate status code
    """
    # Check enrollment
    if not user.course_id or not user.current_semester:
        logger.warning(f"User {user.email} not enrolled in any course")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must be enrolled in a course to access content"
        )
    
    # Fetch content based on type
    if content_type == ContentType.LEARN:
        stmt = (
            select(LearnContent)
            .options(
                joinedload(LearnContent.module).joinedload(ContentModule.subject)
            )
            .where(LearnContent.id == content_id)
        )
    elif content_type == ContentType.CASE:
        stmt = (
            select(CaseContent)
            .options(
                joinedload(CaseContent.module).joinedload(ContentModule.subject)
            )
            .where(CaseContent.id == content_id)
        )
    elif content_type == ContentType.PRACTICE:
        stmt = (
            select(PracticeQuestion)
            .options(
                joinedload(PracticeQuestion.module).joinedload(ContentModule.subject)
            )
            .where(PracticeQuestion.id == content_id)
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid content type: {content_type}"
        )
    
    result = await db.execute(stmt)
    content = result.scalar_one_or_none()
    
    if not content or not content.module or not content.module.subject:
        logger.warning(f"Content not found: {content_type}:{content_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Content not found"
        )
    
    module = content.module
    subject = module.subject
    
    # Verify subject is in user's course
    curriculum_stmt = select(CourseCurriculum).where(
        CourseCurriculum.course_id == user.course_id,
        CourseCurriculum.subject_id == subject.id,
        CourseCurriculum.is_active == True
    )
    curriculum_result = await db.execute(curriculum_stmt)
    curriculum_item = curriculum_result.scalar_one_or_none()
    
    if not curriculum_item:
        logger.warning(
            f"Subject {subject.id} not in user {user.email}'s course"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This content is not part of your enrolled course"
        )
    
    # Check semester lock
    if curriculum_item.semester_number > user.current_semester:
        logger.warning(
            f"User {user.email} attempted to access future semester content: "
            f"semester {curriculum_item.semester_number}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This content is locked. It will be available in Semester {curriculum_item.semester_number}"
        )
    
    # Check module status
    if module.status == ModuleStatus.LOCKED:
        logger.warning(f"Module {module.id} is locked")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This module is currently locked"
        )
    
    if module.status == ModuleStatus.COMING_SOON:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This content is coming soon"
        )
    
    # Check premium access
    if not module.is_free and not user.is_premium:
        logger.warning(f"User {user.email} lacks premium for module {module.id}")
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="This content requires a premium subscription"
        )
    
    logger.info(
        f"Access granted: user={user.email}, content={content_type}:{content_id}"
    )
    return subject.id, module.id, content


async def get_or_create_subject_progress(
    db: AsyncSession,
    user_id: int,
    subject_id: int
) -> SubjectProgress:
    """
    Get existing subject progress or create new record.
    
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
        logger.info(f"Created subject progress: user={user_id}, subject={subject_id}")
    
    return progress


async def recalculate_subject_progress(
    db: AsyncSession,
    user_id: int,
    subject_id: int
) -> Dict[str, Any]:
    """
    Recalculate subject progress from user_content_progress records.
    
    Steps:
    1. Count total items in subject (learn + cases + practice)
    2. Count completed items for user
    3. Calculate completion percentage
    4. Calculate practice accuracy
    5. Update SubjectProgress record
    
    Args:
        db: Database session
        user_id: User ID
        subject_id: Subject ID
    
    Returns:
        Dictionary with progress metrics
    """
    # Get all modules for subject
    modules_stmt = select(ContentModule).where(
        ContentModule.subject_id == subject_id
    )
    modules_result = await db.execute(modules_stmt)
    modules = modules_result.scalars().all()
    module_ids = [m.id for m in modules]
    
    if not module_ids:
        # No modules = 0% progress
        progress = await get_or_create_subject_progress(db, user_id, subject_id)
        progress.recalculate_progress(0, 0)
        progress.update_activity()
        return {
            "completion_percentage": 0.0,
            "total_items": 0,
            "completed_items": 0
        }
    
    # Count total items
    learn_count = (await db.execute(
        select(func.count(LearnContent.id)).where(
            LearnContent.module_id.in_(module_ids)
        )
    )).scalar() or 0
    
    case_count = (await db.execute(
        select(func.count(CaseContent.id)).where(
            CaseContent.module_id.in_(module_ids)
        )
    )).scalar() or 0
    
    practice_count = (await db.execute(
        select(func.count(PracticeQuestion.id)).where(
            PracticeQuestion.module_id.in_(module_ids)
        )
    )).scalar() or 0
    
    total_items = learn_count + case_count + practice_count
    
    # Count completed items per type
    completed_count = 0
    
    if learn_count > 0:
        learn_ids = [row[0] for row in (await db.execute(
            select(LearnContent.id).where(LearnContent.module_id.in_(module_ids))
        )).fetchall()]
        
        completed_count += (await db.execute(
            select(func.count(UserContentProgress.id)).where(
                UserContentProgress.user_id == user_id,
                UserContentProgress.content_type == ContentType.LEARN,
                UserContentProgress.content_id.in_(learn_ids),
                UserContentProgress.is_completed == True
            )
        )).scalar() or 0
    
    if case_count > 0:
        case_ids = [row[0] for row in (await db.execute(
            select(CaseContent.id).where(CaseContent.module_id.in_(module_ids))
        )).fetchall()]
        
        completed_count += (await db.execute(
            select(func.count(UserContentProgress.id)).where(
                UserContentProgress.user_id == user_id,
                UserContentProgress.content_type == ContentType.CASE,
                UserContentProgress.content_id.in_(case_ids),
                UserContentProgress.is_completed == True
            )
        )).scalar() or 0
    
    if practice_count > 0:
        practice_ids = [row[0] for row in (await db.execute(
            select(PracticeQuestion.id).where(PracticeQuestion.module_id.in_(module_ids))
        )).fetchall()]
        
        completed_count += (await db.execute(
            select(func.count(UserContentProgress.id)).where(
                UserContentProgress.user_id == user_id,
                UserContentProgress.content_type == ContentType.PRACTICE,
                UserContentProgress.content_id.in_(practice_ids),
                UserContentProgress.is_completed == True
            )
        )).scalar() or 0
    
    # Update subject progress
    progress = await get_or_create_subject_progress(db, user_id, subject_id)
    progress.recalculate_progress(completed_count, total_items)
    progress.update_activity()
    
    completion_percentage = progress.completion_percentage
    
    logger.info(
        f"Recalculated progress: user={user_id}, subject={subject_id}, "
        f"completion={completion_percentage:.1f}%"
    )
    
    return {
        "completion_percentage": completion_percentage,
        "total_items": total_items,
        "completed_items": completed_count
    }


async def calculate_practice_accuracy(
    db: AsyncSession,
    user_id: int,
    subject_id: int
) -> Optional[float]:
    """
    Calculate user's practice accuracy for a subject.
    
    Accuracy = (correct attempts / total MCQ attempts) * 100
    Only counts MCQ attempts (essays have NULL is_correct).
    
    Args:
        db: Database session
        user_id: User ID
        subject_id: Subject ID
    
    Returns:
        Accuracy percentage or None if no attempts
    """
    # Get practice questions for subject
    modules_stmt = select(ContentModule.id).where(
        ContentModule.subject_id == subject_id,
        ContentModule.module_type == ModuleType.PRACTICE
    )
    module_ids = [row[0] for row in (await db.execute(modules_stmt)).fetchall()]
    
    if not module_ids:
        return None
    
    question_ids = [row[0] for row in (await db.execute(
        select(PracticeQuestion.id).where(
            PracticeQuestion.module_id.in_(module_ids)
        )
    )).fetchall()]
    
    if not question_ids:
        return None
    
    # Count total MCQ attempts (where is_correct is not NULL)
    total_attempts = (await db.execute(
        select(func.count(PracticeAttempt.id)).where(
            PracticeAttempt.user_id == user_id,
            PracticeAttempt.practice_question_id.in_(question_ids),
            PracticeAttempt.is_correct.isnot(None)
        )
    )).scalar() or 0
    
    if total_attempts == 0:
        return None
    
    # Count correct attempts
    correct_attempts = (await db.execute(
        select(func.count(PracticeAttempt.id)).where(
            PracticeAttempt.user_id == user_id,
            PracticeAttempt.practice_question_id.in_(question_ids),
            PracticeAttempt.is_correct == True
        )
    )).scalar() or 0
    
    accuracy = round((correct_attempts / total_attempts) * 100, 2)
    
    logger.info(
        f"Practice accuracy: user={user_id}, subject={subject_id}, "
        f"accuracy={accuracy:.1f}% ({correct_attempts}/{total_attempts})"
    )
    
    return accuracy


# ================= API ENDPOINTS =================

@router.post("/submit-answer", response_model=StandardResponse)
async def submit_answer(
    request: PracticeAttemptRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Submit answer to a practice question.
    
    PHASE 9 ENDPOINT - Standardized Response Format
    
    VALIDATION:
    - User is authenticated ✓
    - Question exists ✓
    - Question belongs to accessible subject/module ✓
    - Semester lock enforced ✓
    
    BEHAVIOR:
    - Server-side answer validation (MCQ only)
    - Stores all attempts (no overwrite)
    - Auto-increments attempt_number
    - Updates user_content_progress
    - Updates subject_progress
    - Returns correct answer after submission
    
    REQUEST:
        {
            "question_id": 42,
            "selected_option": "B",
            "time_taken_seconds": 45
        }
    
    RESPONSE:
        {
            "success": true,
            "message": "Answer submitted successfully",
            "data": {
                "is_correct": true,
                "attempt_number": 2,
                "correct_answer": "B",
                "explanation": "...",
                "current_accuracy": 78.5
            }
        }
    """
    logger.info(
        f"[PHASE 9] Submit answer: question_id={request.question_id}, "
        f"user={current_user.email}"
    )
    
    try:
        # Verify access
        subject_id, module_id, question = await verify_content_access(
            db, current_user, ContentType.PRACTICE, request.question_id
        )
        
        # Type check
        if not isinstance(question, PracticeQuestion):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid question ID"
            )
        
        # Calculate attempt number
        attempt_count_stmt = select(func.count(PracticeAttempt.id)).where(
            PracticeAttempt.user_id == current_user.id,
            PracticeAttempt.practice_question_id == request.question_id
        )
        attempt_count = (await db.execute(attempt_count_stmt)).scalar() or 0
        attempt_number = attempt_count + 1
        
        # Auto-grade if MCQ
        is_correct = None
        if question.question_type == QuestionType.MCQ:
            is_correct = question.check_mcq_answer(request.selected_option)
            logger.info(
                f"MCQ graded: question_id={request.question_id}, "
                f"is_correct={is_correct}"
            )
        else:
            logger.info(
                f"Non-MCQ submitted: question_id={request.question_id}, "
                f"type={question.question_type}"
            )
        
        # Create attempt record
        attempt = PracticeAttempt(
            user_id=current_user.id,
            practice_question_id=request.question_id,
            selected_option=request.selected_option,
            is_correct=is_correct,
            attempt_number=attempt_number,
            time_taken_seconds=request.time_taken_seconds,
            attempted_at=datetime.utcnow()
        )
        db.add(attempt)
        
        # Update or create user_content_progress
        progress_stmt = select(UserContentProgress).where(
            UserContentProgress.user_id == current_user.id,
            UserContentProgress.content_type == ContentType.PRACTICE,
            UserContentProgress.content_id == request.question_id
        )
        progress_result = await db.execute(progress_stmt)
        progress = progress_result.scalar_one_or_none()
        
        if not progress:
            progress = UserContentProgress(
                user_id=current_user.id,
                content_type=ContentType.PRACTICE,
                content_id=request.question_id,
                is_completed=False,  # Practice doesn't auto-complete
                last_viewed_at=datetime.utcnow(),
                view_count=1,
                time_spent_seconds=request.time_taken_seconds
            )
            db.add(progress)
            logger.info(f"Created progress record for question {request.question_id}")
        else:
            progress.record_view(request.time_taken_seconds)
            logger.info(f"Updated progress record for question {request.question_id}")
        
        # Recalculate subject progress
        progress_metrics = await recalculate_subject_progress(
            db, current_user.id, subject_id
        )
        
        # Calculate practice accuracy
        accuracy = await calculate_practice_accuracy(
            db, current_user.id, subject_id
        )
        
        # Commit all changes
        await db.commit()
        await db.refresh(attempt)
        
        # Build response data
        response_data = {
            "is_correct": is_correct,
            "attempt_number": attempt_number,
            "correct_answer": question.correct_answer,
            "explanation": question.explanation,
            "current_accuracy": accuracy,
            "completion_percentage": progress_metrics["completion_percentage"]
        }
        
        logger.info(
            f"[PHASE 9] Answer submitted successfully: user={current_user.email}, "
            f"question={request.question_id}, correct={is_correct}"
        )
        
        return {
            "success": True,
            "message": "Answer submitted successfully",
            "data": response_data
        }
    
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error submitting answer: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to submit answer. Please try again."
        )


@router.post("/complete-content", response_model=StandardResponse)
async def complete_content(
    request: ContentCompleteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Mark content item as completed.
    
    PHASE 9 ENDPOINT - Standardized Response Format
    
    WORKS FOR:
    - LearnContent (theory/concepts)
    - CaseContent (case law)
    - PracticeQuestion (after attempt)
    
    VALIDATION:
    - User is authenticated ✓
    - Content exists ✓
    - Content belongs to accessible subject/module ✓
    - Semester lock enforced ✓
    
    BEHAVIOR:
    - Sets is_completed = true (permanent)
    - Sets completed_at timestamp
    - Increments view_count
    - Updates subject_progress
    - Idempotent (calling twice = no error)
    
    REQUEST:
        {
            "content_type": "learn",
            "content_id": 42,
            "time_spent_seconds": 180
        }
    
    RESPONSE:
        {
            "success": true,
            "message": "Content marked as completed",
            "data": {
                "completion_percentage": 45.5,
                "total_items": 50,
                "completed_items": 23
            }
        }
    """
    logger.info(
        f"[PHASE 9] Complete content: type={request.content_type}, "
        f"id={request.content_id}, user={current_user.email}"
    )
    
    try:
        # Validate content type
        try:
            content_type_enum = ContentType(request.content_type.lower())
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid content_type. Must be: learn, case, or practice"
            )
        
        # Verify access
        subject_id, module_id, content = await verify_content_access(
            db, current_user, content_type_enum, request.content_id
        )
        
        # Get or create progress record
        progress_stmt = select(UserContentProgress).where(
            UserContentProgress.user_id == current_user.id,
            UserContentProgress.content_type == content_type_enum,
            UserContentProgress.content_id == request.content_id
        )
        progress_result = await db.execute(progress_stmt)
        progress = progress_result.scalar_one_or_none()
        
        if progress:
            # Update existing record
            if not progress.is_completed:
                progress.mark_complete()
                logger.info(f"Marked content as complete: {content_type_enum}:{request.content_id}")
            if request.time_spent_seconds:
                progress.record_view(request.time_spent_seconds)
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
            logger.info(f"Created completed progress: {content_type_enum}:{request.content_id}")
        
        # Recalculate subject progress
        progress_metrics = await recalculate_subject_progress(
            db, current_user.id, subject_id
        )
        
        # Commit changes
        await db.commit()
        
        logger.info(
            f"[PHASE 9] Content completed: user={current_user.email}, "
            f"type={request.content_type}, id={request.content_id}"
        )
        
        return {
            "success": True,
            "message": "Content marked as completed",
            "data": progress_metrics
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error completing content: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to complete content. Please try again."
        )


@router.get("/my-progress", response_model=StandardResponse)
async def get_my_progress(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get user's overall progress summary.
    
    PHASE 9 ENDPOINT - Standardized Response Format
    
    RETURNS:
    - Total subjects enrolled
    - Overall completion percentage
    - Practice accuracy across all subjects
    - Recent activity summary
    
    RESPONSE:
        {
            "success": true,
            "message": "Progress retrieved successfully",
            "data": {
                "total_subjects": 8,
                "overall_completion": 37.5,
                "practice_accuracy": 76.0,
                "recent_activity": [...]
            }
        }
    """
    logger.info(f"[PHASE 9] Get progress summary: user={current_user.email}")
    
    try:
        # Check enrollment
        if not current_user.course_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You must be enrolled in a course"
            )
        
        # Get all subject progress records
        progress_stmt = select(SubjectProgress).where(
            SubjectProgress.user_id == current_user.id
        )
        progress_result = await db.execute(progress_stmt)
        all_progress = progress_result.scalars().all()
        
        total_subjects = len(all_progress)
        
        # Calculate overall completion
        if total_subjects > 0:
            overall_completion = round(
                sum(p.completion_percentage for p in all_progress) / total_subjects,
                2
            )
        else:
            overall_completion = 0.0
        
        # Calculate overall practice accuracy
        total_mcq_attempts = (await db.execute(
            select(func.count(PracticeAttempt.id)).where(
                PracticeAttempt.user_id == current_user.id,
                PracticeAttempt.is_correct.isnot(None)
            )
        )).scalar() or 0
        
        if total_mcq_attempts > 0:
            correct_mcq = (await db.execute(
                select(func.count(PracticeAttempt.id)).where(
                    PracticeAttempt.user_id == current_user.id,
                    PracticeAttempt.is_correct == True
                )
            )).scalar() or 0
            
            practice_accuracy = round((correct_mcq / total_mcq_attempts) * 100, 2)
        else:
            practice_accuracy = None
        
        # Get recent activity
        recent_stmt = (
            select(UserContentProgress)
            .where(UserContentProgress.user_id == current_user.id)
            .order_by(UserContentProgress.last_viewed_at.desc())
            .limit(5)
        )
        recent_result = await db.execute(recent_stmt)
        recent_items = recent_result.scalars().all()
        
        recent_activity = [
            {
                "content_type": item.content_type.value,
                "content_id": item.content_id,
                "is_completed": item.is_completed,
                "last_viewed_at": item.last_viewed_at.isoformat()
            }
            for item in recent_items
        ]
        
        response_data = {
            "total_subjects": total_subjects,
            "overall_completion": overall_completion,
            "practice_accuracy": practice_accuracy,
            "total_attempts": total_mcq_attempts,
            "recent_activity": recent_activity
        }
        
        logger.info(f"[PHASE 9] Progress summary retrieved: user={current_user.email}")
        
        return {
            "success": True,
            "message": "Progress retrieved successfully",
            "data": response_data
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving progress: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve progress"
        )


@router.get("/subject/{subject_id}/progress", response_model=StandardResponse)
async def get_subject_progress(
    subject_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed progress for a specific subject.
    
    PHASE 9 ENDPOINT - Standardized Response Format
    
    RETURNS:
    - Completion percentage
    - Practice accuracy
    - Module-wise breakdown
    - Recent items completed
    
    RESPONSE:
        {
            "success": true,
            "message": "Subject progress retrieved",
            "data": {
                "completion_percentage": 45.5,
                "practice_accuracy": 82.0,
                "modules": {...}
            }
        }
    """
    logger.info(
        f"[PHASE 9] Get subject progress: subject_id={subject_id}, "
        f"user={current_user.email}"
    )
    
    try:
        # Verify subject access
        if not current_user.course_id or not current_user.current_semester:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You must be enrolled in a course"
            )
        
        curriculum_stmt = (
            select(CourseCurriculum)
            .options(joinedload(CourseCurriculum.subject))
            .where(
                CourseCurriculum.course_id == current_user.course_id,
                CourseCurriculum.subject_id == subject_id,
                CourseCurriculum.is_active == True
            )
        )
        curriculum_result = await db.execute(curriculum_stmt)
        curriculum_item = curriculum_result.scalar_one_or_none()
        
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
        
        # Get or create subject progress
        progress = await get_or_create_subject_progress(
            db, current_user.id, subject_id
        )
        
        # Recalculate to ensure accuracy
        progress_metrics = await recalculate_subject_progress(
            db, current_user.id, subject_id
        )
        
        # Calculate practice accuracy
        accuracy = await calculate_practice_accuracy(
            db, current_user.id, subject_id
        )
        
        await db.commit()
        
        response_data = {
            "subject_id": subject_id,
            "subject_title": curriculum_item.subject.title,
            "completion_percentage": progress_metrics["completion_percentage"],
            "total_items": progress_metrics["total_items"],
            "completed_items": progress_metrics["completed_items"],
            "practice_accuracy": accuracy,
            "last_activity_at": progress.last_activity_at.isoformat()
        }
        
        logger.info(
            f"[PHASE 9] Subject progress retrieved: user={current_user.email}, "
            f"subject={subject_id}"
        )
        
        return {
            "success": True,
            "message": "Subject progress retrieved successfully",
            "data": response_data
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving subject progress: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve subject progress"
        )