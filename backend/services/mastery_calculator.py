"""
backend/services/mastery_calculator.py
Phase 9B: Topic mastery calculation from practice attempts
"""

import logging
from typing import List, Dict, Any
from datetime import datetime
from collections import defaultdict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from backend.orm.practice_attempt import PracticeAttempt
from backend.orm.practice_question import PracticeQuestion
from backend.orm.topic_mastery import TopicMastery

logger = logging.getLogger(__name__)


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
    3. Calculate mastery score:
       - Accuracy: % correct (weight: 0.6)
       - Recency: Exponential decay for older attempts (weight: 0.3)
       - Confidence: More attempts = more confidence (weight: 0.1)
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
    
    # 1. Fetch practice attempts with questions
    from backend.orm.content_module import ContentModule
    
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
    )
    
    result = await db.execute(stmt)
    attempts_with_questions = result.all()
    
    if not attempts_with_questions:
        logger.info(f"No attempts found for user={user_id}, subject={subject_id}")
        return []
    
    # 2. Group by topic tags
    topic_stats = defaultdict(lambda: {
        "correct": 0,
        "total": 0,
        "attempts": [],
        "last_practiced": None
    })
    
    for attempt, question in attempts_with_questions:
        # Skip if no tags
        if not question.tags:
            continue
        
        # Process each tag
        for tag in question.tags:
            topic_stats[tag]["total"] += 1
            
            # Count correct (only for MCQs where is_correct is not None)
            if attempt.is_correct is True:
                topic_stats[tag]["correct"] += 1
            
            # Store attempt with timestamp for recency calculation
            topic_stats[tag]["attempts"].append({
                "timestamp": attempt.attempted_at,
                "correct": attempt.is_correct
            })
            
            # Track last practice
            if (topic_stats[tag]["last_practiced"] is None or 
                attempt.attempted_at > topic_stats[tag]["last_practiced"]):
                topic_stats[tag]["last_practiced"] = attempt.attempted_at
    
    # 3. Calculate mastery scores
    mastery_results = []
    now = datetime.utcnow()
    
    for topic, stats in topic_stats.items():
        # Accuracy component (weight: 0.6)
        # Only count MCQs (where is_correct is not None)
        mcq_attempts = [a for a in stats["attempts"] if a["correct"] is not None]
        
        if mcq_attempts:
            accuracy = sum(1 for a in mcq_attempts if a["correct"]) / len(mcq_attempts)
        else:
            accuracy = 0.5  # Default if no graded attempts
        
        # Recency component (weight: 0.3)
        # Exponential decay: 0.95 ^ days_since_attempt
        recency_scores = []
        for attempt in stats["attempts"]:
            days_ago = (now - attempt["timestamp"]).days
            recency_weight = 0.95 ** days_ago
            recency_scores.append(recency_weight)
        
        recency = sum(recency_scores) / len(recency_scores) if recency_scores else 0.0
        
        # Confidence component (weight: 0.1)
        # More attempts = higher confidence (capped at 10 attempts)
        attempt_confidence = min(stats["total"] / 10.0, 1.0)
        
        # Combined mastery score
        mastery_score = (
            accuracy * 0.6 +
            recency * 0.3 +
            attempt_confidence * 0.1
        )
        
        # Determine difficulty level
        if mastery_score < 0.3:
            difficulty = "easy"
        elif mastery_score < 0.7:
            difficulty = "medium"
        else:
            difficulty = "hard"
        
        mastery_results.append({
            "topic": topic,
            "mastery_score": round(mastery_score, 3),
            "accuracy": round(accuracy, 3),
            "recency": round(recency, 3),
            "attempt_count": stats["total"],
            "last_practiced": stats["last_practiced"],
            "difficulty_level": difficulty,
            "priority": "high" if mastery_score < 0.5 else "medium" if mastery_score < 0.75 else "low"
        })
    
    # 4. Update topic_mastery table
    for result in mastery_results:
        # Check if record exists
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
            # Update existing
            mastery_record.update_mastery(result["mastery_score"])
            mastery_record.attempt_count = result["attempt_count"]
        else:
            # Create new
            mastery_record = TopicMastery(
                user_id=user_id,
                subject_id=subject_id,
                topic_tag=result["topic"],
                mastery_score=result["mastery_score"],
                attempt_count=result["attempt_count"],
                last_practiced_at=result["last_practiced"],
                difficulty_level=result["difficulty_level"]
            )
            db.add(mastery_record)
    
    await db.commit()
    
    # 5. Sort by mastery (weakest first)
    sorted_results = sorted(mastery_results, key=lambda x: x["mastery_score"])
    
    logger.info(f"Computed mastery for {len(sorted_results)} topics")
    
    return sorted_results


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
    
    # Try to get from topic_mastery table first
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
    
    # If no records, compute mastery
    mastery_data = await compute_topic_mastery(user_id, subject_id, db)
    
    return [item["topic"] for item in mastery_data[:limit]]
