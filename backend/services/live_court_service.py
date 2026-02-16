"""
Phase 5 — Hardened Live Courtroom State Machine Service Layer

Server-authoritative with:
- Deterministic event chain
- Cryptographic hashing
- No race conditions (FOR UPDATE locks)
- SERIALIZABLE for complete_session
- No float(), no random(), no datetime.now()
"""
import hashlib
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, and_, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from backend.orm.live_court import (
    LiveCourtSession, LiveTurn, LiveEventLog,
    LiveCourtStatus, LiveTurnState, LiveEventType,
    OralSide, OralTurnType, get_next_event_sequence
)
from backend.orm.round_pairing import TournamentRound
from backend.orm.user import User, UserRole
from backend.orm.national_network import Institution


# =============================================================================
# Custom Exceptions
# =============================================================================

class LiveCourtError(Exception):
    """Base exception for live courtroom errors."""
    pass


class SessionNotFoundError(LiveCourtError):
    """Raised when session is not found."""
    pass


class SessionCompletedError(LiveCourtError):
    """Raised when session is already completed."""
    pass


class InvalidStateTransitionError(LiveCourtError):
    """Raised when state transition is invalid."""
    pass


class TurnNotFoundError(LiveCourtError):
    """Raised when turn is not found."""
    pass


class TurnAlreadyActiveError(LiveCourtError):
    """Raised when trying to start an already active turn."""
    pass


class ActiveTurnExistsError(LiveCourtError):
    """Raised when another turn is already active."""
    pass


class InstitutionScopeError(LiveCourtError):
    """Raised when institution access is denied."""
    pass


# =============================================================================
# Event Log Helpers
# =============================================================================

async def _get_last_event_hash_and_sequence(
    session_id: int,
    db: AsyncSession
) -> Tuple[str, int]:
    """
    Get the last event hash and sequence for a session.
    Must be called within a transaction with FOR UPDATE lock.
    """
    result = await db.execute(
        select(LiveEventLog.event_hash, LiveEventLog.event_sequence)
        .where(LiveEventLog.session_id == session_id)
        .order_by(LiveEventLog.event_sequence.desc())
        .limit(1)
        .with_for_update()
    )
    row = result.one_or_none()
    
    if row:
        return row[0], row[1]
    
    # Genesis hash (64 zeros)
    return "0" * 64, 0


async def _append_event(
    session_id: int,
    event_type: str,
    payload: Dict[str, Any],
    db: AsyncSession
) -> LiveEventLog:
    """
    Append an event to the log with cryptographic chain hash.
    
    Steps:
    1. Lock last event
    2. Compute next sequence
    3. Compute hash with previous_hash
    4. Insert event
    """
    # Get last event (with lock)
    previous_hash, last_sequence = await _get_last_event_hash_and_sequence(session_id, db)
    
    next_sequence = last_sequence + 1
    created_at = datetime.utcnow()
    
    # Compute deterministic hash
    event_hash = LiveEventLog.compute_event_hash(
        previous_hash=previous_hash,
        event_sequence=next_sequence,
        event_type=event_type,
        payload=payload,
        created_at=created_at
    )
    
    # Create event (payload with sort_keys for determinism)
    event = LiveEventLog(
        session_id=session_id,
        event_sequence=next_sequence,
        event_type=event_type,
        event_payload_json=json.loads(json.dumps(payload, sort_keys=True)),
        previous_hash=previous_hash,
        event_hash=event_hash,
        created_at=created_at
    )
    
    db.add(event)
    await db.flush()
    
    return event


# =============================================================================
# Session Management
# =============================================================================

async def start_session(
    session_id: int,
    user_id: int,
    db: AsyncSession
) -> LiveCourtSession:
    """
    Start a live court session.
    
    Rules:
    - status must be not_started
    - acquire FOR UPDATE on session
    - set status = live
    - set started_at = utcnow
    - append SESSION_STARTED event
    
    Args:
        session_id: Session to start
        user_id: User starting the session
        db: Database session
        
    Returns:
        Updated LiveCourtSession
    """
    # Lock session for update
    result = await db.execute(
        select(LiveCourtSession)
        .where(LiveCourtSession.id == session_id)
        .with_for_update()
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise SessionNotFoundError(f"Session {session_id} not found")
    
    if session.status == LiveCourtStatus.COMPLETED:
        raise SessionCompletedError("Session already completed")
    
    if session.status != LiveCourtStatus.NOT_STARTED:
        raise InvalidStateTransitionError(f"Cannot start session in status {session.status.value}")
    
    # Update session
    session.status = LiveCourtStatus.LIVE
    session.started_at = datetime.utcnow()
    
    await db.flush()
    
    # Append event
    await _append_event(
        session_id=session_id,
        event_type=LiveEventType.SESSION_STARTED,
        payload={
            "session_id": session_id,
            "started_by": user_id,
            "started_at": session.started_at.isoformat()
        },
        db=db
    )
    
    return session


async def pause_session(
    session_id: int,
    user_id: int,
    db: AsyncSession
) -> LiveCourtSession:
    """
    Pause a live court session.
    
    Rules:
    - Only allowed if status == live
    - Append SESSION_PAUSED event
    
    Args:
        session_id: Session to pause
        user_id: User pausing
        db: Database session
        
    Returns:
        Updated LiveCourtSession
    """
    result = await db.execute(
        select(LiveCourtSession)
        .where(LiveCourtSession.id == session_id)
        .with_for_update()
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise SessionNotFoundError(f"Session {session_id} not found")
    
    if session.status != LiveCourtStatus.LIVE:
        raise InvalidStateTransitionError(f"Cannot pause session in status {session.status.value}")
    
    session.status = LiveCourtStatus.PAUSED
    
    await db.flush()
    
    await _append_event(
        session_id=session_id,
        event_type=LiveEventType.SESSION_PAUSED,
        payload={
            "session_id": session_id,
            "paused_by": user_id,
            "paused_at": datetime.utcnow().isoformat()
        },
        db=db
    )
    
    return session


async def resume_session(
    session_id: int,
    user_id: int,
    db: AsyncSession
) -> LiveCourtSession:
    """
    Resume a paused live court session.
    
    Rules:
    - Only allowed if status == paused
    - Append SESSION_RESUMED event
    
    Args:
        session_id: Session to resume
        user_id: User resuming
        db: Database session
        
    Returns:
        Updated LiveCourtSession
    """
    result = await db.execute(
        select(LiveCourtSession)
        .where(LiveCourtSession.id == session_id)
        .with_for_update()
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise SessionNotFoundError(f"Session {session_id} not found")
    
    if session.status != LiveCourtStatus.PAUSED:
        raise InvalidStateTransitionError(f"Cannot resume session in status {session.status.value}")
    
    session.status = LiveCourtStatus.LIVE
    
    await db.flush()
    
    await _append_event(
        session_id=session_id,
        event_type=LiveEventType.SESSION_RESUMED,
        payload={
            "session_id": session_id,
            "resumed_by": user_id,
            "resumed_at": datetime.utcnow().isoformat()
        },
        db=db
    )
    
    return session


# =============================================================================
# Turn Management
# =============================================================================

async def start_turn(
    session_id: int,
    turn_id: int,
    user_id: int,
    db: AsyncSession
) -> Tuple[LiveTurn, LiveCourtSession]:
    """
    Start a turn.
    
    Rules:
    - session.status must be live
    - session.current_turn_id must be null
    - turn.state must be pending
    - lock both session + turn rows
    - set turn.state = active
    - set started_at = utcnow
    - set session.current_turn_id = turn_id
    - append TURN_STARTED event
    
    Args:
        session_id: Session containing the turn
        turn_id: Turn to start
        user_id: User starting the turn
        db: Database session
        
    Returns:
        Tuple of (LiveTurn, LiveCourtSession)
    """
    # Lock session
    result = await db.execute(
        select(LiveCourtSession)
        .where(LiveCourtSession.id == session_id)
        .with_for_update()
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise SessionNotFoundError(f"Session {session_id} not found")
    
    if session.status != LiveCourtStatus.LIVE:
        raise InvalidStateTransitionError(f"Cannot start turn when session status is {session.status.value}")
    
    if session.current_turn_id is not None:
        raise ActiveTurnExistsError(f"Turn {session.current_turn_id} is already active")
    
    # Lock turn
    result = await db.execute(
        select(LiveTurn)
        .where(
            and_(
                LiveTurn.id == turn_id,
                LiveTurn.session_id == session_id
            )
        )
        .with_for_update()
    )
    turn = result.scalar_one_or_none()
    
    if not turn:
        raise TurnNotFoundError(f"Turn {turn_id} not found in session {session_id}")
    
    if turn.state != LiveTurnState.PENDING:
        raise TurnAlreadyActiveError(f"Turn {turn_id} is not in pending state")
    
    # Update turn
    turn.state = LiveTurnState.ACTIVE
    turn.started_at = datetime.utcnow()
    
    # Update session
    session.current_turn_id = turn_id
    
    await db.flush()
    
    # Append event
    await _append_event(
        session_id=session_id,
        event_type=LiveEventType.TURN_STARTED,
        payload={
            "turn_id": turn_id,
            "participant_id": turn.participant_id,
            "turn_type": turn.turn_type.value if turn.turn_type else None,
            "started_by": user_id,
            "started_at": turn.started_at.isoformat(),
            "allocated_seconds": turn.allocated_seconds
        },
        db=db
    )
    
    return turn, session


async def end_turn(
    session_id: int,
    turn_id: int,
    user_id: int,
    db: AsyncSession,
    expired: bool = False
) -> Tuple[LiveTurn, LiveCourtSession]:
    """
    End a turn.
    
    Rules:
    - turn.state must be active
    - set state = ended
    - set ended_at = utcnow
    - session.current_turn_id = null
    - append TURN_ENDED or TURN_EXPIRED event
    
    Args:
        session_id: Session containing the turn
        turn_id: Turn to end
        user_id: User ending the turn
        db: Database session
        expired: If True, mark as time expired
        
    Returns:
        Tuple of (LiveTurn, LiveCourtSession)
    """
    # Lock session
    result = await db.execute(
        select(LiveCourtSession)
        .where(LiveCourtSession.id == session_id)
        .with_for_update()
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise SessionNotFoundError(f"Session {session_id} not found")
    
    # Lock turn
    result = await db.execute(
        select(LiveTurn)
        .where(
            and_(
                LiveTurn.id == turn_id,
                LiveTurn.session_id == session_id
            )
        )
        .with_for_update()
    )
    turn = result.scalar_one_or_none()
    
    if not turn:
        raise TurnNotFoundError(f"Turn {turn_id} not found in session {session_id}")
    
    if turn.state != LiveTurnState.ACTIVE:
        raise InvalidStateTransitionError(f"Cannot end turn in state {turn.state.value}")
    
    # Update turn
    turn.state = LiveTurnState.ENDED
    turn.ended_at = datetime.utcnow()
    
    if expired:
        turn.violation_flag = True
    
    # Clear current turn from session
    if session.current_turn_id == turn_id:
        session.current_turn_id = None
    
    await db.flush()
    
    # Append event
    event_type = LiveEventType.TURN_EXPIRED if expired else LiveEventType.TURN_ENDED
    
    await _append_event(
        session_id=session_id,
        event_type=event_type,
        payload={
            "turn_id": turn_id,
            "ended_by": user_id,
            "ended_at": turn.ended_at.isoformat(),
            "elapsed_seconds": turn.get_elapsed_seconds(),
            "violation_flag": turn.violation_flag
        },
        db=db
    )
    
    return turn, session


# =============================================================================
# Timer Management
# =============================================================================

async def server_timer_tick(
    session_id: int,
    db: AsyncSession
) -> Optional[LiveTurn]:
    """
    Server-side timer tick.
    
    Rules:
    - Fetch active turn
    - elapsed = utcnow - started_at
    - remaining = allocated_seconds - elapsed
    - if remaining <= 0:
        - set violation_flag true
        - end turn
        - append TURN_EXPIRED event
    
    This must be idempotent - multiple ticks won't create duplicate expires.
    
    Args:
        session_id: Session to check
        db: Database session
        
    Returns:
        Turn if expired and ended, None otherwise
    """
    # Lock active turn
    result = await db.execute(
        select(LiveTurn)
        .where(
            and_(
                LiveTurn.session_id == session_id,
                LiveTurn.state == LiveTurnState.ACTIVE
            )
        )
        .with_for_update()
    )
    turn = result.scalar_one_or_none()
    
    if not turn:
        return None
    
    # Phase 6: Skip timer expiration if turn is paused for objection
    if turn.is_timer_paused:
        return None
    
    # Check if time expired
    if turn.is_time_expired():
        # Double-check turn is still active (idempotency)
        if turn.state == LiveTurnState.ACTIVE:
            # End turn as expired
            await end_turn(
                session_id=session_id,
                turn_id=turn.id,
                user_id=0,  # System user
                db=db,
                expired=True
            )
            return turn
    
    return None


# =============================================================================
# Session Completion
# =============================================================================

async def complete_session(
    session_id: int,
    user_id: int,
    db: AsyncSession
) -> LiveCourtSession:
    """
    Complete a live court session.
    
    Rules:
    - Only allowed if no active turn
    - status must be live or paused
    - SERIALIZABLE isolation
    - set status = completed
    - set ended_at = utcnow
    - append SESSION_COMPLETED event
    - freeze triggers prevent future mutations
    
    Args:
        session_id: Session to complete
        user_id: User completing
        db: Database session
        
    Returns:
        Completed LiveCourtSession
    """
    # Set SERIALIZABLE isolation
    await db.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
    
    # Lock session
    result = await db.execute(
        select(LiveCourtSession)
        .where(LiveCourtSession.id == session_id)
        .with_for_update()
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise SessionNotFoundError(f"Session {session_id} not found")
    
    # Check no active turn
    if session.current_turn_id is not None:
        raise ActiveTurnExistsError("Cannot complete session with active turn")
    
    if session.status not in (LiveCourtStatus.LIVE, LiveCourtStatus.PAUSED):
        raise InvalidStateTransitionError(f"Cannot complete session in status {session.status.value}")
    
    # Update session
    session.status = LiveCourtStatus.COMPLETED
    session.ended_at = datetime.utcnow()
    
    await db.flush()
    
    # Append event
    await _append_event(
        session_id=session_id,
        event_type=LiveEventType.SESSION_COMPLETED,
        payload={
            "session_id": session_id,
            "completed_by": user_id,
            "completed_at": session.ended_at.isoformat()
        },
        db=db
    )
    
    return session


# =============================================================================
# Verify Integrity
# =============================================================================

async def verify_event_chain(
    session_id: int,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Verify the integrity of the event chain.
    
    Recomputes all hashes from genesis and checks:
    - Each event's hash matches stored hash
    - Each event's previous_hash matches previous event's hash
    - No gaps in event_sequence
    - No hash mismatches
    
    O(n) time complexity where n = number of events.
    
    Args:
        session_id: Session to verify
        db: Database session
        
    Returns:
        Verification result dictionary
    """
    # Get all events ordered by sequence
    result = await db.execute(
        select(LiveEventLog)
        .where(LiveEventLog.session_id == session_id)
        .order_by(LiveEventLog.event_sequence.asc())
    )
    events = list(result.scalars().all())
    
    if not events:
        return {
            "session_id": session_id,
            "found": True,
            "frozen": False,
            "valid": True,
            "total_events": 0,
            "message": "No events to verify"
        }
    
    # Verify chain
    tampered_events = []
    previous_hash = "0" * 64
    expected_sequence = 1
    
    for event in events:
        # Check sequence continuity
        if event.event_sequence != expected_sequence:
            tampered_events.append({
                "event_sequence": event.event_sequence,
                "expected_sequence": expected_sequence,
                "issue": "Sequence gap or reordering detected"
            })
            break
        
        # Check previous hash
        if event.previous_hash != previous_hash:
            tampered_events.append({
                "event_sequence": event.event_sequence,
                "issue": "Previous hash mismatch - chain broken",
                "stored_previous": event.previous_hash,
                "expected_previous": previous_hash
            })
            break
        
        # Recompute hash
        computed_hash = LiveEventLog.compute_event_hash(
            previous_hash=event.previous_hash,
            event_sequence=event.event_sequence,
            event_type=event.event_type,
            payload=event.event_payload_json,
            created_at=event.created_at
        )
        
        # Check event hash
        if event.event_hash != computed_hash:
            tampered_events.append({
                "event_sequence": event.event_sequence,
                "issue": "Event hash mismatch - tampering detected",
                "stored_hash": event.event_hash,
                "computed_hash": computed_hash
            })
            break
        
        # Update for next iteration
        previous_hash = event.event_hash
        expected_sequence += 1
    
    is_valid = len(tampered_events) == 0
    
    return {
        "session_id": session_id,
        "found": True,
        "valid": is_valid,
        "total_events": len(events),
        "tampered_events": tampered_events if tampered_events else None,
        "tamper_detected": not is_valid,
        "message": "Chain verified successfully" if is_valid else "Tampering detected"
    }


# =============================================================================
# Query Functions
# =============================================================================

async def get_session_by_id(
    session_id: int,
    db: AsyncSession
) -> Optional[LiveCourtSession]:
    """Get session by ID."""
    result = await db.execute(
        select(LiveCourtSession).where(LiveCourtSession.id == session_id)
    )
    return result.scalar_one_or_none()


async def get_turns_by_session(
    session_id: int,
    db: AsyncSession
) -> List[LiveTurn]:
    """Get all turns for a session."""
    result = await db.execute(
        select(LiveTurn)
        .where(LiveTurn.session_id == session_id)
        .order_by(LiveTurn.id.asc())
    )
    return list(result.scalars().all())


async def get_events_by_session(
    session_id: int,
    db: AsyncSession,
    since_sequence: int = 0
) -> List[LiveEventLog]:
    """Get events for a session, optionally since a specific sequence."""
    result = await db.execute(
        select(LiveEventLog)
        .where(
            and_(
                LiveEventLog.session_id == session_id,
                LiveEventLog.event_sequence > since_sequence
            )
        )
        .order_by(LiveEventLog.event_sequence.asc())
    )
    return list(result.scalars().all())


async def get_active_turn(
    session_id: int,
    db: AsyncSession
) -> Optional[LiveTurn]:
    """Get the active turn for a session."""
    result = await db.execute(
        select(LiveTurn)
        .where(
            and_(
                LiveTurn.session_id == session_id,
                LiveTurn.state == LiveTurnState.ACTIVE
            )
        )
    )
    return result.scalar_one_or_none()


async def get_timer_state(
    session_id: int,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Get the current timer state for a session.
    
    Returns:
        Timer state including remaining time, elapsed time, violation status
    """
    # Get session
    result = await db.execute(
        select(LiveCourtSession).where(LiveCourtSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    
    if not session:
        return {
            "session_id": session_id,
            "found": False,
            "error": "Session not found"
        }
    
    # Get active turn
    active_turn = await get_active_turn(session_id, db)
    
    if not active_turn:
        return {
            "session_id": session_id,
            "session_status": session.status.value,
            "has_active_turn": False,
            "message": "No active turn"
        }
    
    return {
        "session_id": session_id,
        "session_status": session.status.value,
        "has_active_turn": True,
        "turn_id": active_turn.id,
        "participant_id": active_turn.participant_id,
        "turn_type": active_turn.turn_type.value if active_turn.turn_type else None,
        "allocated_seconds": active_turn.allocated_seconds,
        "elapsed_seconds": active_turn.get_elapsed_seconds(),
        "remaining_seconds": active_turn.get_remaining_seconds(),
        "violation_flag": active_turn.violation_flag,
        "started_at": active_turn.started_at.isoformat() if active_turn.started_at else None
    }
