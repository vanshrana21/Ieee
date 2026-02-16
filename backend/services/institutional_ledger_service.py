"""
Institutional Ledger Service — Phase 6 (Compliance Ledger with Hash Chaining)

Provides tamper-evident append-only ledger for institutional compliance.

Features:
- Cryptographic hash chaining (blockchain-like)
- SHA256 hashing with previous entry linkage
- Automatic genesis entry creation
- Chain integrity verification
- Institution-scoped ledger isolation

Rules:
- Ledger is append-only (no updates, no deletes)
- Each entry references previous entry hash
- First entry per institution has previous_hash = "GENESIS"
- All events are institution-scoped for multi-tenant isolation
"""
import hashlib
import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.orm.institutional_governance import (
    InstitutionalLedgerEntry,
    LedgerEntityType,
    LedgerEventType,
    Institution
)

logger = logging.getLogger(__name__)


class LedgerError(Exception):
    """Base ledger error."""
    def __init__(self, message: str, code: str):
        self.message = message
        self.code = code
        super().__init__(message)


class ChainIntegrityError(LedgerError):
    """Ledger chain integrity verification failed."""
    def __init__(self, institution_id: int, broken_at_entry: int):
        super().__init__(
            f"Ledger chain broken at entry {broken_at_entry} for institution {institution_id}",
            "CHAIN_INTEGRITY_ERROR"
        )


async def get_last_ledger_entry(
    institution_id: int,
    db: AsyncSession
) -> Optional[InstitutionalLedgerEntry]:
    """
    Get the most recent ledger entry for an institution.
    
    Returns None if no entries exist (needs genesis entry).
    """
    result = await db.execute(
        select(InstitutionalLedgerEntry)
        .where(InstitutionalLedgerEntry.institution_id == institution_id)
        .order_by(InstitutionalLedgerEntry.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_genesis_hash() -> str:
    """
    Return the special genesis hash for first entry in chain.
    
    This is a fixed constant that identifies the start of a ledger chain.
    """
    return "GENESIS"


def compute_event_hash(
    previous_hash: str,
    entity_type: LedgerEntityType,
    entity_id: int,
    event_type: LedgerEventType,
    event_data: Dict[str, Any],
    timestamp: datetime
) -> str:
    """
    Compute SHA256 hash of ledger entry data.
    
    The hash includes:
    - Previous entry hash (for chain linkage)
    - Entity type and ID
    - Event type
    - Event data (JSON)
    - Timestamp (ISO format)
    
    This creates a tamper-evident chain where any modification
    breaks all subsequent hashes.
    """
    # Build data string for hashing
    data = {
        "previous_hash": previous_hash,
        "entity_type": entity_type.value,
        "entity_id": entity_id,
        "event_type": event_type.value,
        "event_data": event_data,
        "timestamp": timestamp.isoformat()
    }
    
    # Canonical JSON representation (sorted keys, no whitespace)
    data_json = json.dumps(data, sort_keys=True, separators=(',', ':'))
    
    # Compute SHA256
    return hashlib.sha256(data_json.encode()).hexdigest()


async def append_institutional_ledger_entry(
    institution_id: int,
    entity_type: LedgerEntityType,
    entity_id: int,
    event_type: LedgerEventType,
    actor_user_id: Optional[int],
    event_data: Dict[str, Any],
    db: AsyncSession
) -> InstitutionalLedgerEntry:
    """
    Append a new entry to the institutional compliance ledger.
    
    This function:
    1. Fetches the last ledger entry to get previous_hash
    2. Uses "GENESIS" if no previous entry exists
    3. Computes SHA256 hash of the event data
    4. Creates and persists the ledger entry
    5. Returns the created entry
    
    Args:
        institution_id: Institution scope for multi-tenant isolation
        entity_type: Type of entity (SESSION, LEADERBOARD, EVALUATION)
        entity_id: ID of the entity
        event_type: Type of event (FREEZE_FINALIZED, etc.)
        actor_user_id: User who triggered the event (nullable for system)
        event_data: JSON-serializable event payload
        db: Database session
        
    Returns:
        Created InstitutionalLedgerEntry
        
    Raises:
        LedgerError: If institution does not exist
    """
    # Get previous entry hash
    last_entry = await get_last_ledger_entry(institution_id, db)
    
    if last_entry:
        previous_hash = last_entry.event_hash
    else:
        previous_hash = await get_genesis_hash()
        logger.info(f"Creating genesis ledger entry for institution {institution_id}")
    
    # Current timestamp
    now = datetime.utcnow()
    
    # Compute event hash
    event_hash = compute_event_hash(
        previous_hash=previous_hash,
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=event_type,
        event_data=event_data,
        timestamp=now
    )
    
    # Create ledger entry
    entry = InstitutionalLedgerEntry(
        institution_id=institution_id,
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=event_type,
        event_data_json=json.dumps(event_data, sort_keys=True),
        event_hash=event_hash,
        previous_hash=previous_hash,
        actor_user_id=actor_user_id,
        created_at=now
    )
    
    db.add(entry)
    await db.flush()
    
    logger.info(
        f"Ledger entry appended: institution={institution_id}, "
        f"entity={entity_type.value}:{entity_id}, "
        f"event={event_type.value}, hash={event_hash[:16]}..."
    )
    
    return entry


async def verify_ledger_chain_integrity(
    institution_id: int,
    db: AsyncSession
) -> Tuple[bool, Optional[int], Optional[str]]:
    """
    Verify the integrity of the institutional ledger chain.
    
    Walks through all entries and verifies:
    - Each entry's previous_hash matches the actual previous entry's hash
    - No entries are missing
    - No tampering has occurred
    
    Args:
        institution_id: Institution to verify
        db: Database session
        
    Returns:
        Tuple of (is_valid, broken_at_entry_id, expected_hash)
        - is_valid: True if chain is intact
        - broken_at_entry_id: Entry ID where chain broke (None if valid)
        - expected_hash: Expected previous hash at break point (None if valid)
    """
    # Fetch all entries in chronological order
    result = await db.execute(
        select(InstitutionalLedgerEntry)
        .where(InstitutionalLedgerEntry.institution_id == institution_id)
        .order_by(InstitutionalLedgerEntry.created_at.asc())
    )
    entries = result.scalars().all()
    
    if not entries:
        # Empty ledger is valid (no entries to verify)
        return True, None, None
    
    # Track expected previous hash
    expected_previous = await get_genesis_hash()
    
    for entry in entries:
        # Verify previous_hash matches expected
        if entry.previous_hash != expected_previous:
            logger.error(
                f"Ledger chain broken at entry {entry.id}: "
                f"expected previous_hash={expected_previous[:16]}..., "
                f"found={entry.previous_hash[:16]}..."
            )
            return False, entry.id, expected_previous
        
        # Verify entry's own hash is correctly computed
        computed_hash = compute_event_hash(
            previous_hash=entry.previous_hash,
            entity_type=entry.entity_type,
            entity_id=entry.entity_id,
            event_type=entry.event_type,
            event_data=json.loads(entry.event_data_json) if entry.event_data_json else {},
            timestamp=entry.created_at
        )
        
        if computed_hash != entry.event_hash:
            logger.error(
                f"Ledger entry hash mismatch at entry {entry.id}: "
                f"stored={entry.event_hash[:16]}..., "
                f"computed={computed_hash[:16]}..."
            )
            return False, entry.id, None
        
        # Update expected previous hash for next entry
        expected_previous = entry.event_hash
    
    logger.info(f"Ledger chain integrity verified for institution {institution_id}: {len(entries)} entries")
    return True, None, None


async def get_ledger_entries_for_entity(
    institution_id: int,
    entity_type: LedgerEntityType,
    entity_id: int,
    db: AsyncSession
) -> List[InstitutionalLedgerEntry]:
    """
    Get all ledger entries for a specific entity.
    
    Useful for audit trails of specific sessions, leaderboards, or evaluations.
    """
    result = await db.execute(
        select(InstitutionalLedgerEntry)
        .where(
            InstitutionalLedgerEntry.institution_id == institution_id,
            InstitutionalLedgerEntry.entity_type == entity_type,
            InstitutionalLedgerEntry.entity_id == entity_id
        )
        .order_by(InstitutionalLedgerEntry.created_at.asc())
    )
    return list(result.scalars().all())


async def get_ledger_summary(
    institution_id: int,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Get summary statistics for an institution's ledger.
    
    Returns:
        {
            "total_entries": int,
            "first_entry_at": datetime,
            "last_entry_at": datetime,
            "event_type_counts": {event_type: count},
            "chain_integrity_valid": bool
        }
    """
    # Count entries by event type
    result = await db.execute(
        select(
            InstitutionalLedgerEntry.event_type,
            func.count().label('count')
        )
        .where(InstitutionalLedgerEntry.institution_id == institution_id)
        .group_by(InstitutionalLedgerEntry.event_type)
    )
    event_counts = {row[0].value: row[1] for row in result.all()}
    
    # Get total count and date range
    total_result = await db.execute(
        select(
            func.count().label('total'),
            func.min(InstitutionalLedgerEntry.created_at).label('first'),
            func.max(InstitutionalLedgerEntry.created_at).label('last')
        )
        .where(InstitutionalLedgerEntry.institution_id == institution_id)
    )
    row = total_result.one()
    
    # Verify chain integrity
    is_valid, _, _ = await verify_ledger_chain_integrity(institution_id, db)
    
    return {
        "institution_id": institution_id,
        "total_entries": row.total,
        "first_entry_at": row.first.isoformat() if row.first else None,
        "last_entry_at": row.last.isoformat() if row.last else None,
        "event_type_counts": event_counts,
        "chain_integrity_valid": is_valid
    }


# =============================================================================
# Convenience Functions for Common Events
# =============================================================================

async def log_leaderboard_freeze_finalized(
    institution_id: int,
    snapshot_id: int,
    faculty_id: int,
    checksum_hash: str,
    db: AsyncSession
) -> InstitutionalLedgerEntry:
    """Log a leaderboard freeze finalization event."""
    return await append_institutional_ledger_entry(
        institution_id=institution_id,
        entity_type=LedgerEntityType.LEADERBOARD,
        entity_id=snapshot_id,
        event_type=LedgerEventType.FREEZE_FINALIZED,
        actor_user_id=faculty_id,
        event_data={
            "snapshot_id": snapshot_id,
            "checksum_hash": checksum_hash,
            "finalized_by": faculty_id
        },
        db=db
    )


async def log_leaderboard_freeze_pending_approval(
    institution_id: int,
    snapshot_id: int,
    faculty_id: int,
    required_approvals: List[str],
    db: AsyncSession
) -> InstitutionalLedgerEntry:
    """Log a leaderboard freeze pending approval event."""
    return await append_institutional_ledger_entry(
        institution_id=institution_id,
        entity_type=LedgerEntityType.LEADERBOARD,
        entity_id=snapshot_id,
        event_type=LedgerEventType.FREEZE_PENDING_APPROVAL,
        actor_user_id=faculty_id,
        event_data={
            "snapshot_id": snapshot_id,
            "required_approvals": required_approvals,
            "requested_by": faculty_id
        },
        db=db
    )


async def log_evaluation_overridden(
    institution_id: int,
    evaluation_id: int,
    faculty_id: int,
    previous_score: str,
    new_score: str,
    reason: str,
    db: AsyncSession
) -> InstitutionalLedgerEntry:
    """Log an evaluation override event."""
    return await append_institutional_ledger_entry(
        institution_id=institution_id,
        entity_type=LedgerEntityType.EVALUATION,
        entity_id=evaluation_id,
        event_type=LedgerEventType.EVALUATION_OVERRIDDEN,
        actor_user_id=faculty_id,
        event_data={
            "evaluation_id": evaluation_id,
            "previous_score": previous_score,
            "new_score": new_score,
            "override_reason": reason,
            "overridden_by": faculty_id
        },
        db=db
    )


async def log_snapshot_invalidated(
    institution_id: int,
    snapshot_id: int,
    admin_id: int,
    reason: str,
    db: AsyncSession
) -> InstitutionalLedgerEntry:
    """Log a snapshot invalidation event."""
    return await append_institutional_ledger_entry(
        institution_id=institution_id,
        entity_type=LedgerEntityType.LEADERBOARD,
        entity_id=snapshot_id,
        event_type=LedgerEventType.SNAPSHOT_INVALIDATED,
        actor_user_id=admin_id,
        event_data={
            "snapshot_id": snapshot_id,
            "invalidation_reason": reason,
            "invalidated_by": admin_id
        },
        db=db
    )


async def log_snapshot_published(
    institution_id: int,
    snapshot_id: int,
    user_id: int,
    publication_mode: str,
    scheduled_date: Optional[str],
    db: AsyncSession
) -> InstitutionalLedgerEntry:
    """Log a snapshot publication event."""
    return await append_institutional_ledger_entry(
        institution_id=institution_id,
        entity_type=LedgerEntityType.LEADERBOARD,
        entity_id=snapshot_id,
        event_type=LedgerEventType.SNAPSHOT_PUBLISHED,
        actor_user_id=user_id,
        event_data={
            "snapshot_id": snapshot_id,
            "publication_mode": publication_mode,
            "scheduled_date": scheduled_date,
            "published_by": user_id
        },
        db=db
    )


async def log_approval_granted(
    institution_id: int,
    session_id: int,
    approver_id: int,
    approver_role: str,
    approval_id: int,
    db: AsyncSession
) -> InstitutionalLedgerEntry:
    """Log an approval grant event."""
    return await append_institutional_ledger_entry(
        institution_id=institution_id,
        entity_type=LedgerEntityType.SESSION,
        entity_id=session_id,
        event_type=LedgerEventType.APPROVAL_GRANTED,
        actor_user_id=approver_id,
        event_data={
            "session_id": session_id,
            "approval_id": approval_id,
            "approver_role": approver_role,
            "approver_id": approver_id
        },
        db=db
    )


async def log_approval_rejected(
    institution_id: int,
    session_id: int,
    rejecter_id: int,
    rejecter_role: str,
    approval_id: int,
    reason: str,
    db: AsyncSession
) -> InstitutionalLedgerEntry:
    """Log an approval rejection event."""
    return await append_institutional_ledger_entry(
        institution_id=institution_id,
        entity_type=LedgerEntityType.SESSION,
        entity_id=session_id,
        event_type=LedgerEventType.APPROVAL_REJECTED,
        actor_user_id=rejecter_id,
        event_data={
            "session_id": session_id,
            "approval_id": approval_id,
            "rejecter_role": rejecter_role,
            "rejecter_id": rejecter_id,
            "rejection_reason": reason
        },
        db=db
    )
