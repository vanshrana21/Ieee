"""
backend/ai/adaptive.py
Phase 10.4: Adaptive Hinting (Non-AI-First)

PURPOSE:
Adjust explanation depth and presentation based on repeated mistakes,
WITHOUT skipping curriculum steps.

CORE PRINCIPLE:
Rules first. AI second.
Backend detects patterns → AI phrases guidance.

WHAT AI CAN ADAPT:
- Explanation depth
- Use of examples
- Simpler language
- Exam-focused framing

WHAT AI CANNOT DO:
- Advance the student
- Skip content
- Unlock practice
- Recommend syllabus reordering
- Override backend progression rules
- Decide "you are ready"
- Unlock next module
- Auto-start revision
- Modify difficulty level directly

All navigation remains backend-controlled.
"""

import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from datetime import datetime, timedelta

from backend.orm.topic_mastery import TopicMastery
from backend.orm.practice_attempt import PracticeAttempt
from backend.orm.practice_question import PracticeQuestion
from backend.orm.subject_progress import SubjectProgress
from backend.exceptions import NotFoundError

logger = logging.getLogger(__name__)


class DifficultyLevel(str, Enum):
    """Backend-determined difficulty levels"""
    HIGH_CONFUSION = "high_confusion"
    MODERATE_CONFUSION = "moderate_confusion"
    LOW_CONFUSION = "low_confusion"
    MASTERED = "mastered"


class AdaptationStyle(str, Enum):
    """AI explanation styles - adjustable, not navigational"""
    BASIC = "basic"
    SIMPLIFIED = "simplified"
    DETAILED = "detailed"
    EXAM_FOCUSED = "exam_focused"
    EXAMPLE_HEAVY = "example_heavy"


@dataclass
class AdaptationSignals:
    """
    Backend-computed signals passed to AI.
    
    AI receives these as FLAGS, not raw analytics.
    AI cannot compute these - backend provides them.
    """
    difficulty_level: DifficultyLevel
    attempt_count: int
    topic_mastery: str
    recent_incorrect_streak: int
    subject_completion: float
    needs_reinforcement: bool
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "difficulty_level": self.difficulty_level.value,
            "attempt_count": self.attempt_count,
            "topic_mastery": self.topic_mastery,
            "recent_incorrect_streak": self.recent_incorrect_streak,
            "subject_completion": round(self.subject_completion, 1),
            "needs_reinforcement": self.needs_reinforcement
        }


STYLE_INSTRUCTIONS = {
    AdaptationStyle.BASIC: """
Use simple, clear language.
Define every legal term before using it.
One concept at a time.
Short sentences.
""",
    AdaptationStyle.SIMPLIFIED: """
Break down into the smallest possible steps.
Use everyday analogies where possible.
Repeat key points.
Check understanding with "In other words..." summaries.
Avoid complex sentence structures.
""",
    AdaptationStyle.DETAILED: """
Provide comprehensive explanation.
Include all relevant sub-points.
Explain connections between concepts.
Add context where helpful.
""",
    AdaptationStyle.EXAM_FOCUSED: """
Structure as an exam answer.
Use proper legal headings.
Include relevant sections and cases from the content.
Focus on what an examiner would look for.
Be precise with legal terminology.
""",
    AdaptationStyle.EXAMPLE_HEAVY: """
Lead with practical examples.
Use hypothetical scenarios.
Show application before theory.
"For instance..." should appear frequently.
Connect abstract concepts to concrete situations.
"""
}


REINFORCEMENT_PHRASES = {
    DifficultyLevel.HIGH_CONFUSION: [
        "Let's revisit the basic principle...",
        "Here's a simpler way to think about it...",
        "Starting from the foundation...",
        "The core idea is simply this..."
    ],
    DifficultyLevel.MODERATE_CONFUSION: [
        "Let me clarify this point...",
        "Another way to understand this...",
        "The key distinction is...",
        "Focus on this essential element..."
    ],
    DifficultyLevel.LOW_CONFUSION: [
        "To deepen your understanding...",
        "Building on what you know...",
        "The nuance here is...",
        "For exam purposes, remember..."
    ],
    DifficultyLevel.MASTERED: [
        "As you already understand...",
        "Reinforcing your knowledge...",
        "The advanced application is...",
        "For distinction-level answers..."
    ]
}


async def compute_adaptation_signals(
    db: AsyncSession,
    user_id: int,
    subject_id: int,
    topic_tag: Optional[str] = None,
    module_id: Optional[int] = None
) -> AdaptationSignals:
    """
    Compute adaptation signals from backend data.
    
    Phase 10.4: Backend detects patterns, AI only receives flags.
    
    This function analyzes:
    - Topic mastery scores
    - Recent attempt history
    - Subject progress
    - Error patterns
    
    Returns signals that AI uses to adjust TONE, not FLOW.
    """
    logger.info(f"[Adaptive] Computing signals: user={user_id}, subject={subject_id}, topic={topic_tag}")
    
    mastery_score = 0.5
    attempt_count = 0
    difficulty_level = "medium"
    
    if topic_tag:
        mastery_result = await db.execute(
            select(TopicMastery).where(
                TopicMastery.user_id == user_id,
                TopicMastery.subject_id == subject_id,
                TopicMastery.topic_tag == topic_tag
            )
        )
        mastery = mastery_result.scalar_one_or_none()
        
        if mastery:
            mastery_score = mastery.mastery_score
            attempt_count = mastery.attempt_count
            difficulty_level = mastery.difficulty_level
    
    recent_attempts_query = select(PracticeAttempt).where(
        PracticeAttempt.user_id == user_id,
        PracticeAttempt.attempted_at >= datetime.utcnow() - timedelta(days=7)
    ).order_by(PracticeAttempt.attempted_at.desc()).limit(10)
    
    if module_id:
        recent_attempts_query = recent_attempts_query.join(
            PracticeQuestion,
            PracticeAttempt.practice_question_id == PracticeQuestion.id
        ).where(PracticeQuestion.module_id == module_id)
    
    recent_result = await db.execute(recent_attempts_query)
    recent_attempts = recent_result.scalars().all()
    
    incorrect_streak = 0
    for attempt in recent_attempts:
        if attempt.is_correct is False:
            incorrect_streak += 1
        else:
            break
    
    progress_result = await db.execute(
        select(SubjectProgress).where(
            SubjectProgress.user_id == user_id,
            SubjectProgress.subject_id == subject_id
        )
    )
    progress = progress_result.scalar_one_or_none()
    subject_completion = progress.completion_percentage if progress else 0.0
    
    if mastery_score < 0.3 or incorrect_streak >= 3:
        computed_difficulty = DifficultyLevel.HIGH_CONFUSION
    elif mastery_score < 0.5 or incorrect_streak >= 2:
        computed_difficulty = DifficultyLevel.MODERATE_CONFUSION
    elif mastery_score < 0.7:
        computed_difficulty = DifficultyLevel.LOW_CONFUSION
    else:
        computed_difficulty = DifficultyLevel.MASTERED
    
    needs_reinforcement = (
        incorrect_streak >= 2 or
        mastery_score < 0.4 or
        (attempt_count >= 3 and mastery_score < 0.5)
    )
    
    return AdaptationSignals(
        difficulty_level=computed_difficulty,
        attempt_count=attempt_count,
        topic_mastery=difficulty_level,
        recent_incorrect_streak=incorrect_streak,
        subject_completion=subject_completion,
        needs_reinforcement=needs_reinforcement
    )


def select_adaptation_style(signals: AdaptationSignals) -> AdaptationStyle:
    """
    Select AI explanation style based on backend signals.
    
    This determines HOW AI explains, not WHAT it teaches.
    Backend signals control this selection.
    """
    if signals.difficulty_level == DifficultyLevel.HIGH_CONFUSION:
        if signals.recent_incorrect_streak >= 3:
            return AdaptationStyle.SIMPLIFIED
        return AdaptationStyle.BASIC
    
    elif signals.difficulty_level == DifficultyLevel.MODERATE_CONFUSION:
        if signals.needs_reinforcement:
            return AdaptationStyle.EXAMPLE_HEAVY
        return AdaptationStyle.DETAILED
    
    elif signals.difficulty_level == DifficultyLevel.LOW_CONFUSION:
        return AdaptationStyle.EXAM_FOCUSED
    
    else:
        return AdaptationStyle.EXAM_FOCUSED


def get_reinforcement_opener(signals: AdaptationSignals) -> str:
    """
    Get an appropriate opening phrase based on difficulty.
    
    AI uses this to SET TONE, not to change curriculum.
    """
    phrases = REINFORCEMENT_PHRASES.get(signals.difficulty_level, [])
    if not phrases:
        return ""
    
    import random
    return random.choice(phrases)


def build_adaptive_prompt_modifier(signals: AdaptationSignals) -> str:
    """
    Build prompt modifier for adaptive explanation.
    
    This modifies HOW content is explained, not WHAT is taught.
    
    Phase 10.4 Rule: AI adjusts tone, not structure.
    """
    style = select_adaptation_style(signals)
    style_instruction = STYLE_INSTRUCTIONS.get(style, "")
    
    opener = get_reinforcement_opener(signals)
    
    modifier = f"""
ADAPTATION CONTEXT (from backend analysis):
- Student difficulty level: {signals.difficulty_level.value}
- Attempts on this topic: {signals.attempt_count}
- Recent incorrect streak: {signals.recent_incorrect_streak}
- Needs reinforcement: {"Yes" if signals.needs_reinforcement else "No"}

EXPLANATION STYLE TO USE:
{style_instruction}

{f"START WITH: {opener}" if opener else ""}

CRITICAL RULES:
- Adapt your EXPLANATION STYLE only
- Do NOT skip any content
- Do NOT suggest moving to next topic
- Do NOT unlock or recommend anything
- Focus ONLY on helping understand the current material
- All progression decisions are made by the backend, not you
"""
    return modifier


async def get_adaptive_feedback(
    *,
    db: AsyncSession,
    user_id: int,
    subject_id: int,
    module_id: int,
    content_text: str,
    topic_tag: Optional[str] = None,
    base_prompt: str
) -> Dict[str, Any]:
    """
    Get adaptively-styled explanation.
    
    Phase 10.4: Combines base prompt with adaptation modifiers.
    
    Returns:
        Dict with adapted_prompt, signals, and style used
    """
    signals = await compute_adaptation_signals(
        db=db,
        user_id=user_id,
        subject_id=subject_id,
        topic_tag=topic_tag,
        module_id=module_id
    )
    
    style = select_adaptation_style(signals)
    modifier = build_adaptive_prompt_modifier(signals)
    
    adapted_prompt = f"{base_prompt}\n\n{modifier}"
    
    return {
        "adapted_prompt": adapted_prompt,
        "signals": signals.to_dict(),
        "style": style.value,
        "opener": get_reinforcement_opener(signals)
    }


async def get_hint_for_struggling_student(
    *,
    db: AsyncSession,
    user_id: int,
    subject_id: int,
    module_id: int,
    question_text: str,
    topic_tag: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generate a hint for a struggling student.
    
    Phase 10.4: Hint is phrased by AI, but CANNOT:
    - Reveal the answer
    - Skip the question
    - Suggest moving on
    
    Only provides encouragement and conceptual guidance.
    """
    signals = await compute_adaptation_signals(
        db=db,
        user_id=user_id,
        subject_id=subject_id,
        topic_tag=topic_tag,
        module_id=module_id
    )
    
    if signals.difficulty_level == DifficultyLevel.HIGH_CONFUSION:
        hint_style = "very basic conceptual hint without revealing the answer"
    elif signals.difficulty_level == DifficultyLevel.MODERATE_CONFUSION:
        hint_style = "guiding hint that points toward the right concept"
    else:
        hint_style = "subtle hint about what angle to consider"
    
    return {
        "hint_available": signals.needs_reinforcement or signals.recent_incorrect_streak >= 2,
        "hint_style": hint_style,
        "signals": signals.to_dict(),
        "message": (
            "Take your time. Think about the fundamental principle involved."
            if signals.needs_reinforcement else
            "You're on the right track. Consider the key elements."
        )
    }


def get_adaptation_summary() -> Dict[str, Any]:
    """
    Return summary of adaptation system for documentation/health check.
    """
    return {
        "version": "10.4",
        "service": "adaptive-hinting-engine",
        "rules": {
            "ai_can_adapt": [
                "Explanation depth",
                "Use of examples",
                "Language simplicity",
                "Exam-focused framing"
            ],
            "ai_cannot_do": [
                "Advance the student",
                "Skip content",
                "Unlock practice",
                "Recommend syllabus reordering",
                "Override backend progression",
                "Decide readiness",
                "Unlock next module",
                "Auto-start revision",
                "Modify difficulty directly"
            ]
        },
        "difficulty_levels": [d.value for d in DifficultyLevel],
        "adaptation_styles": [s.value for s in AdaptationStyle]
    }
