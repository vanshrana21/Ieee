"""
backend/routes/feedback.py
Phase 10.3: Practice Answer Feedback API Endpoints

Post-attempt feedback only. AI explains AFTER submission.

STRICT TIMING RULES:
- No explanation before submission
- No hints during attempt
- No partial feedback mid-answer
- Feedback is post-evaluation ONLY
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from typing import Optional, Dict, List

from backend.database import get_db
from backend.orm.user import User
from backend.routes.auth import get_current_user
from backend.ai.feedback import (
    generate_attempt_feedback,
    get_mcq_option_analysis,
    clear_feedback_cache
)
from backend.exceptions import ForbiddenError, NotFoundError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


class FeedbackResponse(BaseModel):
    """Response from feedback generation"""
    attempt_id: int
    feedback: str
    from_cache: bool = False
    is_correct: Optional[bool] = None
    question_type: str
    correct_answer: Optional[str] = None
    student_answer: Optional[str] = None
    subject: Optional[str] = None
    module: Optional[str] = None
    question_text: Optional[str] = None


class MCQOptionDetail(BaseModel):
    """Detail for a single MCQ option"""
    text: Optional[str] = None
    is_correct: bool = False
    was_selected: bool = False


class MCQAnalysisResponse(BaseModel):
    """Response from MCQ option analysis"""
    attempt_id: int
    question_id: int
    question_text: str
    options: Dict[str, MCQOptionDetail]
    correct_option: str
    selected_option: Optional[str] = None
    is_correct: Optional[bool] = None
    explanation: Optional[str] = None


class FeedbackHealthResponse(BaseModel):
    """Health check response"""
    status: str
    service: str
    version: str
    rules: List[str]


@router.get("/attempt/{attempt_id}", response_model=FeedbackResponse)
async def get_attempt_feedback(
    attempt_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get AI-generated feedback for a submitted attempt.
    
    Phase 10.3 Endpoint - Post-Attempt Feedback
    
    CRITICAL RULES:
    1. Only works AFTER submission (attempt must exist)
    2. Does NOT re-evaluate correctness (backend verdict is final)
    3. Explains WHY the answer is correct/incorrect
    4. Uses ONLY curriculum data (no new laws/cases)
    
    The feedback includes:
    - Why the correct answer is correct
    - Analysis of the student's answer
    - Key takeaways for learning
    
    This endpoint CANNOT be called before submission.
    """
    logger.info(f"[Feedback API] Request from {current_user.email} for attempt={attempt_id}")
    
    try:
        result = await generate_attempt_feedback(
            db=db,
            user_id=current_user.id,
            attempt_id=attempt_id,
            use_cache=True
        )
        
        return FeedbackResponse(
            attempt_id=result["attempt_id"],
            feedback=result["feedback"],
            from_cache=result.get("from_cache", False),
            is_correct=result.get("is_correct"),
            question_type=result.get("question_type", "unknown"),
            correct_answer=result.get("correct_answer"),
            student_answer=result.get("student_answer"),
            subject=result.get("subject"),
            module=result.get("module"),
            question_text=result.get("question_text")
        )
        
    except NotFoundError as e:
        logger.warning(f"[Feedback API] Not found: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message
        )
    except ForbiddenError as e:
        logger.warning(f"[Feedback API] Forbidden: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=e.message
        )
    except Exception as e:
        logger.error(f"[Feedback API] Error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate feedback. Please try again."
        )


@router.get("/attempt/{attempt_id}/mcq-analysis", response_model=MCQAnalysisResponse)
async def get_mcq_analysis(
    attempt_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed MCQ option analysis for a submitted attempt.
    
    Shows which options were correct/incorrect and which was selected.
    Only available for MCQ questions AFTER submission.
    """
    logger.info(f"[Feedback API] MCQ analysis from {current_user.email} for attempt={attempt_id}")
    
    try:
        result = await get_mcq_option_analysis(
            db=db,
            user_id=current_user.id,
            attempt_id=attempt_id
        )
        
        options = {}
        for key, value in result["options"].items():
            options[key] = MCQOptionDetail(
                text=value.get("text"),
                is_correct=value.get("is_correct", False),
                was_selected=value.get("was_selected", False)
            )
        
        return MCQAnalysisResponse(
            attempt_id=result["attempt_id"],
            question_id=result["question_id"],
            question_text=result["question_text"],
            options=options,
            correct_option=result["correct_option"],
            selected_option=result.get("selected_option"),
            is_correct=result.get("is_correct"),
            explanation=result.get("explanation")
        )
        
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message
        )
    except ForbiddenError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=e.message
        )
    except Exception as e:
        logger.error(f"[Feedback API] MCQ analysis error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to analyze MCQ options."
        )


@router.get("/health", response_model=FeedbackHealthResponse)
async def feedback_health():
    """
    Health check for feedback service.
    
    Also returns the Phase 10.3 rules for documentation.
    """
    return FeedbackHealthResponse(
        status="healthy",
        service="practice-feedback-engine",
        version="10.3",
        rules=[
            "Feedback only after submission",
            "No hints during attempt",
            "Backend correctness is final",
            "No new laws/cases introduced",
            "AI explains, never judges"
        ]
    )


@router.post("/cache/clear")
async def clear_cache(
    current_user: User = Depends(get_current_user)
):
    """
    Clear the feedback cache.
    
    Admin/debug endpoint to force regeneration of all feedback.
    """
    count = clear_feedback_cache()
    logger.info(f"[Feedback API] Cache cleared by {current_user.email}: {count} items")
    return {
        "message": f"Cleared {count} cached feedback items",
        "cleared_count": count
    }
