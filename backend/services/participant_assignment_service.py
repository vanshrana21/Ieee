"""
Participant Assignment Service — Production-Hardened

Deterministic, concurrency-safe, database-driven participant assignment engine
for classroom moot sessions.

Core Principles:
- ZERO randomness
- ZERO frontend logic
- Server-authoritative assignment
- Race-condition safe via explicit locking
- Full audit trail
- Fail-fast with clear errors
"""
import asyncio
import logging
from typing import Optional, Tuple, Dict, Any, List
from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.orm.classroom_session import ClassroomSession, ClassroomParticipant
from backend.orm.classroom_participant_audit_log import ClassroomParticipantAuditLog

logger = logging.getLogger(__name__)

# Maximum participants allowed in a moot session — HARDCODED, NOT CONFIGURABLE
MAX_PARTICIPANTS = 4

# Valid states for joining — ONLY PREPARING
JOINABLE_STATES = {"PREPARING"}

# Global lock for serializing concurrent assignments (SQLite compatibility)
_assignment_lock = asyncio.Lock()


class ParticipantAssignmentError(Exception):
    """Base exception for participant assignment errors."""
    def __init__(self, message: str, code: str = "ASSIGNMENT_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class SessionFullError(ParticipantAssignmentError):
    """Raised when session is full (4 participants already)."""
    def __init__(self, session_id: int):
        super().__init__(
            f"Session {session_id} is full (max {MAX_PARTICIPANTS} participants)",
            "SESSION_FULL"
        )


class SessionNotJoinableError(ParticipantAssignmentError):
    """Raised when session is not in a joinable state."""
    def __init__(self, session_id: int, current_state: str):
        super().__init__(
            f"Session {session_id} is not joinable (state: {current_state})",
            "SESSION_NOT_JOINABLE"
        )


class DuplicateJoinError(ParticipantAssignmentError):
    """Raised when user tries to join a session they're already in."""
    def __init__(self, session_id: int, user_id: int):
        super().__init__(
            f"User {user_id} is already a participant in session {session_id}",
            "DUPLICATE_JOIN"
        )


class UnauthorizedRoleError(ParticipantAssignmentError):
    """Raised when non-student tries to join as participant."""
    def __init__(self):
        super().__init__(
            "Only students can join as participants",
            "UNAUTHORIZED_ROLE"
        )


class RaceConditionError(ParticipantAssignmentError):
    """Raised when race condition detected (slot taken during assignment)."""
    def __init__(self, side: str, speaker_number: int):
        super().__init__(
            f"Position {side} #{speaker_number} was just taken. Please try again.",
            "RACE_CONDITION"
        )


def slot_for_position(position: int) -> Tuple[str, int]:
    """
    Pure function: Deterministic slot mapping.
    
    NO randomness. NO shuffle. NO timestamp reliance.
    
    Mapping:
        1 → PETITIONER, 1
        2 → RESPONDENT, 1
        3 → PETITIONER, 2
        4 → RESPONDENT, 2
    
    Args:
        position: 1-indexed position (1-4)
        
    Returns:
        Tuple of (side: str, speaker_number: int)
        
    Raises:
        ValueError: If position not in 1-4
    """
    if position < 1 or position > MAX_PARTICIPANTS:
        raise ValueError(f"Position must be 1-{MAX_PARTICIPANTS}, got {position}")
    
    mapping = {
        1: ("PETITIONER", 1),
        2: ("RESPONDENT", 1),
        3: ("PETITIONER", 2),
        4: ("RESPONDENT", 2)
    }
    return mapping[position]


def get_assignment_for_position(position: int) -> Tuple[str, int]:
    """Backwards compatibility wrapper for slot_for_position."""
    return slot_for_position(position)


async def assign_participant(
    session_id: int,
    user_id: int,
    db: AsyncSession,
    is_student: bool = False,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None
) -> Dict[str, Any]:
    """
    Deterministic, concurrency-safe participant assignment.
    
    Uses global asyncio Lock to serialize concurrent requests for SQLite compatibility.
    This ensures race conditions are handled at the application level.
    
    Args: (same as before)
    Returns: (same as before)
    Raises: (same as before)
    """
    logger.info(f"[ASSIGNMENT START] session={session_id} user={user_id}")
    
    if not is_student:
        raise UnauthorizedRoleError()
    
    # Use global lock to serialize concurrent assignments
    async with _assignment_lock:
        # Check session state
        session_result = await db.execute(
            select(ClassroomSession).where(ClassroomSession.id == session_id)
        )
        session = session_result.scalar_one_or_none()
        
        if not session:
            raise ParticipantAssignmentError(f"Session {session_id} not found", "SESSION_NOT_FOUND")
        
        current_state = (session.current_state or "CREATED").upper()
        if current_state not in JOINABLE_STATES:
            raise SessionNotJoinableError(session_id, current_state)
        
        # Check for existing participant (idempotency)
        existing_result = await db.execute(
            select(ClassroomParticipant)
            .where(
                ClassroomParticipant.session_id == session_id,
                ClassroomParticipant.user_id == user_id,
                ClassroomParticipant.is_active == True
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing:
            return {
                "session_id": session_id, "user_id": user_id,
                "side": existing.side, "speaker_number": existing.speaker_number,
                "total_participants": existing.speaker_number if existing.side == "PETITIONER" else existing.speaker_number + 2,
                "is_new": False
            }
        
        # Get fresh participant count
        count_result = await db.execute(
            select(func.count(ClassroomParticipant.id))
            .where(
                ClassroomParticipant.session_id == session_id,
                ClassroomParticipant.is_active == True
            )
        )
        current_count = count_result.scalar()
        
        if current_count >= MAX_PARTICIPANTS:
            raise SessionFullError(session_id)
        
        # Calculate deterministic assignment
        position = current_count + 1
        side, speaker_number = slot_for_position(position)
        
        logger.info(f"[ASSIGNING] session={session_id} user={user_id} -> {side} #{speaker_number}")
        
        # Create participant
        participant = ClassroomParticipant(
            session_id=session_id, user_id=user_id,
            side=side, speaker_number=speaker_number,
            role=side.lower(), is_active=True, is_connected=True
        )
        db.add(participant)
        
        try:
            await db.flush()
        except IntegrityError as e:
            error_msg = str(e).lower()
            if "side" in error_msg and "speaker_number" in error_msg:
                logger.warning(f"[RACE] Slot {side} #{speaker_number} taken")
                raise RaceConditionError(side, speaker_number)
            elif "user_id" in error_msg:
                raise DuplicateJoinError(session_id, user_id)
            else:
                logger.error(f"[DB ERROR] {e}")
                raise ParticipantAssignmentError(f"Database error: {e}", "DB_ERROR")
        
        # Log success
        log_entry = ClassroomParticipantAuditLog(
            session_id=session_id, user_id=user_id,
            side=side, speaker_number=speaker_number, position=position,
            is_successful=True, ip_address=ip_address, user_agent=user_agent
        )
        db.add(log_entry)
        
        logger.info(f"[ASSIGNMENT SUCCESS] session={session_id} user={user_id} -> {side} #{speaker_number}")
        
        return {
            "session_id": session_id, "user_id": user_id,
            "side": side, "speaker_number": speaker_number,
            "total_participants": position, "position": position, "is_new": True
        }


async def get_participant_assignments(
    db: AsyncSession,
    session_id: int
) -> List[Dict[str, Any]]:
    """
    Get all participant assignments for a session.
    
    Args:
        db: Database session
        session_id: Session ID
        
    Returns:
        List of participant assignment dicts
    """
    result = await db.execute(
        select(ClassroomParticipant)
        .where(
            ClassroomParticipant.session_id == session_id,
            ClassroomParticipant.is_active == True
        )
        .order_by(ClassroomParticipant.joined_at)
    )
    
    participants = result.scalars().all()
    return [p.to_dict() for p in participants]


async def get_assignment_audit_log(
    db: AsyncSession,
    session_id: int,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """
    Get audit log for a session.
    
    Args:
        db: Database session
        session_id: Session ID
        limit: Maximum records to return
        
    Returns:
        List of audit log entries
    """
    result = await db.execute(
        select(ClassroomParticipantAuditLog)
        .where(ClassroomParticipantAuditLog.session_id == session_id)
        .order_by(ClassroomParticipantAuditLog.created_at.desc())
        .limit(limit)
    )
    
    logs = result.scalars().all()
    return [log.to_dict() for log in logs]


async def verify_assignment_integrity(
    db: AsyncSession,
    session_id: int
) -> Dict[str, Any]:
    """
    Verify assignment integrity for a session.
    
    Checks:
    - No duplicate (session_id, user_id)
    - No duplicate (session_id, side, speaker_number)
    - Exactly 4 participants max
    - Correct distribution (2 PETITIONER, 2 RESPONDENT)
    - Speaker numbers [1,2] each side
    
    Args:
        db: Database session
        session_id: Session ID
        
    Returns:
        Dict with integrity check results
    """
    result = await db.execute(
        select(ClassroomParticipant)
        .where(
            ClassroomParticipant.session_id == session_id,
            ClassroomParticipant.is_active == True
        )
    )
    participants = result.scalars().all()
    
    errors = []
    warnings = []
    
    # Check count
    if len(participants) > MAX_PARTICIPANTS:
        errors.append(f"Too many participants: {len(participants)} > {MAX_PARTICIPANTS}")
    
    # Check duplicates
    user_ids = [p.user_id for p in participants]
    if len(user_ids) != len(set(user_ids)):
        errors.append("Duplicate user_id found")
    
    slots = [(p.side, p.speaker_number) for p in participants]
    if len(slots) != len(set(slots)):
        errors.append("Duplicate (side, speaker_number) slot found")
    
    # Check distribution
    petitioners = [p for p in participants if p.side == "PETITIONER"]
    respondents = [p for p in participants if p.side == "RESPONDENT"]
    
    if len(petitioners) > 2:
        errors.append(f"Too many petitioners: {len(petitioners)}")
    if len(respondents) > 2:
        errors.append(f"Too many respondents: {len(respondents)}")
    
    # Check speaker numbers
    pet_speakers = sorted([p.speaker_number for p in petitioners])
    resp_speakers = sorted([p.speaker_number for p in respondents])
    
    if pet_speakers not in [[], [1], [2], [1, 2]]:
        warnings.append(f"Unusual petitioner speaker numbers: {pet_speakers}")
    if resp_speakers not in [[], [1], [2], [1, 2]]:
        warnings.append(f"Unusual respondent speaker numbers: {resp_speakers}")
    
    return {
        "session_id": session_id,
        "total_participants": len(participants),
        "petitioners": len(petitioners),
        "respondents": len(respondents),
        "is_valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "participants": [p.to_dict() for p in participants]
    }
