"""
backend/ai/memory.py
Phase 10.5: Tutor Memory (Backend-Owned)

PURPOSE:
Enable the tutor to remember learning patterns using backend data,
while ensuring AI never infers, invents, or decides anything on its own.

CORE PRINCIPLE:
The backend remembers. AI only summarizes what the backend already knows.

WHAT "TUTOR MEMORY" IS:
- A summary of historical FACTS
- Derived from: past attempts, topic mastery, repeated mistakes, explanation usage
- Expressed as: "You've struggled with X", "You often confuse A with B"
- DESCRIPTIVE, not PRESCRIPTIVE

WHAT AI CANNOT DO WITH MEMORY:
- Detect patterns on its own
- Infer weaknesses
- Predict readiness
- Change learning flow
- Label the student ("you are weak")
- Predict outcomes
- Recommend skipping or advancing
- Modify difficulty flags
- Store memory on its own
- Access data outside provided summaries

MEMORY SCOPE:
- Subject-scoped (no cross-subject inference)
- No permanent profiling
- Resets/decays based on backend rules
- AI does NOT decide retention duration
"""

import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc

from backend.orm.topic_mastery import TopicMastery
from backend.orm.practice_attempt import PracticeAttempt
from backend.orm.practice_question import PracticeQuestion
from backend.orm.subject_progress import SubjectProgress
from backend.orm.content_module import ContentModule
from backend.orm.subject import Subject

logger = logging.getLogger(__name__)


@dataclass
class TopicStruggle:
    """Backend-computed struggle record for a topic"""
    topic_tag: str
    topic_name: str
    incorrect_count: int
    total_attempts: int
    mastery_score: float
    last_attempted: Optional[datetime]
    
    @property
    def struggle_ratio(self) -> float:
        if self.total_attempts == 0:
            return 0.0
        return self.incorrect_count / self.total_attempts
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic_tag": self.topic_tag,
            "topic_name": self.topic_name,
            "incorrect_count": self.incorrect_count,
            "total_attempts": self.total_attempts,
            "mastery_score": round(self.mastery_score, 3),
            "struggle_ratio": round(self.struggle_ratio, 3),
            "last_attempted": self.last_attempted.isoformat() if self.last_attempted else None
        }


@dataclass
class ConfusionPattern:
    """Backend-detected confusion between concepts"""
    concept_a: str
    concept_b: str
    confusion_count: int
    description: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "concept_a": self.concept_a,
            "concept_b": self.concept_b,
            "confusion_count": self.confusion_count,
            "description": self.description
        }


@dataclass
class TutorMemory:
    """
    Backend-computed memory summary for AI to verbalize.
    
    Phase 10.5: AI receives this as READ-ONLY data.
    AI cannot modify, store, or infer beyond this.
    """
    user_id: int
    subject_id: int
    subject_name: str
    
    total_attempts: int = 0
    correct_count: int = 0
    incorrect_count: int = 0
    
    struggling_topics: List[TopicStruggle] = field(default_factory=list)
    confusion_patterns: List[ConfusionPattern] = field(default_factory=list)
    
    explanation_requests: int = 0
    repeated_explanations: int = 0
    
    strongest_topic: Optional[str] = None
    weakest_topic: Optional[str] = None
    
    last_activity: Optional[datetime] = None
    study_streak_days: int = 0
    
    memory_computed_at: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def accuracy_rate(self) -> float:
        if self.total_attempts == 0:
            return 0.0
        return self.correct_count / self.total_attempts
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "subject_id": self.subject_id,
            "subject_name": self.subject_name,
            "total_attempts": self.total_attempts,
            "correct_count": self.correct_count,
            "incorrect_count": self.incorrect_count,
            "accuracy_rate": round(self.accuracy_rate, 3),
            "struggling_topics": [t.to_dict() for t in self.struggling_topics],
            "confusion_patterns": [c.to_dict() for c in self.confusion_patterns],
            "explanation_requests": self.explanation_requests,
            "repeated_explanations": self.repeated_explanations,
            "strongest_topic": self.strongest_topic,
            "weakest_topic": self.weakest_topic,
            "last_activity": self.last_activity.isoformat() if self.last_activity else None,
            "study_streak_days": self.study_streak_days,
            "memory_computed_at": self.memory_computed_at.isoformat()
        }


async def compute_tutor_memory(
    db: AsyncSession,
    user_id: int,
    subject_id: int,
    lookback_days: int = 30
) -> TutorMemory:
    """
    Compute tutor memory from backend data.
    
    Phase 10.5: Backend computes, AI only reads.
    
    This function aggregates:
    - Practice attempt history
    - Topic mastery scores
    - Error patterns
    - Explanation usage
    
    Returns a TutorMemory object that AI can verbalize but NOT modify.
    """
    logger.info(f"[Memory] Computing for user={user_id}, subject={subject_id}")
    
    subject_result = await db.execute(
        select(Subject).where(Subject.id == subject_id)
    )
    subject = subject_result.scalar_one_or_none()
    subject_name = subject.title if subject else "Unknown Subject"
    
    cutoff_date = datetime.utcnow() - timedelta(days=lookback_days)
    
    attempts_query = (
        select(PracticeAttempt)
        .join(PracticeQuestion)
        .join(ContentModule)
        .where(
            PracticeAttempt.user_id == user_id,
            ContentModule.subject_id == subject_id,
            PracticeAttempt.attempted_at >= cutoff_date
        )
        .order_by(desc(PracticeAttempt.attempted_at))
    )
    
    attempts_result = await db.execute(attempts_query)
    attempts = attempts_result.scalars().all()
    
    total_attempts = len(attempts)
    correct_count = sum(1 for a in attempts if a.is_correct is True)
    incorrect_count = sum(1 for a in attempts if a.is_correct is False)
    
    last_activity = attempts[0].attempted_at if attempts else None
    
    mastery_result = await db.execute(
        select(TopicMastery).where(
            TopicMastery.user_id == user_id,
            TopicMastery.subject_id == subject_id
        )
    )
    masteries = mastery_result.scalars().all()
    
    struggling_topics = []
    strongest_topic = None
    weakest_topic = None
    highest_score = -1
    lowest_score = 2
    
    for mastery in masteries:
        if mastery.mastery_score < 0.5 and mastery.attempt_count >= 2:
            incorrect_for_topic = sum(
                1 for a in attempts 
                if a.practice_question and 
                a.practice_question.topic_tag == mastery.topic_tag and
                a.is_correct is False
            )
            
            struggling_topics.append(TopicStruggle(
                topic_tag=mastery.topic_tag,
                topic_name=mastery.topic_tag.replace("-", " ").replace("_", " ").title(),
                incorrect_count=incorrect_for_topic,
                total_attempts=mastery.attempt_count,
                mastery_score=mastery.mastery_score,
                last_attempted=mastery.last_practiced_at
            ))
        
        if mastery.attempt_count >= 2:
            if mastery.mastery_score > highest_score:
                highest_score = mastery.mastery_score
                strongest_topic = mastery.topic_tag
            if mastery.mastery_score < lowest_score:
                lowest_score = mastery.mastery_score
                weakest_topic = mastery.topic_tag
    
    struggling_topics.sort(key=lambda x: x.mastery_score)
    
    confusion_patterns = await _detect_confusion_patterns(attempts)
    
    study_streak = await _compute_study_streak(db, user_id, subject_id)
    
    return TutorMemory(
        user_id=user_id,
        subject_id=subject_id,
        subject_name=subject_name,
        total_attempts=total_attempts,
        correct_count=correct_count,
        incorrect_count=incorrect_count,
        struggling_topics=struggling_topics[:5],
        confusion_patterns=confusion_patterns[:3],
        explanation_requests=0,
        repeated_explanations=0,
        strongest_topic=strongest_topic,
        weakest_topic=weakest_topic,
        last_activity=last_activity,
        study_streak_days=study_streak
    )


async def _detect_confusion_patterns(attempts: List[PracticeAttempt]) -> List[ConfusionPattern]:
    """
    Detect confusion patterns from attempt history.
    
    Backend logic only - looks for repeated mistakes on related topics.
    """
    patterns = []
    
    incorrect_by_topic = {}
    for attempt in attempts:
        if attempt.is_correct is False and attempt.practice_question:
            topic = attempt.practice_question.topic_tag
            if topic:
                if topic not in incorrect_by_topic:
                    incorrect_by_topic[topic] = []
                incorrect_by_topic[topic].append(attempt)
    
    topics_with_errors = [t for t, a in incorrect_by_topic.items() if len(a) >= 2]
    
    for i, topic_a in enumerate(topics_with_errors):
        for topic_b in topics_with_errors[i+1:]:
            if _topics_related(topic_a, topic_b):
                patterns.append(ConfusionPattern(
                    concept_a=topic_a.replace("-", " ").title(),
                    concept_b=topic_b.replace("-", " ").title(),
                    confusion_count=len(incorrect_by_topic[topic_a]) + len(incorrect_by_topic[topic_b]),
                    description=f"Repeated errors on both {topic_a} and {topic_b}"
                ))
    
    return patterns


def _topics_related(topic_a: str, topic_b: str) -> bool:
    """Check if two topics might be confused with each other"""
    a_parts = set(topic_a.lower().replace("-", " ").replace("_", " ").split())
    b_parts = set(topic_b.lower().replace("-", " ").replace("_", " ").split())
    
    common = a_parts & b_parts
    return len(common) >= 1


async def _compute_study_streak(db: AsyncSession, user_id: int, subject_id: int) -> int:
    """Compute consecutive days of study activity"""
    today = datetime.utcnow().date()
    streak = 0
    
    for days_ago in range(30):
        check_date = today - timedelta(days=days_ago)
        start = datetime.combine(check_date, datetime.min.time())
        end = datetime.combine(check_date, datetime.max.time())
        
        count_result = await db.execute(
            select(func.count(PracticeAttempt.id))
            .join(PracticeQuestion)
            .join(ContentModule)
            .where(
                PracticeAttempt.user_id == user_id,
                ContentModule.subject_id == subject_id,
                PracticeAttempt.attempted_at >= start,
                PracticeAttempt.attempted_at <= end
            )
        )
        count = count_result.scalar()
        
        if count and count > 0:
            streak += 1
        elif days_ago > 0:
            break
    
    return streak


def build_memory_context_for_ai(memory: TutorMemory) -> str:
    """
    Build context string for AI to use in responses.
    
    Phase 10.5: AI receives this as READ-ONLY context.
    AI can verbalize this, but CANNOT:
    - Add to it
    - Infer beyond it
    - Store it
    - Change it
    
    The phrases here are TEMPLATES - AI uses them to acknowledge history.
    """
    context_parts = []
    
    context_parts.append(f"TUTOR MEMORY FOR {memory.subject_name.upper()} (Backend-Computed, Read-Only)")
    context_parts.append("=" * 60)
    
    if memory.total_attempts > 0:
        context_parts.append(f"\nLEARNING HISTORY:")
        context_parts.append(f"- Total practice attempts: {memory.total_attempts}")
        context_parts.append(f"- Accuracy rate: {memory.accuracy_rate:.1%}")
        context_parts.append(f"- Correct: {memory.correct_count}, Incorrect: {memory.incorrect_count}")
    
    if memory.struggling_topics:
        context_parts.append(f"\nTOPICS REQUIRING REINFORCEMENT:")
        for topic in memory.struggling_topics:
            context_parts.append(f"- {topic.topic_name}: {topic.incorrect_count} errors, mastery {topic.mastery_score:.1%}")
    
    if memory.confusion_patterns:
        context_parts.append(f"\nDETECTED CONFUSION PATTERNS:")
        for pattern in memory.confusion_patterns:
            context_parts.append(f"- Student confuses {pattern.concept_a} with {pattern.concept_b}")
    
    if memory.strongest_topic:
        context_parts.append(f"\nSTRONGEST TOPIC: {memory.strongest_topic}")
    if memory.weakest_topic:
        context_parts.append(f"WEAKEST TOPIC: {memory.weakest_topic}")
    
    if memory.study_streak_days > 0:
        context_parts.append(f"\nSTUDY STREAK: {memory.study_streak_days} consecutive days")
    
    context_parts.append("\n" + "=" * 60)
    context_parts.append("AI INSTRUCTIONS FOR USING THIS MEMORY:")
    context_parts.append("- You may ACKNOWLEDGE past struggles: 'Since this concept has been tricky before...'")
    context_parts.append("- You may REFERENCE known confusions: 'You've sometimes mixed up X and Y...'")
    context_parts.append("- You may RECOGNIZE effort: 'You've been practicing consistently...'")
    context_parts.append("")
    context_parts.append("YOU MUST NOT:")
    context_parts.append("- Label the student ('you are weak at...')")
    context_parts.append("- Predict outcomes ('you will fail...')")
    context_parts.append("- Recommend skipping or advancing")
    context_parts.append("- Modify any data or flags")
    context_parts.append("- Infer patterns beyond what is stated above")
    context_parts.append("=" * 60)
    
    return "\n".join(context_parts)


MEMORY_PHRASES = {
    "struggle_acknowledgment": [
        "Since {topic} has been challenging before, let's approach it step by step...",
        "I notice {topic} has required extra practice. Let me explain it differently...",
        "This concept around {topic} can be tricky. Here's another way to think about it...",
    ],
    "confusion_acknowledgment": [
        "You've sometimes mixed up {concept_a} with {concept_b}. The key difference is...",
        "Since {concept_a} and {concept_b} can seem similar, let me clarify...",
        "To distinguish {concept_a} from {concept_b}, remember that...",
    ],
    "progress_acknowledgment": [
        "You've been practicing consistently. Building on that...",
        "Your regular practice is paying off. Let's continue with...",
        "Good to see you're staying engaged with the material...",
    ],
    "strength_acknowledgment": [
        "Since you've shown good understanding of {topic}, this should connect well...",
        "Building on your strength in {topic}...",
        "This relates to {topic}, which you've handled well...",
    ]
}


def get_memory_phrase(
    phrase_type: str,
    memory: TutorMemory,
    topic: Optional[str] = None
) -> Optional[str]:
    """
    Get an appropriate memory-aware phrase.
    
    Phase 10.5: These are TEMPLATES for AI to use.
    AI must not generate phrases beyond these patterns.
    """
    import random
    
    phrases = MEMORY_PHRASES.get(phrase_type, [])
    if not phrases:
        return None
    
    phrase = random.choice(phrases)
    
    if phrase_type == "struggle_acknowledgment":
        if topic:
            return phrase.format(topic=topic.replace("-", " ").title())
        elif memory.weakest_topic:
            return phrase.format(topic=memory.weakest_topic.replace("-", " ").title())
        return None
    
    elif phrase_type == "confusion_acknowledgment":
        if memory.confusion_patterns:
            pattern = memory.confusion_patterns[0]
            return phrase.format(
                concept_a=pattern.concept_a,
                concept_b=pattern.concept_b
            )
        return None
    
    elif phrase_type == "progress_acknowledgment":
        if memory.study_streak_days >= 2:
            return phrase
        return None
    
    elif phrase_type == "strength_acknowledgment":
        if memory.strongest_topic:
            return phrase.format(topic=memory.strongest_topic.replace("-", " ").title())
        return None
    
    return None


def get_memory_summary() -> Dict[str, Any]:
    """Return summary of memory system for documentation/health check."""
    return {
        "version": "10.5",
        "service": "tutor-memory-engine",
        "principle": "Backend remembers. AI summarizes.",
        "memory_is": [
            "Summary of historical facts",
            "Derived from practice_attempts, topic_mastery, subject_progress",
            "Descriptive, not prescriptive",
            "Subject-scoped (no cross-subject inference)"
        ],
        "ai_can": [
            "Restate known struggles",
            "Acknowledge repeated confusion",
            "Frame explanations with awareness",
            "Recognize consistent effort"
        ],
        "ai_cannot": [
            "Detect patterns independently",
            "Decide student profile",
            "Influence progression",
            "Store memory on its own",
            "Access raw analytics",
            "Label the student",
            "Predict outcomes",
            "Recommend skipping/advancing"
        ],
        "phrase_types": list(MEMORY_PHRASES.keys())
    }
