"""
backend/routes/dashboard.py
Phase 9.3: Dashboard Data API - Backend-Authoritative Stats
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, distinct, case
from sqlalchemy.sql import extract
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta

from backend.database import get_db
from backend.orm.user import User
from backend.orm.subject import Subject
from backend.orm.curriculum import CourseCurriculum
from backend.orm.content_module import ContentModule
from backend.orm.learn_content import LearnContent
from backend.orm.case_content import CaseContent
from backend.orm.practice_question import PracticeQuestion
from backend.orm.user_content_progress import UserContentProgress, ContentType
from backend.orm.subject_progress import SubjectProgress
from backend.orm.practice_attempt import PracticeAttempt
from backend.routes.auth import get_current_user

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


class DashboardStatsResponse(BaseModel):
    overall_progress: float
    total_subjects: int
    completed_subjects: int
    practice_accuracy: float
    total_attempts: int
    correct_attempts: int
    study_streak: int
    last_activity: Optional[str]
    total_time_spent_seconds: int
    content_completed: int
    content_total: int

    class Config:
        from_attributes = True


class LastActivityResponse(BaseModel):
    content_type: Optional[str]
    content_id: Optional[int]
    content_title: Optional[str]
    subject_id: Optional[int]
    subject_title: Optional[str]
    last_viewed_at: Optional[str]


@router.get("/stats", response_model=DashboardStatsResponse)
async def get_dashboard_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 9.3: Aggregated dashboard statistics.
    All values computed from database - no hardcoding.
    """
    if not current_user.course_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User not enrolled in any course"
        )

    user_id = current_user.id
    course_id = current_user.course_id
    current_semester = current_user.current_semester or 1

    curriculum_stmt = (
        select(CourseCurriculum.subject_id)
        .where(
            and_(
                CourseCurriculum.course_id == course_id,
                CourseCurriculum.semester_number <= current_semester,
                CourseCurriculum.is_active == True
            )
        )
    )
    curriculum_result = await db.execute(curriculum_stmt)
    subject_ids = [row[0] for row in curriculum_result.all()]
    total_subjects = len(subject_ids)

    if total_subjects == 0:
        return DashboardStatsResponse(
            overall_progress=0.0,
            total_subjects=0,
            completed_subjects=0,
            practice_accuracy=0.0,
            total_attempts=0,
            correct_attempts=0,
            study_streak=0,
            last_activity=None,
            total_time_spent_seconds=0,
            content_completed=0,
            content_total=0
        )

    modules_stmt = (
        select(ContentModule.id)
        .where(ContentModule.subject_id.in_(subject_ids))
    )
    modules_result = await db.execute(modules_stmt)
    module_ids = [row[0] for row in modules_result.all()]

    total_learn = 0
    total_case = 0
    total_practice = 0

    if module_ids:
        learn_count_stmt = select(func.count(LearnContent.id)).where(LearnContent.module_id.in_(module_ids))
        learn_count_result = await db.execute(learn_count_stmt)
        total_learn = learn_count_result.scalar() or 0

        case_count_stmt = select(func.count(CaseContent.id)).where(CaseContent.module_id.in_(module_ids))
        case_count_result = await db.execute(case_count_stmt)
        total_case = case_count_result.scalar() or 0

        practice_count_stmt = select(func.count(PracticeQuestion.id)).where(PracticeQuestion.module_id.in_(module_ids))
        practice_count_result = await db.execute(practice_count_stmt)
        total_practice = practice_count_result.scalar() or 0

    content_total = total_learn + total_case + total_practice

    completed_stmt = (
        select(func.count(UserContentProgress.id))
        .where(
            and_(
                UserContentProgress.user_id == user_id,
                UserContentProgress.is_completed == True
            )
        )
    )
    completed_result = await db.execute(completed_stmt)
    content_completed = completed_result.scalar() or 0

    overall_progress = 0.0
    if content_total > 0:
        overall_progress = round((content_completed / content_total) * 100, 1)

    completed_subjects_stmt = (
        select(func.count(SubjectProgress.id))
        .where(
            and_(
                SubjectProgress.user_id == user_id,
                SubjectProgress.subject_id.in_(subject_ids),
                SubjectProgress.completion_percentage >= 100
            )
        )
    )
    completed_subjects_result = await db.execute(completed_subjects_stmt)
    completed_subjects = completed_subjects_result.scalar() or 0

    attempts_stmt = (
        select(
            func.count(PracticeAttempt.id),
            func.sum(case((PracticeAttempt.is_correct == True, 1), else_=0))
        )
        .where(PracticeAttempt.user_id == user_id)
    )
    attempts_result = await db.execute(attempts_stmt)
    attempts_row = attempts_result.one()
    total_attempts = attempts_row[0] or 0
    correct_attempts = attempts_row[1] or 0

    practice_accuracy = 0.0
    if total_attempts > 0:
        practice_accuracy = round((correct_attempts / total_attempts) * 100, 1)

    study_streak = await calculate_study_streak(db, user_id)

    last_activity_stmt = (
        select(UserContentProgress.last_viewed_at)
        .where(UserContentProgress.user_id == user_id)
        .order_by(UserContentProgress.last_viewed_at.desc())
        .limit(1)
    )
    last_activity_result = await db.execute(last_activity_stmt)
    last_activity_row = last_activity_result.scalar_one_or_none()
    last_activity = last_activity_row.isoformat() if last_activity_row else None

    time_spent_stmt = (
        select(func.sum(UserContentProgress.time_spent_seconds))
        .where(UserContentProgress.user_id == user_id)
    )
    time_spent_result = await db.execute(time_spent_stmt)
    total_time_spent_seconds = time_spent_result.scalar() or 0

    return DashboardStatsResponse(
        overall_progress=overall_progress,
        total_subjects=total_subjects,
        completed_subjects=completed_subjects,
        practice_accuracy=practice_accuracy,
        total_attempts=total_attempts,
        correct_attempts=correct_attempts,
        study_streak=study_streak,
        last_activity=last_activity,
        total_time_spent_seconds=total_time_spent_seconds,
        content_completed=content_completed,
        content_total=content_total
    )


async def calculate_study_streak(db: AsyncSession, user_id: int) -> int:
    """
    Calculate consecutive days of study activity.
    A day counts if user completed or viewed any content.
    """
    today = datetime.utcnow().date()
    
    activity_stmt = (
        select(UserContentProgress.last_viewed_at)
        .where(UserContentProgress.user_id == user_id)
        .order_by(UserContentProgress.last_viewed_at.desc())
    )
    result = await db.execute(activity_stmt)
    rows = result.all()

    if not rows:
        return 0

    unique_dates = sorted(set(row[0].date() for row in rows if row[0]), reverse=True)
    
    if not unique_dates:
        return 0

    streak = 0
    check_date = today

    for d in unique_dates:
        if d == check_date:
            streak += 1
            check_date = check_date - timedelta(days=1)
        elif d == check_date - timedelta(days=1):
            check_date = d
            streak += 1
            check_date = check_date - timedelta(days=1)
        else:
            break

    return streak


@router.get("/last-activity", response_model=LastActivityResponse)
async def get_last_activity(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get the most recently accessed content item.
    Used for "Continue where you left off" card.
    """
    stmt = (
        select(UserContentProgress)
        .where(UserContentProgress.user_id == current_user.id)
        .order_by(UserContentProgress.last_viewed_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    progress = result.scalar_one_or_none()

    if not progress:
        return LastActivityResponse(
            content_type=None,
            content_id=None,
            content_title=None,
            subject_id=None,
            subject_title=None,
            last_viewed_at=None
        )

    content_title = None
    subject_id = None
    subject_title = None

    if progress.content_type == ContentType.LEARN:
        content_stmt = (
            select(LearnContent)
            .where(LearnContent.id == progress.content_id)
        )
        content_result = await db.execute(content_stmt)
        content = content_result.scalar_one_or_none()
        if content:
            content_title = content.title
            module_stmt = select(ContentModule).where(ContentModule.id == content.module_id)
            module_result = await db.execute(module_stmt)
            module = module_result.scalar_one_or_none()
            if module:
                subject_id = module.subject_id
                subj_stmt = select(Subject).where(Subject.id == module.subject_id)
                subj_result = await db.execute(subj_stmt)
                subj = subj_result.scalar_one_or_none()
                if subj:
                    subject_title = subj.title

    elif progress.content_type == ContentType.CASE:
        content_stmt = (
            select(CaseContent)
            .where(CaseContent.id == progress.content_id)
        )
        content_result = await db.execute(content_stmt)
        content = content_result.scalar_one_or_none()
        if content:
            content_title = content.case_name
            module_stmt = select(ContentModule).where(ContentModule.id == content.module_id)
            module_result = await db.execute(module_stmt)
            module = module_result.scalar_one_or_none()
            if module:
                subject_id = module.subject_id
                subj_stmt = select(Subject).where(Subject.id == module.subject_id)
                subj_result = await db.execute(subj_stmt)
                subj = subj_result.scalar_one_or_none()
                if subj:
                    subject_title = subj.title

    elif progress.content_type == ContentType.PRACTICE:
        content_stmt = (
            select(PracticeQuestion)
            .where(PracticeQuestion.id == progress.content_id)
        )
        content_result = await db.execute(content_stmt)
        content = content_result.scalar_one_or_none()
        if content:
            content_title = f"Practice Question #{content.id}"
            module_stmt = select(ContentModule).where(ContentModule.id == content.module_id)
            module_result = await db.execute(module_stmt)
            module = module_result.scalar_one_or_none()
            if module:
                subject_id = module.subject_id
                subj_stmt = select(Subject).where(Subject.id == module.subject_id)
                subj_result = await db.execute(subj_stmt)
                subj = subj_result.scalar_one_or_none()
                if subj:
                    subject_title = subj.title

    return LastActivityResponse(
        content_type=progress.content_type.value if progress.content_type else None,
        content_id=progress.content_id,
        content_title=content_title,
        subject_id=subject_id,
        subject_title=subject_title,
        last_viewed_at=progress.last_viewed_at.isoformat() if progress.last_viewed_at else None
    )
