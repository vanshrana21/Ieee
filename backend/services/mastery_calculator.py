"""
backend/services/mastery_calculator.py
Phase 2.2: Topic & Subject Mastery Calculation Engine

MASTERY FORMULA EXPLANATION:
===========================
Topic Mastery % = (Accuracy × 0.50) + (Recency × 0.30) + (Confidence × 0.15) + (Speed Penalty × 0.05)

Components:
1. ACCURACY (50% weight):
   - Correct answers / Total graded attempts
   - Recent 10 attempts weighted 2x more than older attempts
   - Range: 0.0 to 1.0

2. RECENCY (30% weight):
   - Exponential decay: 0.95 ^ days_since_attempt
   - Encourages regular practice
   - Range: 0.0 to 1.0

3. CONFIDENCE (15% weight):
   - Based on attempt count: min(attempts / 10, 1.0)
   - More attempts = higher confidence in the score
   - Range: 0.0 to 1.0

4. SPEED PENALTY (5% weight):
   - Penalizes rapid wrong answers (guessing detection)
   - If wrong AND time < 10 seconds → penalty
   - Range: 0.0 to 1.0 (inverted penalty)

STRENGTH LABELS:
- Weak: < 40%
- Average: 40-70%
- Strong: > 70%

DATABASE OPERATIONS:
- READS: practice_attempts, practice_questions, content_modules
- WRITES: topic_mastery, subject_progress
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from collections import defaultdict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from backend.orm.practice_attempt import PracticeAttempt
from backend.orm.practice_question import PracticeQuestion
from backend.orm.topic_mastery import TopicMastery
from backend.orm.subject_progress import SubjectProgress
from backend.orm.content_module import ContentModule

logger = logging.getLogger(__name__)

ACCURACY_WEIGHT = 0.50
RECENCY_WEIGHT = 0.30
CONFIDENCE_WEIGHT = 0.15
SPEED_PENALTY_WEIGHT = 0.05

RECENT_ATTEMPTS_BOOST = 10
CONFIDENCE_MAX_ATTEMPTS = 10
RECENCY_DECAY_FACTOR = 0.95
GUESSING_TIME_THRESHOLD = 10

WEAK_THRESHOLD = 40.0
STRONG_THRESHOLD = 70.0


def get_strength_label(mastery_percent: float) -> str:
    if mastery_percent < WEAK_THRESHOLD:
        return "Weak"
    elif mastery_percent < STRONG_THRESHOLD:
        return "Average"
    else:
        return "Strong"


async def compute_topic_mastery(
    user_id: int,
    subject_id: int,
    db: AsyncSession
) -> List[Dict[str, Any]]:
    """
    Calculate mastery scores for all topics in a subject.
    
    Algorithm:
    1. Fetch all practice attempts for user + subject
    2. Group by topic tag
    3. Calculate weighted mastery score
    4. Update topic_mastery table
    5. Return sorted by mastery (weakest first)
    
    Args:
        user_id: User ID
        subject_id: Subject ID
        db: Database session
    
    Returns:
        List of topic mastery dicts, sorted weakest first
    """
    
    logger.info(f"Computing mastery for user={user_id}, subject={subject_id}")
    
    stmt = select(PracticeAttempt, PracticeQuestion).join(
        PracticeQuestion,
        PracticeAttempt.practice_question_id == PracticeQuestion.id
    ).join(
        ContentModule,
        PracticeQuestion.module_id == ContentModule.id
    ).where(
        and_(
            PracticeAttempt.user_id == user_id,
            ContentModule.subject_id == subject_id
        )
    ).order_by(PracticeAttempt.attempted_at.desc())
    
    result = await db.execute(stmt)
    attempts_with_questions = result.all()
    
    if not attempts_with_questions:
        logger.info(f"No attempts found for user={user_id}, subject={subject_id}")
        return []
    
    topic_stats = defaultdict(lambda: {
        "attempts": [],
        "last_practiced": None
    })
    
    for attempt, question in attempts_with_questions:
        if not question.tags:
            continue
        
        tags = question.tags.split(",") if isinstance(question.tags, str) else question.tags
        
        for tag in tags:
            tag = tag.strip()
            if not tag:
                continue
                
            topic_stats[tag]["attempts"].append({
                "timestamp": attempt.attempted_at,
                "is_correct": attempt.is_correct,
                "time_taken": attempt.time_taken_seconds or 30
            })
            
            if (topic_stats[tag]["last_practiced"] is None or 
                attempt.attempted_at > topic_stats[tag]["last_practiced"]):
                topic_stats[tag]["last_practiced"] = attempt.attempted_at
    
    mastery_results = []
    now = datetime.utcnow()
    
    for topic, stats in topic_stats.items():
        attempts = stats["attempts"]
        graded_attempts = [a for a in attempts if a["is_correct"] is not None]
        
        if not graded_attempts:
            continue
        
        accuracy = 0.0
        total_weight = 0.0
        
        for i, attempt in enumerate(graded_attempts):
            weight = 2.0 if i < RECENT_ATTEMPTS_BOOST else 1.0
            if attempt["is_correct"]:
                accuracy += weight
            total_weight += weight
        
        accuracy = accuracy / total_weight if total_weight > 0 else 0.0
        
        recency_scores = []
        for attempt in attempts:
            days_ago = (now - attempt["timestamp"]).days
            recency_weight = RECENCY_DECAY_FACTOR ** days_ago
            recency_scores.append(recency_weight)
        
        recency = sum(recency_scores) / len(recency_scores) if recency_scores else 0.0
        
        confidence = min(len(graded_attempts) / CONFIDENCE_MAX_ATTEMPTS, 1.0)
        
        speed_penalty = 1.0
        rapid_wrong_count = sum(
            1 for a in graded_attempts 
            if not a["is_correct"] and a["time_taken"] < GUESSING_TIME_THRESHOLD
        )
        if rapid_wrong_count > 0:
            speed_penalty = max(0.0, 1.0 - (rapid_wrong_count / len(graded_attempts)))
        
        mastery_score = (
            accuracy * ACCURACY_WEIGHT +
            recency * RECENCY_WEIGHT +
            confidence * CONFIDENCE_WEIGHT +
            speed_penalty * SPEED_PENALTY_WEIGHT
        )
        
        mastery_percent = round(mastery_score * 100, 2)
        strength_label = get_strength_label(mastery_percent)
        
        mastery_results.append({
            "topic": topic,
            "mastery_percent": mastery_percent,
            "mastery_score": round(mastery_score, 4),
            "strength_label": strength_label,
            "accuracy": round(accuracy * 100, 2),
            "recency": round(recency, 4),
            "confidence": round(confidence, 4),
            "speed_penalty": round(speed_penalty, 4),
            "attempt_count": len(graded_attempts),
            "last_practiced": stats["last_practiced"]
        })
    
    for result in mastery_results:
        existing_stmt = select(TopicMastery).where(
            and_(
                TopicMastery.user_id == user_id,
                TopicMastery.subject_id == subject_id,
                TopicMastery.topic_tag == result["topic"]
            )
        )
        existing_result = await db.execute(existing_stmt)
        mastery_record = existing_result.scalar_one_or_none()
        
        if mastery_record:
            mastery_record.mastery_score = result["mastery_score"]
            mastery_record.attempt_count = result["attempt_count"]
            mastery_record.last_practiced_at = result["last_practiced"]
            if result["mastery_score"] < 0.4:
                mastery_record.difficulty_level = "easy"
            elif result["mastery_score"] < 0.7:
                mastery_record.difficulty_level = "medium"
            else:
                mastery_record.difficulty_level = "hard"
        else:
            difficulty = "easy"
            if result["mastery_score"] >= 0.7:
                difficulty = "hard"
            elif result["mastery_score"] >= 0.4:
                difficulty = "medium"
            
            mastery_record = TopicMastery(
                user_id=user_id,
                subject_id=subject_id,
                topic_tag=result["topic"],
                mastery_score=result["mastery_score"],
                attempt_count=result["attempt_count"],
                last_practiced_at=result["last_practiced"],
                difficulty_level=difficulty
            )
            db.add(mastery_record)
    
    await db.commit()
    
    sorted_results = sorted(mastery_results, key=lambda x: x["mastery_percent"])
    
    logger.info(f"Computed mastery for {len(sorted_results)} topics")
    
    return sorted_results


async def compute_subject_mastery(
    user_id: int,
    subject_id: int,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Compute subject-level mastery as weighted average of topic masteries.
    
    Topics with more questions have higher weight.
    
    Returns:
        {
            "subject_id": 1,
            "mastery_percent": 65.5,
            "strength_label": "Average",
            "completed_topics": 5,
            "total_topics": 8,
            "topic_breakdown": [...]
        }
    """
    
    logger.info(f"Computing subject mastery for user={user_id}, subject={subject_id}")
    
    topic_masteries = await compute_topic_mastery(user_id, subject_id, db)
    
    if not topic_masteries:
        progress_stmt = select(SubjectProgress).where(
            and_(
                SubjectProgress.user_id == user_id,
                SubjectProgress.subject_id == subject_id
            )
        )
        progress_result = await db.execute(progress_stmt)
        subject_progress = progress_result.scalar_one_or_none()
        
        if subject_progress:
            subject_progress.completion_percentage = 0.0
            await db.commit()
        
        return {
            "subject_id": subject_id,
            "mastery_percent": 0.0,
            "strength_label": "Weak",
            "completed_topics": 0,
            "total_topics": 0,
            "topic_breakdown": []
        }
    
    total_weighted_mastery = 0.0
    total_weight = 0.0
    
    for topic in topic_masteries:
        weight = topic["attempt_count"]
        total_weighted_mastery += topic["mastery_percent"] * weight
        total_weight += weight
    
    subject_mastery_percent = round(total_weighted_mastery / total_weight, 2) if total_weight > 0 else 0.0
    
    completed_topics = sum(1 for t in topic_masteries if t["mastery_percent"] >= STRONG_THRESHOLD)
    total_topics = len(topic_masteries)
    
    progress_stmt = select(SubjectProgress).where(
        and_(
            SubjectProgress.user_id == user_id,
            SubjectProgress.subject_id == subject_id
        )
    )
    progress_result = await db.execute(progress_stmt)
    subject_progress = progress_result.scalar_one_or_none()
    
    if subject_progress:
        subject_progress.completion_percentage = subject_mastery_percent
        subject_progress.completed_items = completed_topics
        subject_progress.total_items = max(total_topics, subject_progress.total_items)
        subject_progress.last_activity_at = datetime.utcnow()
    else:
        subject_progress = SubjectProgress(
            user_id=user_id,
            subject_id=subject_id,
            completion_percentage=subject_mastery_percent,
            completed_items=completed_topics,
            total_items=total_topics,
            last_activity_at=datetime.utcnow()
        )
        db.add(subject_progress)
    
    await db.commit()
    
    return {
        "subject_id": subject_id,
        "mastery_percent": subject_mastery_percent,
        "strength_label": get_strength_label(subject_mastery_percent),
        "completed_topics": completed_topics,
        "total_topics": total_topics,
        "topic_breakdown": topic_masteries
    }


async def get_weak_topics(
    user_id: int,
    subject_id: int,
    db: AsyncSession,
    limit: int = 3
) -> List[str]:
    """
    Get weakest topics for a user in a subject.
    
    Returns topic tags sorted by mastery (lowest first).
    """
    
    stmt = select(TopicMastery).where(
        and_(
            TopicMastery.user_id == user_id,
            TopicMastery.subject_id == subject_id
        )
    ).order_by(TopicMastery.mastery_score.asc())
    
    result = await db.execute(stmt)
    mastery_records = result.scalars().all()
    
    if mastery_records:
        return [record.topic_tag for record in mastery_records[:limit]]
    
    mastery_data = await compute_topic_mastery(user_id, subject_id, db)
    
    return [item["topic"] for item in mastery_data[:limit]]


async def get_strong_topics(
    user_id: int,
    subject_id: int,
    db: AsyncSession,
    limit: int = 3
) -> List[str]:
    """
    Get strongest topics for a user in a subject.
    
    Returns topic tags sorted by mastery (highest first).
    """
    
    stmt = select(TopicMastery).where(
        and_(
            TopicMastery.user_id == user_id,
            TopicMastery.subject_id == subject_id
        )
    ).order_by(TopicMastery.mastery_score.desc())
    
    result = await db.execute(stmt)
    mastery_records = result.scalars().all()
    
    if mastery_records:
        return [record.topic_tag for record in mastery_records[:limit]]
    
    mastery_data = await compute_topic_mastery(user_id, subject_id, db)
    mastery_data.reverse()
    
    return [item["topic"] for item in mastery_data[:limit]]


async def recalculate_all_mastery_for_user(
    user_id: int,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Recalculate mastery for ALL subjects a user has attempted.
    
    Called after any practice attempt to ensure data is fresh.
    
    Returns summary of recalculated data.
    """
    
    logger.info(f"Full mastery recalculation for user={user_id}")
    
    subject_stmt = select(ContentModule.subject_id).distinct().join(
        PracticeQuestion,
        PracticeQuestion.module_id == ContentModule.id
    ).join(
        PracticeAttempt,
        and_(
            PracticeAttempt.practice_question_id == PracticeQuestion.id,
            PracticeAttempt.user_id == user_id
        )
    )
    
    result = await db.execute(subject_stmt)
    subject_ids = [row[0] for row in result.fetchall()]
    
    recalculated = []
    for subject_id in subject_ids:
        mastery = await compute_subject_mastery(user_id, subject_id, db)
        recalculated.append({
            "subject_id": subject_id,
            "mastery_percent": mastery["mastery_percent"],
            "topics_count": mastery["total_topics"]
        })
    
    logger.info(f"Recalculated mastery for {len(recalculated)} subjects")
    
    return {
        "user_id": user_id,
        "subjects_recalculated": len(recalculated),
        "details": recalculated
    }


async def get_topic_mastery_detail(
    user_id: int,
    topic_tag: str,
    db: AsyncSession
) -> Optional[Dict[str, Any]]:
    """
    Get detailed mastery info for a specific topic.
    """
    
    stmt = select(TopicMastery).where(
        and_(
            TopicMastery.user_id == user_id,
            TopicMastery.topic_tag == topic_tag
        )
    )
    
    result = await db.execute(stmt)
    mastery = result.scalar_one_or_none()
    
    if not mastery:
        return None
    
    return {
        "topic_tag": mastery.topic_tag,
        "subject_id": mastery.subject_id,
        "mastery_percent": round(mastery.mastery_score * 100, 2),
        "strength_label": get_strength_label(mastery.mastery_score * 100),
        "attempt_count": mastery.attempt_count,
        "last_practiced": mastery.last_practiced_at.isoformat() if mastery.last_practiced_at else None,
        "difficulty_level": mastery.difficulty_level
    }


async def calculate_study_streak(
    user_id: int,
    db: AsyncSession
) -> int:
    """
    Calculate current study streak based on practice attempts.
    
    A streak is consecutive days with at least one attempt.
    """
    
    stmt = select(
        func.date(PracticeAttempt.attempted_at).label("attempt_date")
    ).where(
        PracticeAttempt.user_id == user_id
    ).distinct().order_by(
        func.date(PracticeAttempt.attempted_at).desc()
    )
    
    result = await db.execute(stmt)
    dates = [row[0] for row in result.fetchall()]
    
    if not dates:
        return 0
    
    today = datetime.utcnow().date()
    last_attempt = dates[0] if isinstance(dates[0], type(today)) else datetime.strptime(str(dates[0]), "%Y-%m-%d").date()
    
    if (today - last_attempt).days > 1:
        return 0
    
    streak = 1
    current_date = last_attempt
    
    for attempt_date in dates[1:]:
        if not isinstance(attempt_date, type(today)):
            attempt_date = datetime.strptime(str(attempt_date), "%Y-%m-%d").date()
        
        if (current_date - attempt_date).days == 1:
            streak += 1
            current_date = attempt_date
        else:
            break
    
    return streak
