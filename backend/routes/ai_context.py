"""
backend/routes/ai_context.py
Phase 10.1: Context-Bound AI API Routes

API endpoints that enforce strict context binding for AI calls.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from typing import Optional

from backend.database import get_db
from backend.orm.user import User
from backend.routes.auth import get_current_user
from backend.ai.context import resolve_ai_context, AIContext
from backend.ai.guards import enforce_scope, ScopeGuard
from backend.ai.prompts import build_scoped_prompt, get_refusal_message
from backend.exceptions import ForbiddenError, ScopeViolationError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai-context"])


class ScopedQuestionRequest(BaseModel):
    """Request with mandatory context binding"""
    question: str = Field(..., min_length=3, max_length=2000)
    subject_id: int = Field(..., description="Current subject ID")
    module_id: Optional[int] = Field(None, description="Current module ID")
    content_id: Optional[int] = Field(None, description="Current content ID")


class ScopedQuestionResponse(BaseModel):
    """Response from scoped AI query"""
    answer: str
    scope: dict
    in_scope: bool = True
    suggestions: list = []


class ContextValidationRequest(BaseModel):
    """Request to validate context only"""
    subject_id: int
    module_id: Optional[int] = None
    content_id: Optional[int] = None


class ContextValidationResponse(BaseModel):
    """Response from context validation"""
    valid: bool
    context: Optional[dict] = None
    error: Optional[str] = None


@router.post("/ask-scoped", response_model=ScopedQuestionResponse)
async def ask_scoped_question(
    request: ScopedQuestionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Ask AI a question with strict context binding.
    
    PHASE 10.1 ENDPOINT - Context-Bound AI
    
    This endpoint:
    1. Validates context (subject/module/content belong together)
    2. Enforces scope guards (rejects out-of-scope questions)
    3. Builds scoped system prompt
    4. Generates response within scope
    
    Frontend CANNOT bypass context validation.
    """
    logger.info(f"[Scoped AI] Question from {current_user.email}: {request.question[:50]}...")
    
    try:
        context = await resolve_ai_context(
            db,
            user_id=current_user.id,
            subject_id=request.subject_id,
            module_id=request.module_id,
            content_id=request.content_id
        )
    except ForbiddenError as e:
        logger.warning(f"[Scoped AI] Context validation failed: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=e.message
        )
    
    try:
        enforce_scope(request.question, context.subject_title)
    except ScopeViolationError as e:
        logger.info(f"[Scoped AI] Scope violation: {e.message}")
        return ScopedQuestionResponse(
            answer=e.message,
            scope=context.to_dict(),
            in_scope=False,
            suggestions=[
                f"What is {context.subject_title} about?",
                f"Explain the key concepts in {context.content_title or context.subject_title}"
            ]
        )
    
    system_prompt = build_scoped_prompt(context)
    
    try:
        import google.generativeai as genai
        model = genai.GenerativeModel("gemini-1.5-flash")
        
        full_prompt = f"{system_prompt}\n\nStudent Question: {request.question}"
        response = await model.generate_content_async(full_prompt)
        answer = response.text
        
    except Exception as e:
        logger.error(f"[Scoped AI] Generation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AI service temporarily unavailable"
        )
    
    suggestions = []
    if context.content_title:
        suggestions.append(f"Can you explain {context.content_title} in simpler terms?")
        suggestions.append(f"Give me an example of {context.content_title}")
    
    return ScopedQuestionResponse(
        answer=answer,
        scope=context.to_dict(),
        in_scope=True,
        suggestions=suggestions
    )


@router.post("/validate-context", response_model=ContextValidationResponse)
async def validate_context(
    request: ContextValidationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Validate context without asking a question.
    
    Useful for frontend to check if navigation is valid
    before loading AI chat interface.
    """
    try:
        context = await resolve_ai_context(
            db,
            user_id=current_user.id,
            subject_id=request.subject_id,
            module_id=request.module_id,
            content_id=request.content_id
        )
        
        return ContextValidationResponse(
            valid=True,
            context=context.to_dict()
        )
        
    except ForbiddenError as e:
        return ContextValidationResponse(
            valid=False,
            error=e.message
        )


@router.get("/current-scope")
async def get_current_scope(
    subject_id: int,
    module_id: Optional[int] = None,
    content_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get human-readable description of current AI scope.
    
    Returns what the AI can and cannot answer about.
    """
    try:
        context = await resolve_ai_context(
            db,
            user_id=current_user.id,
            subject_id=subject_id,
            module_id=module_id,
            content_id=content_id
        )
        
        return {
            "scope": context.get_scope_description(),
            "subject": context.subject_title,
            "module": context.module_title,
            "topic": context.content_title,
            "can_answer": [
                f"Questions about {context.subject_title}",
                f"Explanations of concepts in {context.module_title or context.subject_title}",
                "Examples and case references within curriculum"
            ],
            "cannot_answer": [
                "Questions about other subjects",
                "Legal advice for real situations",
                "Topics outside your curriculum"
            ]
        }
        
    except ForbiddenError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=e.message
        )


@router.post("/check-question")
async def check_question_scope(
    question: str,
    subject_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Pre-check if a question is in scope without generating a response.
    
    Useful for frontend to show warning before submitting.
    """
    try:
        context = await resolve_ai_context(
            db,
            user_id=current_user.id,
            subject_id=subject_id
        )
        
        forbidden = ScopeGuard.check_forbidden_patterns(question)
        escape = ScopeGuard.check_escape_attempts(question)
        
        if forbidden or escape:
            return {
                "in_scope": False,
                "reason": "This question appears to be outside your current study scope.",
                "suggestion": f"Try asking about {context.subject_title} instead."
            }
        
        return {
            "in_scope": True,
            "reason": None,
            "suggestion": None
        }
        
    except ForbiddenError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=e.message
        )
