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
