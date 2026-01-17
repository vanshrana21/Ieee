"""
backend/services/study_priority_engine.py
Phase 2.3: Personalized Study Intelligence (Rule-Based)

PRIORITY SCORING FORMULA:
=========================
Priority Score = (Mastery Deficit × 0.35) + (Staleness × 0.30) + (Importance × 0.20) + (Semester Urgency × 0.15)

Components:
1. MASTERY DEFICIT (35% weight):
   - (100 - mastery_percent) / 100
   - Lower mastery = higher priority
   - Range: 0.0 to 1.0

2. STALENESS (30% weight):
   - Days since last practice / 30 (capped at 1.0)
   - Longer gaps = higher priority
   - Range: 0.0 to 1.0

3. IMPORTANCE (20% weight):
   - question_count / max_question_count in subject
   - More questions = more important topic
   - Range: 0.0 to 1.0

4. SEMESTER URGENCY (15% weight):
   - Based on user's current semester vs topic's semester
   - Same semester = 1.0, Previous = 0.5, Future = 0.2
   - Range: 0.0 to 1.0

PRIORITY LABELS:
- High: score >= 0.65
- Medium: 0.40 <= score < 0.65
- Low: score < 0.40

RECOMMENDATION LOGIC TABLE:
===========================
| Mastery | Staleness | Priority | Action              |
|---------|-----------|----------|---------------------|
| < 40%   | > 7 days  | High     | Focus immediately   |
| < 40%   | <= 7 days | High     | Continue practicing |
| 40-70%  | > 14 days | Medium   | Schedule revision   |
| 40-70%  | <= 14 days| Medium   | Maintain practice   |
| > 70%   | > 21 days | Low      | Quick review        |
| > 70%   | <= 21 days| Low      | Can skip for now    |

NO AI/LLM CALLS - ALL LOGIC IS DETERMINISTIC
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from collections import defaultdict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc

from backend.orm.topic_mastery import TopicMastery
from backend.orm.subject_progress import SubjectProgress
from backend.orm.practice_attempt import PracticeAttempt
from backend.orm.practice_question import PracticeQuestion
from backend.orm.content_module import ContentModule
from backend.orm.subject import Subject
from backend.orm.study_plan import StudyPlan
from backend.orm.study_plan_item import StudyPlanItem
from backend.orm.user import User
from backend.orm.curriculum import CourseCurriculum

logger = logging.getLogger(__name__)

MASTERY_DEFICIT_WEIGHT = 0.35
STALENESS_WEIGHT = 0.30
IMPORTANCE_WEIGHT = 0.20
SEMESTER_URGENCY_WEIGHT = 0.15

HIGH_PRIORITY_THRESHOLD = 0.65
MEDIUM_PRIORITY_THRESHOLD = 0.40

WEAK_MASTERY = 40.0
STRONG_MASTERY = 70.0

STALENESS_CAP_DAYS = 30
CRITICAL_STALE_DAYS = 7
MODERATE_STALE_DAYS = 14
REVIEW_STALE_DAYS = 21


def get_priority_label(score: float) -> str:
    if score >= HIGH_PRIORITY_THRESHOLD:
        return "High"
    elif score >= MEDIUM_PRIORITY_THRESHOLD:
        return "Medium"
    else:
        return "Low"


def generate_explanation(
    topic_tag: str,
    mastery_percent: float,
    days_since_practice: int,
    question_count: int,
    priority: str
) -> str:
    """
    Generate human-readable explanation for why a topic has a given priority.
    
    MUST be deterministic - same inputs = same output.
    """
    parts = []
    
    if mastery_percent < WEAK_MASTERY:
        parts.append(f"{round(mastery_percent)}% mastery (needs improvement)")
    elif mastery_percent < STRONG_MASTERY:
        parts.append(f"{round(mastery_percent)}% mastery (moderate)")
    else:
        parts.append(f"{round(mastery_percent)}% mastery (strong)")
    
    if days_since_practice > REVIEW_STALE_DAYS:
        parts.append(f"no practice in {days_since_practice} days")
    elif days_since_practice > CRITICAL_STALE_DAYS:
        parts.append(f"last practiced {days_since_practice} days ago")
    elif days_since_practice > 0:
        parts.append(f"practiced {days_since_practice} day(s) ago")
    else:
        parts.append("practiced today")
    
    if question_count > 10:
        parts.append(f"{question_count} practice questions available")
    
    topic_display = topic_tag.replace("-", " ").replace("_", " ").title()
    
    return f"{topic_display} marked {priority} priority: {', '.join(parts)}."


def generate_action_recommendations(
    mastery_percent: float,
    days_since_practice: int,
    priority: str
) -> List[str]:
    """
    Generate specific actionable recommendations based on metrics.
    
    Returns list of action strings.
    """
    actions = []
    
    if mastery_percent < WEAK_MASTERY:
        actions.append("Review foundational concepts")
        actions.append("Practice 5+ questions")
        if days_since_practice > CRITICAL_STALE_DAYS:
            actions.append("Start with easy questions to rebuild confidence")
    elif mastery_percent < STRONG_MASTERY:
        actions.append("Practice medium-difficulty questions")
        actions.append("Review incorrect answers from past attempts")
        if days_since_practice > MODERATE_STALE_DAYS:
            actions.append("Schedule regular practice sessions")
    else:
        if days_since_practice > REVIEW_STALE_DAYS:
            actions.append("Quick revision to maintain knowledge")
            actions.append("Try 2-3 challenging questions")
        else:
            actions.append("Ready to move to advanced topics")
            actions.append("Help peers with this topic")
    
    return actions


async def compute_topic_priority(
    user_id: int,
    subject_id: int,
    db: AsyncSession,
    user_semester: int = 1
) -> List[Dict[str, Any]]:
    """
    Compute priority scores for all topics in a subject.
    
    Algorithm:
    1. Fetch topic mastery data
    2. Calculate days since last practice
    3. Count questions per topic
    4. Apply priority formula
    5. Generate explanations
    
    Returns:
        List of topic priorities sorted by score (highest first)
    """
    
    logger.info(f"Computing topic priorities: user={user_id}, subject={subject_id}")
    
    mastery_stmt = select(TopicMastery).where(
        and_(
            TopicMastery.user_id == user_id,
            TopicMastery.subject_id == subject_id
        )
    )
    mastery_result = await db.execute(mastery_stmt)
    masteries = mastery_result.scalars().all()
    
    question_count_stmt = select(
        PracticeQuestion.tags,
        func.count(PracticeQuestion.id).label("count")
    ).join(
        ContentModule,
        PracticeQuestion.module_id == ContentModule.id
    ).where(
        ContentModule.subject_id == subject_id
    ).group_by(PracticeQuestion.tags)
    
    question_result = await db.execute(question_count_stmt)
    question_counts = {}
    max_questions = 1
    
    for row in question_result.fetchall():
        if row.tags:
            tags = row.tags.split(",") if isinstance(row.tags, str) else row.tags
            for tag in tags:
                tag = tag.strip()
                if tag:
                    question_counts[tag] = question_counts.get(tag, 0) + row.count
                    max_questions = max(max_questions, question_counts[tag])
    
    subject_stmt = select(Subject).where(Subject.id == subject_id)
    subject_result = await db.execute(subject_stmt)
    subject = subject_result.scalar_one_or_none()
    
    subject_semester = user_semester
    if subject:
        curriculum_stmt = select(CourseCurriculum.semester).where(
            CourseCurriculum.subject_id == subject_id
        ).limit(1)
        curriculum_result = await db.execute(curriculum_stmt)
        curriculum_row = curriculum_result.scalar_one_or_none()
        if curriculum_row:
            subject_semester = curriculum_row
    
    now = datetime.utcnow()
    priorities = []
    
    for mastery in masteries:
        mastery_percent = mastery.mastery_score * 100
        mastery_deficit = (100 - mastery_percent) / 100
        
        days_since = 999
        if mastery.last_practiced_at:
            days_since = (now - mastery.last_practiced_at).days
        
        staleness = min(days_since / STALENESS_CAP_DAYS, 1.0)
        
        q_count = question_counts.get(mastery.topic_tag, 0)
        importance = q_count / max_questions if max_questions > 0 else 0.0
        
        if subject_semester == user_semester:
            urgency = 1.0
        elif subject_semester < user_semester:
            urgency = 0.5
        else:
            urgency = 0.2
        
        priority_score = (
            mastery_deficit * MASTERY_DEFICIT_WEIGHT +
            staleness * STALENESS_WEIGHT +
            importance * IMPORTANCE_WEIGHT +
            urgency * SEMESTER_URGENCY_WEIGHT
        )
        
        priority_label = get_priority_label(priority_score)
        
        explanation = generate_explanation(
            mastery.topic_tag,
            mastery_percent,
            days_since,
            q_count,
            priority_label
        )
        
        actions = generate_action_recommendations(
            mastery_percent,
            days_since,
            priority_label
        )
        
        priorities.append({
            "topic_tag": mastery.topic_tag,
            "subject_id": subject_id,
            "mastery_percent": round(mastery_percent, 2),
            "days_since_practice": days_since,
            "question_count": q_count,
            "priority_score": round(priority_score, 4),
            "priority": priority_label,
            "explanation": explanation,
            "recommended_actions": actions,
            "components": {
                "mastery_deficit": round(mastery_deficit, 4),
                "staleness": round(staleness, 4),
                "importance": round(importance, 4),
                "urgency": round(urgency, 4)
            }
        })
    
    priorities.sort(key=lambda x: x["priority_score"], reverse=True)
    
    logger.info(f"Computed priorities for {len(priorities)} topics")
    
    return priorities


async def get_study_recommendations(
    user_id: int,
    db: AsyncSession,
    limit: int = 10
) -> Dict[str, Any]:
    """
    Get personalized study recommendations for a user.
    
    Returns:
    - next_topic: Highest priority topic to study now
    - needs_revision: Topics that need revision (stale + weak)
    - mastered: Topics that can be skipped
    - focus_subjects: Subjects needing most attention
    """
    
    logger.info(f"Generating study recommendations: user={user_id}")
    
    user_stmt = select(User).where(User.id == user_id)
    user_result = await db.execute(user_stmt)
    user = user_result.scalar_one_or_none()
    user_semester = user.current_semester if user and user.current_semester else 1
    
    progress_stmt = select(SubjectProgress).where(
        SubjectProgress.user_id == user_id
    )
    progress_result = await db.execute(progress_stmt)
    subject_progresses = progress_result.scalars().all()
    
    if not subject_progresses:
        subjects_stmt = select(Subject).limit(3)
        subjects_result = await db.execute(subjects_stmt)
        subjects = subjects_result.scalars().all()
        
        return {
            "next_topic": None,
            "needs_revision": [],
            "mastered": [],
            "focus_subjects": [
                {
                    "subject_id": s.id,
                    "subject_title": s.title,
                    "mastery_percent": 0.0,
                    "explanation": f"Start practicing {s.title} to build your foundation."
                }
                for s in subjects
            ],
            "message": "No practice history yet. Start with any subject to get personalized recommendations!"
        }
    
    all_priorities = []
    subject_priorities = {}
    
    for sp in subject_progresses:
        priorities = await compute_topic_priority(
            user_id, sp.subject_id, db, user_semester
        )
        all_priorities.extend(priorities)
        
        if priorities:
            avg_priority = sum(p["priority_score"] for p in priorities) / len(priorities)
            subject_priorities[sp.subject_id] = {
                "subject_id": sp.subject_id,
                "avg_priority": avg_priority,
                "mastery_percent": sp.completion_percentage,
                "topic_count": len(priorities)
            }
    
    all_priorities.sort(key=lambda x: x["priority_score"], reverse=True)
    
    next_topic = all_priorities[0] if all_priorities else None
    
    needs_revision = [
        p for p in all_priorities
        if p["mastery_percent"] < STRONG_MASTERY and p["days_since_practice"] > CRITICAL_STALE_DAYS
    ][:5]
    
    mastered = [
        p for p in all_priorities
        if p["mastery_percent"] >= STRONG_MASTERY and p["days_since_practice"] <= REVIEW_STALE_DAYS
    ][:5]
    
    sorted_subjects = sorted(
        subject_priorities.values(),
        key=lambda x: x["avg_priority"],
        reverse=True
    )
    
    focus_subjects = []
    for sp in sorted_subjects[:3]:
        subject_stmt = select(Subject).where(Subject.id == sp["subject_id"])
        subject_result = await db.execute(subject_stmt)
        subject = subject_result.scalar_one_or_none()
        
        if subject:
            focus_subjects.append({
                "subject_id": sp["subject_id"],
                "subject_title": subject.title,
                "mastery_percent": round(sp["mastery_percent"], 2),
                "topic_count": sp["topic_count"],
                "explanation": f"{subject.title} needs attention with {round(sp['mastery_percent'])}% overall mastery."
            })
    
    return {
        "next_topic": next_topic,
        "needs_revision": needs_revision,
        "mastered": mastered,
        "focus_subjects": focus_subjects,
        "total_topics_analyzed": len(all_priorities),
        "message": None
    }


async def generate_weekly_study_plan(
    user_id: int,
    db: AsyncSession,
    weeks: int = 1
) -> Dict[str, Any]:
    """
    Generate a weekly study plan.
    
    Rules:
    - Max 2 subjects per day
    - Mix weak + moderate topics
    - Avoid overload (max 4 hours/day)
    - Prioritize by score
    
    Returns plan with daily breakdown.
    """
    
    logger.info(f"Generating {weeks}-week study plan: user={user_id}")
    
    recommendations = await get_study_recommendations(user_id, db)
    
    if recommendations.get("message"):
        return {
            "success": False,
            "message": recommendations["message"],
            "plan": None
        }
    
    active_plan_stmt = select(StudyPlan).where(
        and_(
            StudyPlan.user_id == user_id,
            StudyPlan.is_active == True
        )
    )
    active_result = await db.execute(active_plan_stmt)
    active_plans = active_result.scalars().all()
    
    for plan in active_plans:
        plan.is_active = False
    
    all_topics = []
    progress_stmt = select(SubjectProgress).where(
        SubjectProgress.user_id == user_id
    )
    progress_result = await db.execute(progress_stmt)
    
    for sp in progress_result.scalars().all():
        priorities = await compute_topic_priority(user_id, sp.subject_id, db)
        for p in priorities:
            all_topics.append(p)
    
    all_topics.sort(key=lambda x: x["priority_score"], reverse=True)
    
    high_priority = [t for t in all_topics if t["priority"] == "High"]
    medium_priority = [t for t in all_topics if t["priority"] == "Medium"]
    low_priority = [t for t in all_topics if t["priority"] == "Low"]
    
    total_topics = len(high_priority) + len(medium_priority) // 2
    
    if total_topics == 0:
        total_topics = min(7, len(all_topics))
    
    plan_summary = f"Focus on {len(high_priority)} high-priority topics"
    if medium_priority:
        plan_summary += f" and {len(medium_priority)} moderate topics"
    plan_summary += f" over {weeks} week(s)."
    
    study_plan = StudyPlan(
        user_id=user_id,
        duration_weeks=weeks,
        summary=plan_summary,
        is_active=True
    )
    db.add(study_plan)
    await db.flush()
    
    plan_items = []
    topics_per_day = 2
    days_per_week = 7
    
    topic_queue = high_priority + medium_priority + low_priority
    topic_index = 0
    
    for week in range(1, weeks + 1):
        for day in range(1, days_per_week + 1):
            daily_subjects = set()
            daily_items = []
            
            while len(daily_items) < topics_per_day and topic_index < len(topic_queue):
                topic = topic_queue[topic_index]
                topic_index += 1
                
                if len(daily_subjects) >= 2 and topic["subject_id"] not in daily_subjects:
                    continue
                
                daily_subjects.add(topic["subject_id"])
                
                estimated_hours = 1
                if topic["priority"] == "High":
                    estimated_hours = 2
                elif topic["priority"] == "Medium":
                    estimated_hours = 1
                
                plan_item = StudyPlanItem(
                    plan_id=study_plan.id,
                    week_number=week,
                    subject_id=topic["subject_id"],
                    topic_tag=topic["topic_tag"],
                    recommended_actions=topic["recommended_actions"],
                    estimated_hours=estimated_hours,
                    priority=topic["priority"],
                    rationale=topic["explanation"]
                )
                db.add(plan_item)
                daily_items.append(plan_item)
                plan_items.append({
                    "week": week,
                    "day": day,
                    "topic_tag": topic["topic_tag"],
                    "subject_id": topic["subject_id"],
                    "priority": topic["priority"],
                    "estimated_hours": estimated_hours,
                    "rationale": topic["explanation"],
                    "actions": topic["recommended_actions"]
                })
    
    await db.commit()
    await db.refresh(study_plan)
    
    logger.info(f"Created study plan {study_plan.id} with {len(plan_items)} items")
    
    return {
        "success": True,
        "message": None,
        "plan": {
            "id": study_plan.id,
            "duration_weeks": weeks,
            "summary": plan_summary,
            "total_items": len(plan_items),
            "items": plan_items,
            "created_at": study_plan.created_at.isoformat() if study_plan.created_at else None
        }
    }


async def get_todays_focus(
    user_id: int,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Get the most important topics to focus on today.
    
    Returns top 3 highest priority topics with full explanations.
    """
    
    recommendations = await get_study_recommendations(user_id, db, limit=3)
    
    if recommendations.get("message"):
        return {
            "has_focus": False,
            "message": recommendations["message"],
            "topics": []
        }
    
    focus_topics = []
    
    if recommendations["next_topic"]:
        focus_topics.append({
            "rank": 1,
            "topic_tag": recommendations["next_topic"]["topic_tag"],
            "subject_id": recommendations["next_topic"]["subject_id"],
            "priority": recommendations["next_topic"]["priority"],
            "mastery_percent": recommendations["next_topic"]["mastery_percent"],
            "explanation": recommendations["next_topic"]["explanation"],
            "actions": recommendations["next_topic"]["recommended_actions"],
            "why_now": "This is your highest priority topic based on mastery and practice history."
        })
    
    for i, topic in enumerate(recommendations["needs_revision"][:2], start=2):
        if topic["topic_tag"] != (recommendations["next_topic"]["topic_tag"] if recommendations["next_topic"] else None):
            focus_topics.append({
                "rank": i,
                "topic_tag": topic["topic_tag"],
                "subject_id": topic["subject_id"],
                "priority": topic["priority"],
                "mastery_percent": topic["mastery_percent"],
                "explanation": topic["explanation"],
                "actions": topic["recommended_actions"],
                "why_now": f"Needs revision - last practiced {topic['days_since_practice']} days ago."
            })
    
    return {
        "has_focus": len(focus_topics) > 0,
        "message": None,
        "topics": focus_topics[:3],
        "total_weak_topics": len(recommendations["needs_revision"]),
        "total_mastered_topics": len(recommendations["mastered"])
    }
