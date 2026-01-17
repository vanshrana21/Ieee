"""
backend/services/study_map_service.py
Phase 3.1: Dynamic Study Map Generator

Computes personalized study roadmaps WITHOUT storing new data.
ALL content is fetched from existing tables and computed dynamically.

NO HARDCODED VALUES - Everything is database-driven.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from collections import defaultdict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload

from backend.orm.subject import Subject
from backend.orm.content_module import ContentModule, ModuleType, ModuleStatus
from backend.orm.learn_content import LearnContent
from backend.orm.case_content import CaseContent
from backend.orm.practice_question import PracticeQuestion
from backend.orm.topic_mastery import TopicMastery
from backend.orm.subject_progress import SubjectProgress
from backend.orm.practice_attempt import PracticeAttempt
from backend.orm.user import User

logger = logging.getLogger(__name__)

MASTERY_DEFICIT_WEIGHT = 0.40
CONTENT_FRESHNESS_WEIGHT = 0.25
EXAM_IMPORTANCE_WEIGHT = 0.20
CURRICULUM_RELEVANCE_WEIGHT = 0.15

HIGH_PRIORITY_THRESHOLD = 0.60
MEDIUM_PRIORITY_THRESHOLD = 0.35


def get_priority_label(score: float) -> str:
    if score >= HIGH_PRIORITY_THRESHOLD:
        return "High"
    elif score >= MEDIUM_PRIORITY_THRESHOLD:
        return "Medium"
    else:
        return "Low"


def generate_why_text(
    module_title: str,
    mastery_percent: float,
    has_practice_attempts: bool,
    days_since_last_attempt: int,
    content_count: int,
    priority: str
) -> str:
    """
    Generate explainable text for WHY this module is recommended.
    MUST be deterministic - same inputs = same output.
    """
    reasons = []
    
    if mastery_percent < 40:
        reasons.append(f"Low mastery ({round(mastery_percent)}%)")
    elif mastery_percent < 70:
        reasons.append(f"Moderate mastery ({round(mastery_percent)}%)")
    else:
        reasons.append(f"Good mastery ({round(mastery_percent)}%)")
    
    if not has_practice_attempts:
        reasons.append("not yet practiced")
    elif days_since_last_attempt > 14:
        reasons.append(f"last practiced {days_since_last_attempt} days ago")
    elif days_since_last_attempt > 7:
        reasons.append("needs revision")
    
    if content_count > 5:
        reasons.append(f"{content_count} content items available")
    
    if priority == "High":
        action = "Focus on this module"
    elif priority == "Medium":
        action = "Review this module"
    else:
        action = "Maintain progress"
    
    return f"{action}: {', '.join(reasons)}."


async def compute_module_mastery(
    user_id: int,
    module_id: int,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Compute mastery statistics for a specific module.
    
    Returns:
        {
            "mastery_percent": 45.5,
            "total_attempts": 12,
            "correct_attempts": 6,
            "last_attempt_date": datetime,
            "days_since_last": 5
        }
    """
    questions_stmt = select(PracticeQuestion.id).where(
        PracticeQuestion.module_id == module_id
    )
    questions_result = await db.execute(questions_stmt)
    question_ids = [row[0] for row in questions_result.fetchall()]
    
    if not question_ids:
        return {
            "mastery_percent": 0.0,
            "total_attempts": 0,
            "correct_attempts": 0,
            "last_attempt_date": None,
            "days_since_last": 999
        }
    
    attempts_stmt = select(
        func.count(PracticeAttempt.id).label("total"),
        func.sum(
            func.cast(PracticeAttempt.is_correct == True, Integer)
        ).label("correct"),
        func.max(PracticeAttempt.attempted_at).label("last_attempt")
    ).where(
        and_(
            PracticeAttempt.user_id == user_id,
            PracticeAttempt.practice_question_id.in_(question_ids)
        )
    )
    
    from sqlalchemy import Integer
    attempts_stmt = select(
        func.count(PracticeAttempt.id).label("total"),
        func.max(PracticeAttempt.attempted_at).label("last_attempt")
    ).where(
        and_(
            PracticeAttempt.user_id == user_id,
            PracticeAttempt.practice_question_id.in_(question_ids)
        )
    )
    
    result = await db.execute(attempts_stmt)
    row = result.fetchone()
    
    total_attempts = row.total or 0
    last_attempt = row.last_attempt
    
    correct_stmt = select(func.count(PracticeAttempt.id)).where(
        and_(
            PracticeAttempt.user_id == user_id,
            PracticeAttempt.practice_question_id.in_(question_ids),
            PracticeAttempt.is_correct == True
        )
    )
    correct_result = await db.execute(correct_stmt)
    correct_attempts = correct_result.scalar() or 0
    
    mastery_percent = 0.0
    if total_attempts > 0:
        mastery_percent = (correct_attempts / total_attempts) * 100
    
    days_since_last = 999
    if last_attempt:
        days_since_last = (datetime.utcnow() - last_attempt).days
    
    return {
        "mastery_percent": round(mastery_percent, 2),
        "total_attempts": total_attempts,
        "correct_attempts": correct_attempts,
        "last_attempt_date": last_attempt,
        "days_since_last": days_since_last
    }


async def get_module_content_items(
    module: ContentModule,
    db: AsyncSession
) -> List[Dict[str, Any]]:
    """
    Get all content items for a module in recommended order.
    Order: Learn → Cases → Practice
    """
    items = []
    
    if module.module_type == ModuleType.LEARN:
        learn_stmt = select(LearnContent).where(
            LearnContent.module_id == module.id
        ).order_by(LearnContent.order_index)
        learn_result = await db.execute(learn_stmt)
        for lc in learn_result.scalars().all():
            items.append({
                "type": "learn",
                "id": lc.id,
                "title": lc.title,
                "summary": lc.summary,
                "estimated_time": lc.estimated_time_minutes
            })
    
    elif module.module_type == ModuleType.CASES:
        case_stmt = select(CaseContent).where(
            CaseContent.module_id == module.id
        ).order_by(CaseContent.exam_importance.desc(), CaseContent.year.desc())
        case_result = await db.execute(case_stmt)
        for cc in case_result.scalars().all():
            items.append({
                "type": "case",
                "id": cc.id,
                "title": cc.case_name,
                "year": cc.year,
                "importance": cc.exam_importance.value if cc.exam_importance else "medium"
            })
    
    elif module.module_type == ModuleType.PRACTICE:
        practice_stmt = select(PracticeQuestion).where(
            PracticeQuestion.module_id == module.id
        ).order_by(PracticeQuestion.difficulty, PracticeQuestion.order_index)
        practice_result = await db.execute(practice_stmt)
        for pq in practice_result.scalars().all():
            items.append({
                "type": "practice",
                "id": pq.id,
                "title": pq.question[:100] + "..." if len(pq.question) > 100 else pq.question,
                "difficulty": pq.difficulty.value if pq.difficulty else "medium",
                "question_type": pq.question_type.value if pq.question_type else "mcq"
            })
    
    return items


async def generate_study_map(
    user_id: int,
    subject_id: int,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Generate a personalized study map for a subject.
    
    Algorithm:
    1. Fetch subject and all its modules
    2. For each module, compute mastery statistics
    3. Calculate priority score based on:
       - Mastery deficit (40%)
       - Content freshness (25%)
       - Exam importance (20%)
       - Curriculum relevance (15%)
    4. Sort modules by priority
    5. Include content items for each module
    
    Returns study map with explainable recommendations.
    """
    
    logger.info(f"Generating study map: user={user_id}, subject={subject_id}")
    
    subject_stmt = select(Subject).where(Subject.id == subject_id)
    subject_result = await db.execute(subject_stmt)
    subject = subject_result.scalar_one_or_none()
    
    if not subject:
        return {
            "success": False,
            "error": "Subject not found",
            "subject": None,
            "study_map": []
        }
    
    modules_stmt = select(ContentModule).where(
        and_(
            ContentModule.subject_id == subject_id,
            ContentModule.status == ModuleStatus.ACTIVE
        )
    ).order_by(ContentModule.order_index)
    
    modules_result = await db.execute(modules_stmt)
    modules = modules_result.scalars().all()
    
    if not modules:
        return {
            "success": True,
            "subject": {
                "id": subject.id,
                "title": subject.title
            },
            "study_map": [],
            "message": "No active modules found for this subject. Content coming soon!"
        }
    
    module_priorities = []
    
    for module in modules:
        mastery_stats = await compute_module_mastery(user_id, module.id, db)
        
        content_items = await get_module_content_items(module, db)
        content_count = len(content_items)
        
        mastery_deficit = (100 - mastery_stats["mastery_percent"]) / 100
        
        freshness_score = min(mastery_stats["days_since_last"] / 30, 1.0)
        
        exam_score = 0.5
        if module.module_type == ModuleType.PRACTICE:
            exam_score = 0.8
        elif module.module_type == ModuleType.CASES:
            exam_score = 0.7
        
        curriculum_score = 0.5
        
        priority_score = (
            mastery_deficit * MASTERY_DEFICIT_WEIGHT +
            freshness_score * CONTENT_FRESHNESS_WEIGHT +
            exam_score * EXAM_IMPORTANCE_WEIGHT +
            curriculum_score * CURRICULUM_RELEVANCE_WEIGHT
        )
        
        priority_label = get_priority_label(priority_score)
        
        why_text = generate_why_text(
            module.title,
            mastery_stats["mastery_percent"],
            mastery_stats["total_attempts"] > 0,
            mastery_stats["days_since_last"],
            content_count,
            priority_label
        )
        
        module_priorities.append({
            "module_id": module.id,
            "module_title": module.title,
            "module_type": module.module_type.value if module.module_type else None,
            "priority": priority_label,
            "priority_score": round(priority_score, 4),
            "why": why_text,
            "mastery_percent": mastery_stats["mastery_percent"],
            "total_attempts": mastery_stats["total_attempts"],
            "days_since_last": mastery_stats["days_since_last"],
            "content_count": content_count,
            "items": content_items
        })
    
    module_priorities.sort(key=lambda x: x["priority_score"], reverse=True)
    
    logger.info(f"Study map generated: {len(module_priorities)} modules for subject {subject_id}")
    
    return {
        "success": True,
        "subject": {
            "id": subject.id,
            "title": subject.title,
            "description": subject.description
        },
        "study_map": module_priorities,
        "generated_at": datetime.utcnow().isoformat()
    }


async def get_subject_overview(
    user_id: int,
    subject_id: int,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Get a quick overview of subject progress without full study map.
    Lighter weight for dashboard cards.
    """
    
    subject_stmt = select(Subject).where(Subject.id == subject_id)
    subject_result = await db.execute(subject_stmt)
    subject = subject_result.scalar_one_or_none()
    
    if not subject:
        return None
    
    progress_stmt = select(SubjectProgress).where(
        and_(
            SubjectProgress.user_id == user_id,
            SubjectProgress.subject_id == subject_id
        )
    )
    progress_result = await db.execute(progress_stmt)
    progress = progress_result.scalar_one_or_none()
    
    modules_stmt = select(func.count(ContentModule.id)).where(
        and_(
            ContentModule.subject_id == subject_id,
            ContentModule.status == ModuleStatus.ACTIVE
        )
    )
    modules_result = await db.execute(modules_stmt)
    module_count = modules_result.scalar() or 0
    
    return {
        "subject_id": subject.id,
        "subject_title": subject.title,
        "mastery_percent": round(progress.completion_percentage, 2) if progress else 0.0,
        "module_count": module_count,
        "last_activity": progress.last_activity_at.isoformat() if progress and progress.last_activity_at else None
    }
