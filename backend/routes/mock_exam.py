"""
backend/routes/mock_exam.py
Phase 7.2: Timed Mock Exam API Routes

Provides endpoints for running timed mock exams:
- Start exam session
- Save answers
- Submit exam
- Get session state (for recovery)
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List

from backend.database import get_db
from backend.orm.user import User
from backend.routes.auth import get_current_user
from backend.services.mock_exam_service import (
    start_exam_session,
    get_session_state,
    save_answer,
    toggle_flag,
    submit_exam,
    get_submission_summary,
    get_user_exam_history,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mock-exam", tags=["mock-exam"])


class StartExamRequest(BaseModel):
    exam_type: str = Field(default="mock_exam", description="Type of exam")
    subject_id: Optional[int] = Field(default=None, description="Subject filter")


class SaveAnswerRequest(BaseModel):
    answer_id: int = Field(..., description="Answer record ID")
    answer_text: str = Field(..., description="User's answer text")
    time_spent_seconds: int = Field(default=0, description="Time spent on this question")


class ToggleFlagRequest(BaseModel):
    answer_id: int = Field(..., description="Answer record ID")


@router.post("/start")
async def start_exam(
    request: StartExamRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Start a new mock exam session.
    
    - Generates blueprint based on exam type
    - Creates session with timer
    - Returns all questions and initial state
    
    If user has an active (in-progress) session, returns that instead.
    If active session is expired, auto-submits it first.
    """
    try:
        result = await start_exam_session(
            user_id=current_user.id,
            exam_type=request.exam_type,
            db=db,
            subject_id=request.subject_id
        )
        
        if "error" in result:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["error"]
            )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start exam: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start exam session"
        )


@router.get("/session/{session_id}")
async def get_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get current session state.
    
    Used for:
    - Session recovery after page refresh
    - Syncing timer with server
    - Getting updated progress
    
    Auto-submits if session has expired.
    """
    try:
        result = await get_session_state(session_id, db)
        
        if "error" in result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=result["error"]
            )
        
        if result.get("session", {}).get("user_id") != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get session state"
        )


@router.get("/active")
async def get_active_session(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Check if user has an active exam session.
    
    Returns session state if active, or null if no active session.
    Used on page load to restore in-progress exams.
    """
    from sqlalchemy import select, and_
    from backend.orm.exam_session import ExamSession, ExamSessionStatus
    
    try:
        stmt = select(ExamSession).where(
            and_(
                ExamSession.user_id == current_user.id,
                ExamSession.status == ExamSessionStatus.IN_PROGRESS
            )
        )
        result = await db.execute(stmt)
        session = result.scalar_one_or_none()
        
        if not session:
            return {"active_session": None}
        
        state = await get_session_state(session.id, db)
        
        return {"active_session": state}
        
    except Exception as e:
        logger.error(f"Failed to check active session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check for active session"
        )


@router.post("/session/{session_id}/answer")
async def save_exam_answer(
    session_id: int,
    request: SaveAnswerRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Save/update an answer during exam.
    
    - Only works while exam is in progress
    - Tracks time spent on question
    - Calculates word count
    - Returns remaining time for timer sync
    """
    try:
        result = await save_answer(
            session_id=session_id,
            answer_id=request.answer_id,
            answer_text=request.answer_text,
            time_spent_seconds=request.time_spent_seconds,
            db=db,
            user_id=current_user.id
        )
        
        if "error" in result:
            status_code = status.HTTP_400_BAD_REQUEST
            if "expired" in result["error"].lower():
                status_code = status.HTTP_410_GONE
            raise HTTPException(
                status_code=status_code,
                detail=result["error"]
            )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to save answer: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save answer"
        )


@router.post("/session/{session_id}/flag")
async def flag_question(
    session_id: int,
    request: ToggleFlagRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Toggle flag status for a question.
    
    Flagged questions appear in review panel.
    """
    try:
        result = await toggle_flag(
            session_id=session_id,
            answer_id=request.answer_id,
            db=db,
            user_id=current_user.id
        )
        
        if "error" in result:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["error"]
            )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to toggle flag: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to toggle flag"
        )


@router.post("/session/{session_id}/submit")
async def submit_exam_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Submit exam manually.
    
    - Locks all answers permanently
    - Calculates final time taken
    - Returns submission summary
    
    Cannot be undone.
    """
    try:
        result = await submit_exam(
            session_id=session_id,
            db=db,
            user_id=current_user.id
        )
        
        if "error" in result:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["error"]
            )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to submit exam: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to submit exam"
        )


@router.get("/session/{session_id}/summary")
async def get_exam_summary(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get submission summary for a completed exam.
    
    Shows:
    - Questions attempted/unattempted
    - Time taken vs allowed
    - Section-wise breakdown
    """
    try:
        result = await get_submission_summary(session_id, db)
        
        if "error" in result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=result["error"]
            )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get exam summary"
        )


@router.get("/history")
async def get_exam_history(
    limit: int = Query(default=10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get user's exam session history.
    
    Returns list of past exams with status and stats.
    """
    try:
        result = await get_user_exam_history(
            user_id=current_user.id,
            db=db,
            limit=limit
        )
        
        return {"exams": result}
        
    except Exception as e:
        logger.error(f"Failed to get history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get exam history"
        )


@router.get("/timer/{session_id}")
async def get_timer_status(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get timer status for a session.
    
    Lightweight endpoint for timer sync without full state.
    """
    from sqlalchemy import select, and_
    from backend.orm.exam_session import ExamSession
    
    try:
        stmt = select(ExamSession).where(
            and_(
                ExamSession.id == session_id,
                ExamSession.user_id == current_user.id
            )
        )
        result = await db.execute(stmt)
        session = result.scalar_one_or_none()
        
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        return {
            "session_id": session.id,
            "status": session.status.value,
            "remaining_seconds": session.get_remaining_seconds(),
            "is_expired": session.is_expired(),
            "duration_minutes": session.duration_minutes,
            "started_at": session.started_at.isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get timer: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get timer status"
        )
