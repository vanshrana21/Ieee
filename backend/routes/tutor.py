"""
backend/routes/tutor.py
Phase 10.2: Tutor Explanation API Endpoints

API endpoints for the Tutor Explanation Engine.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from typing import Optional, List

from backend.database import get_db
from backend.orm.user import User
from backend.routes.auth import get_current_user
from backend.ai.service import (
    explain_content,
    ask_about_content,
    get_available_explanation_types
)
from backend.ai.prompts import ExplanationType
from backend.exceptions import ForbiddenError, ScopeViolationError, NotFoundError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tutor", tags=["tutor"])


class TutorExplainRequest(BaseModel):
    """Request for content explanation"""
    subject_id: int = Field(..., description="Subject ID")
    module_id: int = Field(..., description="Module ID")
    content_id: int = Field(..., description="Content ID to explain")
    type: str = Field(
        default="simple",
        description="Explanation type: simple, exam_oriented, summary, detailed, example"
    )
    question: Optional[str] = Field(
        None,
        max_length=500,
        description="Optional specific question about the content"
    )


class TutorExplainResponse(BaseModel):
    """Response from tutor explanation"""
    content_id: int
    explanation_type: str
    explanation: str
    from_cache: bool = False
    context: dict


class TutorAskRequest(BaseModel):
    """Request for asking a question about content"""
    subject_id: int
    module_id: int
    content_id: int
    question: str = Field(..., min_length=3, max_length=500)


class ExplanationTypeInfo(BaseModel):
    """Info about an explanation type"""
    type: str
    name: str
    description: str


@router.post("/explain", response_model=TutorExplainResponse)
async def tutor_explain(
    payload: TutorExplainRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get AI explanation of curriculum content.
    
    Phase 10.2 Endpoint - Tutor Explanation Engine
    
    This endpoint:
    1. Validates context (subject/module/content chain)
    2. Enforces scope guards
    3. Generates explanation using specified style
    4. Caches responses for efficiency
    
    Explanation Types:
    - simple: Easy to understand explanation
    - exam_oriented: Structured like an exam answer
    - summary: Concise bullet points
    - detailed: Comprehensive explanation
    - example: Explained through examples
    """
    logger.info(f"[Tutor] Explain request from {current_user.email}: content={payload.content_id}, type={payload.type}")
    
    valid_types = [e.value for e in ExplanationType]
    if payload.type not in valid_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid explanation type. Valid types: {valid_types}"
        )
    
    try:
        result = await explain_content(
            db=db,
            user_id=current_user.id,
            subject_id=payload.subject_id,
            module_id=payload.module_id,
            content_id=payload.content_id,
            explanation_type=payload.type,
            question=payload.question
        )
        
        return TutorExplainResponse(
            content_id=result["content_id"],
            explanation_type=result["explanation_type"],
            explanation=result["explanation"],
            from_cache=result.get("from_cache", False),
            context=result["context"]
        )
        
    except ForbiddenError as e:
        logger.warning(f"[Tutor] Forbidden: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=e.message
        )
    except ScopeViolationError as e:
        logger.info(f"[Tutor] Scope violation: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.message
        )
    except NotFoundError as e:
        logger.warning(f"[Tutor] Not found: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message
        )
    except Exception as e:
        logger.error(f"[Tutor] Explanation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate explanation. Please try again."
        )


@router.post("/ask", response_model=TutorExplainResponse)
async def tutor_ask(
    payload: TutorAskRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Ask a specific question about curriculum content.
    
    The question must be about the specified content.
    Out-of-scope questions will be rejected.
    """
    logger.info(f"[Tutor] Ask request from {current_user.email}: {payload.question[:50]}...")
    
    try:
        result = await ask_about_content(
            db=db,
            user_id=current_user.id,
            subject_id=payload.subject_id,
            module_id=payload.module_id,
            content_id=payload.content_id,
            question=payload.question
        )
        
        return TutorExplainResponse(
            content_id=result["content_id"],
            explanation_type="answer",
            explanation=result["explanation"],
            from_cache=False,
            context=result["context"]
        )
        
    except ForbiddenError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=e.message
        )
    except ScopeViolationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.message
        )
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message
        )
    except Exception as e:
        logger.error(f"[Tutor] Ask error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to answer question. Please try again."
        )


@router.get("/explanation-types", response_model=List[ExplanationTypeInfo])
async def get_explanation_types(
    current_user: User = Depends(get_current_user)
):
    """
    Get available explanation types.
    
    Returns list of explanation types with names and descriptions.
    """
    return get_available_explanation_types()


@router.get("/health")
async def tutor_health():
    """Health check for tutor service"""
    return {
        "status": "healthy",
        "service": "tutor-explanation-engine",
        "version": "10.2"
    }
