"""
Phase 5 — Hardened Live Courtroom HTTP Routes

Server-authoritative state machine with:
- Institution scoping
- RBAC enforcement
- 404 on cross-tenant access
- Deterministic responses
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.dependencies import get_current_user, require_role
from backend.orm.user import User, UserRole
from backend.orm.live_court import (
    LiveCourtSession, LiveTurn, LiveCourtStatus, LiveTurnState, LiveEventType
)
from backend.orm.round_pairing import TournamentRound
from backend.orm.national_network import NationalTournament, Institution
from backend.services.live_court_service import (
    start_session, pause_session, resume_session,
    start_turn, end_turn, server_timer_tick, complete_session,
    verify_event_chain, get_session_by_id, get_timer_state,
    get_turns_by_session, get_events_by_session,
    SessionNotFoundError, SessionCompletedError, InvalidStateTransitionError,
    TurnNotFoundError, TurnAlreadyActiveError, ActiveTurnExistsError
)

router = APIRouter(prefix="/live", tags=["Phase 5 — Live Courtroom"])


# =============================================================================
# Helper: Verify Session Access
# =============================================================================

async def verify_session_access(
    session_id: int,
    user: User,
    db: AsyncSession
) -> LiveCourtSession:
    """
    Verify user has access to session and return session.
    
    Returns 404 if session not in user's institution.
    """
    result = await db.execute(
        select(LiveCourtSession)
        .join(Institution, LiveCourtSession.institution_id == Institution.id)
        .where(
            and_(
                LiveCourtSession.id == session_id,
                LiveCourtSession.institution_id == user.institution_id
            )
        )
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    
    return session


# =============================================================================
# Session Management Endpoints
# =============================================================================

@router.post("/sessions/{session_id}/start", status_code=status.HTTP_200_OK)
async def start_session_endpoint(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.teacher, UserRole.teacher, UserRole.teacher]))
) -> Dict[str, Any]:
    """
    Start a live court session.
    
    Rules:
    - Status must be not_started
    - Acquires FOR UPDATE lock
    - Appends SESSION_STARTED event
    
    Roles: ADMIN, HOD, FACULTY
    """
    # Verify access
    await verify_session_access(session_id, current_user, db)
    
    try:
        session = await start_session(session_id, current_user.id, db)
        
        return {
            "session_id": session_id,
            "status": session.status.value,
            "started_at": session.started_at.isoformat() if session.started_at else None,
            "message": "Session started successfully"
        }
        
    except SessionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    except SessionCompletedError:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Session already completed"
        )
    except InvalidStateTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/sessions/{session_id}/pause", status_code=status.HTTP_200_OK)
async def pause_session_endpoint(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.teacher, UserRole.teacher, UserRole.teacher]))
) -> Dict[str, Any]:
    """
    Pause a live court session.
    
    Rules:
    - Only allowed if status == live
    - Appends SESSION_PAUSED event
    
    Roles: ADMIN, HOD, FACULTY
    """
    await verify_session_access(session_id, current_user, db)
    
    try:
        session = await pause_session(session_id, current_user.id, db)
        
        return {
            "session_id": session_id,
            "status": session.status.value,
            "paused_at": datetime.utcnow().isoformat(),
            "message": "Session paused successfully"
        }
        
    except SessionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    except InvalidStateTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/sessions/{session_id}/resume", status_code=status.HTTP_200_OK)
async def resume_session_endpoint(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.teacher, UserRole.teacher, UserRole.teacher]))
) -> Dict[str, Any]:
    """
    Resume a paused live court session.
    
    Rules:
    - Only allowed if status == paused
    - Appends SESSION_RESUMED event
    
    Roles: ADMIN, HOD, FACULTY
    """
    await verify_session_access(session_id, current_user, db)
    
    try:
        session = await resume_session(session_id, current_user.id, db)
        
        return {
            "session_id": session_id,
            "status": session.status.value,
            "resumed_at": datetime.utcnow().isoformat(),
            "message": "Session resumed successfully"
        }
        
    except SessionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    except InvalidStateTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/sessions/{session_id}/complete", status_code=status.HTTP_200_OK)
async def complete_session_endpoint(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.teacher, UserRole.teacher]))
) -> Dict[str, Any]:
    """
    Complete a live court session.
    
    Rules:
    - Only allowed if no active turn
    - Status must be live or paused
    - SERIALIZABLE isolation
    - Appends SESSION_COMPLETED event
    
    Roles: ADMIN, HOD only
    """
    await verify_session_access(session_id, current_user, db)
    
    try:
        session = await complete_session(session_id, current_user.id, db)
        
        return {
            "session_id": session_id,
            "status": session.status.value,
            "completed_at": session.ended_at.isoformat() if session.ended_at else None,
            "message": "Session completed successfully"
        }
        
    except SessionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    except ActiveTurnExistsError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except InvalidStateTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# =============================================================================
# Turn Management Endpoints
# =============================================================================

@router.post("/sessions/{session_id}/turns/{turn_id}/start", status_code=status.HTTP_200_OK)
async def start_turn_endpoint(
    session_id: int,
    turn_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.teacher, UserRole.teacher, UserRole.teacher]))
) -> Dict[str, Any]:
    """
    Start a turn in a session.
    
    Rules:
    - Session.status must be live
    - No other turn can be active
    - Turn.state must be pending
    - Locks both session and turn rows
    - Appends TURN_STARTED event
    
    Roles: ADMIN, HOD, FACULTY
    """
    await verify_session_access(session_id, current_user, db)
    
    try:
        turn, session = await start_turn(session_id, turn_id, current_user.id, db)
        
        return {
            "session_id": session_id,
            "turn_id": turn_id,
            "participant_id": turn.participant_id,
            "status": turn.state.value,
            "started_at": turn.started_at.isoformat() if turn.started_at else None,
            "allocated_seconds": turn.allocated_seconds,
            "message": "Turn started successfully"
        }
        
    except SessionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    except TurnNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Turn not found"
        )
    except InvalidStateTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except ActiveTurnExistsError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except TurnAlreadyActiveError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )


@router.post("/sessions/{session_id}/turns/{turn_id}/end", status_code=status.HTTP_200_OK)
async def end_turn_endpoint(
    session_id: int,
    turn_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.teacher, UserRole.teacher, UserRole.teacher]))
) -> Dict[str, Any]:
    """
    End a turn in a session.
    
    Rules:
    - Turn.state must be active
    - Sets state = ended
    - Clears session.current_turn_id
    - Appends TURN_ENDED event
    
    Roles: ADMIN, HOD, FACULTY
    """
    await verify_session_access(session_id, current_user, db)
    
    try:
        turn, session = await end_turn(session_id, turn_id, current_user.id, db)
        
        return {
            "session_id": session_id,
            "turn_id": turn_id,
            "status": turn.state.value,
            "ended_at": turn.ended_at.isoformat() if turn.ended_at else None,
            "elapsed_seconds": turn.get_elapsed_seconds(),
            "violation_flag": turn.violation_flag,
            "message": "Turn ended successfully"
        }
        
    except SessionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    except TurnNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Turn not found"
        )
    except InvalidStateTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# =============================================================================
# Timer Endpoints
# =============================================================================

@router.get("/sessions/{session_id}/timer", status_code=status.HTTP_200_OK)
async def get_timer_endpoint(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get the current timer state for a session.
    
    Returns remaining time, elapsed time, and violation status.
    """
    await verify_session_access(session_id, current_user, db)
    
    timer_state = await get_timer_state(session_id, db)
    
    return timer_state


@router.post("/sessions/{session_id}/timer/tick", status_code=status.HTTP_200_OK)
async def timer_tick_endpoint(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.teacher, UserRole.teacher, UserRole.teacher]))
) -> Dict[str, Any]:
    """
    Server-side timer tick.
    
    Checks for time expiration and ends turn if expired.
    Idempotent - multiple ticks won't duplicate expiration.
    
    Roles: ADMIN, HOD, FACULTY (System use)
    """
    await verify_session_access(session_id, current_user, db)
    
    expired_turn = await server_timer_tick(session_id, db)
    
    if expired_turn:
        return {
            "session_id": session_id,
            "time_expired": True,
            "turn_id": expired_turn.id,
            "participant_id": expired_turn.participant_id,
            "violation_flag": True,
            "message": "Turn expired - time exceeded allocation"
        }
    
    return {
        "session_id": session_id,
        "time_expired": False,
        "message": "No time expiration"
    }


# =============================================================================
# Session Info Endpoints
# =============================================================================

@router.get("/sessions/{session_id}", status_code=status.HTTP_200_OK)
async def get_session_endpoint(
    session_id: int,
    include_turns: bool = True,
    include_events: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get session details.
    
    Optionally includes turns and events.
    """
    await verify_session_access(session_id, current_user, db)
    
    session = await get_session_by_id(session_id, db)
    
    return {
        "session": session.to_dict(
            include_turns=include_turns,
            include_events=include_events
        )
    }


@router.get("/sessions/{session_id}/turns", status_code=status.HTTP_200_OK)
async def get_turns_endpoint(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get all turns for a session.
    """
    await verify_session_access(session_id, current_user, db)
    
    turns = await get_turns_by_session(session_id, db)
    
    return {
        "session_id": session_id,
        "total_turns": len(turns),
        "turns": [t.to_dict() for t in turns]
    }


@router.get("/sessions/{session_id}/events", status_code=status.HTTP_200_OK)
async def get_events_endpoint(
    session_id: int,
    since_sequence: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get events for a session.
    
    Optionally filter to events after a specific sequence number.
    """
    await verify_session_access(session_id, current_user, db)
    
    events = await get_events_by_session(session_id, db, since_sequence)
    
    return {
        "session_id": session_id,
        "since_sequence": since_sequence,
        "total_events": len(events),
        "events": [e.to_dict() for e in events]
    }


# =============================================================================
# Verification Endpoint
# =============================================================================

@router.get("/sessions/{session_id}/verify", status_code=status.HTTP_200_OK)
async def verify_session_endpoint(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.teacher, UserRole.teacher, UserRole.teacher]))
) -> Dict[str, Any]:
    """
    Verify the integrity of the event chain.
    
    Recomputes all hashes from genesis and checks for tampering.
    Detects:
    - Event hash mismatches
    - Chain breaks
    - Sequence gaps
    - Missing events
    
    Roles: ADMIN, HOD, FACULTY
    """
    await verify_session_access(session_id, current_user, db)
    
    result = await verify_event_chain(session_id, db)
    
    return result


# =============================================================================
# Create Session Endpoint
# =============================================================================

@router.post("/rounds/{round_id}/sessions", status_code=status.HTTP_201_CREATED)
async def create_session_endpoint(
    round_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.teacher, UserRole.teacher]))
) -> Dict[str, Any]:
    """
    Create a new live court session for a round.
    
    Roles: ADMIN, HOD only
    """
    # Verify round access
    result = await db.execute(
        select(TournamentRound)
        .join(NationalTournament, TournamentRound.tournament_id == NationalTournament.id)
        .where(
            and_(
                TournamentRound.id == round_id,
                NationalTournament.host_institution_id == current_user.institution_id
            )
        )
    )
    round_obj = result.scalar_one_or_none()
    
    if not round_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Round not found"
        )
    
    # Create session
    session = LiveCourtSession(
        round_id=round_id,
        institution_id=current_user.institution_id,
        status=LiveCourtStatus.NOT_STARTED,
        created_at=datetime.utcnow()
    )
    
    db.add(session)
    await db.flush()
    
    return {
        "session_id": session.id,
        "round_id": round_id,
        "status": session.status.value,
        "created_at": session.created_at.isoformat(),
        "message": "Session created successfully"
    }


# =============================================================================
# Create Turn Endpoint
# =============================================================================

@router.post("/sessions/{session_id}/turns", status_code=status.HTTP_201_CREATED)
async def create_turn_endpoint(
    session_id: int,
    participant_id: int,
    side: str,
    turn_type: str,
    allocated_seconds: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.teacher, UserRole.teacher, UserRole.teacher]))
) -> Dict[str, Any]:
    """
    Create a new turn for a session.
    
    Args:
        session_id: Session ID
        participant_id: User ID of participant
        side: "petitioner" or "respondent"
        turn_type: "presentation", "rebuttal", "surrebuttal", "question", "answer"
        allocated_seconds: Time allocation in seconds
    
    Roles: ADMIN, HOD, FACULTY
    """
    session = await verify_session_access(session_id, current_user, db)
    
    if session.is_completed():
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Cannot create turn for completed session"
        )
    
    # Validate enums
    try:
        side_enum = OralSide(side)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid side: {side}. Must be 'petitioner' or 'respondent'"
        )
    
    from backend.orm.live_court import OralTurnType
    try:
        turn_type_enum = OralTurnType(turn_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid turn_type: {turn_type}"
        )
    
    if allocated_seconds < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="allocated_seconds must be positive"
        )
    
    # Create turn
    turn = LiveTurn(
        session_id=session_id,
        participant_id=participant_id,
        side=side_enum,
        turn_type=turn_type_enum,
        allocated_seconds=allocated_seconds,
        state=LiveTurnState.PENDING,
        created_at=datetime.utcnow()
    )
    
    db.add(turn)
    await db.flush()
    
    return {
        "turn_id": turn.id,
        "session_id": session_id,
        "participant_id": participant_id,
        "side": side,
        "turn_type": turn_type,
        "allocated_seconds": allocated_seconds,
        "state": turn.state.value,
        "message": "Turn created successfully"
    }
