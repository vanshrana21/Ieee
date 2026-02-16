"""
National Ledger Service — Phase 7 (Cross-Institution Tournament Audit Trail)

Provides tamper-evident blockchain-like ledger for national tournament events.

Features:
- Cryptographic hash chaining (SHA256)
- Append-only enforcement via SQLAlchemy event guards
- Tamper detection via chain verification
- Institution-scoped isolation

Rules:
- All ledger entries are immutable
- Hash = SHA256(previous_hash + sorted_json(event_data) + timestamp)
- Previous hash links create chain integrity
- Updates and deletions are prohibited
"""
import json
import hashlib
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

from sqlalchemy import select, func, and_, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.orm.national_network import (
    NationalLedgerEntry, TournamentLedgerEventType
)

logger = logging.getLogger(__name__)


# =============================================================================
# Hash Chain Functions
# =============================================================================

def compute_ledger_hash(
    previous_hash: str,
    event_data: Dict[str, Any],
    timestamp: str
) -> str:
    """
    Compute the cryptographic hash for a ledger entry.
    
    Hash formula: SHA256(previous_hash + json.dumps(event_data, sort_keys=True) + timestamp)
    
    Args:
        previous_hash: Hash of the previous entry (or "GENESIS")
        event_data: Event data dictionary
        timestamp: ISO format timestamp string
        
    Returns:
        SHA256 hex digest (64 characters)
    """
    # Serialize event data with sorted keys for determinism
    event_json = json.dumps(event_data, sort_keys=True, separators=(',', ':'))
    
    # Concatenate: previous_hash + event_json + timestamp
    data_to_hash = f"{previous_hash}{event_json}{timestamp}"
    
    # Compute SHA256 hash
    hash_digest = hashlib.sha256(data_to_hash.encode('utf-8')).hexdigest()
    
    return hash_digest


async def get_last_ledger_hash(
    tournament_id: int,
    db: AsyncSession
) -> str:
    """
    Get the hash of the most recent ledger entry for a tournament.
    
    Returns "GENESIS" if no entries exist (first entry in chain).
    
    Args:
        tournament_id: Tournament to get last hash for
        db: Database session
        
    Returns:
        Previous hash string (64 hex chars or "GENESIS")
    """
    result = await db.execute(
        select(NationalLedgerEntry.event_hash)
        .where(NationalLedgerEntry.tournament_id == tournament_id)
        .order_by(NationalLedgerEntry.id.desc())
        .limit(1)
    )
    
    last_hash = result.scalar_one_or_none()
    
    if last_hash:
        return last_hash
    
    return "GENESIS"


# =============================================================================
# Ledger Append Functions
# =============================================================================

async def append_national_ledger_entry(
    tournament_id: int,
    event_type: TournamentLedgerEventType,
    entity_type: str,
    entity_id: int,
    event_data: Dict[str, Any],
    actor_user_id: int,
    db: AsyncSession,
    institution_id: Optional[int] = None
) -> NationalLedgerEntry:
    """
    Append a new entry to the national tournament ledger.
    
    Automatically computes hash based on previous entry in chain.
    
    Args:
        tournament_id: Tournament scope
        event_type: Type of tournament event
        entity_type: Entity type (e.g., 'tournament', 'match', 'team')
        entity_id: Entity ID
        event_data: Event-specific data dictionary
        actor_user_id: User performing the action
        db: Database session
        institution_id: Institution scope (optional, defaults to actor's institution)
        
    Returns:
        Created ledger entry
    """
    # Get previous hash
    previous_hash = await get_last_ledger_hash(tournament_id, db)
    
    # Generate timestamp
    timestamp = datetime.utcnow()
    timestamp_str = timestamp.isoformat()
    
    # Compute hash
    event_hash = compute_ledger_hash(previous_hash, event_data, timestamp_str)
    
    # If institution_id not provided, look up from actor
    if institution_id is None and actor_user_id:
        from backend.orm.user import User
        result = await db.execute(
            select(User).where(User.id == actor_user_id)
        )
        user = result.scalar_one_or_none()
        if user:
            institution_id = user.institution_id
    
    # Create entry
    entry = NationalLedgerEntry(
        tournament_id=tournament_id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        event_data_json=json.dumps(event_data, sort_keys=True),
        event_hash=event_hash,
        previous_hash=previous_hash,
        actor_user_id=actor_user_id,
        institution_id=institution_id or 0,  # Default to 0 if still None
        created_at=timestamp
    )
    
    db.add(entry)
    await db.flush()
    
    logger.debug(
        f"Appended ledger entry {entry.id} for tournament {tournament_id}: "
        f"{event_type.value} on {entity_type}#{entity_id}"
    )
    
    return entry


# =============================================================================
# Chain Verification Functions
# =============================================================================

async def verify_national_ledger_chain(
    tournament_id: int,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Verify the integrity of the national tournament ledger chain.
    
    Checks:
    1. Every entry's hash matches recomputed hash
    2. Every entry's previous_hash matches the previous entry's event_hash
    3. No gaps in the chain
    4. Genesis entry has previous_hash = "GENESIS"
    
    Args:
        tournament_id: Tournament to verify
        db: Database session
        
    Returns:
        Verification result dict with:
        - is_valid: Boolean indicating chain integrity
        - total_entries: Number of entries checked
        - first_entry_id: ID of first entry
        - last_entry_id: ID of last entry
        - invalid_entries: List of invalid entry IDs with reasons
        - errors: List of error messages
    """
    # Get all entries for tournament ordered by ID
    result = await db.execute(
        select(NationalLedgerEntry)
        .where(NationalLedgerEntry.tournament_id == tournament_id)
        .order_by(NationalLedgerEntry.id.asc())
    )
    entries = list(result.scalars().all())
    
    if not entries:
        return {
            "is_valid": True,
            "total_entries": 0,
            "first_entry_id": None,
            "last_entry_id": None,
            "invalid_entries": [],
            "errors": ["No ledger entries found for tournament"]
        }
    
    invalid_entries = []
    errors = []
    
    for i, entry in enumerate(entries):
        entry_errors = []
        
        # Check 1: First entry should have GENESIS as previous_hash
        if i == 0:
            if entry.previous_hash != "GENESIS":
                entry_errors.append(f"First entry previous_hash is '{entry.previous_hash}', expected 'GENESIS'")
        else:
            # Check 2: Previous hash should match previous entry's event_hash
            prev_entry = entries[i - 1]
            if entry.previous_hash != prev_entry.event_hash:
                entry_errors.append(
                    f"Broken chain: previous_hash '{entry.previous_hash}' "
                    f"does not match previous entry's event_hash '{prev_entry.event_hash}'"
                )
        
        # Check 3: Recompute hash and verify
        event_data = json.loads(entry.event_data_json) if entry.event_data_json else {}
        timestamp_str = entry.created_at.isoformat() if entry.created_at else ""
        
        computed_hash = compute_ledger_hash(
            entry.previous_hash,
            event_data,
            timestamp_str
        )
        
        if computed_hash != entry.event_hash:
            entry_errors.append(
                f"Hash mismatch: stored '{entry.event_hash}', computed '{computed_hash}'"
            )
        
        if entry_errors:
            invalid_entries.append({
                "entry_id": entry.id,
                "event_type": entry.event_type.value if entry.event_type else None,
                "errors": entry_errors
            })
            errors.extend([f"Entry {entry.id}: {e}" for e in entry_errors])
    
    is_valid = len(invalid_entries) == 0
    
    return {
        "is_valid": is_valid,
        "total_entries": len(entries),
        "first_entry_id": entries[0].id,
        "last_entry_id": entries[-1].id,
        "invalid_entries": invalid_entries,
        "errors": errors if errors else None
    }


async def verify_single_ledger_entry(
    entry_id: int,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Verify a single ledger entry's hash integrity.
    
    Args:
        entry_id: Entry to verify
        db: Database session
        
    Returns:
        Verification result dict
    """
    result = await db.execute(
        select(NationalLedgerEntry).where(NationalLedgerEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    
    if not entry:
        return {
            "is_valid": False,
            "entry_id": entry_id,
            "error": "Entry not found"
        }
    
    # Recompute hash
    event_data = json.loads(entry.event_data_json) if entry.event_data_json else {}
    timestamp_str = entry.created_at.isoformat() if entry.created_at else ""
    
    computed_hash = compute_ledger_hash(
        entry.previous_hash,
        event_data,
        timestamp_str
    )
    
    is_valid = computed_hash == entry.event_hash
    
    return {
        "is_valid": is_valid,
        "entry_id": entry_id,
        "stored_hash": entry.event_hash,
        "computed_hash": computed_hash,
        "event_type": entry.event_type.value if entry.event_type else None,
        "previous_hash": entry.previous_hash,
        "timestamp": timestamp_str,
        "error": None if is_valid else f"Hash mismatch: stored '{entry.event_hash}', computed '{computed_hash}'"
    }


# =============================================================================
# Ledger Query Functions
# =============================================================================

async def get_ledger_entries_for_tournament(
    tournament_id: int,
    db: AsyncSession,
    event_type: Optional[TournamentLedgerEventType] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0
) -> List[NationalLedgerEntry]:
    """
    Get ledger entries for a tournament with optional filtering.
    
    Args:
        tournament_id: Tournament scope
        db: Database session
        event_type: Filter by event type
        entity_type: Filter by entity type
        entity_id: Filter by specific entity
        limit: Maximum entries to return
        offset: Pagination offset
        
    Returns:
        List of ledger entries
    """
    query = select(NationalLedgerEntry).where(
        NationalLedgerEntry.tournament_id == tournament_id
    )
    
    if event_type:
        query = query.where(NationalLedgerEntry.event_type == event_type)
    
    if entity_type:
        query = query.where(NationalLedgerEntry.entity_type == entity_type)
    
    if entity_id:
        query = query.where(NationalLedgerEntry.entity_id == entity_id)
    
    query = query.order_by(NationalLedgerEntry.id.desc())
    query = query.limit(limit).offset(offset)
    
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_ledger_entries_for_institution(
    institution_id: int,
    db: AsyncSession,
    limit: int = 100
) -> List[NationalLedgerEntry]:
    """
    Get ledger entries scoped to an institution.
    
    Args:
        institution_id: Institution to filter by
        db: Database session
        limit: Maximum entries to return
        
    Returns:
        List of ledger entries
    """
    result = await db.execute(
        select(NationalLedgerEntry)
        .where(NationalLedgerEntry.institution_id == institution_id)
        .order_by(NationalLedgerEntry.id.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_ledger_summary_for_tournament(
    tournament_id: int,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Get summary statistics for a tournament's ledger.
    
    Args:
        tournament_id: Tournament to summarize
        db: Database session
        
    Returns:
        Summary dictionary
    """
    # Total entries
    result = await db.execute(
        select(func.count(NationalLedgerEntry.id))
        .where(NationalLedgerEntry.tournament_id == tournament_id)
    )
    total_entries = result.scalar() or 0
    
    # Entries by event type
    result = await db.execute(
        select(
            NationalLedgerEntry.event_type,
            func.count(NationalLedgerEntry.id).label('count')
        )
        .where(NationalLedgerEntry.tournament_id == tournament_id)
        .group_by(NationalLedgerEntry.event_type)
    )
    event_type_counts = {
        row.event_type.value: row.count for row in result.all()
    }
    
    # First and last entry dates
    result = await db.execute(
        select(
            func.min(NationalLedgerEntry.created_at).label('first_entry'),
            func.max(NationalLedgerEntry.created_at).label('last_entry')
        )
        .where(NationalLedgerEntry.tournament_id == tournament_id)
    )
    row = result.one()
    
    # Unique institutions involved
    result = await db.execute(
        select(func.count(func.distinct(NationalLedgerEntry.institution_id)))
        .where(NationalLedgerEntry.tournament_id == tournament_id)
    )
    unique_institutions = result.scalar() or 0
    
    return {
        "tournament_id": tournament_id,
        "total_entries": total_entries,
        "event_type_counts": event_type_counts,
        "first_entry_at": row.first_entry.isoformat() if row.first_entry else None,
        "last_entry_at": row.last_entry.isoformat() if row.last_entry else None,
        "unique_institutions": unique_institutions
    }


# =============================================================================
# Ledger Export Functions
# =============================================================================

async def export_ledger_to_dict(
    tournament_id: int,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Export entire ledger for a tournament as a dictionary.
    
    Useful for external verification or backup.
    
    Args:
        tournament_id: Tournament to export
        db: Database session
        
    Returns:
        Dictionary with ledger entries and verification info
    """
    # Get all entries
    entries = await get_ledger_entries_for_tournament(
        tournament_id=tournament_id,
        db=db,
        limit=10000  # High limit for export
    )
    
    # Reverse to chronological order (oldest first)
    entries.reverse()
    
    # Verify chain
    verification = await verify_national_ledger_chain(tournament_id, db)
    
    return {
        "tournament_id": tournament_id,
        "export_timestamp": datetime.utcnow().isoformat(),
        "chain_verified": verification["is_valid"],
        "total_entries": len(entries),
        "entries": [entry.to_dict() for entry in entries],
        "verification": verification
    }


# =============================================================================
# Ledger Integrity Monitoring
# =============================================================================

async def check_ledger_integrity_alerts(
    db: AsyncSession
) -> List[Dict[str, Any]]:
    """
    Check for ledger integrity issues across all tournaments.
    
    Returns list of tournaments with invalid chains.
    
    Args:
        db: Database session
        
    Returns:
        List of integrity alerts
    """
    # Get all tournament IDs with ledger entries
    result = await db.execute(
        select(NationalLedgerEntry.tournament_id)
        .distinct()
    )
    tournament_ids = [row[0] for row in result.all()]
    
    alerts = []
    
    for tournament_id in tournament_ids:
        verification = await verify_national_ledger_chain(tournament_id, db)
        
        if not verification["is_valid"]:
            alerts.append({
                "tournament_id": tournament_id,
                "severity": "CRITICAL",
                "issue": "Ledger chain integrity failure",
                "invalid_entries": verification["invalid_entries"],
                "errors": verification["errors"]
            })
    
    return alerts
