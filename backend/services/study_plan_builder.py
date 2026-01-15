"""
backend/services/study_plan_builder.py
Phase 9C: Deterministic study plan generation

CRITICAL: NO AI CALLS - Pure algorithmic logic only
All recommendations are explainable and traceable
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from collections import defaultdict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from backend.orm.user import User
from backend.orm.topic_mastery import TopicMastery
from backend.orm.tutor_message import TutorMessage
from backend.orm.subject import Subject
from backend.orm.curriculum import CourseCurriculum

logger = logging.getLogger(__name__)


async def build_study_plan(
    user: User,
    duration_weeks: int,
    focus_subject_ids: Optional[List[int]],
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Build a personalized study plan using deterministic logic.
    
    Algorithm:
    1. Get all topic mastery scores
    2. Analyze tutor message frequency per topic
    3. Combine signals: mastery + tutor confusion
    4. Prioritize weakest topics
    5. Distribute across weeks (earliest = weakest)
    6. Generate actionable recommendations
    
    NO AI CALLS - Pure data-driven logic.
    
    Args:
        user: Authenticated user
        duration_weeks: Plan duration
        focus_subject_ids: Optional subject filter
        db: Database session
    
    Returns:
        Plan structure with weeks and topics
    """
    
    logger.info(f"Building study plan: user={user.id}, weeks={duration_weeks}, focus={focus_subject_ids}")
    
    # 1. Get topic mastery scores
    mastery_data = await _get_topic_mastery(user.id, focus_subject_ids, db)
    
    if not mastery_data:
        logger.warning(f"No mastery data for user {user.id}")
        # Return empty plan with explanation
        return {
            "summary": "No study history found. Complete some practice questions to generate a personalized plan.",
            "weeks": [],
            "total_topics": 0
        }
    
    # 2. Analyze tutor interactions
    tutor_confusion_scores = await _analyze_tutor_confusion(user.id, db)
    
    # 3. Merge signals and prioritize
    prioritized_topics = _prioritize_topics(mastery_data, tutor_confusion_scores)
    
    logger.info(f"Prioritized {len(prioritized_topics)} topics")
    
    # 4. Distribute topics across weeks
    weekly_plan = _distribute_topics_across_weeks(
        prioritized_topics,
        duration_weeks,
        max_topics_per_week=3,
        max_hours_per_week=8
    )
    
    # 5. Generate summary
    summary = _generate_plan_summary(prioritized_topics, duration_weeks)
    
    logger.info(f"Plan built: {len(weekly_plan)} weeks, {sum(len(w['topics']) for w in weekly_plan)} total topics")
    
    return {
        "summary": summary,
        "weeks": weekly_plan,
        "total_topics": sum(len(w['topics']) for w in weekly_plan)
    }


async def _get_topic_mastery(
    user_id: int,
    focus_subject_ids: Optional[List[int]],
    db: AsyncSession
) -> List[Dict[str, Any]]:
    """
    Fetch topic mastery scores with subject information.
    
    Returns list of:
    {
        "topic_tag": "article-21",
        "subject_id": 5,
        "subject_name": "Constitutional Law",
        "subject_code": "LAW101",
        "mastery_score": 0.42,
        "attempt_count": 8,
        "difficulty_level": "medium"
    }
    """
    
    # Query mastery with subject info
    stmt = select(TopicMastery, Subject).join(
        Subject,
        TopicMastery.subject_id == Subject.id
    ).where(
        TopicMastery.user_id == user_id
    )
    
    # Apply subject filter if provided
    if focus_subject_ids:
        stmt = stmt.where(Subject.id.in_(focus_subject_ids))
    
    result = await db.execute(stmt)
    rows = result.all()
    
    mastery_list = []
    for mastery, subject in rows:
        mastery_list.append({
            "topic_tag": mastery.topic_tag,
            "subject_id": subject.id,
            "subject_name": subject.title,
            "subject_code": subject.code,
            "mastery_score": mastery.mastery_score,
            "attempt_count": mastery.attempt_count,
            "difficulty_level": mastery.difficulty_level,
            "last_practiced": mastery.last_practiced_at
        })
    
    return mastery_list


async def _analyze_tutor_confusion(
    user_id: int,
    db: AsyncSession
) -> Dict[str, int]:
    """
    Analyze tutor messages to detect topics user is confused about.
    
    Logic:
    - Count frequency of topic mentions in user's questions
    - Higher frequency = more confusion
    
    Returns:
    {
        "article-21": 5,  # Asked 5 times
        "contract-law": 3
    }
    """
    
    # Get all user messages from last 30 days
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    
    stmt = select(TutorMessage).join(
        # Join through tutor_sessions
        # Note: We're reading session_id directly from tutor_messages
        select(TutorMessage.session_id).distinct().subquery(),
        TutorMessage.session_id == select(TutorMessage.session_id).distinct().subquery().c.session_id
    ).where(
        and_(
            TutorMessage.role == "user",
            TutorMessage.created_at >= thirty_days_ago
        )
    )
    
    # Simpler query: just get user messages
    stmt = select(TutorMessage).where(
        and_(
            TutorMessage.role == "user",
            TutorMessage.created_at >= thirty_days_ago
        )
    )
    
    result = await db.execute(stmt)
    messages = result.scalars().all()
    
    # Count topic mentions (simple keyword matching)
    topic_mentions = defaultdict(int)
    
    # Common legal topics to search for
    topic_keywords = {
        "article-21": ["article 21", "right to life", "personal liberty"],
        "article-14": ["article 14", "equality", "equal protection"],
        "contract-law": ["contract", "offer", "acceptance", "consideration"],
        "tort-law": ["tort", "negligence", "duty of care"],
        "criminal-law": ["criminal", "ipc", "mens rea", "actus reus"],
        "property-law": ["property", "ownership", "possession"],
    }
    
    for message in messages:
        content_lower = message.content.lower()
        
        for topic, keywords in topic_keywords.items():
            for keyword in keywords:
                if keyword in content_lower:
                    topic_mentions[topic] += 1
                    break  # Count once per message
    
    logger.info(f"Tutor confusion analysis: {len(topic_mentions)} topics mentioned")
    
    return dict(topic_mentions)


def _prioritize_topics(
    mastery_data: List[Dict[str, Any]],
    tutor_confusion: Dict[str, int]
) -> List[Dict[str, Any]]:
    """
    Prioritize topics based on combined signals.
    
    Priority score formula:
    - Mastery weakness (inverse): (1 - mastery_score) * 0.7
    - Tutor confusion boost: min(tutor_count / 10, 0.3)
    
    Higher score = higher priority
    """
    
    prioritized = []
    
    for topic_data in mastery_data:
        topic_tag = topic_data["topic_tag"]
        mastery_score = topic_data["mastery_score"]
        
        # Weakness score (inverse of mastery)
        weakness_score = (1.0 - mastery_score) * 0.7
        
        # Tutor confusion boost
        confusion_count = tutor_confusion.get(topic_tag, 0)
        confusion_boost = min(confusion_count / 10.0, 0.3)
        
        # Combined priority
        priority_score = weakness_score + confusion_boost
        
        # Determine priority level
        if priority_score >= 0.7:
            priority_level = "high"
        elif priority_score >= 0.4:
            priority_level = "medium"
        else:
            priority_level = "low"
        
        # Build rationale
        rationale_parts = []
        
        if mastery_score < 0.5:
            rationale_parts.append(f"Low mastery ({int(mastery_score * 100)}%)")
        
        if confusion_count > 0:
            rationale_parts.append(f"{confusion_count} tutor queries")
        
        if not rationale_parts:
            rationale_parts.append("Improvement recommended")
        
        rationale = " and ".join(rationale_parts)
        
        prioritized.append({
            **topic_data,
            "priority_score": round(priority_score, 3),
            "priority_level": priority_level,
            "rationale": rationale,
            "tutor_queries": confusion_count
        })
    
    # Sort by priority (highest first)
    prioritized.sort(key=lambda x: x["priority_score"], reverse=True)
    
    return prioritized


def _distribute_topics_across_weeks(
    prioritized_topics: List[Dict[str, Any]],
    duration_weeks: int,
    max_topics_per_week: int = 3,
    max_hours_per_week: int = 8
) -> List[Dict[str, Any]]:
    """
    Distribute topics across weeks.
    
    Rules:
    - Earliest weeks get highest priority topics
    - Max 3 topics per week
    - Max 8 hours per week
    - Hours allocated based on priority:
      - High: 3 hours
      - Medium: 2 hours
      - Low: 1 hour
    """
    
    weekly_plan = []
    
    topics_per_week = max_topics_per_week
    total_topics = len(prioritized_topics)
    topics_assigned = 0
    
    for week in range(1, duration_weeks + 1):
        week_topics = []
        week_hours = 0
        
        # Assign topics to this week
        while (topics_assigned < total_topics and 
               len(week_topics) < topics_per_week and 
               week_hours < max_hours_per_week):
            
            topic = prioritized_topics[topics_assigned]
            
            # Estimate hours based on priority
            if topic["priority_level"] == "high":
                hours = 3
            elif topic["priority_level"] == "medium":
                hours = 2
            else:
                hours = 1
            
            # Check if adding would exceed weekly limit
            if week_hours + hours > max_hours_per_week:
                break
            
            # Generate recommended actions
            actions = _generate_recommended_actions(topic)
            
            week_topics.append({
                "subject_name": topic["subject_name"],
                "subject_code": topic["subject_code"],
                "subject_id": topic["subject_id"],
                "topic_tag": topic["topic_tag"],
                "priority": topic["priority_level"],
                "estimated_hours": hours,
                "recommended_actions": actions,
                "rationale": topic["rationale"],
                "mastery_score": topic["mastery_score"]
            })
            
            week_hours += hours
            topics_assigned += 1
        
        if week_topics:
            weekly_plan.append({
                "week_number": week,
                "total_hours": week_hours,
                "topics": week_topics
            })
    
    return weekly_plan


def _generate_recommended_actions(topic_data: Dict[str, Any]) -> List[str]:
    """
    Generate specific, actionable recommendations.
    
    Based on:
    - Mastery score
    - Attempt count
    - Priority level
    """
    
    actions = []
    mastery = topic_data["mastery_score"]
    priority = topic_data["priority_level"]
    
    # Always include fundamentals review for weak topics
    if mastery < 0.5:
        actions.append("Review fundamental concepts and definitions")
    
    # Practice recommendations
    if mastery < 0.3:
        actions.append("Complete 3-4 easy practice questions")
    elif mastery < 0.7:
        actions.append("Attempt 2-3 medium difficulty questions")
    else:
        actions.append("Challenge yourself with 1-2 hard questions")
    
    # Case law review
    if priority in ["high", "medium"]:
        actions.append("Review landmark cases and key judgments")
    
    # Notes
    if topic_data.get("tutor_queries", 0) > 2:
        actions.append("Create summary notes addressing your common questions")
    
    # Quick revision
    if mastery >= 0.5:
        actions.append("Quick revision of key points (30 min)")
    
    return actions[:4]  # Max 4 actions


def _generate_plan_summary(
    prioritized_topics: List[Dict[str, Any]],
    duration_weeks: int
) -> str:
    """
    Generate human-readable plan summary.
    """
    
    if not prioritized_topics:
        return "No topics identified for study plan."
    
    # Count topics by priority
    high_priority = sum(1 for t in prioritized_topics if t["priority_level"] == "high")
    
    # Get unique subjects
    subjects = set(t["subject_name"] for t in prioritized_topics)
    subject_names = ", ".join(sorted(subjects))
    
    # Build summary
    if high_priority > 0:
        summary = (
            f"{duration_weeks}-week focused study plan addressing {high_priority} high-priority "
            f"topics across {subject_names}. "
            f"Plan targets areas with low mastery and frequent tutor queries."
        )
    else:
        summary = (
            f"{duration_weeks}-week study plan covering {len(prioritized_topics)} topics "
            f"in {subject_names} to strengthen foundational understanding."
        )
    
    return summary
