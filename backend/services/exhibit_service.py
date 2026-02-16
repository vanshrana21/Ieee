"""
Phase 7 — Evidence & Exhibit Management Service Layer

Server-authoritative with:
- Streaming file upload with SHA256 hash
- Deterministic exhibit numbering (P-1, P-2, R-1, R-2...)
- State machine: uploaded → marked → tendered → admitted/rejected
- Presiding judge authority enforcement
- Cryptographic event logging
- SERIALIZABLE isolation for critical paths
- FOR UPDATE locking

All state changes append events to chain.
"""
import hashlib
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, and_, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.orm.live_court import (
    LiveCourtSession, LiveTurn, LiveCourtStatus, LiveTurnState
)
from backend.orm.exhibit import SessionExhibit, ExhibitState
from backend.orm.user import User, UserRole


# =============================================================================
# Custom Exceptions
# =============================================================================

class ExhibitNotFoundError(Exception):
    pass


class ExhibitAlreadyRuledError(Exception):
    pass


class InvalidStateTransitionError(Exception):
    pass


class NotPresidingJudgeError(Exception):
    """Raised when non-presiding judge tries to rule."""
    pass


class SessionNotLiveError(Exception):
    """Raised when session is not in LIVE status."""
    pass


class SessionCompletedError(Exception):
    """Raised when session is completed."""
    pass


class InvalidFileError(Exception):
    """Raised when file validation fails."""
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
# Private: File Validation
# =============================================================================

def validate_pdf_magic_bytes(file_content: bytes) -> bool:
    """
    Validate PDF file by checking magic bytes.
    PDF files start with %PDF- (0x25 0x50 0x44 0x46)
    """
    if len(file_content) < 4:
        return False
    return file_content[:4] == b'%PDF'


def compute_file_hash(file_content: bytes) -> str:
    """Compute SHA256 hash of file content."""
    return hashlib.sha256(file_content).hexdigest()


# =============================================================================
# A) upload_exhibit()
# =============================================================================

async def upload_exhibit(
    session_id: int,
    institution_id: int,
    side: str,
    original_filename: str,
    file_content: bytes,
    uploaded_by_user_id: int,
    db: AsyncSession,
    storage_path: str = "/tmp/exhibits"
) -> SessionExhibit:
    """
    Upload an exhibit file.

    Flow:
    1. Validate PDF magic bytes
    2. Compute SHA256 file hash
    3. Store file with UUID filename
    4. Create exhibit record (state=uploaded)
    5. Append EXHIBIT_UPLOADED event
    6. Commit

    Args:
        session_id: Session ID
        institution_id: Institution ID (for scoping)
        side: "petitioner" or "respondent"
        original_filename: Original filename
        file_content: File bytes
        uploaded_by_user_id: User uploading
        db: Database session
        storage_path: Path to store files

    Returns:
        SessionExhibit record

    Raises:
        InvalidFileError: If file not valid PDF
        SessionCompletedError: If session completed
    """
    # Validate session exists and not completed
    result = await db.execute(
        select(LiveCourtSession)
        .where(LiveCourtSession.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise ExhibitNotFoundError(f"Session {session_id} not found")

    if session.is_completed():
        raise SessionCompletedError("Cannot upload exhibit after session completed")

    # Validate PDF
    if not validate_pdf_magic_bytes(file_content):
        raise InvalidFileError("File must be a valid PDF")

    # Compute file hash
    file_hash = compute_file_hash(file_content)

    # Generate UUID filename
    file_uuid = str(uuid.uuid4())
    file_extension = Path(original_filename).suffix.lower()
    if file_extension != '.pdf':
        file_extension = '.pdf'

    stored_filename = f"{file_uuid}{file_extension}"
    file_path = os.path.join(storage_path, stored_filename)

    # Store file (in production, use proper storage)
    os.makedirs(storage_path, exist_ok=True)
    with open(file_path, 'wb') as f:
        f.write(file_content)

    # Create exhibit record (uploaded state - no exhibit_number yet)
    now = datetime.utcnow()
    exhibit = SessionExhibit(
        session_id=session_id,
        institution_id=institution_id,
        side=side,
        exhibit_number=0,  # Will be assigned at marking
        original_filename=original_filename,
        file_path=file_path,
        file_hash_sha256=file_hash,
        state=ExhibitState.UPLOADED,
        marked_by_user_id=uploaded_by_user_id,
        exhibit_hash="0" * 64,  # Will be computed at marking
        marked_at=now,
        created_at=now
    )

    db.add(exhibit)
    await db.flush()  # Get exhibit.id

    # Append event
    await _append_event(
        session_id=session_id,
        event_type="EXHIBIT_UPLOADED",
        payload={
            "exhibit_id": exhibit.id,
            "original_filename": original_filename,
            "file_hash": file_hash,
            "side": side,
            "uploaded_by": uploaded_by_user_id
        },
        db=db
    )

    await db.flush()

    return exhibit


# =============================================================================
# B) mark_exhibit()
# =============================================================================

async def mark_exhibit(
    exhibit_id: int,
    marked_by_user_id: int,
    db: AsyncSession
) -> SessionExhibit:
    """
    Mark an exhibit with deterministic numbering.

    Flow:
    1. SERIALIZABLE isolation
    2. Lock session FOR UPDATE
    3. Lock existing exhibits FOR UPDATE
    4. Validate session.status == LIVE
    5. Validate exhibit.state == uploaded
    6. Assign exhibit_number deterministically:
       SELECT COALESCE(MAX(exhibit_number), 0) + 1
       FROM session_exhibits
       WHERE session_id = :session_id AND side = :side
       FOR UPDATE
    7. Compute exhibit_hash
    8. Update state = marked
    9. Append EXHIBIT_MARKED event
    10. Commit

    Args:
        exhibit_id: Exhibit to mark
        marked_by_user_id: User marking
        db: Database session

    Returns:
        Updated SessionExhibit

    Raises:
        ExhibitNotFoundError: If exhibit not found
        InvalidStateTransitionError: If not in uploaded state
        SessionNotLiveError: If session not live
    """
    # Set SERIALIZABLE isolation
    await db.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))

    # Get exhibit
    result = await db.execute(
        select(SessionExhibit)
        .where(SessionExhibit.id == exhibit_id)
        .with_for_update()
    )
    exhibit = result.scalar_one_or_none()

    if not exhibit:
        raise ExhibitNotFoundError(f"Exhibit {exhibit_id} not found")

    if exhibit.state != ExhibitState.UPLOADED:
        raise InvalidStateTransitionError(f"Cannot mark exhibit in state {exhibit.state.value}")

    # Lock session FOR UPDATE
    result = await db.execute(
        select(LiveCourtSession)
        .where(LiveCourtSession.id == exhibit.session_id)
        .with_for_update()
    )
    session = result.scalar_one_or_none()

    if not session:
        raise ExhibitNotFoundError(f"Session {exhibit.session_id} not found")

    if session.is_completed():
        raise SessionCompletedError("Cannot mark exhibit after session completed")

    if session.status != LiveCourtStatus.LIVE:
        raise SessionNotLiveError(f"Session status is {session.status.value}, must be 'live'")

    # Get next exhibit number deterministically with lock
    result = await db.execute(
        select(func.coalesce(func.max(SessionExhibit.exhibit_number), 0) + 1)
        .where(
            and_(
                SessionExhibit.session_id == exhibit.session_id,
                SessionExhibit.side == exhibit.side
            )
        )
        .with_for_update()
    )
    next_number = result.scalar_one()

    # Update exhibit
    exhibit.exhibit_number = next_number
    exhibit.state = ExhibitState.MARKED
    exhibit.marked_by_user_id = marked_by_user_id
    exhibit.marked_at = datetime.utcnow()

    # Compute exhibit hash
    exhibit.exhibit_hash = SessionExhibit.compute_exhibit_hash(
        session_id=exhibit.session_id,
        side=exhibit.side,
        exhibit_number=exhibit.exhibit_number,
        file_hash_sha256=exhibit.file_hash_sha256,
        marked_at=exhibit.marked_at
    )

    await db.flush()

    # Append event
    await _append_event(
        session_id=exhibit.session_id,
        event_type="EXHIBIT_MARKED",
        payload={
            "exhibit_id": exhibit.id,
            "exhibit_number": exhibit.exhibit_number,
            "formatted_number": exhibit.get_formatted_number(),
            "side": exhibit.side,
            "exhibit_hash": exhibit.exhibit_hash,
            "marked_by": marked_by_user_id
        },
        db=db
    )

    await db.flush()

    return exhibit


# =============================================================================
# C) tender_exhibit()
# =============================================================================

async def tender_exhibit(
    exhibit_id: int,
    turn_id: int,
    tendered_by_user_id: int,
    db: AsyncSession
) -> SessionExhibit:
    """
    Tender an exhibit during a turn.

    Validates:
    - exhibit.state == marked
    - turn is ACTIVE
    - turn.session_id == exhibit.session_id

    Updates:
    - state = tendered
    - turn_id = turn_id
    - Append EXHIBIT_TENDERED event

    Args:
        exhibit_id: Exhibit to tender
        turn_id: Turn during which exhibit is tendered
        tendered_by_user_id: User tendering
        db: Database session

    Returns:
        Updated SessionExhibit
    """
    # Set SERIALIZABLE isolation
    await db.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))

    # Get exhibit
    result = await db.execute(
        select(SessionExhibit)
        .where(SessionExhibit.id == exhibit_id)
        .with_for_update()
    )
    exhibit = result.scalar_one_or_none()

    if not exhibit:
        raise ExhibitNotFoundError(f"Exhibit {exhibit_id} not found")

    if exhibit.state != ExhibitState.MARKED:
        raise InvalidStateTransitionError(f"Cannot tender exhibit in state {exhibit.state.value}")

    # Get and lock turn
    result = await db.execute(
        select(LiveTurn)
        .where(
            and_(
                LiveTurn.id == turn_id,
                LiveTurn.session_id == exhibit.session_id
            )
        )
        .with_for_update()
    )
    turn = result.scalar_one_or_none()

    if not turn:
        raise ExhibitNotFoundError(f"Turn {turn_id} not found in session")

    if turn.state != LiveTurnState.ACTIVE:
        raise InvalidStateTransitionError(f"Turn is not active (state: {turn.state.value})")

    # Update exhibit
    exhibit.state = ExhibitState.TENDERED
    exhibit.turn_id = turn_id

    await db.flush()

    # Append event
    await _append_event(
        session_id=exhibit.session_id,
        event_type="EXHIBIT_TENDERED",
        payload={
            "exhibit_id": exhibit.id,
            "turn_id": turn_id,
            "formatted_number": exhibit.get_formatted_number(),
            "tendered_by": tendered_by_user_id
        },
        db=db
    )

    await db.flush()

    return exhibit


# =============================================================================
# D) rule_exhibit()
# =============================================================================

async def rule_exhibit(
    exhibit_id: int,
    decision: ExhibitState,
    ruling_reason_text: Optional[str],
    ruled_by_user_id: int,
    is_presiding_judge: bool,
    db: AsyncSession
) -> SessionExhibit:
    """
    Rule on a tendered exhibit (admit or reject).

    Flow:
    1. SERIALIZABLE isolation
    2. Lock exhibit FOR UPDATE
    3. Validate state == tendered
    4. Validate presiding authority
    5. Validate session.status == LIVE
    6. Update state → admitted or rejected
    7. Set ruled_by_user_id
    8. Set ruled_at
    9. Append EXHIBIT_ADMITTED or EXHIBIT_REJECTED event
    10. Commit

    Idempotent: second ruling attempt fails cleanly.

    Args:
        exhibit_id: Exhibit to rule on
        decision: ADMITTED or REJECTED
        ruling_reason_text: Optional explanation
        ruled_by_user_id: Judge making ruling
        is_presiding_judge: Whether user is presiding
        db: Database session

    Returns:
        Updated SessionExhibit

    Raises:
        ExhibitNotFoundError: If exhibit not found
        ExhibitAlreadyRuledError: If already ruled
        InvalidStateTransitionError: If not in tendered state
        NotPresidingJudgeError: If not presiding judge
    """
    if decision not in (ExhibitState.ADMITTED, ExhibitState.REJECTED):
        raise InvalidStateTransitionError("Decision must be ADMITTED or REJECTED")

    # Set SERIALIZABLE isolation
    await db.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))

    # Lock exhibit
    result = await db.execute(
        select(SessionExhibit)
        .where(SessionExhibit.id == exhibit_id)
        .with_for_update()
    )
    exhibit = result.scalar_one_or_none()

    if not exhibit:
        raise ExhibitNotFoundError(f"Exhibit {exhibit_id} not found")

    # Idempotency check
    if exhibit.is_ruled():
        raise ExhibitAlreadyRuledError(f"Exhibit already {exhibit.state.value}")

    if exhibit.state != ExhibitState.TENDERED:
        raise InvalidStateTransitionError(f"Cannot rule on exhibit in state {exhibit.state.value}")

    # Validate presiding judge
    if not is_presiding_judge:
        raise NotPresidingJudgeError("Only the presiding judge can rule on exhibits")

    # Validate session
    result = await db.execute(
        select(LiveCourtSession)
        .where(LiveCourtSession.id == exhibit.session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise ExhibitNotFoundError(f"Session {exhibit.session_id} not found")

    if session.is_completed():
        raise SessionCompletedError("Cannot rule on exhibit after session completed")

    if session.status != LiveCourtStatus.LIVE:
        raise SessionNotLiveError(f"Session status is {session.status.value}")

    # Update exhibit
    exhibit.state = decision
    exhibit.ruled_by_user_id = ruled_by_user_id
    exhibit.ruled_at = datetime.utcnow()

    await db.flush()

    # Append event
    event_type = (
        "EXHIBIT_ADMITTED" if decision == ExhibitState.ADMITTED
        else "EXHIBIT_REJECTED"
    )

    await _append_event(
        session_id=exhibit.session_id,
        event_type=event_type,
        payload={
            "exhibit_id": exhibit.id,
            "formatted_number": exhibit.get_formatted_number(),
            "ruling": decision.value,
            "ruling_reason": ruling_reason_text or "",
            "ruled_by": ruled_by_user_id
        },
        db=db
    )

    await db.flush()

    return exhibit


# =============================================================================
# E) Query Functions
# =============================================================================

async def get_exhibit_by_id(
    exhibit_id: int,
    db: AsyncSession
) -> Optional[SessionExhibit]:
    """Get exhibit by ID with relationships loaded."""
    result = await db.execute(
        select(SessionExhibit)
        .options(
            selectinload(SessionExhibit.marked_by),
            selectinload(SessionExhibit.ruled_by)
        )
        .where(SessionExhibit.id == exhibit_id)
    )
    return result.scalar_one_or_none()


async def get_exhibits_by_session(
    session_id: int,
    db: AsyncSession,
    state: Optional[ExhibitState] = None,
    side: Optional[str] = None
) -> List[SessionExhibit]:
    """Get all exhibits for a session with optional filters."""
    query = (
        select(SessionExhibit)
        .options(
            selectinload(SessionExhibit.marked_by),
            selectinload(SessionExhibit.ruled_by)
        )
        .where(SessionExhibit.session_id == session_id)
    )

    if state:
        query = query.where(SessionExhibit.state == state)

    if side:
        query = query.where(SessionExhibit.side == side)

    # Order by side then exhibit number for deterministic listing
    query = query.order_by(SessionExhibit.side.asc(), SessionExhibit.exhibit_number.asc())

    result = await db.execute(query)
    return list(result.scalars().all())


async def get_exhibits_by_turn(
    turn_id: int,
    db: AsyncSession
) -> List[SessionExhibit]:
    """Get all exhibits tendered during a turn."""
    result = await db.execute(
        select(SessionExhibit)
        .options(
            selectinload(SessionExhibit.marked_by),
            selectinload(SessionExhibit.ruled_by)
        )
        .where(SessionExhibit.turn_id == turn_id)
        .order_by(SessionExhibit.exhibit_number.asc())
    )
    return list(result.scalars().all())


async def verify_exhibit_integrity(
    exhibit_id: int,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Verify exhibit integrity by checking:
    - Exhibit hash matches computed hash
    - File hash matches stored hash
    - File exists on disk
    """
    exhibit = await get_exhibit_by_id(exhibit_id, db)

    if not exhibit:
        return {
            "exhibit_id": exhibit_id,
            "found": False,
            "valid": False,
            "error": "Exhibit not found"
        }

    issues = []

    # Check exhibit hash
    if not exhibit.verify_hash():
        issues.append("Exhibit hash mismatch")

    # Check file exists
    if not os.path.exists(exhibit.file_path):
        issues.append("File not found on disk")
    else:
        # Verify file hash
        try:
            with open(exhibit.file_path, 'rb') as f:
                content = f.read()
            computed_file_hash = compute_file_hash(content)
            if computed_file_hash != exhibit.file_hash_sha256:
                issues.append("File hash mismatch - file tampered")
        except Exception as e:
            issues.append(f"Error reading file: {e}")

    is_valid = len(issues) == 0

    return {
        "exhibit_id": exhibit_id,
        "found": True,
        "valid": is_valid,
        "exhibit_hash_valid": exhibit.verify_hash(),
        "file_hash_valid": "File hash mismatch" not in issues,
        "file_exists": os.path.exists(exhibit.file_path),
        "issues": issues if issues else None,
        "message": "Exhibit verified" if is_valid else "Integrity issues detected"
    }
