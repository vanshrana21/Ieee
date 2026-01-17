"""
backend/services/study_planner_service.py
Phase 6.3: Auto-Generated Personalized Study Planner

SYSTEM GOAL:
Create a fully automated, explainable, data-driven study planner that tells a student:
- WHAT to study
- WHEN to study
- WHY it matters
- HOW MUCH to study

This is a LIVING PLAN that adapts to performance.

PLANNING LOGIC:
===============
1. TOPIC SELECTION RULES
   - High priority topics (from study_priority_engine)
   - Weak / medium mastery topics
   - Recently incorrect or stale topics
   - EXCLUDE: Strong topics practiced recently, out-of-semester topics

2. EFFORT ALLOCATION
   - 40% Weak topics
   - 40% Medium topics
   - 20% Revision / retention

3. CONTENT MIX PER SESSION
   - 1 Learn item (concept clarity)
   - 1 Case OR example
   - 1 Practice task (MCQ / essay / application)

4. TIME ESTIMATION (Rule-Based)
   - Content length
   - Question marks
   - Historical time_taken averages

NO AI CALLS - ALL LOGIC IS DETERMINISTIC
NO FIXED SCHEDULES - ADAPTS TO DATA
NO HARDCODED SYLLABUS LOGIC
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from enum import Enum
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc, or_
from sqlalchemy.orm import joinedload

from backend.orm.user import User
from backend.orm.subject import Subject
from backend.orm.curriculum import CourseCurriculum
from backend.orm.content_module import ContentModule, ModuleType
from backend.orm.learn_content import LearnContent
from backend.orm.case_content import CaseContent
from backend.orm.practice_question import PracticeQuestion
from backend.orm.topic_mastery import TopicMastery
from backend.orm.subject_progress import SubjectProgress
from backend.orm.practice_attempt import PracticeAttempt
from backend.orm.study_plan import StudyPlan
from backend.orm.study_plan_item import StudyPlanItem
from backend.services.study_priority_engine import (
    compute_topic_priority,
    get_priority_label,
    WEAK_MASTERY,
    STRONG_MASTERY,
    CRITICAL_STALE_DAYS,
)
from backend.services.mistake_pattern_service import get_quick_diagnosis

logger = logging.getLogger(__name__)


class ActivityType(str, Enum):
    LEARN = "learn"
    CASE = "case"
    PRACTICE = "practice"
    REVISION = "revision"


class PlanHorizon(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    EXAM_PREP = "exam_prep"


EFFORT_ALLOCATION = {
    "weak": 0.40,
    "medium": 0.40,
    "revision": 0.20,
}

TIME_PER_MARK_MINUTES = 3
LEARN_TIME_PER_100_CHARS = 0.5
CASE_BASE_TIME_MINUTES = 15
MIN_SESSION_MINUTES = 30
MAX_SESSION_MINUTES = 120
DEFAULT_DAILY_STUDY_MINUTES = 120

MASTERY_THRESHOLDS = {
    "weak": WEAK_MASTERY,
    "strong": STRONG_MASTERY,
}


@dataclass
class PlanItem:
    """Single study plan item with full explainability."""
    subject_id: int
    subject_name: str
    module_id: Optional[int]
    module_name: Optional[str]
    topic_tag: Optional[str]
    activity_type: ActivityType
    content_id: Optional[int]
    content_title: str
    estimated_time_minutes: int
    priority_level: str
    why: str
    focus: str
    success_criteria: str
    mastery_percent: Optional[float] = None
    days_since_practice: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "subject_id": self.subject_id,
            "subject_name": self.subject_name,
            "module_id": self.module_id,
            "module_name": self.module_name,
            "topic_tag": self.topic_tag,
            "activity_type": self.activity_type.value,
            "content_id": self.content_id,
            "content_title": self.content_title,
            "estimated_time_minutes": self.estimated_time_minutes,
            "priority_level": self.priority_level,
            "why": self.why,
            "focus": self.focus,
            "success_criteria": self.success_criteria,
            "mastery_percent": self.mastery_percent,
            "days_since_practice": self.days_since_practice,
        }


@dataclass
class DayPlan:
    """Study plan for a single day."""
    day_label: str
    date: Optional[str]
    items: List[PlanItem]
    total_time_minutes: int
    focus_subjects: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "day_label": self.day_label,
            "date": self.date,
            "items": [item.to_dict() for item in self.items],
            "total_time_minutes": self.total_time_minutes,
            "focus_subjects": self.focus_subjects,
        }


@dataclass
class StudyPlanResult:
    """Complete study plan with metadata."""
    user_id: int
    plan_type: PlanHorizon
    generated_at: str
    days: List[DayPlan]
    summary: Dict[str, Any]
    recommendations: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "plan_type": self.plan_type.value,
            "generated_at": self.generated_at,
            "days": [day.to_dict() for day in self.days],
            "summary": self.summary,
            "recommendations": self.recommendations,
        }


def estimate_learn_time(content: LearnContent) -> int:
    """Estimate time to study learn content based on length."""
    if content.estimated_time_minutes:
        return content.estimated_time_minutes
    
    body_length = len(content.body) if content.body else 0
    estimated = int(body_length * LEARN_TIME_PER_100_CHARS / 100)
    return max(10, min(45, estimated))


def estimate_case_time(case: CaseContent) -> int:
    """Estimate time to study a case based on importance and length."""
    base_time = CASE_BASE_TIME_MINUTES
    
    if case.exam_importance and case.exam_importance.value == "high":
        base_time += 10
    elif case.exam_importance and case.exam_importance.value == "low":
        base_time -= 5
    
    total_length = sum([
        len(case.facts or ""),
        len(case.issue or ""),
        len(case.judgment or ""),
        len(case.ratio or ""),
    ])
    
    length_factor = min(total_length / 2000, 1.0)
    adjusted = base_time + int(length_factor * 10)
    
    return max(10, min(30, adjusted))


def estimate_practice_time(question: PracticeQuestion, avg_time: Optional[float] = None) -> int:
    """Estimate time for practice question based on marks and history."""
    if avg_time:
        return int(avg_time / 60)
    
    marks = question.marks or 5
    estimated = marks * TIME_PER_MARK_MINUTES
    
    if question.question_type and question.question_type.value == "essay":
        estimated = int(estimated * 1.5)
    
    return max(5, min(60, estimated))


def generate_why_explanation(
    topic_tag: str,
    mastery_percent: Optional[float],
    days_since_practice: Optional[int],
    priority: str,
    activity_type: ActivityType
) -> str:
    """Generate human-readable WHY explanation for a plan item."""
    parts = []
    
    if mastery_percent is not None:
        if mastery_percent < WEAK_MASTERY:
            parts.append(f"Low mastery ({mastery_percent:.0f}%)")
        elif mastery_percent < STRONG_MASTERY:
            parts.append(f"Moderate mastery ({mastery_percent:.0f}%)")
        else:
            parts.append(f"Strong mastery ({mastery_percent:.0f}%)")
    
    if days_since_practice is not None:
        if days_since_practice > 21:
            parts.append(f"not practiced in {days_since_practice} days")
        elif days_since_practice > 7:
            parts.append(f"last practiced {days_since_practice} days ago")
        elif days_since_practice > 0:
            parts.append("recently practiced")
    
    if activity_type == ActivityType.REVISION:
        parts.append("scheduled for retention")
    elif activity_type == ActivityType.PRACTICE:
        parts.append("practice recommended")
    
    topic_display = topic_tag.replace("-", " ").replace("_", " ").title() if topic_tag else "General"
    
    if not parts:
        return f"{topic_display} marked {priority} priority"
    
    return f"{topic_display}: {' and '.join(parts)}"


def generate_focus_text(
    activity_type: ActivityType,
    topic_tag: Optional[str],
    mastery_percent: Optional[float]
) -> str:
    """Generate WHAT to focus on text."""
    topic_display = topic_tag.replace("-", " ").replace("_", " ").title() if topic_tag else "key concepts"
    
    if activity_type == ActivityType.LEARN:
        if mastery_percent and mastery_percent < WEAK_MASTERY:
            return f"Understand fundamentals of {topic_display}"
        return f"Review and consolidate {topic_display}"
    
    elif activity_type == ActivityType.CASE:
        return f"Study ratio decidendi and application of {topic_display}"
    
    elif activity_type == ActivityType.PRACTICE:
        if mastery_percent and mastery_percent < WEAK_MASTERY:
            return f"Practice basic questions on {topic_display}"
        return f"Apply {topic_display} to problem scenarios"
    
    elif activity_type == ActivityType.REVISION:
        return f"Quick review of {topic_display} key points"
    
    return f"Study {topic_display}"


def generate_success_criteria(
    activity_type: ActivityType,
    mastery_percent: Optional[float]
) -> str:
    """Generate WHAT success looks like."""
    if activity_type == ActivityType.LEARN:
        if mastery_percent and mastery_percent < WEAK_MASTERY:
            return "Can explain the concept in your own words"
        return "Can recall key points without looking"
    
    elif activity_type == ActivityType.CASE:
        return "Can state case name, year, ratio, and apply to new facts"
    
    elif activity_type == ActivityType.PRACTICE:
        if mastery_percent and mastery_percent < WEAK_MASTERY:
            return "Attempt without referencing notes; score > 50%"
        return "Correct issue framing + case usage in answer"
    
    elif activity_type == ActivityType.REVISION:
        return "Recall key points within 2 minutes"
    
    return "Complete the activity with understanding"


async def fetch_user_learning_data(
    user_id: int,
    db: AsyncSession
) -> Tuple[User, List[Dict], Dict[str, Dict], Dict[int, Dict]]:
    """
    Fetch all relevant user learning data for plan generation.
    
    Returns:
        - user: User object
        - topic_priorities: List of topic priorities from all subjects
        - topic_mastery_map: Dict mapping topic_tag to mastery data
        - subject_map: Dict mapping subject_id to subject info
    """
    user_stmt = select(User).where(User.id == user_id)
    user_result = await db.execute(user_stmt)
    user = user_result.scalar_one_or_none()
    
    if not user:
        raise ValueError(f"User {user_id} not found")
    
    user_semester = user.current_semester or 1
    
    subject_ids = []
    if user.course_id:
        curriculum_stmt = (
            select(CourseCurriculum.subject_id)
            .where(
                CourseCurriculum.course_id == user.course_id,
                CourseCurriculum.semester_number <= user_semester,
                CourseCurriculum.is_active == True
            )
        )
        curriculum_result = await db.execute(curriculum_stmt)
        subject_ids = [row[0] for row in curriculum_result.fetchall()]
    
    if not subject_ids:
        progress_stmt = select(SubjectProgress.subject_id).where(
            SubjectProgress.user_id == user_id
        )
        progress_result = await db.execute(progress_stmt)
        subject_ids = [row[0] for row in progress_result.fetchall()]
    
    if not subject_ids:
        subjects_stmt = select(Subject.id).limit(5)
        subjects_result = await db.execute(subjects_stmt)
        subject_ids = [row[0] for row in subjects_result.fetchall()]
    
    subject_map = {}
    for subject_id in subject_ids:
        subject_stmt = select(Subject).where(Subject.id == subject_id)
        subject_result = await db.execute(subject_stmt)
        subject = subject_result.scalar_one_or_none()
        if subject:
            subject_map[subject_id] = {
                "id": subject_id,
                "title": subject.title,
            }
    
    all_priorities = []
    for subject_id in subject_ids:
        priorities = await compute_topic_priority(
            user_id, subject_id, db, user_semester
        )
        for p in priorities:
            p["subject_name"] = subject_map.get(subject_id, {}).get("title", "Unknown")
        all_priorities.extend(priorities)
    
    all_priorities.sort(key=lambda x: x["priority_score"], reverse=True)
    
    mastery_stmt = select(TopicMastery).where(TopicMastery.user_id == user_id)
    mastery_result = await db.execute(mastery_stmt)
    masteries = mastery_result.scalars().all()
    
    topic_mastery_map = {}
    now = datetime.utcnow()
    for m in masteries:
        days_since = 999
        if m.last_practiced_at:
            days_since = (now - m.last_practiced_at).days
        
        topic_mastery_map[m.topic_tag] = {
            "mastery_score": m.mastery_score * 100 if m.mastery_score else 0,
            "subject_id": m.subject_id,
            "days_since_practice": days_since,
        }
    
    return user, all_priorities, topic_mastery_map, subject_map


async def fetch_content_for_topic(
    subject_id: int,
    topic_tag: Optional[str],
    db: AsyncSession
) -> Dict[str, List[Dict]]:
    """Fetch learn, case, and practice content for a topic."""
    content = {
        "learn": [],
        "cases": [],
        "practice": [],
    }
    
    modules_stmt = select(ContentModule).where(
        ContentModule.subject_id == subject_id
    )
    modules_result = await db.execute(modules_stmt)
    modules = modules_result.scalars().all()
    
    for module in modules:
        if module.module_type == ModuleType.LEARN:
            learn_stmt = select(LearnContent).where(
                LearnContent.module_id == module.id
            ).limit(5)
            learn_result = await db.execute(learn_stmt)
            
            for item in learn_result.scalars().all():
                if topic_tag:
                    title_lower = item.title.lower() if item.title else ""
                    topic_lower = topic_tag.lower().replace("-", " ").replace("_", " ")
                    if topic_lower not in title_lower and topic_tag.lower() not in title_lower:
                        continue
                
                content["learn"].append({
                    "id": item.id,
                    "module_id": module.id,
                    "title": item.title,
                    "estimated_time": estimate_learn_time(item),
                })
        
        elif module.module_type == ModuleType.CASES:
            case_stmt = select(CaseContent).where(
                CaseContent.module_id == module.id
            ).limit(5)
            case_result = await db.execute(case_stmt)
            
            for case in case_result.scalars().all():
                if topic_tag:
                    tags = case.tags.lower() if case.tags else ""
                    if topic_tag.lower() not in tags:
                        continue
                
                content["cases"].append({
                    "id": case.id,
                    "module_id": module.id,
                    "title": case.case_name,
                    "estimated_time": estimate_case_time(case),
                    "importance": case.exam_importance.value if case.exam_importance else "medium",
                })
        
        elif module.module_type == ModuleType.PRACTICE:
            practice_stmt = select(PracticeQuestion).where(
                PracticeQuestion.module_id == module.id
            ).limit(10)
            practice_result = await db.execute(practice_stmt)
            
            for q in practice_result.scalars().all():
                if topic_tag:
                    tags = q.tags.lower() if q.tags else ""
                    if topic_tag.lower() not in tags:
                        continue
                
                content["practice"].append({
                    "id": q.id,
                    "module_id": module.id,
                    "title": q.question_text[:100] + "..." if q.question_text and len(q.question_text) > 100 else q.question_text,
                    "estimated_time": estimate_practice_time(q),
                    "marks": q.marks,
                    "type": q.question_type.value if q.question_type else "mcq",
                })
    
    return content


def categorize_topics_by_mastery(
    priorities: List[Dict],
    topic_mastery_map: Dict[str, Dict]
) -> Dict[str, List[Dict]]:
    """
    Categorize topics into weak, medium, and strong based on mastery.
    
    Returns dict with:
    - weak: mastery < 40%
    - medium: 40% <= mastery < 70%
    - strong: mastery >= 70%
    - stale: strong but not practiced > 21 days (for revision)
    """
    categories = {
        "weak": [],
        "medium": [],
        "strong": [],
        "stale": [],
    }
    
    for priority in priorities:
        topic_tag = priority["topic_tag"]
        mastery_data = topic_mastery_map.get(topic_tag, {})
        mastery_percent = mastery_data.get("mastery_score", priority.get("mastery_percent", 50))
        days_since = mastery_data.get("days_since_practice", priority.get("days_since_practice", 999))
        
        priority["mastery_percent"] = mastery_percent
        priority["days_since_practice"] = days_since
        
        if mastery_percent < WEAK_MASTERY:
            categories["weak"].append(priority)
        elif mastery_percent < STRONG_MASTERY:
            categories["medium"].append(priority)
        else:
            if days_since > 21:
                categories["stale"].append(priority)
            else:
                categories["strong"].append(priority)
    
    return categories


def select_topics_for_session(
    categories: Dict[str, List[Dict]],
    target_minutes: int,
    already_selected: set
) -> List[Dict]:
    """
    Select topics for a study session based on effort allocation.
    
    Allocation:
    - 40% weak topics
    - 40% medium topics  
    - 20% revision (stale strong topics)
    
    Excludes already selected topics.
    """
    selected = []
    
    weak_minutes = int(target_minutes * EFFORT_ALLOCATION["weak"])
    medium_minutes = int(target_minutes * EFFORT_ALLOCATION["medium"])
    revision_minutes = int(target_minutes * EFFORT_ALLOCATION["revision"])
    
    def add_topics(topic_list: List[Dict], max_minutes: int, category: str) -> int:
        used = 0
        for topic in topic_list:
            if topic["topic_tag"] in already_selected:
                continue
            
            estimated_session_time = 30
            if topic["priority"] == "High":
                estimated_session_time = 45
            elif topic["priority"] == "Low":
                estimated_session_time = 20
            
            if used + estimated_session_time <= max_minutes + 15:
                topic["category"] = category
                topic["session_time"] = estimated_session_time
                selected.append(topic)
                already_selected.add(topic["topic_tag"])
                used += estimated_session_time
            
            if used >= max_minutes:
                break
        return used
    
    add_topics(categories["weak"], weak_minutes, "weak")
    add_topics(categories["medium"], medium_minutes, "medium")
    add_topics(categories["stale"], revision_minutes, "revision")
    
    if len(selected) < 2:
        remaining = weak_minutes + medium_minutes + revision_minutes
        all_available = categories["weak"] + categories["medium"] + categories["stale"]
        add_topics(all_available, remaining, "mixed")
    
    return selected


async def create_session_items(
    topic: Dict,
    subject_map: Dict[int, Dict],
    topic_mastery_map: Dict[str, Dict],
    db: AsyncSession
) -> List[PlanItem]:
    """
    Create plan items for a single topic session.
    
    Each session MUST include:
    - 1 Learn item (concept clarity)
    - 1 Case OR example
    - 1 Practice task
    """
    items = []
    
    subject_id = topic["subject_id"]
    subject_name = subject_map.get(subject_id, {}).get("title", "Unknown Subject")
    topic_tag = topic["topic_tag"]
    mastery_data = topic_mastery_map.get(topic_tag, {})
    mastery_percent = topic.get("mastery_percent", mastery_data.get("mastery_score", 50))
    days_since = topic.get("days_since_practice", mastery_data.get("days_since_practice", 999))
    priority = topic.get("priority", "Medium")
    category = topic.get("category", "medium")
    
    content = await fetch_content_for_topic(subject_id, topic_tag, db)
    
    activity_type = ActivityType.LEARN
    if category == "revision":
        activity_type = ActivityType.REVISION
    
    if content["learn"]:
        learn_item = content["learn"][0]
        items.append(PlanItem(
            subject_id=subject_id,
            subject_name=subject_name,
            module_id=learn_item["module_id"],
            module_name="Learn",
            topic_tag=topic_tag,
            activity_type=activity_type,
            content_id=learn_item["id"],
            content_title=learn_item["title"],
            estimated_time_minutes=learn_item["estimated_time"],
            priority_level=priority,
            why=generate_why_explanation(topic_tag, mastery_percent, days_since, priority, activity_type),
            focus=generate_focus_text(activity_type, topic_tag, mastery_percent),
            success_criteria=generate_success_criteria(activity_type, mastery_percent),
            mastery_percent=mastery_percent,
            days_since_practice=days_since,
        ))
    
    if content["cases"]:
        case_item = content["cases"][0]
        items.append(PlanItem(
            subject_id=subject_id,
            subject_name=subject_name,
            module_id=case_item["module_id"],
            module_name="Cases",
            topic_tag=topic_tag,
            activity_type=ActivityType.CASE,
            content_id=case_item["id"],
            content_title=case_item["title"],
            estimated_time_minutes=case_item["estimated_time"],
            priority_level=priority,
            why=generate_why_explanation(topic_tag, mastery_percent, days_since, priority, ActivityType.CASE),
            focus=generate_focus_text(ActivityType.CASE, topic_tag, mastery_percent),
            success_criteria=generate_success_criteria(ActivityType.CASE, mastery_percent),
            mastery_percent=mastery_percent,
            days_since_practice=days_since,
        ))
    
    if content["practice"]:
        practice_item = content["practice"][0]
        items.append(PlanItem(
            subject_id=subject_id,
            subject_name=subject_name,
            module_id=practice_item["module_id"],
            module_name="Practice",
            topic_tag=topic_tag,
            activity_type=ActivityType.PRACTICE,
            content_id=practice_item["id"],
            content_title=practice_item["title"],
            estimated_time_minutes=practice_item["estimated_time"],
            priority_level=priority,
            why=generate_why_explanation(topic_tag, mastery_percent, days_since, priority, ActivityType.PRACTICE),
            focus=generate_focus_text(ActivityType.PRACTICE, topic_tag, mastery_percent),
            success_criteria=generate_success_criteria(ActivityType.PRACTICE, mastery_percent),
            mastery_percent=mastery_percent,
            days_since_practice=days_since,
        ))
    
    if not items:
        items.append(PlanItem(
            subject_id=subject_id,
            subject_name=subject_name,
            module_id=None,
            module_name=None,
            topic_tag=topic_tag,
            activity_type=ActivityType.LEARN,
            content_id=None,
            content_title=f"Study {topic_tag.replace('-', ' ').replace('_', ' ').title()}",
            estimated_time_minutes=30,
            priority_level=priority,
            why=generate_why_explanation(topic_tag, mastery_percent, days_since, priority, ActivityType.LEARN),
            focus=generate_focus_text(ActivityType.LEARN, topic_tag, mastery_percent),
            success_criteria=generate_success_criteria(ActivityType.LEARN, mastery_percent),
            mastery_percent=mastery_percent,
            days_since_practice=days_since,
        ))
    
    return items


async def generate_daily_plan(
    user_id: int,
    db: AsyncSession,
    target_minutes: int = DEFAULT_DAILY_STUDY_MINUTES
) -> StudyPlanResult:
    """
    Generate a single day study plan.
    
    Returns the most important items to study today.
    """
    logger.info(f"Generating daily plan for user_id={user_id}")
    
    user, priorities, topic_mastery_map, subject_map = await fetch_user_learning_data(user_id, db)
    
    if not priorities:
        return StudyPlanResult(
            user_id=user_id,
            plan_type=PlanHorizon.DAILY,
            generated_at=datetime.utcnow().isoformat(),
            days=[],
            summary={
                "message": "No topics available. Start exploring subjects to get a personalized plan.",
                "total_topics": 0,
            },
            recommendations=["Browse available subjects and start learning"],
        )
    
    categories = categorize_topics_by_mastery(priorities, topic_mastery_map)
    
    selected_topics = select_topics_for_session(categories, target_minutes, set())
    
    all_items = []
    for topic in selected_topics:
        items = await create_session_items(topic, subject_map, topic_mastery_map, db)
        all_items.extend(items)
    
    total_time = sum(item.estimated_time_minutes for item in all_items)
    focus_subjects = list(set(item.subject_name for item in all_items))
    
    day_plan = DayPlan(
        day_label="Today",
        date=datetime.utcnow().strftime("%Y-%m-%d"),
        items=all_items,
        total_time_minutes=total_time,
        focus_subjects=focus_subjects,
    )
    
    recommendations = []
    if categories["weak"]:
        recommendations.append(f"Focus on weak topics: {len(categories['weak'])} topics need attention")
    if categories["stale"]:
        recommendations.append(f"Revision needed: {len(categories['stale'])} strong topics getting stale")
    
    try:
        diagnosis = await get_quick_diagnosis(user_id, db)
        if diagnosis and diagnosis.get("top_recommendation"):
            recommendations.append(diagnosis["top_recommendation"])
    except:
        pass
    
    return StudyPlanResult(
        user_id=user_id,
        plan_type=PlanHorizon.DAILY,
        generated_at=datetime.utcnow().isoformat(),
        days=[day_plan],
        summary={
            "total_items": len(all_items),
            "total_time_minutes": total_time,
            "weak_topics_covered": len([t for t in selected_topics if t.get("category") == "weak"]),
            "medium_topics_covered": len([t for t in selected_topics if t.get("category") == "medium"]),
            "revision_topics": len([t for t in selected_topics if t.get("category") == "revision"]),
            "subjects_covered": len(focus_subjects),
        },
        recommendations=recommendations[:5],
    )


async def generate_weekly_plan(
    user_id: int,
    db: AsyncSession,
    days: int = 7,
    daily_minutes: int = DEFAULT_DAILY_STUDY_MINUTES
) -> StudyPlanResult:
    """
    Generate a weekly study plan.
    
    Distributes topics across days with proper balance.
    """
    logger.info(f"Generating {days}-day plan for user_id={user_id}")
    
    user, priorities, topic_mastery_map, subject_map = await fetch_user_learning_data(user_id, db)
    
    if not priorities:
        return StudyPlanResult(
            user_id=user_id,
            plan_type=PlanHorizon.WEEKLY,
            generated_at=datetime.utcnow().isoformat(),
            days=[],
            summary={
                "message": "No topics available. Start exploring subjects to get a personalized plan.",
                "total_topics": 0,
            },
            recommendations=["Browse available subjects and start learning"],
        )
    
    categories = categorize_topics_by_mastery(priorities, topic_mastery_map)
    
    day_plans = []
    already_selected = set()
    base_date = datetime.utcnow()
    
    for day_num in range(days):
        day_date = base_date + timedelta(days=day_num)
        day_label = f"Day {day_num + 1}" if day_num > 0 else "Today"
        
        if day_num == 6:
            day_label = "Day 7 (Review)"
        
        selected_topics = select_topics_for_session(
            categories, 
            daily_minutes,
            already_selected
        )
        
        if not selected_topics:
            already_selected.clear()
            selected_topics = select_topics_for_session(
                categories,
                daily_minutes,
                already_selected
            )
        
        all_items = []
        for topic in selected_topics:
            items = await create_session_items(topic, subject_map, topic_mastery_map, db)
            all_items.extend(items)
        
        total_time = sum(item.estimated_time_minutes for item in all_items)
        focus_subjects = list(set(item.subject_name for item in all_items))
        
        day_plans.append(DayPlan(
            day_label=day_label,
            date=day_date.strftime("%Y-%m-%d"),
            items=all_items,
            total_time_minutes=total_time,
            focus_subjects=focus_subjects,
        ))
    
    total_items = sum(len(d.items) for d in day_plans)
    total_time = sum(d.total_time_minutes for d in day_plans)
    all_subjects = list(set(s for d in day_plans for s in d.focus_subjects))
    
    recommendations = []
    if categories["weak"]:
        recommendations.append(f"Priority focus: {len(categories['weak'])} weak topics identified")
    if categories["stale"]:
        recommendations.append(f"Schedule revision: {len(categories['stale'])} topics getting stale")
    recommendations.append(f"Estimated {total_time // 60} hours of study over {days} days")
    
    try:
        diagnosis = await get_quick_diagnosis(user_id, db)
        if diagnosis and diagnosis.get("top_recommendation"):
            recommendations.append(diagnosis["top_recommendation"])
    except:
        pass
    
    return StudyPlanResult(
        user_id=user_id,
        plan_type=PlanHorizon.WEEKLY,
        generated_at=datetime.utcnow().isoformat(),
        days=day_plans,
        summary={
            "total_days": len(day_plans),
            "total_items": total_items,
            "total_time_minutes": total_time,
            "average_daily_minutes": total_time // days if days > 0 else 0,
            "subjects_covered": len(all_subjects),
            "weak_topics_total": len(categories["weak"]),
            "medium_topics_total": len(categories["medium"]),
            "revision_topics_total": len(categories["stale"]),
        },
        recommendations=recommendations[:5],
    )


async def save_plan_to_db(
    user_id: int,
    plan_result: StudyPlanResult,
    db: AsyncSession
) -> int:
    """
    Save generated plan to database for tracking.
    
    Deactivates any existing active plans.
    """
    active_plans_stmt = select(StudyPlan).where(
        and_(
            StudyPlan.user_id == user_id,
            StudyPlan.is_active == True
        )
    )
    active_result = await db.execute(active_plans_stmt)
    for plan in active_result.scalars().all():
        plan.is_active = False
    
    weeks = len(plan_result.days) // 7 + (1 if len(plan_result.days) % 7 else 0)
    weeks = max(1, weeks)
    
    summary_text = f"Auto-generated {plan_result.plan_type.value} plan covering {plan_result.summary.get('subjects_covered', 0)} subjects"
    
    study_plan = StudyPlan(
        user_id=user_id,
        duration_weeks=weeks,
        summary=summary_text,
        is_active=True
    )
    db.add(study_plan)
    await db.flush()
    
    for day_idx, day in enumerate(plan_result.days):
        week_number = day_idx // 7 + 1
        
        topics_in_day = set()
        for item in day.items:
            if item.topic_tag and item.topic_tag not in topics_in_day:
                topics_in_day.add(item.topic_tag)
                
                plan_item = StudyPlanItem(
                    plan_id=study_plan.id,
                    week_number=week_number,
                    subject_id=item.subject_id,
                    topic_tag=item.topic_tag,
                    recommended_actions=[item.focus, item.success_criteria],
                    estimated_hours=max(1, item.estimated_time_minutes // 60),
                    priority=item.priority_level,
                    rationale=item.why
                )
                db.add(plan_item)
    
    await db.commit()
    await db.refresh(study_plan)
    
    logger.info(f"Saved study plan {study_plan.id} for user {user_id}")
    
    return study_plan.id


async def get_next_study_item(
    user_id: int,
    db: AsyncSession
) -> Optional[Dict[str, Any]]:
    """
    Get the single most important item to study right now.
    
    Quick endpoint for "What should I study next?"
    """
    plan = await generate_daily_plan(user_id, db, target_minutes=60)
    
    if not plan.days or not plan.days[0].items:
        return None
    
    top_item = plan.days[0].items[0]
    
    return {
        "subject": top_item.subject_name,
        "topic": top_item.topic_tag,
        "activity": top_item.activity_type.value,
        "content_title": top_item.content_title,
        "estimated_time_minutes": top_item.estimated_time_minutes,
        "priority": top_item.priority_level,
        "why": top_item.why,
        "focus": top_item.focus,
        "success_criteria": top_item.success_criteria,
        "content_id": top_item.content_id,
        "module_id": top_item.module_id,
    }
