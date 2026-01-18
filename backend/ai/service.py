"""
backend/ai/service.py
Phase 10.2: Tutor Explanation Service

PURPOSE:
Explain existing curriculum content - nothing else.

GUARANTEES:
- AI only explains existing content
- Same input → same output (cached)
- Exam-safe language
- No curriculum bypass
- Tutor is optional, not dominant
"""

import logging
import hashlib
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.ai.context import resolve_ai_context, AIContext
from backend.ai.guards import enforce_scope
from backend.ai.prompts import (
    build_explanation_prompt,
    build_question_answer_prompt,
    ExplanationType,
    SYSTEM_GUARD_PROMPT
)
from backend.orm.learn_content import LearnContent
from backend.orm.case_content import CaseContent
from backend.orm.content_module import ContentModule
from backend.orm.subject import Subject
from backend.exceptions import ForbiddenError, NotFoundError

logger = logging.getLogger(__name__)

_explanation_cache: Dict[str, str] = {}
CACHE_MAX_SIZE = 100


def _get_cache_key(content_id: int, explanation_type: str) -> str:
    """Generate cache key for explanation"""
    return f"explain:{content_id}:{explanation_type}"


def _cache_get(key: str) -> Optional[str]:
    """Get from cache"""
    return _explanation_cache.get(key)


def _cache_set(key: str, value: str) -> None:
    """Set in cache with LRU-like eviction"""
    global _explanation_cache
    if len(_explanation_cache) >= CACHE_MAX_SIZE:
        oldest = next(iter(_explanation_cache))
        del _explanation_cache[oldest]
    _explanation_cache[key] = value


async def _call_llm(prompt: str, system_prompt: str = None) -> str:
    """
    Call Gemini LLM.
    
    Wrapper for async LLM call with proper error handling.
    """
    import google.generativeai as genai
    
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"
        
        response = await model.generate_content_async(full_prompt)
        return response.text
        
    except Exception as e:
        logger.error(f"[LLM] Generation error: {e}")
        raise


async def get_content_with_context(
    db: AsyncSession,
    content_id: int,
    module_id: int
) -> Dict[str, Any]:
    """
    Get content with full context (subject, module info).
    
    Returns dict with subject_name, module_title, content_title, content_text
    """
    content_result = await db.execute(
        select(LearnContent).where(
            LearnContent.id == content_id,
            LearnContent.module_id == module_id
        )
    )
    content = content_result.scalar_one_or_none()
    
    is_case = False
    if not content:
        case_result = await db.execute(
            select(CaseContent).where(
                CaseContent.id == content_id,
                CaseContent.module_id == module_id
            )
        )
        content = case_result.scalar_one_or_none()
        is_case = True
    
    if not content:
        raise NotFoundError("Content not found")
    
    module_result = await db.execute(
        select(ContentModule).where(ContentModule.id == module_id)
    )
    module = module_result.scalar_one_or_none()
    
    if not module:
        raise NotFoundError("Module not found")
    
    subject_result = await db.execute(
        select(Subject).where(Subject.id == module.subject_id)
    )
    subject = subject_result.scalar_one_or_none()
    
    if not subject:
        raise NotFoundError("Subject not found")
    
    if is_case:
        content_title = content.case_name if hasattr(content, 'case_name') else content.title
        content_text = ""
        if hasattr(content, 'summary') and content.summary:
            content_text += f"Summary:\n{content.summary}\n\n"
        if hasattr(content, 'facts') and content.facts:
            content_text += f"Facts:\n{content.facts}\n\n"
        if hasattr(content, 'issues') and content.issues:
            content_text += f"Issues:\n{content.issues}\n\n"
        if hasattr(content, 'held') and content.held:
            content_text += f"Held:\n{content.held}\n\n"
        if hasattr(content, 'significance') and content.significance:
            content_text += f"Significance:\n{content.significance}"
    else:
        content_title = content.title
        content_text = content.body if hasattr(content, 'body') else ""
    
    return {
        "subject_name": subject.title,
        "module_title": module.title,
        "content_title": content_title,
        "content_text": content_text,
        "is_case": is_case
    }


async def explain_content(
    *,
    db: AsyncSession,
    user_id: int,
    subject_id: int,
    module_id: int,
    content_id: int,
    explanation_type: str = "simple",
    question: Optional[str] = None,
    use_cache: bool = True
) -> Dict[str, Any]:
    """
    Generate explanation for curriculum content.
    
    Phase 10.2: Tutor Explanation Engine
    
    This service:
    1. Resolves & validates context
    2. Enforces scope guards on optional question
    3. Builds appropriate prompt
    4. Generates response (with caching)
    
    Args:
        db: Database session
        user_id: Current user ID
        subject_id: Subject ID
        module_id: Module ID
        content_id: Content ID to explain
        explanation_type: Type of explanation (simple, exam_oriented, summary, detailed, example)
        question: Optional specific question about the content
        use_cache: Whether to use cached responses
    
    Returns:
        Dict with content_id, explanation_type, explanation, and context
    """
    logger.info(f"[Explain] user={user_id}, content={content_id}, type={explanation_type}")
    
    context = await resolve_ai_context(
        db,
        user_id=user_id,
        subject_id=subject_id,
        module_id=module_id,
        content_id=content_id
    )
    
    if question:
        enforce_scope(question, context.subject_title)
    
    cache_key = _get_cache_key(content_id, explanation_type)
    if use_cache and not question:
        cached = _cache_get(cache_key)
        if cached:
            logger.info(f"[Explain] Cache hit for {cache_key}")
            return {
                "content_id": content_id,
                "explanation_type": explanation_type,
                "explanation": cached,
                "from_cache": True,
                "context": context.to_dict()
            }
    
    content_data = await get_content_with_context(db, content_id, module_id)
    
    if question:
        prompt = build_question_answer_prompt(
            question=question,
            subject_name=content_data["subject_name"],
            module_title=content_data["module_title"],
            content_title=content_data["content_title"],
            content_text=content_data["content_text"]
        )
    else:
        prompt = build_explanation_prompt(
            explanation_type=explanation_type,
            subject_name=content_data["subject_name"],
            module_title=content_data["module_title"],
            content_title=content_data["content_title"],
            content_text=content_data["content_text"]
        )
    
    try:
        explanation = await _call_llm(prompt)
    except Exception as e:
        logger.error(f"[Explain] LLM error: {e}")
        raise
    
    if not question and use_cache:
        _cache_set(cache_key, explanation)
        logger.info(f"[Explain] Cached response for {cache_key}")
    
    return {
        "content_id": content_id,
        "explanation_type": explanation_type,
        "explanation": explanation,
        "from_cache": False,
        "context": context.to_dict()
    }


async def ask_about_content(
    *,
    db: AsyncSession,
    user_id: int,
    subject_id: int,
    module_id: int,
    content_id: int,
    question: str
) -> Dict[str, Any]:
    """
    Answer a specific question about curriculum content.
    
    Convenience wrapper around explain_content with a question.
    """
    return await explain_content(
        db=db,
        user_id=user_id,
        subject_id=subject_id,
        module_id=module_id,
        content_id=content_id,
        explanation_type="simple",
        question=question,
        use_cache=False
    )


def get_available_explanation_types() -> list:
    """Get list of available explanation types with descriptions"""
    return [
        {"type": ExplanationType.SIMPLE.value, "name": "Simple", "description": "Easy to understand explanation"},
        {"type": ExplanationType.EXAM.value, "name": "Exam-Oriented", "description": "Structured like an exam answer"},
        {"type": ExplanationType.SUMMARY.value, "name": "Summary", "description": "Concise bullet points"},
        {"type": ExplanationType.DETAILED.value, "name": "Detailed", "description": "Comprehensive explanation"},
        {"type": ExplanationType.EXAMPLE.value, "name": "With Examples", "description": "Explained through examples"}
    ]


def clear_explanation_cache() -> int:
    """Clear the explanation cache. Returns number of items cleared."""
    global _explanation_cache
    count = len(_explanation_cache)
    _explanation_cache = {}
    return count
