"""
backend/routes/oral_round_timer.py
Phase 3.1: Timer control endpoints for virtual courtroom
Isolated from existing routes - NEW FILE
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from pydantic import BaseModel

from backend.database import get_db
from backend.orm.oral_round import OralRound, OralRoundStatus
from backend.orm.user import User, UserRole
from backend.routes.auth import get_current_user

router = APIRouter(prefix="/oral-rounds", tags=["oral-round-timer"])


# ================= SCHEMAS =================

class TimerStartRequest(BaseModel):
    """Request to start timer for a speaker"""
    speaker_role: str  # "petitioner" | "respondent" | "judge"


class TimerPauseRequest(BaseModel):
    """Request to pause/resume timer"""
    is_paused: bool


# ================= ROUTES =================

def _check_judge_permission(current_user: User):
    """Verify user has judge/admin/faculty role"""
    if current_user.role not in [UserRole.JUDGE, UserRole.ADMIN, UserRole.FACULTY]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only judges/admins can control timer"
        )


async def _get_round_or_404(round_id: int, db: AsyncSession):
    """Fetch round or raise 404"""
    result = await db.execute(select(OralRound).where(OralRound.id == round_id))
    round_obj = result.scalar_one_or_none()
    if not round_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Round not found"
        )
    return round_obj


@router.post("/{round_id}/timer/start")
async def start_timer(
    round_id: int,
    request: TimerStartRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Start timer for a specific speaker.
    Only judges/admins can control the timer.
    """
    _check_judge_permission(current_user)
    round_obj = await _get_round_or_404(round_id, db)
    
    # Validate speaker role
    valid_roles = ["petitioner", "respondent", "judge", "none"]
    if request.speaker_role not in valid_roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid speaker_role. Must be one of: {valid_roles}"
        )
    
    # Set time based on speaker role (default 5 min per speaker)
    time_map = {
        "petitioner": 300,  # 5 minutes
        "respondent": 300,  # 5 minutes
        "judge": 180,       # 3 minutes for Q&A
        "none": 0
    }
    
    round_obj.current_speaker = request.speaker_role
    round_obj.time_remaining = time_map.get(request.speaker_role, 300)
    round_obj.is_paused = False
    
    if not round_obj.actual_start:
        round_obj.actual_start = datetime.now(timezone.utc)
    
    round_obj.status = OralRoundStatus.IN_PROGRESS
    
    await db.commit()
    await db.refresh(round_obj)
    
    return {
        "status": "started",
        "speaker": request.speaker_role,
        "time_remaining": round_obj.time_remaining,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@router.post("/{round_id}/timer/pause")
async def pause_timer(
    round_id: int,
    request: TimerPauseRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Pause or resume the timer.
    Only judges/admins can control the timer.
    """
    _check_judge_permission(current_user)
    round_obj = await _get_round_or_404(round_id, db)
    
    round_obj.is_paused = request.is_paused
    
    await db.commit()
    await db.refresh(round_obj)
    
    return {
        "status": "paused" if request.is_paused else "resumed",
        "is_paused": round_obj.is_paused,
        "time_remaining": round_obj.time_remaining,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@router.post("/{round_id}/timer/complete")
async def complete_round(
    round_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Complete the oral round.
    Only judges/admins can complete the round.
    """
    _check_judge_permission(current_user)
    round_obj = await _get_round_or_404(round_id, db)
    
    round_obj.status = OralRoundStatus.COMPLETED
    round_obj.actual_end = datetime.now(timezone.utc)
    round_obj.is_paused = True
    round_obj.current_speaker = "none"
    
    await db.commit()
    await db.refresh(round_obj)
    
    return {
        "status": "completed",
        "actual_end": round_obj.actual_end.isoformat() if round_obj.actual_end else None,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@router.get("/{round_id}/timer/state")
async def get_timer_state(
    round_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get current timer state.
    Any authenticated user can view timer state.
    """
    round_obj = await _get_round_or_404(round_id, db)
    
    return {
        "round_id": round_id,
        "status": round_obj.status.value,
        "current_speaker": round_obj.current_speaker,
        "time_remaining": round_obj.time_remaining,
        "is_paused": round_obj.is_paused,
        "actual_start": round_obj.actual_start.isoformat() if round_obj.actual_start else None,
        "actual_end": round_obj.actual_end.isoformat() if round_obj.actual_end else None,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
