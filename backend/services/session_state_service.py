"""
Session State Service

Strict, auditable, concurrency-safe session state machine implementation.
All state transitions are data-driven from the session_state_transitions table.
"""
import logging
from typing import Optional, Tuple, List
from datetime import datetime

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.orm.classroom_session import ClassroomSession
from backend.orm.session_state_transition import SessionStateTransition
from backend.orm.classroom_session_state_log import ClassroomSessionStateLog

logger = logging.getLogger(__name__)

# Valid state constants (canonical uppercase)
VALID_STATES = {
    "CREATED",
    "PREPARING",
    "ARGUING_PETITIONER",
    "ARGUING_RESPONDENT",
    "REBUTTAL",
    "JUDGING",
    "COMPLETED",
    "CANCELLED"
}


class StateTransitionError(Exception):
    """Exception for state transition failures."""
    def __init__(self, message: str, from_state: str, to_state: str, allowed_states: Optional[List[str]] = None):
        self.message = message
        self.from_state = from_state
        self.to_state = to_state
        self.allowed_states = allowed_states or []
        super().__init__(self.message)


class ConcurrentModificationError(Exception):
    """Exception for concurrent modification conflicts."""
    def __init__(self, message: str, current_state: str):
        self.message = message
        self.current_state = current_state
        super().__init__(self.message)


class PreconditionError(Exception):
    """Exception for precondition failures."""
    def __init__(self, message: str, precondition: str):
        self.message = message
        self.precondition = precondition
        super().__init__(self.message)


async def get_allowed_transition(
    db: AsyncSession,
    from_state: str,
    to_state: str
) -> Optional[SessionStateTransition]:
    """
    Get an allowed transition rule from the database.
    
    Args:
        db: Database session
        from_state: Source state
        to_state: Target state
        
    Returns:
        SessionStateTransition if allowed, None otherwise
    """
    # Normalize states to uppercase
    from_state = from_state.upper()
    to_state = to_state.upper()
    
    result = await db.execute(
        select(SessionStateTransition).where(
            and_(
                SessionStateTransition.from_state == from_state,
                SessionStateTransition.to_state == to_state
            )
        )
    )
    
    return result.scalar_one_or_none()


async def get_allowed_transitions_from_state(
    db: AsyncSession,
    from_state: str
) -> List[SessionStateTransition]:
    """
    Get all allowed transitions from a given state.
    
    Args:
        db: Database session
        from_state: Current state
        
    Returns:
        List of allowed SessionStateTransition objects
    """
    from_state = from_state.upper()
    
    result = await db.execute(
        select(SessionStateTransition).where(
            SessionStateTransition.from_state == from_state
        )
    )
    
    return result.scalars().all()


async def can_transition(
    session: ClassroomSession,
    to_state: str,
    db: AsyncSession,
    acting_user_id: Optional[int] = None,
    is_faculty: bool = False
) -> Tuple[bool, str]:
    """
    Check if a transition is allowed with all preconditions.
    
    Args:
        session: The classroom session
        to_state: Target state
        db: Database session
        acting_user_id: ID of user attempting the transition
        is_faculty: Whether the acting user is faculty
        
    Returns:
        Tuple of (is_allowed, reason_message)
    """
    to_state = to_state.upper()
    from_state = session.current_state.upper() if session.current_state else "CREATED"
    
    # Check if target state is valid
    if to_state not in VALID_STATES:
        return False, f"Invalid target state: {to_state}"
    
    # Idempotency: if already in target state, allow (no-op)
    if from_state == to_state:
        return True, "Already in target state"
    
    # Get transition rule from database
    transition = await get_allowed_transition(db, from_state, to_state)
    
    if not transition:
        # Get allowed states for better error message
        allowed = await get_allowed_transitions_from_state(db, from_state)
        allowed_states = [t.to_state for t in allowed]
        return False, f"Cannot transition {from_state} -> {to_state}. Allowed: {allowed_states}"
    
    # Check faculty requirement
    if transition.requires_faculty and not is_faculty:
        return False, f"Transition {from_state} -> {to_state} requires faculty authorization"
    
    # Check rounds complete precondition
    if transition.requires_all_rounds_complete:
        # TODO: Implement round completion check
        # For now, we'll log this requirement
        logger.info(f"Transition {from_state} -> {to_state} requires all rounds complete")
    
    return True, "Transition allowed"


async def transition_session_state(
    session_id: int,
    to_state: str,
    acting_user_id: Optional[int],
    db: AsyncSession,
    is_faculty: bool = False,
    reason: Optional[str] = None,
    trigger_type: Optional[str] = None
) -> ClassroomSession:
    """
    Transition a session to a new state with full audit logging.
    
    This function uses database row locking (SELECT ... FOR UPDATE) to ensure
    concurrency safety. If the session state has changed between read and write,
    a ConcurrentModificationError is raised.
    
    Args:
        session_id: ID of the session to transition
        to_state: Target state
        acting_user_id: ID of user making the transition (None for system)
        db: Database session
        is_faculty: Whether the acting user is faculty
        reason: Optional reason for the transition
        trigger_type: Type of trigger (e.g., 'faculty_action', 'round_completed')
        
    Returns:
        Updated ClassroomSession object
        
    Raises:
        StateTransitionError: If transition is not allowed
        ConcurrentModificationError: If session was modified concurrently
        PreconditionError: If preconditions are not met
    """
    to_state = to_state.upper()
    
    logger.info(
        f"[TRANSITION ATTEMPT] session={session_id} to={to_state} "
        f"by={acting_user_id} faculty={is_faculty}"
    )
    
    # Use explicit transaction with row locking
    # Note: Don't use async with db.begin() as the session might already be in a transaction
    # Lock the session row for update to prevent concurrent modifications
    result = await db.execute(
        select(ClassroomSession)
        .where(ClassroomSession.id == session_id)
        .with_for_update()  # Pessimistic locking
    )
    
    session = result.scalar_one_or_none()
    
    if not session:
        raise StateTransitionError(
            f"Session {session_id} not found",
            "UNKNOWN", to_state
        )
    
    from_state = session.current_state.upper() if session.current_state else "CREATED"
    
    # Idempotency check: if already in target state, return success (no-op)
    if from_state == to_state:
        logger.info(f"[TRANSITION NO-OP] session={session_id} already in {to_state}")
        await _log_transition(
            db, session_id, from_state, to_state, acting_user_id,
            trigger_type, reason, True, "Already in target state"
        )
        return session
    
    # Check if transition is allowed
    is_allowed, message = await can_transition(
        session, to_state, db, acting_user_id, is_faculty
    )
    
    if not is_allowed:
        logger.warning(
            f"[TRANSITION BLOCKED] session={session_id} {from_state} -> {to_state}: {message}"
        )
        
        # Log failed attempt
        await _log_transition(
            db, session_id, from_state, to_state, acting_user_id,
            trigger_type, reason, False, message
        )
        
        # Get allowed states for error response
        allowed = await get_allowed_transitions_from_state(db, from_state)
        allowed_states = [t.to_state for t in allowed]
        
        raise StateTransitionError(
            message, from_state, to_state, allowed_states
        )
    
    # Get transition details
    transition = await get_allowed_transition(db, from_state, to_state)
    
    # Check preconditions
    if transition and transition.requires_all_rounds_complete:
        # Check if all rounds are complete
        rounds_complete = await _check_all_rounds_complete(db, session_id)
        if not rounds_complete:
            error_msg = "All rounds must be completed before this transition"
            logger.warning(f"[TRANSITION BLOCKED] session={session_id}: {error_msg}")
            
            await _log_transition(
                db, session_id, from_state, to_state, acting_user_id,
                trigger_type, reason, False, error_msg
            )
            
            raise PreconditionError(error_msg, "requires_all_rounds_complete")
    
    # Perform the transition
    old_state = session.current_state
    session.current_state = to_state
    session.state_updated_at = datetime.utcnow()
    
    # Update timestamps for terminal states
    if to_state == "COMPLETED":
        session.completed_at = datetime.utcnow()
        session.is_active = False
    elif to_state == "CANCELLED":
        session.cancelled_at = datetime.utcnow()
        session.is_active = False
    
    # Flush to ensure changes are written to the database session
    await db.flush()
    
    # Log successful transition
    await _log_transition(
        db, session_id, from_state, to_state, acting_user_id,
        trigger_type or (transition.trigger_type if transition else None),
        reason, True, None
    )
    
    logger.info(
        f"[TRANSITION SUCCESS] session={session_id} {old_state} -> {to_state} "
        f"by={acting_user_id}"
    )
    
    # Commit happens automatically at end of async with db.begin() block
    return session


async def _check_all_rounds_complete(db: AsyncSession, session_id: int) -> bool:
    """
    Check if all rounds for a session are completed.
    
    Args:
        db: Database session
        session_id: Session ID
        
    Returns:
        True if all rounds are complete, False otherwise
    """
    # Import here to avoid circular imports
    from backend.orm.classroom_session import ClassroomRound
    
    result = await db.execute(
        select(ClassroomRound).where(
            and_(
                ClassroomRound.session_id == session_id,
                ClassroomRound.status.notin_(["COMPLETED", "SKIPPED"])
            )
        )
    )
    
    incomplete_rounds = result.scalars().all()
    return len(incomplete_rounds) == 0


async def _log_transition(
    db: AsyncSession,
    session_id: int,
    from_state: str,
    to_state: str,
    triggered_by_user_id: Optional[int],
    trigger_type: Optional[str],
    reason: Optional[str],
    is_successful: bool,
    error_message: Optional[str]
):
    """
    Log a state transition attempt to the audit log.
    
    Args:
        db: Database session
        session_id: Session ID
        from_state: Previous state
        to_state: New state
        triggered_by_user_id: User who triggered the transition
        trigger_type: Type of trigger
        reason: Reason for transition
        is_successful: Whether the transition succeeded
        error_message: Error message if failed
    """
    log_entry = ClassroomSessionStateLog(
        session_id=session_id,
        from_state=from_state,
        to_state=to_state,
        triggered_by_user_id=triggered_by_user_id,
        trigger_type=trigger_type,
        reason=reason,
        is_successful=is_successful,
        error_message=error_message
    )
    
    db.add(log_entry)
    # Note: Commit happens in parent transaction


async def get_session_state_history(
    db: AsyncSession,
    session_id: int,
    limit: int = 50
) -> List[ClassroomSessionStateLog]:
    """
    Get the state transition history for a session.
    
    Args:
        db: Database session
        session_id: Session ID
        limit: Maximum number of records to return
        
    Returns:
        List of ClassroomSessionStateLog objects, newest first
    """
    result = await db.execute(
        select(ClassroomSessionStateLog)
        .where(ClassroomSessionStateLog.session_id == session_id)
        .order_by(ClassroomSessionStateLog.created_at.desc())
        .limit(limit)
    )
    
    return result.scalars().all()
