"""
backend/routes/tutor.py
Phase 4.1: Tutor Context Engine API

Provides curriculum-grounded context for AI Tutor.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

from backend.database import get_db
from backend.orm.user import User
from backend.routes.auth import get_current_user
from backend.services.tutor_context_service import assemble_context
from backend.schemas.tutor import TutorChatRequest, TutorChatResponse, AdaptiveTutorResponse
from backend.services.tutor_chat_service import process_tutor_chat
from backend.services.tutor_adaptive import process_adaptive_chat, get_remediation_pack

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tutor", tags=["tutor"])


class StudentInfo(BaseModel):
    course: Optional[str]
    semester: Optional[int]


class SubjectInfo(BaseModel):
    id: int
    title: str


class TopicMasteryInfo(BaseModel):
    topic_tag: str
    mastery_percent: float


class RecentActivityInfo(BaseModel):
    last_practice_days_ago: Optional[int]
    last_subject: Optional[str]


class StudyMapItem(BaseModel):
    module: str
    priority: str


class ConstraintsInfo(BaseModel):
    allowed_subjects_only: bool
    no_legal_advice: bool
    exam_oriented: bool


class TutorContext(BaseModel):
    student: StudentInfo
    active_subjects: List[SubjectInfo]
    weak_topics: List[TopicMasteryInfo]
    strong_topics: List[TopicMasteryInfo]
    recent_activity: RecentActivityInfo
    study_map_snapshot: List[StudyMapItem]
    constraints: ConstraintsInfo
    error: Optional[str] = None


class TutorContextResponse(BaseModel):
    success: bool
    context: TutorContext


@router.get("/context", response_model=TutorContextResponse)
async def get_tutor_context(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get curriculum-grounded context for AI Tutor.
    
    Phase 4.1: Tutor Context Engine
    
    Returns deterministic context based on:
    - User's course and semester
    - Active subjects from curriculum
    - Topic mastery (weak/strong topics)
    - Recent practice activity
    - Study map priorities
    
    Rules:
    - Same user state → same context
    - No hallucinated topics
    - Works with empty mastery tables
    - Zero AI calls
    """
    logger.info(f"Tutor context request: user_id={current_user.id}")
    
    try:
        context = await assemble_context(current_user.id, db)
        
        has_error = "error" in context
        
        return TutorContextResponse(
            success=not has_error,
            context=TutorContext(**context)
        )
        
    except Exception as e:
        logger.error(f"Failed to assemble tutor context: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to assemble tutor context"
        )


@router.post("/chat", response_model=TutorChatResponse)
async def tutor_chat(
    request: TutorChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Curriculum-aware AI Tutor Chat.
    
    Phase 4.2 & 4.3: Curriculum-Aware & Adaptive AI Tutor Chat
    """
    logger.info(f"Tutor chat request: user_id={current_user.id}, mode={request.mode}, question='{request.question[:50]}...'")
    
    try:
        if request.mode in ["adaptive", "concise", "standard", "scaffolded"]:
            adaptive_result = await process_adaptive_chat(current_user.id, request.question, request.mode, db)
            
            # If error in adaptive processing
            if "error" in adaptive_result and not adaptive_result.get("answer"):
                return TutorChatResponse(
                    answer=adaptive_result.get("fallback", "Error processing request"),
                    confidence="Low",
                    linked_topics=[],
                    why_this_answer=adaptive_result.get("error", "Unknown error")
                )
            
            # Map adaptive result to TutorChatResponse format
            return TutorChatResponse(
                answer=adaptive_result.get("answer", ""),
                confidence=str(adaptive_result.get("confidence_score", "Medium")),
                linked_topics=adaptive_result.get("linked_topics", []),
                why_this_answer=adaptive_result.get("why_this_help", "Based on your curriculum and mastery"),
                adaptive=AdaptiveTutorResponse(**adaptive_result)
            )
        else:
            # Fallback to Phase 4.2 logic for other modes if any
            response_data = await process_tutor_chat(current_user.id, request.question, db)
            return TutorChatResponse(**response_data)
            
    except Exception as e:
        logger.error(f"Tutor chat error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Tutor chat service error: {str(e)}"
        )

@router.get("/remediation/{topic_tag}", response_model=TutorChatResponse)
async def get_remediation(
    topic_tag: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get a remediation pack for a specific topic.
    Phase 4.3: Weakness-Aware Tutor remediation.
    """
    logger.info(f"Remediation request: user_id={current_user.id}, topic_tag={topic_tag}")
    
    try:
        result = await get_remediation_pack(current_user.id, topic_tag, db)
        return TutorChatResponse(
            answer=result.get("answer", ""),
            confidence=str(result.get("confidence_score", "High")),
            linked_topics=[topic_tag],
            why_this_answer=f"Remediation pack for {topic_tag}",
            adaptive=AdaptiveTutorResponse(**result)
        )
    except Exception as e:
        logger.error(f"Remediation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate remediation pack: {str(e)}"
        )
