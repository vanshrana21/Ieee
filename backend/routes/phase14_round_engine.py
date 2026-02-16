"""
Phase 14 — Round Engine API Routes

Deterministic round engine with strict state control.
"""
import uuid
from typing import List, Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.rbac import require_min_role, UserRole
from backend.services.phase14_round_service import RoundService
from backend.services.phase14_match_service import MatchService
from backend.services.phase14_timer_service import TimerService
from backend.orm.phase14_round_engine import (
    RoundType, RoundStatus, MatchStatus, TurnStatus, SpeakerRole
)


router = APIRouter(
    prefix="/api/round-engine",
    tags=["Phase 14 - Round Engine"],
    responses={
        409: {"description": "State transition conflict"},
        404: {"description": "Resource not found"},
        400: {"description": "Bad request"}
    }
)


# =============================================================================
# Pydantic Models
# =============================================================================

class CreateRoundRequest(BaseModel):
    tournament_id: str = Field(..., description="Tournament UUID")
    round_number: int = Field(..., ge=1, description="Round number")
    round_type: RoundType
    bench_count: int = Field(default=0, ge=0)


class CreateRoundResponse(BaseModel):
    id: str
    tournament_id: str
    round_number: int
    round_type: str
    status: str
    created_at: str


class MatchConfig(BaseModel):
    bench_number: int
    team_petitioner_id: str
    team_respondent_id: str


class AssignMatchesRequest(BaseModel):
    matches: List[MatchConfig]


class MatchResponse(BaseModel):
    id: str
    round_id: str
    bench_number: int
    team_petitioner_id: str
    team_respondent_id: str
    status: str
    created_at: str


class GenerateTurnsRequest(BaseModel):
    team_petitioner_id: str
    team_respondent_id: str
    allocated_seconds: int = Field(default=600, ge=60)


class TurnResponse(BaseModel):
    id: str
    match_id: str
    team_id: str
    speaker_role: str
    turn_order: int
    allocated_seconds: int
    status: str
    started_at: Optional[str]
    ended_at: Optional[str]


class AdvanceTurnResponse(BaseModel):
    previous_turn: Optional[dict]
    current_turn: dict


class FreezeMatchRequest(BaseModel):
    petitioner_score: Decimal = Field(..., decimal_places=2)
    respondent_score: Decimal = Field(..., decimal_places=2)
    winner_team_id: str
    judge_ids: List[str]


class IntegrityResponse(BaseModel):
    match_id: str
    frozen: bool
    verified: bool
    frozen_hash: Optional[str]
    frozen_at: Optional[str]
    error: Optional[str]


class TimerStateResponse(BaseModel):
    match_id: str
    active_turn_id: Optional[str]
    remaining_seconds: int
    paused: bool
    last_tick: Optional[str]


class CrashRecoveryResponse(BaseModel):
    live_matches: List[dict]
    recovered_count: int


# =============================================================================
# Round Routes
# =============================================================================

@router.post("/tournaments/{tournament_id}/rounds", response_model=CreateRoundResponse)
async def create_round(
    tournament_id: str,
    request: CreateRoundRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_min_role(UserRole.ADMIN))
):
    """Create a new round. Admin/Judge only."""
    round_obj = await RoundService.create_round(
        db=db,
        tournament_id=uuid.UUID(tournament_id),
        round_number=request.round_number,
        round_type=request.round_type,
        bench_count=request.bench_count
    )
    
    return CreateRoundResponse(
        id=str(round_obj.id),
        tournament_id=str(round_obj.tournament_id),
        round_number=round_obj.round_number,
        round_type=round_obj.round_type,
        status=round_obj.status,
        created_at=round_obj.created_at.isoformat() if round_obj.created_at else None
    )


@router.post("/rounds/{round_id}/matches/assign")
async def assign_matches(
    round_id: str,
    request: AssignMatchesRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_min_role(UserRole.ADMIN))
):
    """Assign matches to a round. Admin/Judge only."""
    matches_config = [
        {
            "bench_number": m.bench_number,
            "team_petitioner_id": uuid.UUID(m.team_petitioner_id),
            "team_respondent_id": uuid.UUID(m.team_respondent_id)
        }
        for m in request.matches
    ]
    
    matches = await RoundService.assign_matches(
        db=db,
        round_id=uuid.UUID(round_id),
        matches_config=matches_config
    )
    
    return {
        "matches": [
            {
                "id": str(m.id),
                "round_id": str(m.round_id),
                "bench_number": m.bench_number,
                "status": m.status
            }
            for m in matches
        ]
    }


@router.post("/rounds/{round_id}/start")
async def start_round(
    round_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_min_role(UserRole.ADMIN))
):
    """Start a round (SCHEDULED → LIVE). Admin/Judge only."""
    round_obj = await RoundService.start_round(
        db=db,
        round_id=uuid.UUID(round_id)
    )
    
    return {
        "id": str(round_obj.id),
        "status": round_obj.status,
        "started": True
    }


@router.post("/rounds/{round_id}/complete")
async def complete_round(
    round_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_min_role(UserRole.ADMIN))
):
    """Complete a round (LIVE → COMPLETED). Admin/Judge only."""
    round_obj = await RoundService.complete_round(
        db=db,
        round_id=uuid.UUID(round_id)
    )
    
    return {
        "id": str(round_obj.id),
        "status": round_obj.status,
        "completed": True
    }


@router.post("/rounds/{round_id}/freeze")
async def freeze_round(
    round_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_min_role(UserRole.ADMIN))
):
    """Freeze a round (COMPLETED → FROZEN). Admin/Judge only."""
    round_obj = await RoundService.freeze_round(
        db=db,
        round_id=uuid.UUID(round_id)
    )
    
    return {
        "id": str(round_obj.id),
        "status": round_obj.status,
        "frozen": True
    }


# =============================================================================
# Match Routes
# =============================================================================

@router.post("/matches/{match_id}/turns/generate")
async def generate_speaker_turns(
    match_id: str,
    request: GenerateTurnsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_min_role(UserRole.ADMIN))
):
    """Generate deterministic speaker turns. Admin/Judge only."""
    turns = await MatchService.generate_speaker_turns(
        db=db,
        match_id=uuid.UUID(match_id),
        team_petitioner_id=uuid.UUID(request.team_petitioner_id),
        team_respondent_id=uuid.UUID(request.team_respondent_id),
        allocated_seconds=request.allocated_seconds
    )
    
    return {
        "turns": [
            {
                "id": str(t.id),
                "match_id": str(t.match_id),
                "team_id": str(t.team_id),
                "speaker_role": t.speaker_role,
                "turn_order": t.turn_order,
                "allocated_seconds": t.allocated_seconds,
                "status": t.status
            }
            for t in turns
        ]
    }


@router.post("/matches/{match_id}/start")
async def start_match(
    match_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_min_role(UserRole.ADMIN))
):
    """Start a match (SCHEDULED → LIVE). Admin/Judge only."""
    match = await MatchService.start_match(
        db=db,
        match_id=uuid.UUID(match_id)
    )
    
    return {
        "id": str(match.id),
        "status": match.status,
        "started": True
    }


@router.post("/matches/{match_id}/advance")
async def advance_turn(
    match_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_min_role(UserRole.ADMIN))
):
    """Advance to next speaker turn. Admin/Judge only."""
    result = await MatchService.advance_turn(
        db=db,
        match_id=uuid.UUID(match_id)
    )
    
    return AdvanceTurnResponse(**result)


@router.post("/matches/{match_id}/turns/{turn_id}/complete")
async def complete_turn(
    match_id: str,
    turn_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_min_role(UserRole.ADMIN))
):
    """Complete the active turn. Admin/Judge only."""
    turn = await MatchService.complete_turn(
        db=db,
        turn_id=uuid.UUID(turn_id)
    )
    
    return {
        "id": str(turn.id),
        "status": turn.status,
        "ended_at": turn.ended_at.isoformat() if turn.ended_at else None
    }


@router.post("/matches/{match_id}/complete")
async def complete_match(
    match_id: str,
    winner_team_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_min_role(UserRole.ADMIN))
):
    """Complete a match (LIVE/SCORING → COMPLETED). Admin/Judge only."""
    match = await MatchService.complete_match(
        db=db,
        match_id=uuid.UUID(match_id),
        winner_team_id=uuid.UUID(winner_team_id)
    )
    
    return {
        "id": str(match.id),
        "status": match.status,
        "winner_team_id": str(match.winner_team_id),
        "completed": True
    }


@router.post("/matches/{match_id}/freeze")
async def freeze_match(
    match_id: str,
    request: FreezeMatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_min_role(UserRole.ADMIN))
):
    """Freeze a match with immutable score lock. Admin/Judge only."""
    score_lock = await MatchService.freeze_match(
        db=db,
        match_id=uuid.UUID(match_id),
        petitioner_score=request.petitioner_score,
        respondent_score=request.respondent_score,
        winner_team_id=uuid.UUID(request.winner_team_id),
        judge_ids=[uuid.UUID(jid) for jid in request.judge_ids]
    )
    
    return {
        "match_id": str(score_lock.match_id),
        "frozen": True,
        "frozen_hash": score_lock.frozen_hash,
        "frozen_at": score_lock.frozen_at.isoformat() if score_lock.frozen_at else None
    }


# =============================================================================
# Timer Routes
# =============================================================================

@router.post("/matches/{match_id}/timer/pause")
async def pause_timer(
    match_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_min_role(UserRole.ADMIN))
):
    """Pause the match timer. Admin/Judge only."""
    timer = await TimerService.pause_timer(
        db=db,
        match_id=uuid.UUID(match_id)
    )
    
    return {
        "match_id": str(timer.match_id),
        "paused": timer.paused,
        "remaining_seconds": timer.remaining_seconds
    }


@router.post("/matches/{match_id}/timer/resume")
async def resume_timer(
    match_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_min_role(UserRole.ADMIN))
):
    """Resume the match timer. Admin/Judge only."""
    timer = await TimerService.resume_timer(
        db=db,
        match_id=uuid.UUID(match_id)
    )
    
    return {
        "match_id": str(timer.match_id),
        "paused": timer.paused,
        "remaining_seconds": timer.remaining_seconds
    }


# =============================================================================
# Query Routes
# =============================================================================

@router.get("/matches/{match_id}/state")
async def get_match_state(
    match_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_min_role(UserRole.STUDENT))
):
    """Get full match state including turns and timer."""
    match = await MatchService.get_match_with_turns(
        db=db,
        match_id=uuid.UUID(match_id)
    )
    
    if not match:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Match not found"
        )
    
    timer = await TimerService.get_timer_state(
        db=db,
        match_id=uuid.UUID(match_id)
    )
    
    return {
        "match": {
            "id": str(match.id),
            "status": match.status,
            "bench_number": match.bench_number,
            "winner_team_id": str(match.winner_team_id) if match.winner_team_id else None
        },
        "turns": [
            {
                "id": str(t.id),
                "turn_order": t.turn_order,
                "speaker_role": t.speaker_role,
                "status": t.status,
                "allocated_seconds": t.allocated_seconds,
                "started_at": t.started_at.isoformat() if t.started_at else None,
                "ended_at": t.ended_at.isoformat() if t.ended_at else None
            }
            for t in match.speaker_turns
        ],
        "timer": {
            "remaining_seconds": timer.remaining_seconds if timer else 0,
            "paused": timer.paused if timer else True,
            "active_turn_id": str(timer.active_turn_id) if timer and timer.active_turn_id else None
        } if timer else None
    }


@router.get("/matches/{match_id}/integrity", response_model=IntegrityResponse)
async def verify_match_integrity(
    match_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_min_role(UserRole.STUDENT))
):
    """Verify match integrity hash."""
    result = await MatchService.verify_match_integrity(
        db=db,
        match_id=uuid.UUID(match_id)
    )
    
    return IntegrityResponse(**result)


@router.get("/crash-recovery")
async def crash_recovery(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_min_role(UserRole.SUPER_ADMIN))
):
    """Check for LIVE matches requiring recovery. SuperAdmin only."""
    live_matches = await TimerService.restore_live_matches(db=db)
    
    return CrashRecoveryResponse(
        live_matches=live_matches,
        recovered_count=len(live_matches)
    )
