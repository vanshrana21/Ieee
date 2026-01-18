"""
backend/ai/feedback.py
Phase 10.3: Practice Answer Explanation ("Why You're Wrong")

PURPOSE:
Explain why an answer is correct or incorrect, using ONLY existing
curriculum data and the student's submitted attempt.

STRICT RULES:
1. Evaluation first, explanation later (AI speaks ONLY after submission)
2. AI cannot infer or fetch anything outside provided inputs
3. AI explains, never judges or re-evaluates
4. Backend correctness is FINAL

WHAT AI CAN SEE:
- Question text (from practice_questions)
- Correct answer (from DB)
- Student's submitted answer
- Marking guidelines (if present)
- Current subject/module context

WHAT AI MUST NEVER DO:
- Suggest answers beforehand
- Re-evaluate scores
- Override backend correctness
- Introduce new cases, laws, or doctrines
- Recommend next topic
"""

import logging
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from backend.orm.practice_question import PracticeQuestion, QuestionType
from backend.orm.practice_attempt import PracticeAttempt
from backend.orm.practice_evaluation import PracticeEvaluation
from backend.orm.content_module import ContentModule
from backend.orm.subject import Subject
from backend.exceptions import ForbiddenError, NotFoundError

logger = logging.getLogger(__name__)

_feedback_cache: Dict[str, str] = {}
FEEDBACK_CACHE_MAX_SIZE = 200


FEEDBACK_PROMPT_TEMPLATE = """You are a legal tutor providing post-attempt feedback for Indian law students.

CONTEXT:
Subject: {subject_name}
Module: {module_title}

QUESTION ({question_type}, {marks} marks):
{question_text}

CORRECT ANSWER:
{correct_answer}

STUDENT'S SUBMITTED ANSWER:
{student_answer}

RESULT: {result_text}

{guidelines_section}

YOUR TASK:
Explain why the correct answer is correct, and why the student's answer is {result_explanation}.

STRICT RULES:
1. Use ONLY the information provided above.
2. Do NOT introduce new cases, laws, sections, or doctrines.
3. Do NOT re-evaluate or change the correctness verdict.
4. Use exam-safe, clear language.
5. Be constructive and educational.

FORMAT YOUR RESPONSE AS:
## Why the Correct Answer is Right
[Explain the legal principle/reasoning behind the correct answer]

## Analysis of Your Answer
[Explain specifically what was {result_word} about the student's answer]

{comparison_instruction}

## Key Takeaway
[One concise learning point from this question]
"""

MCQ_COMPARISON_INSTRUCTION = """## Option Analysis
[Briefly explain why each wrong option is incorrect]"""

DESCRIPTIVE_COMPARISON_INSTRUCTION = """## What Was Missing/Incorrect
[List specific points that were missing or incorrect in the student's answer]"""


def _get_feedback_cache_key(attempt_id: int) -> str:
    """Generate cache key for feedback"""
    return f"feedback:{attempt_id}"


def _feedback_cache_get(key: str) -> Optional[str]:
    """Get from feedback cache"""
    return _feedback_cache.get(key)


def _feedback_cache_set(key: str, value: str) -> None:
    """Set in feedback cache with LRU-like eviction"""
    global _feedback_cache
    if len(_feedback_cache) >= FEEDBACK_CACHE_MAX_SIZE:
        oldest = next(iter(_feedback_cache))
        del _feedback_cache[oldest]
    _feedback_cache[key] = value


async def _call_llm_for_feedback(prompt: str) -> str:
    """
    Call Gemini LLM for feedback generation.
    """
    import google.generativeai as genai
    
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = await model.generate_content_async(prompt)
        return response.text
    except Exception as e:
        logger.error(f"[Feedback LLM] Generation error: {e}")
        raise


async def get_attempt_with_context(
    db: AsyncSession,
    attempt_id: int,
    user_id: int
) -> Dict[str, Any]:
    """
    Fetch attempt with full context for feedback generation.
    
    Validates:
    - Attempt exists
    - Attempt belongs to user
    - Question data is available
    
    Returns dict with all data needed for feedback prompt.
    """
    attempt_result = await db.execute(
        select(PracticeAttempt)
        .options(
            joinedload(PracticeAttempt.practice_question),
            joinedload(PracticeAttempt.evaluation)
        )
        .where(
            PracticeAttempt.id == attempt_id,
            PracticeAttempt.user_id == user_id
        )
    )
    attempt = attempt_result.scalar_one_or_none()
    
    if not attempt:
        raise NotFoundError("Attempt not found or does not belong to you")
    
    question = attempt.practice_question
    if not question:
        raise NotFoundError("Question not found for this attempt")
    
    module_result = await db.execute(
        select(ContentModule).where(ContentModule.id == question.module_id)
    )
    module = module_result.scalar_one_or_none()
    
    subject_result = await db.execute(
        select(Subject).where(Subject.id == module.subject_id)
    ) if module else None
    subject = subject_result.scalar_one_or_none() if subject_result else None
    
    return {
        "attempt": attempt,
        "question": question,
        "module": module,
        "subject": subject,
        "evaluation": attempt.evaluation
    }


def build_feedback_prompt(
    *,
    question: PracticeQuestion,
    student_answer: str,
    is_correct: Optional[bool],
    subject_name: str,
    module_title: str
) -> str:
    """
    Build prompt for post-attempt feedback.
    
    Phase 10.3: Generates feedback prompt using ONLY provided data.
    """
    question_type_display = {
        QuestionType.MCQ: "Multiple Choice",
        QuestionType.SHORT_ANSWER: "Short Answer",
        QuestionType.ESSAY: "Essay",
        QuestionType.CASE_ANALYSIS: "Case Analysis"
    }.get(question.question_type, "Question")
    
    if is_correct is True:
        result_text = "CORRECT"
        result_explanation = "correct"
        result_word = "right"
    elif is_correct is False:
        result_text = "INCORRECT"
        result_explanation = "incorrect"
        result_word = "wrong"
    else:
        result_text = "SUBMITTED (Pending Review)"
        result_explanation = "submitted for review"
        result_word = "to improve"
    
    guidelines_section = ""
    if question.explanation:
        guidelines_section = f"MARKING GUIDELINES/EXPLANATION:\n{question.explanation}"
    
    if question.question_type == QuestionType.MCQ:
        comparison_instruction = MCQ_COMPARISON_INSTRUCTION
        correct_answer_display = f"{question.correct_answer}"
        if question.correct_answer.upper() == "A" and question.option_a:
            correct_answer_display = f"A: {question.option_a}"
        elif question.correct_answer.upper() == "B" and question.option_b:
            correct_answer_display = f"B: {question.option_b}"
        elif question.correct_answer.upper() == "C" and question.option_c:
            correct_answer_display = f"C: {question.option_c}"
        elif question.correct_answer.upper() == "D" and question.option_d:
            correct_answer_display = f"D: {question.option_d}"
    else:
        comparison_instruction = DESCRIPTIVE_COMPARISON_INSTRUCTION
        correct_answer_display = question.correct_answer
    
    return FEEDBACK_PROMPT_TEMPLATE.format(
        subject_name=subject_name or "Law",
        module_title=module_title or "Practice",
        question_type=question_type_display,
        marks=question.marks,
        question_text=question.question,
        correct_answer=correct_answer_display,
        student_answer=student_answer[:2000],
        result_text=result_text,
        result_explanation=result_explanation,
        result_word=result_word,
        guidelines_section=guidelines_section,
        comparison_instruction=comparison_instruction
    )


async def generate_attempt_feedback(
    *,
    db: AsyncSession,
    user_id: int,
    attempt_id: int,
    use_cache: bool = True
) -> Dict[str, Any]:
    """
    Generate AI feedback for a submitted practice attempt.
    
    Phase 10.3: Post-Attempt Feedback Engine
    
    CRITICAL RULES:
    1. Only works on SUBMITTED attempts (attempt must exist)
    2. Does NOT re-evaluate correctness
    3. Uses ONLY data from DB (question, answer, correctness)
    4. Cached for identical requests
    
    Args:
        db: Database session
        user_id: Current user ID (for ownership validation)
        attempt_id: ID of the attempt to explain
        use_cache: Whether to use cached feedback
    
    Returns:
        Dict with feedback, context, and attempt details
    
    Raises:
        NotFoundError: If attempt doesn't exist or doesn't belong to user
        ForbiddenError: If attempt has no submission yet
    """
    logger.info(f"[Feedback] Generating for attempt={attempt_id}, user={user_id}")
    
    cache_key = _get_feedback_cache_key(attempt_id)
    if use_cache:
        cached = _feedback_cache_get(cache_key)
        if cached:
            logger.info(f"[Feedback] Cache hit for {cache_key}")
            context_data = await get_attempt_with_context(db, attempt_id, user_id)
            return {
                "attempt_id": attempt_id,
                "feedback": cached,
                "from_cache": True,
                "is_correct": context_data["attempt"].is_correct,
                "question_type": context_data["question"].question_type.value,
                "subject": context_data["subject"].title if context_data["subject"] else None,
                "module": context_data["module"].title if context_data["module"] else None
            }
    
    context_data = await get_attempt_with_context(db, attempt_id, user_id)
    
    attempt = context_data["attempt"]
    question = context_data["question"]
    module = context_data["module"]
    subject = context_data["subject"]
    
    if not attempt.selected_option:
        raise ForbiddenError("No answer submitted for this attempt")
    
    prompt = build_feedback_prompt(
        question=question,
        student_answer=attempt.selected_option,
        is_correct=attempt.is_correct,
        subject_name=subject.title if subject else "Law",
        module_title=module.title if module else "Practice"
    )
    
    try:
        feedback = await _call_llm_for_feedback(prompt)
    except Exception as e:
        logger.error(f"[Feedback] LLM error: {e}")
        feedback = generate_fallback_feedback(
            question=question,
            student_answer=attempt.selected_option,
            is_correct=attempt.is_correct
        )
    
    if use_cache:
        _feedback_cache_set(cache_key, feedback)
        logger.info(f"[Feedback] Cached for {cache_key}")
    
    return {
        "attempt_id": attempt_id,
        "feedback": feedback,
        "from_cache": False,
        "is_correct": attempt.is_correct,
        "question_type": question.question_type.value,
        "correct_answer": question.correct_answer,
        "student_answer": attempt.selected_option,
        "subject": subject.title if subject else None,
        "module": module.title if module else None,
        "question_text": question.question
    }


def generate_fallback_feedback(
    *,
    question: PracticeQuestion,
    student_answer: str,
    is_correct: Optional[bool]
) -> str:
    """
    Generate simple fallback feedback when LLM fails.
    
    Uses static templates based on question type and correctness.
    """
    if is_correct is True:
        return f"""## Correct Answer!

Your answer "{student_answer}" is correct.

**Correct Answer:** {question.correct_answer}

{f"**Explanation:** {question.explanation}" if question.explanation else ""}

Keep up the good work!
"""
    elif is_correct is False:
        return f"""## Incorrect Answer

Your answer "{student_answer}" was incorrect.

**Correct Answer:** {question.correct_answer}

{f"**Explanation:** {question.explanation}" if question.explanation else ""}

Review this topic and try again.
"""
    else:
        return f"""## Answer Submitted

Your answer has been recorded for review.

**Your Answer:** {student_answer[:200]}{"..." if len(student_answer) > 200 else ""}

**Model Answer/Key Points:**
{question.correct_answer}

{f"**Marking Guidelines:** {question.explanation}" if question.explanation else ""}

Compare your answer with the model answer to identify areas for improvement.
"""


async def get_mcq_option_analysis(
    *,
    db: AsyncSession,
    user_id: int,
    attempt_id: int
) -> Dict[str, Any]:
    """
    Get detailed analysis of all MCQ options.
    
    Only available for MCQ questions after submission.
    """
    context_data = await get_attempt_with_context(db, attempt_id, user_id)
    
    question = context_data["question"]
    attempt = context_data["attempt"]
    
    if question.question_type != QuestionType.MCQ:
        raise ForbiddenError("Option analysis only available for MCQ questions")
    
    correct = question.correct_answer.upper()
    selected = attempt.selected_option.upper() if attempt.selected_option else None
    
    options = {
        "A": {
            "text": question.option_a,
            "is_correct": correct == "A",
            "was_selected": selected == "A"
        },
        "B": {
            "text": question.option_b,
            "is_correct": correct == "B",
            "was_selected": selected == "B"
        },
        "C": {
            "text": question.option_c,
            "is_correct": correct == "C",
            "was_selected": selected == "C"
        },
        "D": {
            "text": question.option_d,
            "is_correct": correct == "D",
            "was_selected": selected == "D"
        }
    }
    
    return {
        "attempt_id": attempt_id,
        "question_id": question.id,
        "question_text": question.question,
        "options": options,
        "correct_option": correct,
        "selected_option": selected,
        "is_correct": attempt.is_correct,
        "explanation": question.explanation
    }


def clear_feedback_cache() -> int:
    """Clear the feedback cache. Returns number of items cleared."""
    global _feedback_cache
    count = len(_feedback_cache)
    _feedback_cache = {}
    return count
