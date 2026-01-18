"""
backend/routes/adaptive.py
Phase 10.4: Adaptive Hinting API Endpoints

Backend-controlled adaptation. AI adjusts tone, not flow.

CORE PRINCIPLE:
Rules first. AI second.
Backend detects patterns → AI phrases guidance.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List

from backend.database import get_db
from backend.orm.user import User
from backend.routes.auth import get_current_user
from backend.ai.adaptive import (
    compute_adaptation_signals,
    select_adaptation_style,
    get_adaptive_feedback,
    get_hint_for_struggling_student,
    get_adaptation_summary,
    DifficultyLevel,
    AdaptationStyle
)
from backend.exceptions import NotFoundError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/adaptive", tags=["adaptive"])


class AdaptationSignalsResponse(BaseModel):
    """Response containing backend-computed adaptation signals"""
    difficulty_level: str
    attempt_count: int
    topic_mastery: str
    recent_incorrect_streak: int
    subject_completion: float
    needs_reinforcement: bool
    recommended_style: str


class AdaptiveHintRequest(BaseModel):
    """Request for adaptive hint"""
    subject_id: int = Field(..., description="Subject ID")
    module_id: int = Field(..., description="Module ID")
    question_text: str = Field(..., description="Question being attempted")
    topic_tag: Optional[str] = Field(None, description="Optional topic tag")


class AdaptiveHintResponse(BaseModel):
    """Response with adaptive hint"""
    hint_available: bool
    hint_style: str
    message: str
    signals: Dict[str, Any]


class AdaptiveExplainRequest(BaseModel):
    """Request for adaptive explanation"""
    subject_id: int
    module_id: int
    content_text: str = Field(..., max_length=5000)
    topic_tag: Optional[str] = None
    base_prompt: str = Field(..., max_length=2000)


class AdaptiveExplainResponse(BaseModel):
    """Response with adapted prompt"""
    adapted_prompt: str
    signals: Dict[str, Any]
    style: str
    opener: str


class AdaptationSummaryResponse(BaseModel):
    """Health check and documentation response"""
    version: str
    service: str
    rules: Dict[str, List[str]]
    difficulty_levels: List[str]
    adaptation_styles: List[str]


@router.get(
    "/signals/{subject_id}",
    response_model=AdaptationSignalsResponse,
    summary="Get adaptation signals for a subject"
)
async def get_signals(
    subject_id: int,
    module_id: Optional[int] = None,
    topic_tag: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get backend-computed adaptation signals.
    
    Phase 10.4: Backend detects patterns, returns signals.
    
    These signals determine:
    - How confused the student is (difficulty_level)
    - How many attempts they've made
    - Whether they need reinforcement
    
    AI uses these to adjust TONE, not CURRICULUM.
    """
    logger.info(f"[Adaptive API] Signals request: user={current_user.id}, subject={subject_id}")
    
    try:
        signals = await compute_adaptation_signals(
            db=db,
            user_id=current_user.id,
            subject_id=subject_id,
            topic_tag=topic_tag,
            module_id=module_id
        )
        
        style = select_adaptation_style(signals)
        
        return AdaptationSignalsResponse(
            difficulty_level=signals.difficulty_level.value,
            attempt_count=signals.attempt_count,
            topic_mastery=signals.topic_mastery,
            recent_incorrect_streak=signals.recent_incorrect_streak,
            subject_completion=signals.subject_completion,
            needs_reinforcement=signals.needs_reinforcement,
            recommended_style=style.value
        )
        
    except Exception as e:
        logger.error(f"[Adaptive API] Error computing signals: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to compute adaptation signals"
        )


@router.post(
    "/hint",
    response_model=AdaptiveHintResponse,
    summary="Get adaptive hint for struggling student"
)
async def get_hint(
    payload: AdaptiveHintRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get a hint for a struggling student.
    
    Phase 10.4 Rules:
    - Hint is phrased by AI
    - Hint CANNOT reveal the answer
    - Hint CANNOT skip the question
    - Hint CANNOT suggest moving on
    
    Only provides encouragement and conceptual guidance.
    
    Phase 11.2: Graceful empty state handling
    - Returns neutral guidance when no history available
    - Never returns error for missing context
    """
    logger.info(f"[Adaptive API] Hint request: user={current_user.id}, subject={payload.subject_id}")
    
    try:
        result = await get_hint_for_struggling_student(
            db=db,
            user_id=current_user.id,
            subject_id=payload.subject_id,
            module_id=payload.module_id,
            question_text=payload.question_text,
            topic_tag=payload.topic_tag
        )
        
        return AdaptiveHintResponse(
            hint_available=result["hint_available"],
            hint_style=result["hint_style"],
            message=result["message"],
            signals=result["signals"]
        )
        
    except Exception as e:
        logger.warning(f"[Adaptive API] Hint generation failed, returning neutral: {e}")
        return AdaptiveHintResponse(
            hint_available=True,
            hint_style="neutral",
            message="Take your time with this question. Focus on the key concepts and consider each option carefully.",
            signals={
                "has_history": False,
                "fallback_reason": "neutral_guidance"
            }
        )


@router.post(
    "/explain",
    response_model=AdaptiveExplainResponse,
    summary="Get adaptively-styled explanation prompt"
)
async def get_adaptive_explanation(
    payload: AdaptiveExplainRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get an adaptively-styled explanation prompt.
    
    Phase 10.4: Combines base prompt with adaptation modifiers.
    
    The adaptation modifies HOW content is explained:
    - Simpler language for confused students
    - More examples for those who need them
    - Exam-focused for advanced students
    
    The adaptation does NOT change WHAT is taught.
    
    Phase 11.2: Graceful empty state handling
    - Returns basic style when no history available
    - AI never invents context
    """
    logger.info(f"[Adaptive API] Explain request: user={current_user.id}, subject={payload.subject_id}")
    
    try:
        result = await get_adaptive_feedback(
            db=db,
            user_id=current_user.id,
            subject_id=payload.subject_id,
            module_id=payload.module_id,
            content_text=payload.content_text,
            topic_tag=payload.topic_tag,
            base_prompt=payload.base_prompt
        )
        
        return AdaptiveExplainResponse(
            adapted_prompt=result["adapted_prompt"],
            signals=result["signals"],
            style=result["style"],
            opener=result["opener"]
        )
        
    except Exception as e:
        logger.warning(f"[Adaptive API] Adaptive explanation failed, returning basic: {e}")
        return AdaptiveExplainResponse(
            adapted_prompt=payload.base_prompt,
            signals={
                "has_history": False,
                "fallback_reason": "basic_style"
            },
            style="basic",
            opener="Let me explain this concept."
        )


@router.get(
    "/styles",
    summary="Get available adaptation styles"
)
async def get_styles():
    """
    Get available adaptation styles and their descriptions.
    
    These are the ways AI can adjust its explanations:
    - basic: Simple, clear language
    - simplified: Broken down into smallest steps
    - detailed: Comprehensive with all points
    - exam_focused: Structured like an exam answer
    - example_heavy: Lead with practical examples
    """
    return {
        "styles": [
            {"id": "basic", "name": "Basic", "description": "Simple, clear language with one concept at a time"},
            {"id": "simplified", "name": "Simplified", "description": "Broken down into smallest possible steps"},
            {"id": "detailed", "name": "Detailed", "description": "Comprehensive explanation with all sub-points"},
            {"id": "exam_focused", "name": "Exam-Focused", "description": "Structured like an exam answer"},
            {"id": "example_heavy", "name": "Example-Heavy", "description": "Lead with practical examples"}
        ],
        "difficulty_levels": [
            {"id": "high_confusion", "name": "High Confusion", "triggers": "mastery < 0.3 or 3+ incorrect streak"},
            {"id": "moderate_confusion", "name": "Moderate Confusion", "triggers": "mastery < 0.5 or 2+ incorrect streak"},
            {"id": "low_confusion", "name": "Low Confusion", "triggers": "mastery < 0.7"},
            {"id": "mastered", "name": "Mastered", "triggers": "mastery >= 0.7"}
        ]
    }


@router.get(
    "/health",
    response_model=AdaptationSummaryResponse,
    summary="Health check and documentation"
)
async def adaptive_health():
    """
    Health check for adaptive hinting service.
    
    Returns the Phase 10.4 rules for documentation:
    - What AI CAN adapt (tone, examples, depth)
    - What AI CANNOT do (advance, skip, unlock)
    """
    return get_adaptation_summary()
