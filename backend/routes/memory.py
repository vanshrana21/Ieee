"""
backend/routes/memory.py
Phase 10.5: Tutor Memory API Endpoints

Backend-owned memory. AI summarizes, never decides.

CORE PRINCIPLE:
The backend remembers. AI only summarizes what the backend already knows.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List

from backend.database import get_db
from backend.orm.user import User
from backend.routes.auth import get_current_user
from backend.ai.memory import (
    compute_tutor_memory,
    build_memory_context_for_ai,
    get_memory_phrase,
    get_memory_summary,
    TutorMemory
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/memory", tags=["memory"])


class TopicStruggleResponse(BaseModel):
    topic_tag: str
    topic_name: str
    incorrect_count: int
    total_attempts: int
    mastery_score: float
    struggle_ratio: float
    last_attempted: Optional[str] = None


class ConfusionPatternResponse(BaseModel):
    concept_a: str
    concept_b: str
    confusion_count: int
    description: str


class TutorMemoryResponse(BaseModel):
    user_id: int
    subject_id: int
    subject_name: str
    total_attempts: int
    correct_count: int
    incorrect_count: int
    accuracy_rate: float
    struggling_topics: List[TopicStruggleResponse]
    confusion_patterns: List[ConfusionPatternResponse]
    explanation_requests: int
    repeated_explanations: int
    strongest_topic: Optional[str] = None
    weakest_topic: Optional[str] = None
    last_activity: Optional[str] = None
    study_streak_days: int
    memory_computed_at: str


class MemoryContextResponse(BaseModel):
    memory: TutorMemoryResponse
    ai_context: str
    phrases: Dict[str, Optional[str]]


class MemoryPhraseRequest(BaseModel):
    subject_id: int
    phrase_type: str = Field(..., description="Type: struggle_acknowledgment, confusion_acknowledgment, progress_acknowledgment, strength_acknowledgment")
    topic: Optional[str] = None


class MemoryPhraseResponse(BaseModel):
    phrase_type: str
    phrase: Optional[str] = None
    available: bool


class MemoryHealthResponse(BaseModel):
    version: str
    service: str
    principle: str
    memory_is: List[str]
    ai_can: List[str]
    ai_cannot: List[str]
    phrase_types: List[str]


@router.get(
    "/{subject_id}",
    response_model=TutorMemoryResponse,
    summary="Get tutor memory for a subject"
)
async def get_tutor_memory(
    subject_id: int,
    lookback_days: int = 30,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get backend-computed tutor memory for a subject.
    
    Phase 10.5: Memory is computed by backend from:
    - practice_attempts
    - topic_mastery
    - subject_progress
    
    AI receives this as READ-ONLY data.
    """
    logger.info(f"[Memory API] Request: user={current_user.id}, subject={subject_id}")
    
    try:
        memory = await compute_tutor_memory(
            db=db,
            user_id=current_user.id,
            subject_id=subject_id,
            lookback_days=lookback_days
        )
        
        memory_dict = memory.to_dict()
        
        return TutorMemoryResponse(
            user_id=memory_dict["user_id"],
            subject_id=memory_dict["subject_id"],
            subject_name=memory_dict["subject_name"],
            total_attempts=memory_dict["total_attempts"],
            correct_count=memory_dict["correct_count"],
            incorrect_count=memory_dict["incorrect_count"],
            accuracy_rate=memory_dict["accuracy_rate"],
            struggling_topics=[TopicStruggleResponse(**t) for t in memory_dict["struggling_topics"]],
            confusion_patterns=[ConfusionPatternResponse(**c) for c in memory_dict["confusion_patterns"]],
            explanation_requests=memory_dict["explanation_requests"],
            repeated_explanations=memory_dict["repeated_explanations"],
            strongest_topic=memory_dict["strongest_topic"],
            weakest_topic=memory_dict["weakest_topic"],
            last_activity=memory_dict["last_activity"],
            study_streak_days=memory_dict["study_streak_days"],
            memory_computed_at=memory_dict["memory_computed_at"]
        )
        
    except Exception as e:
        logger.error(f"[Memory API] Error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to compute tutor memory"
        )


@router.get(
    "/{subject_id}/context",
    response_model=MemoryContextResponse,
    summary="Get memory with AI context"
)
async def get_memory_with_context(
    subject_id: int,
    lookback_days: int = 30,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get tutor memory with AI-ready context string.
    
    Phase 10.5: Returns:
    - Raw memory data
    - Formatted context string for AI
    - Available memory phrases
    
    AI uses the context to verbalize memory, but CANNOT modify it.
    """
    logger.info(f"[Memory API] Context request: user={current_user.id}, subject={subject_id}")
    
    try:
        memory = await compute_tutor_memory(
            db=db,
            user_id=current_user.id,
            subject_id=subject_id,
            lookback_days=lookback_days
        )
        
        ai_context = build_memory_context_for_ai(memory)
        
        phrases = {
            "struggle_acknowledgment": get_memory_phrase("struggle_acknowledgment", memory),
            "confusion_acknowledgment": get_memory_phrase("confusion_acknowledgment", memory),
            "progress_acknowledgment": get_memory_phrase("progress_acknowledgment", memory),
            "strength_acknowledgment": get_memory_phrase("strength_acknowledgment", memory)
        }
        
        memory_dict = memory.to_dict()
        
        return MemoryContextResponse(
            memory=TutorMemoryResponse(
                user_id=memory_dict["user_id"],
                subject_id=memory_dict["subject_id"],
                subject_name=memory_dict["subject_name"],
                total_attempts=memory_dict["total_attempts"],
                correct_count=memory_dict["correct_count"],
                incorrect_count=memory_dict["incorrect_count"],
                accuracy_rate=memory_dict["accuracy_rate"],
                struggling_topics=[TopicStruggleResponse(**t) for t in memory_dict["struggling_topics"]],
                confusion_patterns=[ConfusionPatternResponse(**c) for c in memory_dict["confusion_patterns"]],
                explanation_requests=memory_dict["explanation_requests"],
                repeated_explanations=memory_dict["repeated_explanations"],
                strongest_topic=memory_dict["strongest_topic"],
                weakest_topic=memory_dict["weakest_topic"],
                last_activity=memory_dict["last_activity"],
                study_streak_days=memory_dict["study_streak_days"],
                memory_computed_at=memory_dict["memory_computed_at"]
            ),
            ai_context=ai_context,
            phrases=phrases
        )
        
    except Exception as e:
        logger.error(f"[Memory API] Context error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate memory context"
        )


@router.post(
    "/phrase",
    response_model=MemoryPhraseResponse,
    summary="Get a memory-aware phrase"
)
async def get_phrase(
    payload: MemoryPhraseRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get a memory-aware phrase for AI to use.
    
    Phase 10.5: These are TEMPLATES for AI.
    AI uses these phrases to acknowledge history, not to infer or decide.
    
    Available phrase types:
    - struggle_acknowledgment: "Since {topic} has been challenging..."
    - confusion_acknowledgment: "You've sometimes mixed up X with Y..."
    - progress_acknowledgment: "You've been practicing consistently..."
    - strength_acknowledgment: "Building on your strength in {topic}..."
    """
    logger.info(f"[Memory API] Phrase request: type={payload.phrase_type}")
    
    try:
        memory = await compute_tutor_memory(
            db=db,
            user_id=current_user.id,
            subject_id=payload.subject_id
        )
        
        phrase = get_memory_phrase(
            phrase_type=payload.phrase_type,
            memory=memory,
            topic=payload.topic
        )
        
        return MemoryPhraseResponse(
            phrase_type=payload.phrase_type,
            phrase=phrase,
            available=phrase is not None
        )
        
    except Exception as e:
        logger.error(f"[Memory API] Phrase error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get memory phrase"
        )


@router.get(
    "/health",
    response_model=MemoryHealthResponse,
    summary="Health check and documentation"
)
async def memory_health():
    """
    Health check for tutor memory service.
    
    Returns Phase 10.5 rules:
    - What memory IS (summary of facts, subject-scoped)
    - What AI CAN do (acknowledge, reference)
    - What AI CANNOT do (infer, store, decide)
    """
    summary = get_memory_summary()
    return MemoryHealthResponse(**summary)
