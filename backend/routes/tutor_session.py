"""
backend/routes/tutor_session.py
Phase 4.4: Tutor Session API Routes
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List

from backend.database import get_db
from backend.orm.user import User
from backend.routes.auth import get_current_user
from backend.services.tutor_session_service import (
    start_session,
    append_message,
    get_history,
    clear_session,
    pin_preference,
    extend_session_ttl,
    make_session_permanent,
    get_session
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tutor/session", tags=["tutor-session"])


class StartSessionRequest(BaseModel):
    session_name: Optional[str] = None
    preferences: Optional[Dict[str, Any]] = None


class StartSessionResponse(BaseModel):
    session_id: str
    started_at: str
    expires_at: str


class AppendMessageRequest(BaseModel):
    role: str = Field(..., pattern="^(student|assistant|user)$")
    text: str = Field(..., min_length=1, max_length=10000)
    metadata: Optional[Dict[str, Any]] = None


class PinPreferenceRequest(BaseModel):
    key: str = Field(..., min_length=1, max_length=50)
    value: Any


class HistoryResponse(BaseModel):
    session_id: str
    messages: List[Dict[str, Any]]
    preferences: Dict[str, Any]
    pinned_preferences: Dict[str, Any]
    message_count: int
    expires_at: Optional[str]


@router.post("/start", response_model=StartSessionResponse)
async def start_tutor_session(
    request: StartSessionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Start a new tutor session."""
    logger.info(f"Starting session: user_id={current_user.id}")
    
    try:
        result = await start_session(
            user_id=current_user.id,
            db=db,
            session_name=request.session_name,
            preferences=request.preferences
        )
        return StartSessionResponse(**result)
    except Exception as e:
        logger.error(f"Failed to start session: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start session"
        )


@router.post("/{session_id}/message")
async def add_message(
    session_id: str,
    request: AppendMessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Append a message to the session."""
    success = await append_message(
        session_id=session_id,
        user_id=current_user.id,
        role=request.role,
        text=request.text,
        db=db,
        metadata=request.metadata
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or expired"
        )
        
    return {"status": "ok"}


@router.get("/{session_id}/history", response_model=HistoryResponse)
async def get_session_history(
    session_id: str,
    limit: int = 10,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get session history with messages and preferences."""
    result = await get_history(session_id, current_user.id, db, limit=limit)
    
    if "error" in result and not result.get("messages"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result["error"]
        )
        
    return HistoryResponse(**result)


@router.post("/{session_id}/clear")
async def clear_tutor_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Clear all messages from a session."""
    success = await clear_session(session_id, current_user.id, db)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or expired"
        )
        
    return {"status": "cleared"}


@router.post("/{session_id}/pin-preference")
async def pin_session_preference(
    session_id: str,
    request: PinPreferenceRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Pin a preference for the session."""
    success = await pin_preference(
        session_id=session_id,
        user_id=current_user.id,
        key=request.key,
        value=request.value,
        db=db
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or expired"
        )
        
    return {"status": "pinned", "key": request.key}


@router.post("/{session_id}/extend")
async def extend_session(
    session_id: str,
    hours: int = 24,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Extend session TTL."""
    success = await extend_session_ttl(session_id, current_user.id, db, hours)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or expired"
        )
        
    return {"status": "extended", "hours": hours}


@router.post("/{session_id}/save-permanently")
async def save_session_permanently(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Save session permanently (opt-in to long-term storage)."""
    success = await make_session_permanent(session_id, current_user.id, db)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or expired"
        )
        
    return {"status": "saved_permanently"}


@router.get("/{session_id}")
async def get_session_info(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get session info."""
    session = await get_session(session_id, current_user.id, db)
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or expired"
        )
        
    return session.to_dict()
