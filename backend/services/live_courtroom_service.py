"""
Live Courtroom Service Layer — Phase 8

Real-time session management with:
- Deterministic turn state machine
- Server-authoritative timer enforcement
- Objection workflow engine
- Live judge scoring system
- Append-only event log with hash chaining

Security:
- All numeric values use Decimal (never float)
- Row-level locking with FOR UPDATE
- Institution-scoped queries
- Judge conflict detection
- Strict ENUM validation

Concurrency:
- PostgreSQL-compatible row locking
- SERIALIZABLE isolation for critical transitions
- Idempotent operations
"""
import json
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any, List

from sqlalchemy import select, and_, or_, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.orm.live_courtroom import (
    LiveCourtSession, LiveTurn, LiveObjection, LiveJudgeScore, LiveSessionEvent,
    LiveSessionStatus, LiveTurnType, ObjectionType, ObjectionStatus,
    VisibilityMode, ScoreVisibility, LiveScoreType, LiveEventType,
    compute_event_hash
)
from backend.orm.national_network import TournamentMatch, SideType, PanelJudge
from backend.orm.user import User, UserRole
from backend.orm.classroom_session import ClassroomSession, ClassroomParticipant


# =============================================================================
# Custom Exceptions
# =============================================================================

class LiveCourtroomError(Exception):
    """Base exception for live courtroom errors."""
    pass


class SessionConflictError(LiveCourtroomError):
    """Raised when there's a conflict with session state."""
    pass


class TurnConflictError(LiveCourtroomError):
    """Raised when there's a conflict with turn state."""
    pass


class ObjectionError(LiveCourtroomError):
    """Raised when there's an objection-related error."""
    pass


class JudgeConflictError(LiveCourtroomError):
    """Raised when judge has conflict of interest."""
    pass


class TimerViolationError(LiveCourtroomError):
    """Raised when time limit is violated."""
    pass


# =============================================================================
# Helper Functions
# =============================================================================

async def get_last_event_info(
    live_session_id: int,
    db: AsyncSession
) -> tuple[str, int]:
    """
    Get the hash and sequence of the last event in a session's event log.
    
    Elite Hardening: Returns both hash and sequence for deterministic ordering.
    
    Args:
        live_session_id: ID of the live session
        db: Database session
        
    Returns:
        Tuple of (hash, sequence) - hash is "GENESIS" if no events, sequence is 0 if no events
    """
    result = await db.execute(
        select(LiveSessionEvent)
        .where(LiveSessionEvent.live_session_id == live_session_id)
        .order_by(LiveSessionEvent.event_sequence.desc())
        .limit(1)
    )
    last_event = result.scalar_one_or_none()
    
    if last_event:
        return last_event.event_hash, last_event.event_sequence
    return "GENESIS", 0


# Legacy function for backward compatibility
async def get_last_event_hash(
    live_session_id: int,
    db: AsyncSession
) -> str:
    """Get the hash of the last event (legacy wrapper)."""
    hash, _ = await get_last_event_info(live_session_id, db)
    return hash


async def append_live_event(
    live_session_id: int,
    event_type: str,
    event_payload: Optional[Dict[str, Any]],
    db: AsyncSession
) -> LiveSessionEvent:
    """
    Append a new event to the live session event log (Elite Hardened).
    
    Elite Hardening:
    - Uses event_sequence for deterministic ordering
    - Queries MAX(event_sequence) FOR UPDATE to prevent race conditions
    - Hash formula includes: previous_hash + sequence + payload + timestamp
    
    Args:
        live_session_id: ID of the live session
        event_type: Type of event (from LiveEventType)
        event_payload: Optional payload dictionary
        db: Database session
        
    Returns:
        Created LiveSessionEvent
    """
    # Elite Hardening: Lock and get next sequence atomically
    result = await db.execute(
        select(func.max(LiveSessionEvent.event_sequence))
        .where(LiveSessionEvent.live_session_id == live_session_id)
        .with_for_update()
    )
    max_sequence = result.scalar() or 0
    next_sequence = max_sequence + 1
    
    # Get previous hash based on last event
    if max_sequence > 0:
        result = await db.execute(
            select(LiveSessionEvent.event_hash)
            .where(
                and_(
                    LiveSessionEvent.live_session_id == live_session_id,
                    LiveSessionEvent.event_sequence == max_sequence
                )
            )
        )
        previous_hash = result.scalar() or "GENESIS"
    else:
        previous_hash = "GENESIS"
    
    # Create timestamp (UTC)
    created_at = datetime.utcnow()
    timestamp_str = created_at.isoformat()
    
    # Elite Hardening: Compute hash with sequence
    event_hash = compute_event_hash(
        previous_hash,
        next_sequence,
        event_payload or {},
        timestamp_str
    )
    
    # Create event with sequence
    event = LiveSessionEvent(
        live_session_id=live_session_id,
        event_sequence=next_sequence,
        event_type=event_type,
        event_payload_json=json.dumps(event_payload, sort_keys=True) if event_payload else None,
        event_hash=event_hash,
        previous_hash=previous_hash,
        created_at=created_at
    )
    
    db.add(event)
    await db.flush()
    
    return event


async def get_session_with_lock(
    live_session_id: int,
    db: AsyncSession
) -> Optional[LiveCourtSession]:
    """
    Get a live session with row-level locking (FOR UPDATE).
    
    This ensures exclusive access for state transitions.
    
    Args:
        live_session_id: ID of the live session
        db: Database session
        
    Returns:
        Locked LiveCourtSession or None
    """
    result = await db.execute(
        select(LiveCourtSession)
        .where(LiveCourtSession.id == live_session_id)
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def check_judge_conflict(
    live_session_id: int,
    judge_id: int,
    db: AsyncSession
) -> bool:
    """
    Check if judge has a conflict of interest for this session.
    
    A judge has a conflict if they are from the same institution as
    any participant in a tournament match.
    
    Args:
        live_session_id: ID of the live session
        judge_id: ID of the judge
        db: Database session
        
    Returns:
        True if judge has conflict, False otherwise
    """
    # Get the session
    result = await db.execute(
        select(LiveCourtSession).where(LiveCourtSession.id == live_session_id)
    )
    session = result.scalar_one_or_none()
    
    if not session:
        return False
    
    # Get judge's institution
    result = await db.execute(
        select(User).where(User.id == judge_id)
    )
    judge = result.scalar_one_or_none()
    
    if not judge:
        return False
    
    judge_institution_id = judge.institution_id
    
    # Check if this is a tournament match
    if session.tournament_match_id:
        # Get the match to find competing institutions
        result = await db.execute(
            select(TournamentMatch).where(
                TournamentMatch.id == session.tournament_match_id
            )
        )
        match = result.scalar_one_or_none()
        
        if match:
            # Get teams and their institutions
            from backend.orm.national_network import TournamentTeam
            
            result = await db.execute(
                select(TournamentTeam).where(
                    TournamentTeam.id.in_([
                        match.petitioner_team_id,
                        match.respondent_team_id
                    ])
                )
            )
            teams = list(result.scalars().all())
            
            for team in teams:
                if team.institution_id == judge_institution_id:
                    return True
    
    return False


async def count_pending_objections(
    live_session_id: int,
    db: AsyncSession
) -> int:
    """
    Count pending objections in a live session.
    
    Args:
        live_session_id: ID of the live session
        db: Database session
        
    Returns:
        Number of pending objections
    """
    result = await db.execute(
        select(func.count(LiveObjection.id))
        .join(LiveTurn, LiveObjection.live_turn_id == LiveTurn.id)
        .where(
            and_(
                LiveTurn.live_session_id == live_session_id,
                LiveObjection.status == ObjectionStatus.PENDING
            )
        )
    )
    return result.scalar() or 0


# =============================================================================
# A. start_live_session()
# =============================================================================

async def start_live_session(
    session_id: Optional[int],
    tournament_match_id: Optional[int],
    institution_id: int,
    created_by: int,
    db: AsyncSession,
    visibility_mode: str = VisibilityMode.INSTITUTION,
    score_visibility: str = ScoreVisibility.AFTER_COMPLETION
) -> LiveCourtSession:
    """
    Start a new live courtroom session.
    
    Args:
        session_id: Optional FK to classroom_sessions
        tournament_match_id: Optional FK to tournament_matches
        institution_id: Institution hosting the session
        created_by: User ID creating the session
        db: Database session
        visibility_mode: Visibility mode (default: INSTITUTION)
        score_visibility: When scores are visible (default: AFTER_COMPLETION)
        
    Returns:
        Created LiveCourtSession
        
    Raises:
        LiveCourtroomError: If neither session_id nor tournament_match_id provided
        SessionConflictError: If a live session already exists for this match
    """
    # Validate inputs
    if not session_id and not tournament_match_id:
        raise LiveCourtroomError(
            "Must provide either session_id or tournament_match_id"
        )
    
    # Check for existing live session (for tournament matches)
    if tournament_match_id:
        result = await db.execute(
            select(LiveCourtSession).where(
                and_(
                    LiveCourtSession.tournament_match_id == tournament_match_id,
                    LiveCourtSession.status == LiveSessionStatus.LIVE
                )
            )
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            raise SessionConflictError(
                f"A live session already exists for match {tournament_match_id}"
            )
    
    # Create the session
    live_session = LiveCourtSession(
        session_id=session_id,
        tournament_match_id=tournament_match_id,
        institution_id=institution_id,
        status=LiveSessionStatus.LIVE,
        visibility_mode=visibility_mode,
        score_visibility=score_visibility,
        started_at=datetime.utcnow(),
        created_at=datetime.utcnow()
    )
    
    db.add(live_session)
    await db.flush()
    
    # Append SESSION_STARTED event
    await append_live_event(
        live_session_id=live_session.id,
        event_type=LiveEventType.SESSION_STARTED,
        event_payload={
            "session_id": session_id,
            "tournament_match_id": tournament_match_id,
            "institution_id": institution_id,
            "created_by": created_by,
            "visibility_mode": visibility_mode,
            "score_visibility": score_visibility
        },
        db=db
    )
    
    return live_session


# =============================================================================
# B. start_turn()
# =============================================================================

async def start_turn(
    live_session_id: int,
    participant_id: int,
    side: str,
    turn_type: str,
    allocated_seconds: int,
    db: AsyncSession
) -> LiveTurn:
    """
    Start a new turn in a live session.
    
    Uses row-level locking to ensure only one active turn at a time.
    
    Args:
        live_session_id: ID of the live session
        participant_id: ID of the participant giving the turn
        side: Side (PETITIONER or RESPONDENT)
        turn_type: Type of turn (OPENING, ARGUMENT, REBUTTAL, SUR_REBUTTAL)
        allocated_seconds: Time allocated for this turn
        db: Database session
        
    Returns:
        Created LiveTurn
        
    Raises:
        SessionConflictError: If session is not in LIVE status
        TurnConflictError: If another turn is already active
    """
    # Lock the session row
    live_session = await get_session_with_lock(live_session_id, db)
    
    if not live_session:
        raise LiveCourtroomError(f"Live session {live_session_id} not found")
    
    if live_session.status != LiveSessionStatus.LIVE:
        raise SessionConflictError(
            f"Cannot start turn: session is {live_session.status}"
        )
    
    # Check for active turn
    if live_session.current_turn_id:
        result = await db.execute(
            select(LiveTurn).where(LiveTurn.id == live_session.current_turn_id)
        )
        current_turn = result.scalar_one_or_none()
        
        if current_turn and current_turn.is_active():
            raise TurnConflictError(
                f"Cannot start new turn: turn {current_turn.id} is still active"
            )
    
    # Check for pending objections
    pending_count = await count_pending_objections(live_session_id, db)
    if pending_count > 0:
        raise ObjectionError(
            f"Cannot start turn: {pending_count} pending objection(s)"
        )
    
    # Create the turn
    turn = LiveTurn(
        live_session_id=live_session_id,
        participant_id=participant_id,
        side=side,
        turn_type=turn_type,
        allocated_seconds=allocated_seconds,
        actual_seconds=0,
        started_at=datetime.utcnow(),
        is_interrupted=False,
        violation_flag=False,
        created_at=datetime.utcnow()
    )
    
    db.add(turn)
    await db.flush()
    
    # Update session with current turn
    live_session.current_turn_id = turn.id
    live_session.current_speaker_id = participant_id
    live_session.current_side = side
    
    # Append TURN_STARTED event
    await append_live_event(
        live_session_id=live_session_id,
        event_type=LiveEventType.TURN_STARTED,
        event_payload={
            "turn_id": turn.id,
            "participant_id": participant_id,
            "side": side,
            "turn_type": turn_type,
            "allocated_seconds": allocated_seconds,
            "started_at": turn.started_at.isoformat()
        },
        db=db
    )
    
    return turn


# =============================================================================
# C. server_authoritative_timer()
# =============================================================================

async def get_timer_status(
    turn_id: int,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Get the server-authoritative timer status for a turn.
    
    This function NEVER trusts frontend timer values.
    All timing calculations are done server-side.
    
    Args:
        turn_id: ID of the turn
        db: Database session
        
    Returns:
        Dictionary with timer status
    """
    result = await db.execute(
        select(LiveTurn).where(LiveTurn.id == turn_id)
    )
    turn = result.scalar_one_or_none()
    
    if not turn:
        raise LiveCourtroomError(f"Turn {turn_id} not found")
    
    if not turn.is_active():
        return {
            "turn_id": turn_id,
            "is_active": False,
            "elapsed_seconds": turn.actual_seconds or 0,
            "allocated_seconds": turn.allocated_seconds,
            "remaining_seconds": 0,
            "is_expired": False,
            "violation_flag": turn.violation_flag
        }
    
    # Server-authoritative calculation
    elapsed_seconds = turn.get_elapsed_seconds()
    remaining_seconds = max(0, turn.allocated_seconds - elapsed_seconds)
    is_expired = elapsed_seconds >= turn.allocated_seconds
    
    return {
        "turn_id": turn_id,
        "is_active": True,
        "elapsed_seconds": elapsed_seconds,
        "allocated_seconds": turn.allocated_seconds,
        "remaining_seconds": remaining_seconds,
        "is_expired": is_expired,
        "violation_flag": turn.violation_flag
    }


async def check_and_handle_timer_expiration(
    turn_id: int,
    db: AsyncSession
) -> Optional[LiveTurn]:
    """
    Check if a turn has expired and handle auto-end (Elite Hardened).
    
    Elite Hardening:
    - Uses FOR UPDATE lock on LiveTurn to prevent concurrent expiration
    - Returns None if turn already ended (idempotent)
    - Exactly one TURN_EXPIRED event per expired turn
    
    Args:
        turn_id: ID of the turn
        db: Database session
        
    Returns:
        Updated LiveTurn if expired and ended, None otherwise
    """
    # Elite Hardening: Lock turn row first to prevent race conditions
    result = await db.execute(
        select(LiveTurn)
        .where(
            and_(
                LiveTurn.id == turn_id,
                LiveTurn.ended_at.is_(None)  # Only select if not already ended
            )
        )
        .with_for_update()
    )
    turn = result.scalar_one_or_none()
    
    # Elite Hardening: If no row returned, turn already ended
    if not turn:
        return None
    
    if not turn.is_active():
        return None
    
    # Check expiration
    elapsed = turn.get_elapsed_seconds()
    
    if elapsed >= turn.allocated_seconds:
        # Turn has expired - auto end
        now = datetime.utcnow()
        turn.ended_at = now
        turn.actual_seconds = elapsed
        turn.violation_flag = True
        
        # Lock session to update
        result = await db.execute(
            select(LiveCourtSession)
            .where(LiveCourtSession.id == turn.live_session_id)
            .with_for_update()
        )
        live_session = result.scalar_one()
        
        # Clear current turn from session
        if live_session.current_turn_id == turn_id:
            live_session.current_turn_id = None
        
        # Append TURN_EXPIRED event
        await append_live_event(
            live_session_id=turn.live_session_id,
            event_type=LiveEventType.TURN_EXPIRED,
            event_payload={
                "turn_id": turn_id,
                "elapsed_seconds": elapsed,
                "allocated_seconds": turn.allocated_seconds,
                "violation": True,
                "ended_at": now.isoformat()
            },
            db=db
        )
        
        await db.flush()
        return turn
    
    return None


# =============================================================================
# D. raise_objection()
# =============================================================================

async def raise_objection(
    live_turn_id: int,
    raised_by_participant_id: int,
    objection_type: str,
    db: AsyncSession,
    max_objections_per_turn: int = 3
) -> LiveObjection:
    """
    Raise an objection during a turn.
    
    This pauses the session and requires judge resolution.
    
    Args:
        live_turn_id: ID of the turn being objected to
        raised_by_participant_id: ID of participant raising objection
        objection_type: Type of objection
        db: Database session
        max_objections_per_turn: Maximum objections allowed per turn
        
    Returns:
        Created LiveObjection
        
    Raises:
        ObjectionError: If participant is the speaker, or max objections reached
    """
    # Lock the turn and session
    result = await db.execute(
        select(LiveTurn, LiveCourtSession)
        .join(LiveCourtSession, LiveTurn.live_session_id == LiveCourtSession.id)
        .where(LiveTurn.id == live_turn_id)
        .with_for_update(of=LiveCourtSession)
    )
    row = result.one_or_none()
    
    if not row:
        raise LiveCourtroomError(f"Turn {live_turn_id} not found")
    
    turn, live_session = row
    
    # Validate turn is active
    if not turn.is_active():
        raise ObjectionError("Cannot raise objection: turn is not active")
    
    # Validate objector is not the speaker
    if turn.participant_id == raised_by_participant_id:
        raise ObjectionError("Speaker cannot object to their own turn")
    
    # Check if objector is on opposing side
    result = await db.execute(
        select(ClassroomParticipant).where(
            ClassroomParticipant.id == raised_by_participant_id
        )
    )
    objector = result.scalar_one_or_none()
    
    if not objector:
        raise LiveCourtroomError(f"Participant {raised_by_participant_id} not found")
    
    # Count objections in this turn
    result = await db.execute(
        select(func.count(LiveObjection.id))
        .where(LiveObjection.live_turn_id == live_turn_id)
    )
    objection_count = result.scalar() or 0
    
    if objection_count >= max_objections_per_turn:
        raise ObjectionError(
            f"Maximum objections ({max_objections_per_turn}) reached for this turn"
        )
    
    # Create the objection
    objection = LiveObjection(
        live_turn_id=live_turn_id,
        raised_by_participant_id=raised_by_participant_id,
        objection_type=objection_type,
        status=ObjectionStatus.PENDING,
        resolved_by_judge_id=None,
        resolved_at=None,
        created_at=datetime.utcnow()
    )
    
    db.add(objection)
    
    # Pause the session
    if live_session.status == LiveSessionStatus.LIVE:
        live_session.status = LiveSessionStatus.PAUSED
        
        # Mark turn as interrupted
        turn.is_interrupted = True
        
        # Append events
        await append_live_event(
            live_session_id=live_session.id,
            event_type=LiveEventType.OBJECTION_RAISED,
            event_payload={
                "objection_id": objection.id,
                "turn_id": live_turn_id,
                "raised_by": raised_by_participant_id,
                "objection_type": objection_type,
                "elapsed_at_objection": turn.get_elapsed_seconds()
            },
            db=db
        )
        
        await append_live_event(
            live_session_id=live_session.id,
            event_type=LiveEventType.SESSION_PAUSED,
            event_payload={
                "reason": "objection_raised",
                "objection_id": objection.id
            },
            db=db
        )
    
    await db.flush()
    return objection


# =============================================================================
# E. resolve_objection()
# =============================================================================

async def resolve_objection(
    objection_id: int,
    judge_id: int,
    status: str,  # SUSTAINED or OVERRULED
    db: AsyncSession
) -> LiveObjection:
    """
    Resolve a pending objection (judge-only).
    
    Args:
        objection_id: ID of the objection to resolve
        judge_id: ID of the judge resolving the objection
        status: Resolution status (SUSTAINED or OVERRULED)
        db: Database session
        
    Returns:
        Updated LiveObjection
        
    Raises:
        ObjectionError: If objection is not pending
        LiveCourtroomError: If judge has conflict
    """
    # Validate status
    if status not in [ObjectionStatus.SUSTAINED, ObjectionStatus.OVERRULED]:
        raise ObjectionError(f"Invalid resolution status: {status}")
    
    # Lock the objection, turn, and session
    result = await db.execute(
        select(LiveObjection, LiveTurn, LiveCourtSession)
        .join(LiveTurn, LiveObjection.live_turn_id == LiveTurn.id)
        .join(LiveCourtSession, LiveTurn.live_session_id == LiveCourtSession.id)
        .where(LiveObjection.id == objection_id)
        .with_for_update(of=[LiveObjection, LiveCourtSession])
    )
    row = result.one_or_none()
    
    if not row:
        raise LiveCourtroomError(f"Objection {objection_id} not found")
    
    objection, turn, live_session = row
    
    # Check objection is pending
    if objection.status != ObjectionStatus.PENDING:
        raise ObjectionError(f"Objection is already {objection.status}")
    
    # Check judge conflict (for tournament matches)
    if live_session.tournament_match_id:
        has_conflict = await check_judge_conflict(live_session.id, judge_id, db)
        if has_conflict:
            raise JudgeConflictError(
                "Judge cannot resolve objections for matches involving their institution"
            )
    
    # Resolve the objection
    now = datetime.utcnow()
    objection.status = status
    objection.resolved_by_judge_id = judge_id
    objection.resolved_at = now
    
    # Resume the session if no more pending objections
    remaining_pending = await count_pending_objections(live_session.id, db)
    
    if remaining_pending == 0 and live_session.status == LiveSessionStatus.PAUSED:
        live_session.status = LiveSessionStatus.LIVE
        
        # Append SESSION_RESUMED event
        await append_live_event(
            live_session_id=live_session.id,
            event_type=LiveEventType.SESSION_RESUMED,
            event_payload={
                "reason": "objection_resolved",
                "objection_id": objection_id,
                "resolution": status
            },
            db=db
        )
    
    # Append OBJECTION_RESOLVED event
    await append_live_event(
        live_session_id=live_session.id,
        event_type=LiveEventType.OBJECTION_RESOLVED,
        event_payload={
            "objection_id": objection_id,
            "judge_id": judge_id,
            "resolution": status,
            "resolved_at": now.isoformat()
        },
        db=db
    )
    
    await db.flush()
    return objection


# =============================================================================
# F. submit_live_score()
# =============================================================================

async def submit_live_score(
    live_session_id: int,
    judge_id: int,
    participant_id: int,
    score_type: str,
    provisional_score: Decimal,
    db: AsyncSession,
    comment: Optional[str] = None
) -> LiveJudgeScore:
    """
    Submit a judge's score during a live session (judge-only).
    
    Args:
        live_session_id: ID of the live session
        judge_id: ID of the judge submitting the score
        participant_id: ID of the participant being scored
        score_type: Type of score (ARGUMENT, REBUTTAL, COURTROOM_ETIQUETTE)
        provisional_score: Score value (0.00 - 100.00)
        db: Database session
        comment: Optional judge comment
        
    Returns:
        Created LiveJudgeScore
        
    Raises:
        JudgeConflictError: If judge has conflict of interest
        LiveCourtroomError: If session is not active
    """
    # Validate score type
    allowed_types = [
        LiveScoreType.ARGUMENT,
        LiveScoreType.REBUTTAL,
        LiveScoreType.COURTROOM_ETIQUETTE
    ]
    if score_type not in allowed_types:
        raise LiveCourtroomError(f"Invalid score type: {score_type}")
    
    # Validate score is Decimal
    if not isinstance(provisional_score, Decimal):
        provisional_score = Decimal(str(provisional_score))
    
    # Check score range
    if provisional_score < Decimal("0") or provisional_score > Decimal("100"):
        raise LiveCourtroomError("Score must be between 0.00 and 100.00")
    
    # Check session exists and is active
    result = await db.execute(
        select(LiveCourtSession).where(LiveCourtSession.id == live_session_id)
    )
    live_session = result.scalar_one_or_none()
    
    if not live_session:
        raise LiveCourtroomError(f"Live session {live_session_id} not found")
    
    if live_session.status not in [LiveSessionStatus.LIVE, LiveSessionStatus.PAUSED]:
        raise LiveCourtroomError(
            f"Cannot submit scores: session is {live_session.status}"
        )
    
    # Check judge conflict (for tournament matches)
    if live_session.tournament_match_id:
        has_conflict = await check_judge_conflict(live_session_id, judge_id, db)
        if has_conflict:
            raise JudgeConflictError(
                "Judge cannot score participants from their own institution"
            )
    
    # Check for existing score (update or create)
    result = await db.execute(
        select(LiveJudgeScore).where(
            and_(
                LiveJudgeScore.live_session_id == live_session_id,
                LiveJudgeScore.judge_id == judge_id,
                LiveJudgeScore.participant_id == participant_id,
                LiveJudgeScore.score_type == score_type
            )
        )
    )
    existing_score = result.scalar_one_or_none()
    
    if existing_score:
        # Update existing score
        existing_score.provisional_score = provisional_score
        existing_score.comment = comment
        score = existing_score
    else:
        # Create new score
        score = LiveJudgeScore(
            live_session_id=live_session_id,
            judge_id=judge_id,
            participant_id=participant_id,
            score_type=score_type,
            provisional_score=provisional_score,
            comment=comment,
            created_at=datetime.utcnow()
        )
        db.add(score)
    
    await db.flush()
    
    # Append SCORE_SUBMITTED event
    await append_live_event(
        live_session_id=live_session_id,
        event_type=LiveEventType.SCORE_SUBMITTED,
        event_payload={
            "score_id": score.id,
            "judge_id": judge_id,
            "participant_id": participant_id,
            "score_type": score_type,
            "provisional_score": str(provisional_score),
            "is_update": existing_score is not None
        },
        db=db
    )
    
    return score


# =============================================================================
# G. complete_live_session()
# =============================================================================

async def complete_live_session(
    live_session_id: int,
    completed_by: int,
    db: AsyncSession
) -> LiveCourtSession:
    """
    Complete a live courtroom session.
    
    Args:
        live_session_id: ID of the live session
        completed_by: User ID completing the session
        db: Database session
        
    Returns:
        Completed LiveCourtSession
        
    Raises:
        SessionConflictError: If session is not active or has pending objections
        LiveCourtroomError: If active turn exists
    """
    # Lock the session
    live_session = await get_session_with_lock(live_session_id, db)
    
    if not live_session:
        raise LiveCourtroomError(f"Live session {live_session_id} not found")
    
    if live_session.status == LiveSessionStatus.COMPLETED:
        raise SessionConflictError("Session is already completed")
    
    if live_session.status not in [LiveSessionStatus.LIVE, LiveSessionStatus.PAUSED]:
        raise SessionConflictError(
            f"Cannot complete session: current status is {live_session.status}"
        )
    
    # Check for pending objections
    pending_count = await count_pending_objections(live_session_id, db)
    if pending_count > 0:
        raise SessionConflictError(
            f"Cannot complete session: {pending_count} pending objection(s)"
        )
    
    # Check for active turn
    if live_session.current_turn_id:
        result = await db.execute(
            select(LiveTurn).where(LiveTurn.id == live_session.current_turn_id)
        )
        current_turn = result.scalar_one_or_none()
        
        if current_turn and current_turn.is_active():
            raise SessionConflictError(
                f"Cannot complete session: turn {current_turn.id} is still active"
            )
    
    # Complete the session
    now = datetime.utcnow()
    live_session.status = LiveSessionStatus.COMPLETED
    live_session.ended_at = now
    live_session.current_turn_id = None
    live_session.current_speaker_id = None
    
    # Append SESSION_COMPLETED event
    await append_live_event(
        live_session_id=live_session_id,
        event_type=LiveEventType.SESSION_COMPLETED,
        event_payload={
            "completed_by": completed_by,
            "ended_at": now.isoformat(),
            "total_turns": await get_session_turn_count(live_session_id, db),
            "total_objections": await get_session_objection_count(live_session_id, db),
            "total_scores": await get_session_score_count(live_session_id, db)
        },
        db=db
    )
    
    await db.flush()
    
    # Note: Phase 4 evaluation pipeline trigger would happen here
    # This is a placeholder for the actual trigger
    # await trigger_phase4_evaluation(live_session_id, db)
    
    return live_session


# =============================================================================
# Helper Query Functions
# =============================================================================

async def get_session_turn_count(live_session_id: int, db: AsyncSession) -> int:
    """Get the total number of turns in a session."""
    result = await db.execute(
        select(func.count(LiveTurn.id))
        .where(LiveTurn.live_session_id == live_session_id)
    )
    return result.scalar() or 0


async def get_session_objection_count(live_session_id: int, db: AsyncSession) -> int:
    """Get the total number of objections in a session."""
    result = await db.execute(
        select(func.count(LiveObjection.id))
        .join(LiveTurn, LiveObjection.live_turn_id == LiveTurn.id)
        .where(LiveTurn.live_session_id == live_session_id)
    )
    return result.scalar() or 0


async def get_session_score_count(live_session_id: int, db: AsyncSession) -> int:
    """Get the total number of scores in a session."""
    result = await db.execute(
        select(func.count(LiveJudgeScore.id))
        .where(LiveJudgeScore.live_session_id == live_session_id)
    )
    return result.scalar() or 0


async def get_session_state(
    live_session_id: int,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Get the complete state of a live session.
    
    Returns snapshot including current turn, pending objections, and recent events.
    """
    # Get session
    result = await db.execute(
        select(LiveCourtSession).where(LiveCourtSession.id == live_session_id)
    )
    session = result.scalar_one_or_none()
    
    if not session:
        return None
    
    state = {
        "session": session.to_dict(),
        "current_turn": None,
        "pending_objections": [],
        "recent_events": []
    }
    
    # Get current turn
    if session.current_turn_id:
        result = await db.execute(
            select(LiveTurn).where(LiveTurn.id == session.current_turn_id)
        )
        turn = result.scalar_one_or_none()
        if turn:
            state["current_turn"] = turn.to_dict()
            state["timer"] = await get_timer_status(turn.id, db)
    
    # Get pending objections
    result = await db.execute(
        select(LiveObjection)
        .join(LiveTurn, LiveObjection.live_turn_id == LiveTurn.id)
        .where(
            and_(
                LiveTurn.live_session_id == live_session_id,
                LiveObjection.status == ObjectionStatus.PENDING
            )
        )
        .order_by(LiveObjection.created_at.asc())
    )
    objections = list(result.scalars().all())
    state["pending_objections"] = [o.to_dict() for o in objections]
    
    # Get recent events (last 50)
    result = await db.execute(
        select(LiveSessionEvent)
        .where(LiveSessionEvent.live_session_id == live_session_id)
        .order_by(LiveSessionEvent.id.desc())
        .limit(50)
    )
    events = list(result.scalars().all())
    state["recent_events"] = [e.to_dict() for e in reversed(events)]
    
    return state


async def get_events_since(
    live_session_id: int,
    last_event_id: int,
    db: AsyncSession
) -> List[LiveSessionEvent]:
    """
    Get all events after a specific event ID for replay.
    
    Used for WebSocket reconnect scenarios.
    """
    result = await db.execute(
        select(LiveSessionEvent)
        .where(
            and_(
                LiveSessionEvent.live_session_id == live_session_id,
                LiveSessionEvent.id > last_event_id
            )
        )
        .order_by(LiveSessionEvent.id.asc())
    )
    return list(result.scalars().all())


# =============================================================================
# Event Chain Verification
# =============================================================================

async def verify_live_event_chain(
    live_session_id: int,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Verify the integrity of the live session event chain.
    
    Returns verification results including:
    - is_valid: True if chain is intact
    - total_events: Number of events verified
    - invalid_events: List of events with hash mismatches
    - errors: Description of any errors found
    
    Args:
        live_session_id: ID of the live session
        db: Database session
        
    Returns:
        Dictionary with verification results
    """
    result = await db.execute(
        select(LiveSessionEvent)
        .where(LiveSessionEvent.live_session_id == live_session_id)
        .order_by(LiveSessionEvent.id.asc())
    )
    events = list(result.scalars().all())
    
    if not events:
        return {
            "is_valid": True,
            "total_events": 0,
            "first_event_id": None,
            "last_event_id": None,
            "invalid_events": [],
            "errors": None
        }
    
    invalid_events = []
    errors = []
    
    for i, event in enumerate(events):
        # Check first event has GENESIS previous_hash
        if i == 0:
            if event.previous_hash != "GENESIS":
                invalid_events.append({
                    "event_id": event.id,
                    "issue": "First event must have GENESIS previous_hash",
                    "expected": "GENESIS",
                    "actual": event.previous_hash
                })
        else:
            # Check chain link
            prev_event = events[i - 1]
            if event.previous_hash != prev_event.event_hash:
                invalid_events.append({
                    "event_id": event.id,
                    "issue": "Broken chain link",
                    "expected": prev_event.event_hash,
                    "actual": event.previous_hash
                })
        
        # Verify hash
        if not event.verify_hash():
            invalid_events.append({
                "event_id": event.id,
                "issue": "Hash mismatch",
                "stored_hash": event.event_hash,
                "computed_hash": compute_event_hash(
                    event.previous_hash,
                    event.get_payload() or {},
                    event.created_at.isoformat() if event.created_at else ""
                )
            })
    
    is_valid = len(invalid_events) == 0
    
    return {
        "is_valid": is_valid,
        "total_events": len(events),
        "first_event_id": events[0].id,
        "last_event_id": events[-1].id,
        "invalid_events": invalid_events,
        "errors": "; ".join([e["issue"] for e in invalid_events]) if invalid_events else None
    }
