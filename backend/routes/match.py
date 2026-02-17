"""
Phase 4 — Competitive Match API

Endpoints:
- POST /api/match/queue
- GET  /api/match/{id}
- POST /api/match/{id}/round/{round_number}/submit
- GET  /api/match/{id}/status
"""
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.database import get_db
from backend.rbac import get_current_user, require_role
from backend.orm.user import User, UserRole
from backend.orm.online_match import Match
from backend.services.matchmaking_service import MatchmakingService


router = APIRouter(prefix="/api/match", tags=["Competitive Match"])


class RoundSubmitRequest(BaseModel):
    argument_text: str


@router.post("/queue", status_code=status.HTTP_201_CREATED)
@require_role([UserRole.student])
async def queue_ranked_match(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Request a ranked competitive match.
    
    Flow:
    - Attempts to find opponent within ±100 rating
    - If found → immediate match with 3 rounds per player
    - If not → queued match and server-driven AI fallback timer starts
    """
    result = await MatchmakingService.request_ranked_match(db, current_user)

    # Ensure fallback worker is scheduled even if called outside service
    if not result.get("match_found"):
        match_id = result.get("match_id")
        if match_id is not None:
            background_tasks.add_task(
                MatchmakingService._ai_fallback_worker, match_id
            )

    return result


@router.get("/{match_id}")
@require_role([UserRole.student])
async def get_match(
    match_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Get full match snapshot plus integrity state.
    """
    result = await db.execute(select(Match).where(Match.id == match_id))
    match = result.scalar_one_or_none()
    if not match:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Match not found"
        )

    if current_user.id not in {match.player1_id, match.player2_id}:
        if not match.is_ai_match or current_user.id != match.player1_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not a participant in this match",
            )

    status_payload = await MatchmakingService.get_match_status(
        db, match_id, current_user
    )

    return {
        "id": match.id,
        "player_1_id": match.player1_id,
        "player_2_id": match.player2_id,
        "player_1_score": match.player_1_score,
        "player_2_score": match.player_2_score,
        "winner_id": match.winner_id,
        "state": match.state,
        "current_state": match.current_state,
        "is_ai_match": match.is_ai_match,
        "is_locked": match.is_locked,
        "created_at": match.created_at,
        "started_at": match.started_at,
        "completed_at": match.completed_at,
        "finalized_at": match.finalized_at,
        "status": status_payload,
    }


@router.post("/{match_id}/round/{round_number}/submit")
@require_role([UserRole.student])
async def submit_round(
    match_id: int,
    round_number: int,
    payload: RoundSubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Submit an argument for a specific round.
    
    Enforces:
    - Round order (1 → 2 → 3)
    - No edits after submission
    - Phase 3-style locking via MatchRound.is_locked
    """
    return await MatchmakingService.submit_round(
        db=db,
        match_id=match_id,
        round_number=round_number,
        argument_text=payload.argument_text,
        current_user=current_user,
    )


@router.get("/{match_id}/status")
@require_role([UserRole.student])
async def match_status(
    match_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Lightweight status endpoint.
    """
    return await MatchmakingService.get_match_status(db, match_id, current_user)

