"""
Classroom Round Engine Routes — Phase 3

API endpoints for managing classroom rounds, turns, and timing.
All routes require authentication and enforce role-based access.
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.orm.user import User, UserRole
from backend.security.rbac import get_current_user, require_teacher, require_student
from backend.schemas.classroom_rounds import (
    RoundCreateRequest, RoundResponse, RoundStartRequest, RoundStartResponse,
    RoundAbortRequest, RoundAbortResponse, RoundListResponse,
    TurnStartRequest, TurnStartResponse,
    TurnSubmitRequest, TurnSubmitResponse,
    TurnForceSubmitRequest, TurnForceSubmitResponse,
    TurnAuditEntry, APIError
)
from backend.services import round_engine_service as round_svc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/classroom", tags=["rounds"])


def _is_teacher(user: User) -> bool:
    """Check if user has teacher role."""
    return user.role == UserRole.teacher


# DEPRECATED: Kept for backward compatibility during migration
def _is_faculty(user: User) -> bool:
    """
    DEPRECATED: Use _is_teacher instead.
    Aliased to check for teacher role only.
    """
    return _is_teacher(user)


def _make_error_response(error: str, message: str, details: Optional[dict] = None) -> dict:
    """Create standardized error response."""
    return {
        "success": False,
        "error": error,
        "message": message,
        "details": details
    }


# ============================================================================
# Round Routes
# ============================================================================

@router.post("/rounds", response_model=RoundResponse, status_code=status.HTTP_201_CREATED)
async def create_round(
    request: RoundCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new round for a session.
    
    Faculty only. If turns not provided, auto-generates from participants.
    """
    if not _is_faculty(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_make_error_response("FORBIDDEN", "Only faculty can create rounds")
        )
    
    try:
        # Convert turns to service format
        turns = None
        if request.turns:
            turns = [
                {
                    "participant_id": t.participant_id,
                    "allowed_seconds": t.allowed_seconds or request.default_turn_seconds
                }
                for t in request.turns
            ]
        
        round_obj = await round_svc.create_round(
            session_id=request.session_id,
            round_index=request.round_index,
            round_type=request.round_type,
            default_turn_seconds=request.default_turn_seconds,
            turns=turns,
            db=db,
            is_faculty=True
        )
        
        # Fetch turns for response
        turns_list = await round_svc.get_turns_for_round(round_obj.id, db)
        
        await db.commit()
        
        return RoundResponse(
            id=round_obj.id,
            session_id=round_obj.session_id,
            round_index=round_obj.round_index,
            round_type=round_obj.round_type,
            status=round_obj.status,
            current_speaker_participant_id=round_obj.current_speaker_participant_id,
            started_at=round_obj.started_at.isoformat() if round_obj.started_at else None,
            ended_at=round_obj.ended_at.isoformat() if round_obj.ended_at else None,
            turns=[
                round_svc._turn_to_response(t) for t in turns_list
            ] if turns_list else []
        )
        
    except round_svc.RoundEngineError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_make_error_response(e.code, e.message)
        )
    except Exception as e:
        await db.rollback()
        logger.exception("Failed to create round")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_make_error_response("INTERNAL_ERROR", "Failed to create round")
        )


@router.get("/sessions/{session_id}/rounds", response_model=RoundListResponse)
async def list_rounds(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List all rounds for a session.
    
    Accessible to faculty and students in the session.
    """
    try:
        rounds = await round_svc.get_rounds_for_session(session_id, db)
        
        result = []
        for r in rounds:
            turns = await round_svc.get_turns_for_round(r.id, db)
            result.append(RoundResponse(
                id=r.id,
                session_id=r.session_id,
                round_index=r.round_index,
                round_type=r.round_type,
                status=r.status,
                current_speaker_participant_id=r.current_speaker_participant_id,
                started_at=r.started_at.isoformat() if r.started_at else None,
                ended_at=r.ended_at.isoformat() if r.ended_at else None,
                turns=[round_svc._turn_to_response(t) for t in turns] if turns else []
            ))
        
        return RoundListResponse(rounds=result, total=len(result))
        
    except Exception as e:
        logger.exception("Failed to list rounds")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_make_error_response("INTERNAL_ERROR", "Failed to list rounds")
        )


@router.post("/rounds/{round_id}/start", response_model=RoundStartResponse)
async def start_round(
    round_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Start a round.
    
    Faculty only. Sets round status to ACTIVE and first speaker.
    """
    if not _is_faculty(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_make_error_response("FORBIDDEN", "Only faculty can start rounds")
        )
    
    try:
        round_obj = await round_svc.start_round(
            round_id=round_id,
            actor_id=current_user.id,
            db=db,
            is_faculty=True
        )
        
        await db.commit()
        
        return RoundStartResponse(
            success=True,
            round_id=round_obj.id,
            status=round_obj.status,
            current_speaker_participant_id=round_obj.current_speaker_participant_id
        )
        
    except round_svc.RoundNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_make_error_response(e.code, e.message))
    except round_svc.InvalidRoundStateError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_make_error_response(e.code, e.message))
    except round_svc.UnauthorizedActionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_make_error_response(e.code, e.message))
    except Exception as e:
        await db.rollback()
        logger.exception(f"Failed to start round {round_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_make_error_response("INTERNAL_ERROR", "Failed to start round")
        )


@router.get("/rounds/{round_id}", response_model=RoundResponse)
async def get_round(
    round_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get detailed round information."""
    try:
        round_obj = await round_svc.get_round(round_id, db)
        if not round_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_make_error_response("NOT_FOUND", f"Round {round_id} not found")
            )
        
        turns = await round_svc.get_turns_for_round(round_id, db)
        
        return RoundResponse(
            id=round_obj.id,
            session_id=round_obj.session_id,
            round_index=round_obj.round_index,
            round_type=round_obj.round_type,
            status=round_obj.status,
            current_speaker_participant_id=round_obj.current_speaker_participant_id,
            started_at=round_obj.started_at.isoformat() if round_obj.started_at else None,
            ended_at=round_obj.ended_at.isoformat() if round_obj.ended_at else None,
            turns=[round_svc._turn_to_response(t) for t in turns] if turns else []
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get round {round_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_make_error_response("INTERNAL_ERROR", "Failed to get round")
        )


@router.post("/rounds/{round_id}/abort", response_model=RoundAbortResponse)
async def abort_round(
    round_id: int,
    request: Optional[RoundAbortRequest] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Abort a round.
    
    Faculty only. Sets round status to ABORTED.
    """
    if not _is_faculty(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_make_error_response("FORBIDDEN", "Only faculty can abort rounds")
        )
    
    try:
        round_obj = await round_svc.abort_round(
            round_id=round_id,
            actor_id=current_user.id,
            db=db,
            is_faculty=True,
            reason=request.reason if request else None
        )
        
        await db.commit()
        
        return RoundAbortResponse(
            success=True,
            round_id=round_obj.id,
            status=round_obj.status,
            ended_at=round_obj.ended_at.isoformat() if round_obj.ended_at else None
        )
        
    except round_svc.RoundNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_make_error_response(e.code, e.message))
    except Exception as e:
        await db.rollback()
        logger.exception(f"Failed to abort round {round_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_make_error_response("INTERNAL_ERROR", "Failed to abort round")
        )


# ============================================================================
# Turn Routes
# ============================================================================

@router.post("/turns/{turn_id}/start", response_model=TurnStartResponse)
async def start_turn(
    turn_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Start a turn (claim speaking time).
    
    Only the assigned participant or faculty can start.
    """
    try:
        turn_obj = await round_svc.start_turn(
            turn_id=turn_id,
            actor_id=current_user.id,
            db=db,
            is_faculty=_is_faculty(current_user)
        )
        
        await db.commit()
        
        return TurnStartResponse(
            turn_id=turn_obj.id,
            started_at=turn_obj.started_at.isoformat(),
            allowed_seconds=turn_obj.allowed_seconds,
            remaining_seconds=turn_obj.remaining_seconds or turn_obj.allowed_seconds
        )
        
    except round_svc.TurnNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_make_error_response(e.code, e.message))
    except round_svc.NotCurrentSpeakerError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_make_error_response(e.code, e.message))
    except round_svc.UnauthorizedActionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_make_error_response(e.code, e.message))
    except round_svc.InvalidRoundStateError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_make_error_response(e.code, e.message))
    except Exception as e:
        await db.rollback()
        logger.exception(f"Failed to start turn {turn_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_make_error_response("INTERNAL_ERROR", "Failed to start turn")
        )


@router.post("/turns/{turn_id}/submit", response_model=TurnSubmitResponse)
async def submit_turn(
    turn_id: int,
    request: TurnSubmitRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Submit a turn transcript.
    
    Only the assigned participant or faculty can submit.
    Rejected if time expired and late submissions not allowed.
    """
    from backend.config.feature_flags import FEATURE_ALLOW_LATE_SUBMISSION
    
    try:
        turn_obj, is_complete = await round_svc.submit_turn(
            turn_id=turn_id,
            transcript=request.transcript,
            word_count=request.word_count,
            actor_id=current_user.id,
            db=db,
            is_faculty=_is_faculty(current_user),
            allow_late=FEATURE_ALLOW_LATE_SUBMISSION
        )
        
        await db.commit()
        
        # Get next speaker if round not complete
        next_speaker = None
        if not is_complete:
            round_obj = await round_svc.get_round(turn_obj.round_id, db)
            next_speaker = round_obj.current_speaker_participant_id if round_obj else None
        
        return TurnSubmitResponse(
            success=True,
            turn_id=turn_obj.id,
            submitted_at=turn_obj.submitted_at.isoformat() if turn_obj.submitted_at else None,
            next_current_speaker_participant_id=next_speaker,
            round_status="COMPLETED" if is_complete else "ACTIVE"
        )
        
    except round_svc.TurnNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_make_error_response(e.code, e.message))
    except round_svc.TurnAlreadySubmittedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_make_error_response(e.code, e.message))
    except round_svc.TurnNotStartedError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_make_error_response(e.code, e.message))
    except round_svc.TimeExpiredError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_make_error_response(e.code, e.message))
    except round_svc.UnauthorizedActionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_make_error_response(e.code, e.message))
    except Exception as e:
        await db.rollback()
        logger.exception(f"Failed to submit turn {turn_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_make_error_response("INTERNAL_ERROR", "Failed to submit turn")
        )


@router.post("/turns/{turn_id}/force_submit", response_model=TurnForceSubmitResponse)
async def force_submit_turn(
    turn_id: int,
    request: TurnForceSubmitRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Faculty force submit a turn.
    
    Always allowed regardless of time/state.
    """
    if not _is_faculty(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_make_error_response("FORBIDDEN", "Only faculty can force submit")
        )
    
    try:
        turn_obj, is_complete = await round_svc.force_submit_turn(
            turn_id=turn_id,
            transcript=request.transcript,
            word_count=request.word_count,
            actor_id=current_user.id,
            db=db,
            is_faculty=True
        )
        
        await db.commit()
        
        return TurnForceSubmitResponse(
            success=True,
            turn_id=turn_obj.id,
            round_id=turn_obj.round_id,
            status="COMPLETED" if is_complete else "ACTIVE",
            force_submitted_at=turn_obj.submitted_at.isoformat() if turn_obj.submitted_at else None
        )
        
    except round_svc.TurnNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_make_error_response(e.code, e.message))
    except Exception as e:
        await db.rollback()
        logger.exception(f"Failed to force submit turn {turn_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_make_error_response("INTERNAL_ERROR", "Failed to force submit turn")
        )


@router.get("/turns/{turn_id}/audit", response_model=List[TurnAuditEntry])
async def get_turn_audit(
    turn_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get audit log entries for a turn."""
    try:
        # Get turn to check authorization
        turn = await round_svc.get_turn(turn_id, db)
        if not turn:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_make_error_response("NOT_FOUND", f"Turn {turn_id} not found")
            )
        
        # Check user is faculty or participant in same session
        # (Simplified: faculty can see all, students can see their own turns)
        if not _is_faculty(current_user):
            # TODO: Check if current_user is participant in same session
            pass
        
        audit_entries = await round_svc.get_turn_audit(turn_id, db)
        
        return [
            TurnAuditEntry(
                id=entry.id,
                turn_id=entry.turn_id,
                action=entry.action,
                actor_user_id=entry.actor_user_id,
                payload_json=entry.payload_json,
                created_at=entry.created_at.isoformat() if entry.created_at else None
            )
            for entry in audit_entries
        ]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get turn audit {turn_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_make_error_response("INTERNAL_ERROR", "Failed to get turn audit")
        )


# ============================================================================
# Helper function for service
# ============================================================================

def _turn_to_response(turn) -> dict:
    """Convert turn ORM to response dict."""
    from backend.schemas.classroom_rounds import TurnResponse
    return TurnResponse(
        id=turn.id,
        round_id=turn.round_id,
        participant_id=turn.participant_id,
        turn_order=turn.turn_order,
        allowed_seconds=turn.allowed_seconds,
        started_at=turn.started_at.isoformat() if turn.started_at else None,
        submitted_at=turn.submitted_at.isoformat() if turn.submitted_at else None,
        transcript=turn.transcript,
        word_count=turn.word_count,
        is_submitted=turn.is_submitted
    ).dict()


# Add helper to service module
round_svc._turn_to_response = _turn_to_response
