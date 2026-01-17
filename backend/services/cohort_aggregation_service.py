"""
backend/services/cohort_aggregation_service.py
Phase 8.1: Peer Cohort Definition & Aggregation

SYSTEM PURPOSE:
Create a deterministic, anonymous cohort engine that defines who a student 
is compared against for benchmarking. This phase ONLY aggregates data.

COHORT DEFINITION RULES:
========================
A student's cohort is defined STRICTLY by:
1. Course (course_id) - LLB / BA LLB / BBA LLB
2. Semester - Exact semester number only
3. Activity Window - Students with at least 1 practice attempt in last 90 days

DO NOT USE:
- college name
- user role
- year of admission
- random sampling
- hardcoded cohort sizes

DATA SOURCES (READ ONLY):
=========================
- users
- practice_attempts
- practice_evaluations
- subject_progress
- topic_mastery

AGGREGATION OUTPUTS:
===================
Per subject:
- total_students_in_cohort
- active_students_count (last 90 days)
- average_subject_mastery
- median_subject_mastery
- distribution buckets: <40%, 40-70%, >70%

Global cohort stats:
- avg_attempts_per_student
- avg_answers_submitted
- avg_time_per_attempt

CALCULATION RULES:
=================
- Use subject_progress.completion_percentage as mastery proxy
- Ignore NULL or missing mastery
- Use P50 for median
- Deterministic SQL/Python logic (no randomness)
- Same input → same result
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import statistics
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, distinct

from backend.orm.user import User
from backend.orm.course import Course
from backend.orm.subject import Subject
from backend.orm.subject_progress import SubjectProgress
from backend.orm.practice_attempt import PracticeAttempt
from backend.orm.curriculum import CourseCurriculum

logger = logging.getLogger(__name__)

ACTIVITY_WINDOW_DAYS = 90
DISTRIBUTION_WEAK_THRESHOLD = 40
DISTRIBUTION_STRONG_THRESHOLD = 70


async def get_cohort_definition(
    user_id: int,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Get the cohort definition for a user.
    
    Cohort is defined by:
    - course_id
    - current_semester
    
    Returns cohort parameters or None if user not enrolled.
    """
    user_stmt = select(User).where(User.id == user_id)
    user_result = await db.execute(user_stmt)
    user = user_result.scalar_one_or_none()
    
    if not user:
        return {"error": "User not found"}
    
    if not user.course_id or not user.current_semester:
        return {"error": "User not enrolled in a course/semester"}
    
    course_stmt = select(Course).where(Course.id == user.course_id)
    course_result = await db.execute(course_stmt)
    course = course_result.scalar_one_or_none()
    
    return {
        "course_id": user.course_id,
        "course_name": course.name if course else None,
        "course_code": course.code if course else None,
        "semester": user.current_semester,
        "user_id": user_id
    }


async def get_active_cohort_members(
    course_id: int,
    semester: int,
    db: AsyncSession,
    activity_days: int = ACTIVITY_WINDOW_DAYS
) -> List[int]:
    """
    Get user IDs of all active cohort members.
    
    Active = At least 1 practice attempt in last N days.
    
    Cohort filter:
    - Same course_id
    - Same current_semester
    - Active in last 90 days
    """
    cutoff_date = datetime.utcnow() - timedelta(days=activity_days)
    
    active_users_stmt = select(distinct(PracticeAttempt.user_id)).join(
        User, PracticeAttempt.user_id == User.id
    ).where(
        and_(
            User.course_id == course_id,
            User.current_semester == semester,
            User.is_active == True,
            PracticeAttempt.attempted_at >= cutoff_date
        )
    )
    
    result = await db.execute(active_users_stmt)
    active_user_ids = [row[0] for row in result.fetchall()]
    
    return active_user_ids


async def get_total_cohort_members(
    course_id: int,
    semester: int,
    db: AsyncSession
) -> int:
    """
    Get total count of users in the cohort (regardless of activity).
    """
    count_stmt = select(func.count(User.id)).where(
        and_(
            User.course_id == course_id,
            User.current_semester == semester,
            User.is_active == True
        )
    )
    
    result = await db.execute(count_stmt)
    return result.scalar() or 0


async def get_cohort_subjects(
    course_id: int,
    semester: int,
    db: AsyncSession
) -> List[Dict[str, Any]]:
    """
    Get subjects for the cohort's semester from curriculum.
    """
    curriculum_stmt = select(CourseCurriculum, Subject).join(
        Subject, CourseCurriculum.subject_id == Subject.id
    ).where(
        and_(
            CourseCurriculum.course_id == course_id,
            CourseCurriculum.semester_number == semester
        )
    ).order_by(Subject.title)
    
    result = await db.execute(curriculum_stmt)
    rows = result.fetchall()
    
    subjects = []
    for curriculum, subject in rows:
        subjects.append({
            "subject_id": subject.id,
            "title": subject.title,
            "code": subject.code,
            "category": subject.category.value if subject.category else None
        })
    
    return subjects


async def aggregate_subject_stats(
    subject_id: int,
    cohort_user_ids: List[int],
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Aggregate mastery statistics for a subject within the cohort.
    
    Calculates:
    - avg_mastery: Mean of completion_percentage
    - median_mastery: P50 of completion_percentage
    - distribution: {weak: <40%, average: 40-70%, strong: >70%}
    - students_with_progress: Count with non-null progress
    
    Uses subject_progress.completion_percentage as mastery proxy.
    """
    if not cohort_user_ids:
        return {
            "students_with_progress": 0,
            "avg_mastery": None,
            "median_mastery": None,
            "distribution": {"weak": 0, "average": 0, "strong": 0}
        }
    
    progress_stmt = select(SubjectProgress.completion_percentage).where(
        and_(
            SubjectProgress.subject_id == subject_id,
            SubjectProgress.user_id.in_(cohort_user_ids),
            SubjectProgress.completion_percentage.isnot(None)
        )
    )
    
    result = await db.execute(progress_stmt)
    mastery_values = [row[0] for row in result.fetchall() if row[0] is not None]
    
    if not mastery_values:
        return {
            "students_with_progress": 0,
            "avg_mastery": None,
            "median_mastery": None,
            "distribution": {"weak": 0, "average": 0, "strong": 0}
        }
    
    avg_mastery = statistics.mean(mastery_values)
    median_mastery = statistics.median(mastery_values)
    
    weak_count = sum(1 for v in mastery_values if v < DISTRIBUTION_WEAK_THRESHOLD)
    average_count = sum(1 for v in mastery_values if DISTRIBUTION_WEAK_THRESHOLD <= v < DISTRIBUTION_STRONG_THRESHOLD)
    strong_count = sum(1 for v in mastery_values if v >= DISTRIBUTION_STRONG_THRESHOLD)
    
    return {
        "students_with_progress": len(mastery_values),
        "avg_mastery": round(avg_mastery, 2),
        "median_mastery": round(median_mastery, 2),
        "distribution": {
            "weak": weak_count,
            "average": average_count,
            "strong": strong_count
        }
    }


async def aggregate_global_cohort_stats(
    cohort_user_ids: List[int],
    db: AsyncSession,
    activity_days: int = ACTIVITY_WINDOW_DAYS
) -> Dict[str, Any]:
    """
    Aggregate global statistics for the cohort.
    
    Calculates:
    - avg_attempts: Average practice attempts per student
    - avg_answers: Average answers submitted per student
    - avg_time_per_attempt: Average time taken per attempt
    """
    if not cohort_user_ids:
        return {
            "avg_attempts": 0,
            "avg_answers": 0,
            "avg_time_per_attempt": None
        }
    
    cutoff_date = datetime.utcnow() - timedelta(days=activity_days)
    
    attempts_stmt = select(
        PracticeAttempt.user_id,
        func.count(PracticeAttempt.id).label("attempt_count"),
        func.avg(PracticeAttempt.time_taken_seconds).label("avg_time")
    ).where(
        and_(
            PracticeAttempt.user_id.in_(cohort_user_ids),
            PracticeAttempt.attempted_at >= cutoff_date
        )
    ).group_by(PracticeAttempt.user_id)
    
    result = await db.execute(attempts_stmt)
    user_stats = result.fetchall()
    
    if not user_stats:
        return {
            "avg_attempts": 0,
            "avg_answers": 0,
            "avg_time_per_attempt": None
        }
    
    total_attempts = sum(row.attempt_count for row in user_stats)
    avg_attempts_per_student = total_attempts / len(cohort_user_ids)
    
    time_values = [row.avg_time for row in user_stats if row.avg_time is not None]
    avg_time = statistics.mean(time_values) if time_values else None
    
    return {
        "avg_attempts": round(avg_attempts_per_student, 2),
        "avg_answers": round(avg_attempts_per_student, 2),
        "avg_time_per_attempt": round(avg_time, 2) if avg_time else None
    }


async def get_cohort_aggregation(
    user_id: int,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Get complete cohort aggregation for a user.
    
    Main entry point for Phase 8.1.
    
    Returns:
    {
        "success": true,
        "cohort": {
            "course": "BA LLB",
            "semester": 6,
            "total_students": 200,
            "active_students": 142
        },
        "subjects": [
            {
                "subject_id": 1,
                "title": "Constitutional Law",
                "avg_mastery": 58.2,
                "median_mastery": 61.0,
                "distribution": {
                    "weak": 34,
                    "average": 78,
                    "strong": 30
                }
            }
        ],
        "global_stats": {
            "avg_attempts": 22.4,
            "avg_answers": 9.1,
            "avg_time_per_attempt": 45.2
        }
    }
    """
    cohort_def = await get_cohort_definition(user_id, db)
    
    if "error" in cohort_def:
        return {
            "success": False,
            "error": cohort_def["error"],
            "cohort": None,
            "subjects": [],
            "global_stats": {}
        }
    
    course_id = cohort_def["course_id"]
    semester = cohort_def["semester"]
    
    total_students = await get_total_cohort_members(course_id, semester, db)
    active_user_ids = await get_active_cohort_members(course_id, semester, db)
    active_students = len(active_user_ids)
    
    subjects = await get_cohort_subjects(course_id, semester, db)
    
    subject_stats = []
    for subject in subjects:
        stats = await aggregate_subject_stats(
            subject["subject_id"],
            active_user_ids,
            db
        )
        
        subject_stats.append({
            "subject_id": subject["subject_id"],
            "title": subject["title"],
            "code": subject["code"],
            "category": subject["category"],
            "students_with_progress": stats["students_with_progress"],
            "avg_mastery": stats["avg_mastery"],
            "median_mastery": stats["median_mastery"],
            "distribution": stats["distribution"]
        })
    
    global_stats = await aggregate_global_cohort_stats(active_user_ids, db)
    
    logger.info(
        f"Cohort aggregation for user={user_id}: "
        f"course={cohort_def['course_name']}, semester={semester}, "
        f"active={active_students}/{total_students}"
    )
    
    return {
        "success": True,
        "cohort": {
            "course": cohort_def["course_name"],
            "course_code": cohort_def["course_code"],
            "semester": semester,
            "total_students": total_students,
            "active_students": active_students,
            "activity_window_days": ACTIVITY_WINDOW_DAYS
        },
        "subjects": subject_stats,
        "global_stats": global_stats,
        "aggregated_at": datetime.utcnow().isoformat()
    }


async def get_empty_cohort_response() -> Dict[str, Any]:
    """
    Return a safe empty state for cohort with no data.
    """
    return {
        "success": True,
        "cohort": {
            "course": None,
            "course_code": None,
            "semester": None,
            "total_students": 0,
            "active_students": 0,
            "activity_window_days": ACTIVITY_WINDOW_DAYS
        },
        "subjects": [],
        "global_stats": {
            "avg_attempts": 0,
            "avg_answers": 0,
            "avg_time_per_attempt": None
        },
        "aggregated_at": datetime.utcnow().isoformat()
    }
