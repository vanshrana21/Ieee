"""
backend/services/tutor_context_service.py
Phase 4.1: Tutor Context Engine (Curriculum-Grounded)

Assembles deterministic, curriculum-grounded context for AI Tutor.
NO AI calls - pure data assembly from database.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from sqlalchemy.orm import joinedload

from backend.orm.user import User
from backend.orm.course import Course
from backend.orm.subject import Subject
from backend.orm.curriculum import CourseCurriculum
from backend.orm.topic_mastery import TopicMastery
from backend.orm.subject_progress import SubjectProgress
from backend.orm.practice_attempt import PracticeAttempt
from backend.orm.practice_question import PracticeQuestion
from backend.orm.content_module import ContentModule

logger = logging.getLogger(__name__)

WEAK_TOPIC_THRESHOLD = 50.0
STRONG_TOPIC_THRESHOLD = 70.0


async def assemble_context(user_id: int, db: AsyncSession) -> Dict[str, Any]:
    """
    Assemble curriculum-grounded context package for AI Tutor.
    
    Args:
        user_id: The user's ID
        db: Async database session
        
    Returns:
        Deterministic context dictionary
        
    Rules:
        - Same user state → same context (deterministic)
        - No hallucinated topics (only from mastery table)
        - Works with empty mastery tables
        - Zero AI calls
    """
    logger.info(f"Assembling tutor context for user_id={user_id}")
    
    user_stmt = (
        select(User)
        .options(joinedload(User.course))
        .where(User.id == user_id)
    )
    user_result = await db.execute(user_stmt)
    user = user_result.scalar_one_or_none()
    
    if not user:
        logger.warning(f"User not found: {user_id}")
        return _empty_context("User not found")
    
    student_info = _build_student_info(user)
    active_subjects = await _get_active_subjects(user, db)
    weak_topics, strong_topics = await _get_topic_mastery(user_id, db)
    recent_activity = await _get_recent_activity(user_id, db)
    study_map_snapshot = await _get_study_map_snapshot(user_id, active_subjects, db)
    
    context = {
        "student": student_info,
        "active_subjects": active_subjects,
        "weak_topics": weak_topics,
        "strong_topics": strong_topics,
        "recent_activity": recent_activity,
        "study_map_snapshot": study_map_snapshot,
        "constraints": {
            "allowed_subjects_only": True,
            "no_legal_advice": True,
            "exam_oriented": True
        }
    }
    
    logger.info(f"Context assembled: {len(active_subjects)} subjects, {len(weak_topics)} weak topics, {len(strong_topics)} strong topics")
    
    return context


def _build_student_info(user: User) -> Dict[str, Any]:
    """Build student information section."""
    course_name = user.course.name if user.course else "Not Enrolled"
    semester = user.current_semester or 1
    
    return {
        "course": course_name,
        "semester": semester
    }


async def _get_active_subjects(user: User, db: AsyncSession) -> List[Dict[str, Any]]:
    """
    Get subjects the student is currently enrolled in.
    Based on course_curriculum for user's course and semester.
    """
    if not user.course_id or not user.current_semester:
        return []
    
    stmt = (
        select(Subject)
        .join(CourseCurriculum, CourseCurriculum.subject_id == Subject.id)
        .where(
            CourseCurriculum.course_id == user.course_id,
            CourseCurriculum.semester_number <= user.current_semester,
            CourseCurriculum.is_active == True
        )
        .order_by(CourseCurriculum.semester_number, CourseCurriculum.display_order)
    )
    
    result = await db.execute(stmt)
    subjects = result.scalars().all()
    
    return [
        {
            "id": s.id,
            "title": s.title
        }
        for s in subjects
    ]


async def _get_topic_mastery(user_id: int, db: AsyncSession) -> tuple[List[Dict], List[Dict]]:
    """
    Get weak and strong topics from topic_mastery table.
    
    Returns:
        Tuple of (weak_topics, strong_topics)
    """
    stmt = (
        select(TopicMastery)
        .where(TopicMastery.user_id == user_id)
        .order_by(TopicMastery.mastery_score)
    )
    
    result = await db.execute(stmt)
    masteries = result.scalars().all()
    
    weak_topics = []
    strong_topics = []
    
    for m in masteries:
        topic_data = {
            "topic_tag": m.topic_tag,
            "mastery_percent": round(m.mastery_score, 1)
        }
        
        if m.mastery_score < WEAK_TOPIC_THRESHOLD:
            weak_topics.append(topic_data)
        elif m.mastery_score >= STRONG_TOPIC_THRESHOLD:
            strong_topics.append(topic_data)
    
    weak_topics = weak_topics[:10]
    strong_topics = sorted(strong_topics, key=lambda x: x["mastery_percent"], reverse=True)[:10]
    
    return weak_topics, strong_topics


async def _get_recent_activity(user_id: int, db: AsyncSession) -> Dict[str, Any]:
    """
    Get recent practice activity.
    """
    stmt = (
        select(PracticeAttempt)
        .options(
            joinedload(PracticeAttempt.practice_question)
            .joinedload(PracticeQuestion.module)
            .joinedload(ContentModule.subject)
        )
        .where(PracticeAttempt.user_id == user_id)
        .order_by(desc(PracticeAttempt.attempted_at))
        .limit(1)
    )
    
    result = await db.execute(stmt)
    last_attempt = result.scalar_one_or_none()
    
    if not last_attempt:
        return {
            "last_practice_days_ago": None,
            "last_subject": None
        }
    
    days_ago = (datetime.utcnow() - last_attempt.attempted_at).days
    
    last_subject = None
    if (last_attempt.practice_question and 
        last_attempt.practice_question.module and 
        last_attempt.practice_question.module.subject):
        last_subject = last_attempt.practice_question.module.subject.title
    
    return {
        "last_practice_days_ago": days_ago,
        "last_subject": last_subject
    }


async def _get_study_map_snapshot(
    user_id: int, 
    active_subjects: List[Dict], 
    db: AsyncSession
) -> List[Dict[str, Any]]:
    """
    Get study map snapshot based on subject progress.
    Priority is derived from completion percentage.
    """
    if not active_subjects:
        return []
    
    subject_ids = [s["id"] for s in active_subjects]
    
    modules_stmt = (
        select(ContentModule)
        .where(ContentModule.subject_id.in_(subject_ids))
        .order_by(ContentModule.subject_id, ContentModule.order_index)
    )
    
    modules_result = await db.execute(modules_stmt)
    modules = modules_result.scalars().all()
    
    progress_stmt = (
        select(SubjectProgress)
        .where(
            SubjectProgress.user_id == user_id,
            SubjectProgress.subject_id.in_(subject_ids)
        )
    )
    
    progress_result = await db.execute(progress_stmt)
    progress_map = {p.subject_id: p for p in progress_result.scalars().all()}
    
    snapshot = []
    seen_modules = set()
    
    for module in modules:
        if module.id in seen_modules:
            continue
        seen_modules.add(module.id)
        
        progress = progress_map.get(module.subject_id)
        completion = progress.completion_percentage if progress else 0
        
        if completion < 30:
            priority = "High"
        elif completion < 70:
            priority = "Medium"
        else:
            priority = "Low"
        
        snapshot.append({
            "module": module.title,
            "priority": priority
        })
    
    snapshot = sorted(
        snapshot, 
        key=lambda x: {"High": 0, "Medium": 1, "Low": 2}.get(x["priority"], 3)
    )[:10]
    
    return snapshot


def _empty_context(reason: str) -> Dict[str, Any]:
    """Return empty context structure with error."""
    return {
        "student": {
            "course": None,
            "semester": None
        },
        "active_subjects": [],
        "weak_topics": [],
        "strong_topics": [],
        "recent_activity": {
            "last_practice_days_ago": None,
            "last_subject": None
        },
        "study_map_snapshot": [],
        "constraints": {
            "allowed_subjects_only": True,
            "no_legal_advice": True,
            "exam_oriented": True
        },
        "error": reason
    }
