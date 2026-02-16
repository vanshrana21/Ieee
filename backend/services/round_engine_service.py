"""
Round Engine Service — Phase 3

Core service for managing classroom rounds, turns, timing, and auto-advance.
Implements deterministic speaking order, server-side timers, and audit logging.

Design:
- SQLite-compatible using asyncio.Lock per session for serialization
- Deterministic turn ordering based on participant sides
- Server-authoritative timing (no client trust)
- Full audit trail for all actions
- Retry logic for race condition handling
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple

from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.orm.classroom_session import ClassroomSession, ClassroomParticipant
from backend.orm.classroom_round import ClassroomRound
from backend.orm.classroom_turn import ClassroomTurn, ClassroomTurnAudit

logger = logging.getLogger(__name__)

# Global locks for SQLite concurrency (one lock per session_id)
_session_locks: Dict[int, asyncio.Lock] = {}
_lock_lock = asyncio.Lock()  # Lock for creating session locks


async def _get_session_lock(session_id: int) -> asyncio.Lock:
    """Get or create a lock for a specific session."""
    async with _lock_lock:
        if session_id not in _session_locks:
            _session_locks[session_id] = asyncio.Lock()
        return _session_locks[session_id]


async def _with_retry(
    operation, 
    max_retries: int = 3, 
    backoff_ms: List[int] = [50, 150, 300]
) -> Any:
    """Execute operation with retry on IntegrityError or OperationalError."""
    last_error = None
    for attempt in range(max_retries):
        try:
            return await operation()
        except (IntegrityError, OperationalError) as e:
            last_error = e
            if attempt < max_retries - 1:
                delay = backoff_ms[min(attempt, len(backoff_ms) - 1)] / 1000
                logger.warning(f"Retry {attempt + 1}/{max_retries} after error: {e}. Waiting {delay}s")
                await asyncio.sleep(delay)
            else:
                raise
    raise last_error if last_error else Exception("Operation failed")


class RoundEngineError(Exception):
    """Base exception for round engine errors."""
    def __init__(self, message: str, code: str = "ROUND_ENGINE_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class RoundNotFoundError(RoundEngineError):
    def __init__(self, round_id: int):
        super().__init__(f"Round {round_id} not found", "ROUND_NOT_FOUND")


class TurnNotFoundError(RoundEngineError):
    def __init__(self, turn_id: int):
        super().__init__(f"Turn {turn_id} not found", "TURN_NOT_FOUND")


class InvalidRoundStateError(RoundEngineError):
    def __init__(self, round_id: int, status: str, required: str):
        super().__init__(f"Round {round_id} status is {status}, required {required}", "INVALID_ROUND_STATE")


class NotCurrentSpeakerError(RoundEngineError):
    def __init__(self, turn_id: int):
        super().__init__(f"Turn {turn_id} is not the current speaker", "NOT_CURRENT_SPEAKER")


class TurnAlreadySubmittedError(RoundEngineError):
    def __init__(self, turn_id: int):
        super().__init__(f"Turn {turn_id} already submitted", "TURN_ALREADY_SUBMITTED")


class TurnNotStartedError(RoundEngineError):
    def __init__(self, turn_id: int):
        super().__init__(f"Turn {turn_id} has not been started", "TURN_NOT_STARTED")


class TimeExpiredError(RoundEngineError):
    def __init__(self, turn_id: int, allowed: int, actual: float):
        super().__init__(
            f"Time expired: allowed {allowed}s, took {actual:.1f}s", 
            "TIME_EXPIRED"
        )


class UnauthorizedActionError(RoundEngineError):
    def __init__(self, action: str):
        super().__init__(f"Not authorized to perform {action}", "UNAUTHORIZED")


# ============================================================================
# Core Round Operations
# ============================================================================

async def create_round(
    session_id: int,
    round_index: int,
    round_type: str,
    default_turn_seconds: int,
    turns: Optional[List[Dict[str, Any]]],
    db: AsyncSession,
    is_faculty: bool = False
) -> ClassroomRound:
    """
    Create a new round with optional explicit turns.
    
    If turns is None, auto-generate from active participants in deterministic order.
    """
    if not is_faculty:
        raise UnauthorizedActionError("create round")
    
    # Check session exists and is in appropriate state
    session_result = await db.execute(
        select(ClassroomSession).where(ClassroomSession.id == session_id)
    )
    session = session_result.scalar_one_or_none()
    
    if not session:
        raise RoundEngineError(f"Session {session_id} not found", "SESSION_NOT_FOUND")
    
    # Only allow round creation in PREPARING or ACTIVE states
    current_state = (session.current_state or "CREATED").upper()
    if current_state not in ("PREPARING", "ACTIVE"):
        raise RoundEngineError(
            f"Cannot create round in state {current_state}", 
            "INVALID_SESSION_STATE"
        )
    
    # Check round_index uniqueness
    existing = await db.execute(
        select(ClassroomRound).where(
            ClassroomRound.session_id == session_id,
            ClassroomRound.round_index == round_index
        )
    )
    if existing.scalar_one_or_none():
        raise RoundEngineError(
            f"Round with index {round_index} already exists in session {session_id}",
            "DUPLICATE_ROUND_INDEX"
        )
    
    # Create the round
    round_obj = ClassroomRound(
        session_id=session_id,
        round_index=round_index,
        round_type=round_type,
        status="PENDING",
        current_speaker_participant_id=None,
        created_at=datetime.utcnow()
    )
    db.add(round_obj)
    await db.flush()  # Get the round ID
    
    # Create turns
    if turns is not None:
        # Use explicit turn definitions
        for i, turn_def in enumerate(turns, 1):
            turn = ClassroomTurn(
                round_id=round_obj.id,
                participant_id=turn_def["participant_id"],
                turn_order=i,
                allowed_seconds=turn_def.get("allowed_seconds", default_turn_seconds),
                is_submitted=False,
                created_at=datetime.utcnow()
            )
            db.add(turn)
    else:
        # Auto-generate from participants in deterministic order
        participants_result = await db.execute(
            select(ClassroomParticipant)
            .where(
                ClassroomParticipant.session_id == session_id,
                ClassroomParticipant.is_active == True
            )
            .order_by(ClassroomParticipant.id)
        )
        participants = participants_result.scalars().all()
        
        # Create deterministic speaking order: P1, R1, P2, R2
        speaking_order = _calculate_speaking_order(participants)
        
        for i, participant in enumerate(speaking_order, 1):
            turn = ClassroomTurn(
                round_id=round_obj.id,
                participant_id=participant.id,
                turn_order=i,
                allowed_seconds=default_turn_seconds,
                is_submitted=False,
                created_at=datetime.utcnow()
            )
            db.add(turn)
    
    await db.flush()
    return round_obj


def _calculate_speaking_order(participants: List[ClassroomParticipant]) -> List[ClassroomParticipant]:
    """
    Calculate deterministic speaking order from participants.
    
    Order: Petitioner #1, Respondent #1, Petitioner #2, Respondent #2
    """
    # Sort by side then speaker_number
    petitioners = [p for p in participants if p.side == "PETITIONER"]
    respondents = [p for p in participants if p.side == "RESPONDENT"]
    
    # Sort by speaker number
    petitioners.sort(key=lambda p: p.speaker_number or 99)
    respondents.sort(key=lambda p: p.speaker_number or 99)
    
    # Interleave: P1, R1, P2, R2
    result = []
    max_len = max(len(petitioners), len(respondents))
    for i in range(max_len):
        if i < len(petitioners):
            result.append(petitioners[i])
        if i < len(respondents):
            result.append(respondents[i])
    
    return result


async def start_round(
    round_id: int,
    actor_id: int,
    db: AsyncSession,
    is_faculty: bool = False
) -> ClassroomRound:
    """Start a round and set first speaker."""
    if not is_faculty:
        raise UnauthorizedActionError("start round")
    
    async with await _get_session_lock(round_id):
        # Get round
        round_result = await db.execute(
            select(ClassroomRound).where(ClassroomRound.id == round_id)
        )
        round_obj = round_result.scalar_one_or_none()
        
        if not round_obj:
            raise RoundNotFoundError(round_id)
        
        if round_obj.status != "PENDING":
            raise InvalidRoundStateError(round_id, round_obj.status, "PENDING")
        
        # Get turns
        turns_result = await db.execute(
            select(ClassroomTurn)
            .where(ClassroomTurn.round_id == round_id)
            .order_by(ClassroomTurn.turn_order)
        )
        turns = turns_result.scalars().all()
        
        if not turns:
            raise RoundEngineError(f"No turns defined for round {round_id}", "NO_TURNS")
        
        # Set first speaker
        first_turn = turns[0]
        round_obj.status = "ACTIVE"
        round_obj.started_at = datetime.utcnow()
        round_obj.current_speaker_participant_id = first_turn.participant_id
        
        # Audit log
        await _create_audit_entry(
            db, first_turn.id, "ROUND_STARTED", actor_id,
            {"round_id": round_id, "first_speaker_id": first_turn.participant_id}
        )
        
        await db.flush()
        return round_obj


async def start_turn(
    turn_id: int,
    actor_id: int,
    db: AsyncSession,
    is_faculty: bool = False,
    allow_override: bool = False
) -> ClassroomTurn:
    """
    Start a turn (claim speaking time).
    
    Only the participant owner or faculty can start a turn.
    """
    async with await _get_session_lock(turn_id):
        # Get turn with round info
        turn_result = await db.execute(
            select(ClassroomTurn, ClassroomRound)
            .join(ClassroomRound, ClassroomTurn.round_id == ClassroomRound.id)
            .where(ClassroomTurn.id == turn_id)
        )
        row = turn_result.first()
        
        if not row:
            raise TurnNotFoundError(turn_id)
        
        turn_obj, round_obj = row
        
        # Validate round is active
        if round_obj.status != "ACTIVE":
            raise InvalidRoundStateError(round_obj.id, round_obj.status, "ACTIVE")
        
        # Validate this is the current speaker
        if round_obj.current_speaker_participant_id != turn_obj.participant_id:
            raise NotCurrentSpeakerError(turn_id)
        
        # Validate actor authorization
        if not is_faculty and not allow_override:
            # Check if actor owns this participant
            participant_result = await db.execute(
                select(ClassroomParticipant).where(
                    ClassroomParticipant.id == turn_obj.participant_id
                )
            )
            participant = participant_result.scalar_one_or_none()
            
            if not participant or participant.user_id != actor_id:
                raise UnauthorizedActionError("start turn")
        
        # Start the turn
        turn_obj.started_at = datetime.utcnow()
        
        # Audit log
        await _create_audit_entry(
            db, turn_id, "START", actor_id,
            {"allowed_seconds": turn_obj.allowed_seconds}
        )
        
        await db.flush()
        
        # Schedule timeout check
        await schedule_turn_timeout(turn_id, datetime.utcnow() + timedelta(seconds=turn_obj.allowed_seconds))
        
        return turn_obj


async def submit_turn(
    turn_id: int,
    transcript: str,
    word_count: int,
    actor_id: int,
    db: AsyncSession,
    is_faculty: bool = False,
    allow_late: bool = False
) -> Tuple[ClassroomTurn, bool]:
    """
    Submit a turn transcript.
    
    Returns: (turn, is_round_complete)
    
    Raises TimeExpiredError if submission is late and allow_late is False.
    """
    async with await _get_session_lock(turn_id):
        # Get turn with round info
        turn_result = await db.execute(
            select(ClassroomTurn, ClassroomRound)
            .join(ClassroomRound, ClassroomTurn.round_id == ClassroomRound.id)
            .where(ClassroomTurn.id == turn_id)
        )
        row = turn_result.first()
        
        if not row:
            raise TurnNotFoundError(turn_id)
        
        turn_obj, round_obj = row
        
        # Validate turn state
        if turn_obj.is_submitted:
            raise TurnAlreadySubmittedError(turn_id)
        
        if not turn_obj.started_at:
            raise TurnNotStartedError(turn_id)
        
        # Validate round is active
        if round_obj.status != "ACTIVE":
            raise InvalidRoundStateError(round_obj.id, round_obj.status, "ACTIVE")
        
        # Check time limit
        now = datetime.utcnow()
        elapsed = (now - turn_obj.started_at).total_seconds()
        
        if elapsed > turn_obj.allowed_seconds:
            if not allow_late:
                raise TimeExpiredError(turn_id, turn_obj.allowed_seconds, elapsed)
            # Late submission accepted with penalty (logged)
            logger.warning(f"Late submission accepted for turn {turn_id}: {elapsed:.1f}s > {turn_obj.allowed_seconds}s")
        
        # Validate actor
        if not is_faculty:
            participant_result = await db.execute(
                select(ClassroomParticipant).where(
                    ClassroomParticipant.id == turn_obj.participant_id
                )
            )
            participant = participant_result.scalar_one_or_none()
            
            if not participant or participant.user_id != actor_id:
                raise UnauthorizedActionError("submit turn")
        
        # Submit the turn
        turn_obj.transcript = transcript
        turn_obj.word_count = word_count
        turn_obj.submitted_at = now
        turn_obj.is_submitted = True
        
        # Audit log
        await _create_audit_entry(
            db, turn_id, "SUBMIT", actor_id,
            {
                "word_count": word_count,
                "elapsed_seconds": elapsed,
                "was_late": elapsed > turn_obj.allowed_seconds
            }
        )
        
        await db.flush()
        
        # Cancel timeout (if scheduled)
        await cancel_scheduled_timeout(turn_id)
        
        # Advance to next turn or complete round
        is_complete = await advance_after_submit(round_obj.id, turn_id, db)
        
        return turn_obj, is_complete


async def force_submit_turn(
    turn_id: int,
    transcript: Optional[str],
    word_count: Optional[int],
    actor_id: int,
    db: AsyncSession,
    is_faculty: bool = False
) -> Tuple[ClassroomTurn, bool]:
    """Faculty force submit a turn (always allowed)."""
    if not is_faculty:
        raise UnauthorizedActionError("force submit turn")
    
    # Use submit_turn with allow_late=True
    return await submit_turn(
        turn_id=turn_id,
        transcript=transcript or "",
        word_count=word_count or 0,
        actor_id=actor_id,
        db=db,
        is_faculty=True,
        allow_late=True
    )


async def advance_after_submit(
    round_id: int,
    completed_turn_id: int,
    db: AsyncSession
) -> bool:
    """
    Advance round after turn submission.
    
    Returns True if round is now complete.
    """
    # Get all turns for this round
    turns_result = await db.execute(
        select(ClassroomTurn)
        .where(ClassroomTurn.round_id == round_id)
        .order_by(ClassroomTurn.turn_order)
    )
    turns = turns_result.scalars().all()
    
    # Find next unsubmitted turn
    next_turn = None
    found_completed = False
    for turn in turns:
        if turn.id == completed_turn_id:
            found_completed = True
            continue
        if found_completed and not turn.is_submitted:
            next_turn = turn
            break
    
    if next_turn:
        # Set next speaker
        await db.execute(
            select(ClassroomRound)
            .where(ClassroomRound.id == round_id)
        )
        round_result = await db.execute(
            select(ClassroomRound).where(ClassroomRound.id == round_id)
        )
        round_obj = round_result.scalar_one()
        round_obj.current_speaker_participant_id = next_turn.participant_id
        
        logger.info(f"Advanced round {round_id} to turn {next_turn.id} (participant {next_turn.participant_id})")
        return False
    else:
        # All turns submitted - complete the round
        round_result = await db.execute(
            select(ClassroomRound).where(ClassroomRound.id == round_id)
        )
        round_obj = round_result.scalar_one()
        round_obj.status = "COMPLETED"
        round_obj.ended_at = datetime.utcnow()
        round_obj.current_speaker_participant_id = None
        
        logger.info(f"Round {round_id} completed")
        
        # Could trigger session state machine here
        # await transition_session_state(round_obj.session_id, ...)
        
        return True


async def auto_advance_on_timeout(
    turn_id: int,
    db: AsyncSession
) -> bool:
    """
    Handle turn timeout - auto-advance to next turn.
    
    Called by timer when turn time expires.
    """
    async with await _get_session_lock(turn_id):
        # Get turn
        turn_result = await db.execute(
            select(ClassroomTurn, ClassroomRound)
            .join(ClassroomRound, ClassroomTurn.round_id == ClassroomRound.id)
            .where(ClassroomTurn.id == turn_id)
        )
        row = turn_result.first()
        
        if not row:
            logger.warning(f"Turn {turn_id} not found for timeout handling")
            return False
        
        turn_obj, round_obj = row
        
        # Check if already submitted
        if turn_obj.is_submitted:
            logger.info(f"Turn {turn_id} already submitted, skipping timeout")
            return False
        
        # Check if round is still active
        if round_obj.status != "ACTIVE":
            logger.info(f"Round {round_obj.id} not active (status: {round_obj.status}), skipping timeout")
            return False
        
        # Create audit entry for timeout
        await _create_audit_entry(
            db, turn_id, "TIME_EXPIRED", 0,  # System action
            {"allowed_seconds": turn_obj.allowed_seconds}
        )
        
        # Auto-submit with empty transcript if configured
        from backend.config.feature_flags import FEATURE_AUTO_SUBMIT_ON_TIMEOUT
        if FEATURE_AUTO_SUBMIT_ON_TIMEOUT:
            turn_obj.transcript = "[TIMEOUT - AUTO SUBMITTED]"
            turn_obj.word_count = 0
            turn_obj.submitted_at = datetime.utcnow()
            turn_obj.is_submitted = True
            
            await _create_audit_entry(
                db, turn_id, "AUTO_SUBMIT", 0,
                {"reason": "timeout"}
            )
        
        await db.flush()
        
        # Advance round
        is_complete = await advance_after_submit(round_obj.id, turn_id, db)
        
        return is_complete


async def abort_round(
    round_id: int,
    actor_id: int,
    db: AsyncSession,
    is_faculty: bool = False,
    reason: Optional[str] = None
) -> ClassroomRound:
    """Abort a round (faculty only)."""
    if not is_faculty:
        raise UnauthorizedActionError("abort round")
    
    round_result = await db.execute(
        select(ClassroomRound).where(ClassroomRound.id == round_id)
    )
    round_obj = round_result.scalar_one_or_none()
    
    if not round_obj:
        raise RoundNotFoundError(round_id)
    
    round_obj.status = "ABORTED"
    round_obj.ended_at = datetime.utcnow()
    round_obj.current_speaker_participant_id = None
    
    # Audit log for all unfinished turns
    turns_result = await db.execute(
        select(ClassroomTurn).where(
            ClassroomTurn.round_id == round_id,
            ClassroomTurn.is_submitted == False
        )
    )
    turns = turns_result.scalars().all()
    
    for turn in turns:
        await _create_audit_entry(
            db, turn.id, "OVERRIDE", actor_id,
            {"action": "round_abort", "reason": reason or "Faculty abort"}
        )
    
    await db.flush()
    return round_obj


# ============================================================================
# Audit Operations
# ============================================================================

async def _create_audit_entry(
    db: AsyncSession,
    turn_id: int,
    action: str,
    actor_user_id: int,
    payload: Dict[str, Any]
) -> ClassroomTurnAudit:
    """Create an audit log entry."""
    audit = ClassroomTurnAudit(
        turn_id=turn_id,
        action=action,
        actor_user_id=actor_user_id,
        payload_json=json.dumps(payload) if payload else None,
        created_at=datetime.utcnow()
    )
    db.add(audit)
    return audit


async def get_turn_audit(
    turn_id: int,
    db: AsyncSession
) -> List[ClassroomTurnAudit]:
    """Get all audit entries for a turn."""
    result = await db.execute(
        select(ClassroomTurnAudit)
        .where(ClassroomTurnAudit.turn_id == turn_id)
        .order_by(ClassroomTurnAudit.created_at)
    )
    return list(result.scalars().all())


# ============================================================================
# Timer Operations (Pluggable Interface)
# ============================================================================

# In-memory scheduled timeouts (for dev/SQLite)
_scheduled_timeouts: Dict[int, asyncio.Task] = {}


async def schedule_turn_timeout(turn_id: int, due_at: datetime) -> None:
    """
    Schedule a timeout check for a turn.
    
    This is a pluggable interface - for production, replace with Celery/Redis.
    """
    # Cancel any existing timeout for this turn
    await cancel_scheduled_timeout(turn_id)
    
    # Calculate delay
    now = datetime.utcnow()
    delay_seconds = (due_at - now).total_seconds()
    
    if delay_seconds <= 0:
        # Already expired - handle immediately
        logger.warning(f"Turn {turn_id} already expired, handling immediately")
        # We can't use db here, caller must handle
        return
    
    # Schedule asyncio task (for dev/SQLite)
    async def timeout_task():
        await asyncio.sleep(delay_seconds)
        try:
            # Import here to avoid circular imports
            from backend.database import AsyncSessionLocal
            async with AsyncSessionLocal() as db:
                await auto_advance_on_timeout(turn_id, db)
                await db.commit()
        except Exception as e:
            logger.error(f"Error in timeout task for turn {turn_id}: {e}")
        finally:
            _scheduled_timeouts.pop(turn_id, None)
    
    task = asyncio.create_task(timeout_task())
    _scheduled_timeouts[turn_id] = task
    
    logger.info(f"Scheduled timeout for turn {turn_id} at {due_at.isoformat()}")


async def cancel_scheduled_timeout(turn_id: int) -> None:
    """Cancel a scheduled timeout for a turn."""
    task = _scheduled_timeouts.pop(turn_id, None)
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        logger.info(f"Cancelled timeout for turn {turn_id}")


# ============================================================================
# Query Operations
# ============================================================================

async def get_round(
    round_id: int,
    db: AsyncSession
) -> Optional[ClassroomRound]:
    """Get a round by ID."""
    result = await db.execute(
        select(ClassroomRound).where(ClassroomRound.id == round_id)
    )
    return result.scalar_one_or_none()


async def get_rounds_for_session(
    session_id: int,
    db: AsyncSession
) -> List[ClassroomRound]:
    """Get all rounds for a session."""
    result = await db.execute(
        select(ClassroomRound)
        .where(ClassroomRound.session_id == session_id)
        .order_by(ClassroomRound.round_index)
    )
    return list(result.scalars().all())


async def get_turn(
    turn_id: int,
    db: AsyncSession
) -> Optional[ClassroomTurn]:
    """Get a turn by ID."""
    result = await db.execute(
        select(ClassroomTurn).where(ClassroomTurn.id == turn_id)
    )
    return result.scalar_one_or_none()


async def get_turns_for_round(
    round_id: int,
    db: AsyncSession
) -> List[ClassroomTurn]:
    """Get all turns for a round."""
    result = await db.execute(
        select(ClassroomTurn)
        .where(ClassroomTurn.round_id == round_id)
        .order_by(ClassroomTurn.turn_order)
    )
    return list(result.scalars().all())
