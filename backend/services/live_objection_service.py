"""
Phase 6 — Objection & Procedural Control Engine Service Layer

Server-authoritative with:
- Single pending objection per turn (enforced by DB + code)
- Timer pause/resume on objection
- Presiding judge authority enforcement
- Cryptographic event logging
- SERIALIZABLE isolation for critical paths
- FOR UPDATE locking

All state changes append events to chain.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, and_, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.orm.live_court import (
    LiveCourtSession, LiveTurn, LiveCourtStatus, LiveTurnState
)
from backend.orm.live_objection import (
    LiveObjection, ObjectionType, ObjectionState,
    ProceduralViolation
)
from backend.orm.user import User, UserRole


# =============================================================================
# Custom Exceptions
# =============================================================================

class ObjectionNotFoundError(Exception):
    pass


class ObjectionAlreadyRuledError(Exception):
    pass


class ObjectionAlreadyPendingError(Exception):
    """Raised when trying to raise objection while one is already pending."""
    pass


class NotPresidingJudgeError(Exception):
    """Raised when non-presiding judge tries to rule."""
    pass


class TurnNotActiveError(Exception):
    """Raised when trying to raise objection on inactive turn."""
    pass


class SessionNotLiveError(Exception):
    """Raised when session is not in LIVE status."""
    pass


class SessionCompletedError(Exception):
    """Raised when session is completed."""
    pass


# =============================================================================
# Private: Event Append Helper
# =============================================================================

async def _append_event(
    session_id: int,
    event_type: str,
    payload: Dict[str, Any],
    db: AsyncSession
) -> Any:
    """
    Append event to chain.
    
    Reuses Phase 5 event log integration.
    """
    from backend.services.live_court_service import _append_event as base_append_event
    return await base_append_event(session_id, event_type, payload, db)


# =============================================================================
# A) raise_objection()
# =============================================================================

async def raise_objection(
    session_id: int,
    turn_id: int,
    raised_by_user_id: int,
    objection_type: ObjectionType,
    reason_text: Optional[str],
    db: AsyncSession
) -> Tuple[LiveObjection, LiveTurn]:
    """
    Raise an objection during a turn.
    
    Flow:
    1. SERIALIZABLE isolation
    2. Lock session FOR UPDATE
    3. Lock turn FOR UPDATE
    4. Validate session.status == LIVE
    5. Validate turn.state == ACTIVE
    6. Validate turn.is_timer_paused == False
    7. Validate no pending objection exists
    8. Create objection (state=pending)
    9. Set turn.is_timer_paused = True
    10. Append events: OBJECTION_RAISED, TURN_PAUSED_FOR_OBJECTION
    11. Commit
    
    Args:
        session_id: Session ID
        turn_id: Turn being objected to
        raised_by_user_id: User raising the objection
        objection_type: Type of objection
        reason_text: Optional explanation
        db: Database session
    
    Returns:
        Tuple of (objection, turn)
    
    Raises:
        SessionNotLiveError: If session not live
        TurnNotActiveError: If turn not active
        ObjectionAlreadyPendingError: If objection already pending
    """
    # Set SERIALIZABLE isolation
    await db.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
    
    # 1. Lock session FOR UPDATE
    result = await db.execute(
        select(LiveCourtSession)
        .where(LiveCourtSession.id == session_id)
        .with_for_update()
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise ObjectionNotFoundError(f"Session {session_id} not found")
    
    if session.is_completed():
        raise SessionCompletedError("Cannot raise objection after session completed")
    
    if session.status != LiveCourtStatus.LIVE:
        raise SessionNotLiveError(f"Session status is {session.status.value}, must be 'live'")
    
    # 2. Lock turn FOR UPDATE
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
        raise ObjectionNotFoundError(f"Turn {turn_id} not found in session")
    
    if turn.state != LiveTurnState.ACTIVE:
        raise TurnNotActiveError(f"Turn is {turn.state.value}, must be 'active'")
    
    if turn.is_timer_paused:
        raise ObjectionAlreadyPendingError("Turn timer already paused - objection in progress")
    
    # 3. Check for existing pending objection
    result = await db.execute(
        select(func.count(LiveObjection.id))
        .where(
            and_(
                LiveObjection.turn_id == turn_id,
                LiveObjection.state == ObjectionState.PENDING
            )
        )
    )
    pending_count = result.scalar_one()
    
    if pending_count > 0:
        raise ObjectionAlreadyPendingError("An objection is already pending for this turn")
    
    # 4. Create objection
    raised_at = datetime.utcnow()
    objection_hash = LiveObjection.compute_objection_hash(
        session_id=session_id,
        turn_id=turn_id,
        raised_by_user_id=raised_by_user_id,
        objection_type=objection_type,
        reason_text=reason_text,
        raised_at=raised_at
    )
    
    objection = LiveObjection(
        session_id=session_id,
        turn_id=turn_id,
        raised_by_user_id=raised_by_user_id,
        objection_type=objection_type,
        state=ObjectionState.PENDING,
        reason_text=reason_text,
        raised_at=raised_at,
        objection_hash=objection_hash,
        created_at=raised_at
    )
    
    db.add(objection)
    await db.flush()  # Get objection.id
    
    # 5. Pause turn timer
    turn.is_timer_paused = True
    
    # 6. Append events
    await _append_event(
        session_id=session_id,
        event_type="OBJECTION_RAISED",
        payload={
            "objection_id": objection.id,
            "turn_id": turn_id,
            "raised_by_user_id": raised_by_user_id,
            "objection_type": objection_type.value,
            "reason_text": reason_text or ""
        },
        db=db
    )
    
    await _append_event(
        session_id=session_id,
        event_type="TURN_PAUSED_FOR_OBJECTION",
        payload={
            "turn_id": turn_id,
            "objection_id": objection.id,
            "paused_at": raised_at.isoformat()
        },
        db=db
    )
    
    await db.flush()
    
    return objection, turn


# =============================================================================
# B) rule_objection()
# =============================================================================

async def rule_objection(
    objection_id: int,
    decision: ObjectionState,
    ruling_reason_text: Optional[str],
    ruled_by_user_id: int,
    is_presiding_judge: bool,
    db: AsyncSession
) -> Tuple[LiveObjection, LiveTurn]:
    """
    Rule on a pending objection.
    
    Flow:
    1. SERIALIZABLE isolation
    2. Lock objection FOR UPDATE
    3. Lock session FOR UPDATE
    4. Validate objection.state == pending
    5. Validate session.status == LIVE
    6. Validate user is presiding judge
    7. Update objection.state, ruled_by_user_id, ruled_at
    8. Set turn.is_timer_paused = False
    9. Append events: OBJECTION_SUSTAINED/OVERRULED, TURN_RESUMED
    10. Commit
    
    Idempotent: second ruling attempt fails cleanly.
    
    Args:
        objection_id: Objection to rule on
        decision: SUSTAINED or OVERRULED
        ruling_reason_text: Optional explanation
        ruled_by_user_id: Judge making the ruling
        is_presiding_judge: Whether user is presiding judge
        db: Database session
    
    Returns:
        Tuple of (objection, turn)
    
    Raises:
        ObjectionNotFoundError: If objection not found
        ObjectionAlreadyRuledError: If already ruled
        NotPresidingJudgeError: If not presiding judge
        SessionNotLiveError: If session not live
    """
    from sqlalchemy import text
    
    # Set SERIALIZABLE isolation
    await db.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
    
    # 1. Lock objection FOR UPDATE
    result = await db.execute(
        select(LiveObjection)
        .where(LiveObjection.id == objection_id)
        .with_for_update()
    )
    objection = result.scalar_one_or_none()
    
    if not objection:
        raise ObjectionNotFoundError(f"Objection {objection_id} not found")
    
    # 2. Idempotency check
    if objection.is_ruled():
        raise ObjectionAlreadyRuledError(
            f"Objection already {objection.state.value}"
        )
    
    # 3. Validate presiding judge
    if not is_presiding_judge:
        raise NotPresidingJudgeError("Only the presiding judge can rule on objections")
    
    # 4. Lock session FOR UPDATE
    result = await db.execute(
        select(LiveCourtSession)
        .where(LiveCourtSession.id == objection.session_id)
        .with_for_update()
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise ObjectionNotFoundError(f"Session {objection.session_id} not found")
    
    if session.is_completed():
        raise SessionCompletedError("Cannot rule on objection after session completed")
    
    if session.status != LiveCourtStatus.LIVE:
        raise SessionNotLiveError(f"Session status is {session.status.value}")
    
    # 5. Lock turn FOR UPDATE
    result = await db.execute(
        select(LiveTurn)
        .where(LiveTurn.id == objection.turn_id)
        .with_for_update()
    )
    turn = result.scalar_one_or_none()
    
    if not turn:
        raise ObjectionNotFoundError(f"Turn {objection.turn_id} not found")
    
    # 6. Update objection
    ruled_at = datetime.utcnow()
    objection.state = decision
    objection.ruled_by_user_id = ruled_by_user_id
    objection.ruling_reason_text = ruling_reason_text
    objection.ruled_at = ruled_at
    
    # 7. Resume turn timer
    turn.is_timer_paused = False
    
    # 8. Append events
    event_type = (
        "OBJECTION_SUSTAINED" if decision == ObjectionState.SUSTAINED 
        else "OBJECTION_OVERRULED"
    )
    
    await _append_event(
        session_id=objection.session_id,
        event_type=event_type,
        payload={
            "objection_id": objection.id,
            "turn_id": objection.turn_id,
            "ruled_by_user_id": ruled_by_user_id,
            "ruling_reason_text": ruling_reason_text or ""
        },
        db=db
    )
    
    await _append_event(
        session_id=objection.session_id,
        event_type="TURN_RESUMED_AFTER_OBJECTION",
        payload={
            "turn_id": objection.turn_id,
            "objection_id": objection.id,
            "resumed_at": ruled_at.isoformat()
        },
        db=db
    )
    
    await db.flush()
    
    return objection, turn


# =============================================================================
# C) record_procedural_violation()
# =============================================================================

async def record_procedural_violation(
    session_id: int,
    turn_id: int,
    user_id: int,
    recorded_by_user_id: int,
    violation_type: str,
    description: Optional[str],
    db: AsyncSession
) -> ProceduralViolation:
    """
    Record a procedural violation during a session.
    
    Creates violation record and appends PROCEDURAL_VIOLATION event.
    
    Args:
        session_id: Session ID
        turn_id: Turn where violation occurred
        user_id: User who committed violation
        recorded_by_user_id: User recording the violation
        violation_type: Type of violation
        description: Optional description
        db: Database session
    
    Returns:
        ProceduralViolation record
    """
    # Verify session exists and is not completed
    result = await db.execute(
        select(LiveCourtSession)
        .where(LiveCourtSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise ObjectionNotFoundError(f"Session {session_id} not found")
    
    if session.is_completed():
        raise SessionCompletedError("Cannot record violation after session completed")
    
    # Create violation record
    violation = ProceduralViolation(
        session_id=session_id,
        turn_id=turn_id,
        user_id=user_id,
        recorded_by_user_id=recorded_by_user_id,
        violation_type=violation_type,
        description=description,
        occurred_at=datetime.utcnow(),
        recorded_at=datetime.utcnow()
    )
    
    db.add(violation)
    await db.flush()  # Get violation.id
    
    # Append event
    await _append_event(
        session_id=session_id,
        event_type="PROCEDURAL_VIOLATION",
        payload={
            "violation_id": violation.id,
            "turn_id": turn_id,
            "user_id": user_id,
            "violation_type": violation_type,
            "description": description or ""
        },
        db=db
    )
    
    await db.flush()
    
    return violation


# =============================================================================
# D) Query Functions
# =============================================================================

async def get_objection_by_id(
    objection_id: int,
    db: AsyncSession
) -> Optional[LiveObjection]:
    """Get objection by ID with all relationships loaded."""
    result = await db.execute(
        select(LiveObjection)
        .options(
            selectinload(LiveObjection.raised_by),
            selectinload(LiveObjection.ruled_by),
            selectinload(LiveObjection.turn),
            selectinload(LiveObjection.session)
        )
        .where(LiveObjection.id == objection_id)
    )
    return result.scalar_one_or_none()


async def get_objections_by_session(
    session_id: int,
    db: AsyncSession,
    state: Optional[ObjectionState] = None
) -> List[LiveObjection]:
    """Get all objections for a session, optionally filtered by state."""
    query = (
        select(LiveObjection)
        .options(
            selectinload(LiveObjection.raised_by),
            selectinload(LiveObjection.ruled_by)
        )
        .where(LiveObjection.session_id == session_id)
        .order_by(LiveObjection.raised_at.asc())
    )
    
    if state:
        query = query.where(LiveObjection.state == state)
    
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_objections_by_turn(
    turn_id: int,
    db: AsyncSession
) -> List[LiveObjection]:
    """Get all objections for a specific turn."""
    result = await db.execute(
        select(LiveObjection)
        .options(
            selectinload(LiveObjection.raised_by),
            selectinload(LiveObjection.ruled_by)
        )
        .where(LiveObjection.turn_id == turn_id)
        .order_by(LiveObjection.raised_at.asc())
    )
    return list(result.scalars().all())


async def get_pending_objection_for_turn(
    turn_id: int,
    db: AsyncSession
) -> Optional[LiveObjection]:
    """Get the pending objection for a turn (if any)."""
    result = await db.execute(
        select(LiveObjection)
        .options(
            selectinload(LiveObjection.raised_by)
        )
        .where(
            and_(
                LiveObjection.turn_id == turn_id,
                LiveObjection.state == ObjectionState.PENDING
            )
        )
    )
    return result.scalar_one_or_none()


async def check_user_can_raise_objection(
    session_id: int,
    user_id: int,
    turn_id: int,
    db: AsyncSession
) -> Tuple[bool, Optional[str]]:
    """
    Check if user can raise objection on a turn.
    
    Returns (can_raise, reason_if_not)
    """
    # Get user
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        return False, "User not found"
    
    # Check roles that can raise objections
    # PHASE 1: Only teachers can raise objections
    if user.role != UserRole.teacher:
        return False, f"Role {user.role.value} cannot raise objections"
    
    # Check session
    result = await db.execute(
        select(LiveCourtSession).where(LiveCourtSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    
    if not session:
        return False, "Session not found"
    
    if session.is_completed():
        return False, "Session is completed"
    
    if session.status != LiveCourtStatus.LIVE:
        return False, f"Session is {session.status.value}, must be 'live'"
    
    # Check turn
    result = await db.execute(
        select(LiveTurn).where(LiveTurn.id == turn_id)
    )
    turn = result.scalar_one_or_none()
    
    if not turn:
        return False, "Turn not found"
    
    if turn.state != LiveTurnState.ACTIVE:
        return False, f"Turn is {turn.state.value}, must be 'active'"
    
    if turn.is_timer_paused:
        return False, "Turn timer already paused"
    
    return True, None


async def check_user_can_rule_objection(
    user_id: int,
    is_presiding_judge: bool
) -> Tuple[bool, Optional[str]]:
    """
    Check if user can rule on objection.
    
    Returns (can_rule, reason_if_not)
    """
    if not is_presiding_judge:
        return False, "Only the presiding judge can rule on objections"
    
    return True, None
