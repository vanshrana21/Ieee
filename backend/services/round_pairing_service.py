"""
Phase 3 — Hardened Round Pairing Service Layer

Swiss + Knockout Pairing with:
- Deterministic algorithms
- Rematch prevention
- Side balancing
- SERIALIZABLE finalization
- No float(), no random(), no datetime.now()
"""
import hashlib
import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import select, and_, or_, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from backend.orm.round_pairing import (
    TournamentRound, RoundPairing, PairingHistory, RoundFreeze,
    RoundType, RoundStatus
)
from backend.orm.national_network import TournamentTeam, NationalTournament


# =============================================================================
# Custom Exceptions
# =============================================================================

class RoundPairingError(Exception):
    """Base exception for round pairing errors."""
    pass


class RoundNotFoundError(RoundPairingError):
    """Raised when round is not found."""
    pass


class RoundFinalizedError(RoundPairingError):
    """Raised when trying to modify finalized round."""
    pass


class RematchError(RoundPairingError):
    """Raised when trying to pair teams that have already met."""
    pass


class InsufficientTeamsError(RoundPairingError):
    """Raised when not enough teams for pairing."""
    pass


class TournamentScopeError(RoundPairingError):
    """Raised when tournament access is denied."""
    pass


# =============================================================================
# Helper Functions
# =============================================================================

def normalize_team_ids(team_a_id: int, team_b_id: int) -> Tuple[int, int]:
    """
    Normalize team IDs so team_a_id is always the smaller ID.
    
    This ensures consistent ordering in pairing_history.
    """
    if team_a_id < team_b_id:
        return (team_a_id, team_b_id)
    return (team_b_id, team_a_id)


# =============================================================================
# Round CRUD
# =============================================================================

async def create_round(
    tournament_id: int,
    round_number: int,
    round_type: RoundType,
    db: AsyncSession
) -> TournamentRound:
    """
    Create new tournament round.
    
    Args:
        tournament_id: Tournament ID
        round_number: Round number (1-indexed)
        round_type: swiss or knockout
        db: Database session
        
    Returns:
        Created TournamentRound
    """
    round_obj = TournamentRound(
        tournament_id=tournament_id,
        round_number=round_number,
        round_type=round_type,
        status=RoundStatus.DRAFT,
        pairing_checksum=None,
        published_at=None,
        finalized_at=None,
        created_at=datetime.utcnow()
    )
    
    db.add(round_obj)
    await db.flush()
    
    return round_obj


async def get_round_by_id(
    round_id: int,
    db: AsyncSession
) -> Optional[TournamentRound]:
    """Get round by ID."""
    result = await db.execute(
        select(TournamentRound).where(TournamentRound.id == round_id)
    )
    return result.scalar_one_or_none()


async def get_rounds_by_tournament(
    tournament_id: int,
    status: Optional[RoundStatus],
    db: AsyncSession
) -> List[TournamentRound]:
    """Get rounds for tournament (tournament-scoped)."""
    query = select(TournamentRound).where(TournamentRound.tournament_id == tournament_id)
    
    if status:
        query = query.where(TournamentRound.status == status)
    
    query = query.order_by(TournamentRound.round_number.asc())
    
    result = await db.execute(query)
    return list(result.scalars().all())


# =============================================================================
# Swiss Algorithm (Deterministic)
# =============================================================================

async def get_team_standings(
    tournament_id: int,
    db: AsyncSession
) -> List[Dict[str, Any]]:
    """
    Get team standings sorted deterministically:
    1. total_points DESC
    2. total_score DESC
    3. memorial_score DESC
    4. team_id ASC (final tiebreaker)
    """
    # Query team standings - this is a simplified version
    # In production, this would join with actual score tables
    result = await db.execute(
        select(
            TournamentTeam.id,
            TournamentTeam.team_code,
            func.coalesce(func.sum(0), 0).label("total_points"),
            func.coalesce(func.sum(0), 0).label("total_score"),
            func.coalesce(func.sum(0), 0).label("memorial_score"),
        )
        .where(TournamentTeam.tournament_id == tournament_id)
        .group_by(TournamentTeam.id)
        .order_by(
            func.coalesce(func.sum(0), 0).desc(),  # total_points
            func.coalesce(func.sum(0), 0).desc(),  # total_score
            func.coalesce(func.sum(0), 0).desc(),  # memorial_score
            TournamentTeam.id.asc()                 # final tiebreaker
        )
    )
    
    rows = result.all()
    
    standings = []
    for row in rows:
        standings.append({
            "team_id": row[0],
            "team_code": row[1],
            "total_points": row[2] or Decimal("0"),
            "total_score": row[3] or Decimal("0"),
            "memorial_score": row[4] or Decimal("0"),
        })
    
    return standings


async def get_past_pairings_for_tournament(
    tournament_id: int,
    db: AsyncSession
) -> Set[Tuple[int, int]]:
    """
    Get all historical pairings for rematch prevention.
    
    Returns set of (team_a_id, team_b_id) tuples where team_a_id < team_b_id.
    """
    result = await db.execute(
        select(PairingHistory.team_a_id, PairingHistory.team_b_id)
        .where(PairingHistory.tournament_id == tournament_id)
    )
    
    return set((row[0], row[1]) for row in result.all())


async def count_petitioner_appearances(
    team_id: int,
    db: AsyncSession
) -> int:
    """
    Count how many times a team has been petitioner.
    
    Used for side balancing.
    """
    result = await db.execute(
        select(func.count(RoundPairing.id))
        .where(RoundPairing.petitioner_team_id == team_id)
    )
    return result.scalar() or 0


async def generate_swiss_pairings(
    round_id: int,
    db: AsyncSession
) -> List[RoundPairing]:
    """
    Generate Swiss pairings for a round.
    
    Algorithm:
    1. Get standings sorted by points, scores, team_id
    2. For each unpaired team:
       - Find next team in standings that hasn't been paired
       - Check pairing_history - skip if rematch
       - If no valid opponent, pair with lowest remaining team_id
    3. Side balancing: team with fewer petitioner appearances petitions
       - Tie → lower team_id petitions
    4. Store pairing_history with team_a_id < team_b_id
    
    Args:
        round_id: Round to generate pairings for
        db: Database session
        
    Returns:
        List of created RoundPairing objects
    """
    # Get round
    round_obj = await get_round_by_id(round_id, db)
    if not round_obj:
        raise RoundNotFoundError(f"Round {round_id} not found")
    
    if round_obj.status == RoundStatus.FINALIZED:
        raise RoundFinalizedError("Cannot generate pairings for finalized round")
    
    tournament_id = round_obj.tournament_id
    
    # Get standings (deterministically sorted)
    standings = await get_team_standings(tournament_id, db)
    
    if len(standings) < 2:
        raise InsufficientTeamsError("Need at least 2 teams for pairing")
    
    # Get past pairings for rematch prevention
    past_pairings = await get_past_pairings_for_tournament(tournament_id, db)
    
    # Track paired teams
    paired_teams: Set[int] = set()
    created_pairings: List[RoundPairing] = []
    
    # Get all team IDs for fallback pairing
    all_team_ids = [s["team_id"] for s in standings]
    
    table_number = 1
    
    # Process teams in standings order
    for team_data in standings:
        team1_id = team_data["team_id"]
        
        # Skip if already paired
        if team1_id in paired_teams:
            continue
        
        # Find opponent
        opponent_id = None
        
        # Try to find unpaired, non-rematch opponent
        for opponent_data in standings:
            team2_id = opponent_data["team_id"]
            
            if team2_id == team1_id:
                continue
            if team2_id in paired_teams:
                continue
            
            # Check for rematch
            norm_ids = normalize_team_ids(team1_id, team2_id)
            if norm_ids in past_pairings:
                continue  # Skip - rematch not allowed
            
            # Valid opponent found
            opponent_id = team2_id
            break
        
        # If no valid opponent found, pair with lowest remaining team_id
        if opponent_id is None:
            for fallback_id in sorted(all_team_ids):  # Deterministic: lowest ID first
                if fallback_id != team1_id and fallback_id not in paired_teams:
                    opponent_id = fallback_id
                    break
        
        if opponent_id is None:
            raise RoundPairingError(f"Could not find opponent for team {team1_id}")
        
        # Side balancing: count petitioner appearances
        team1_petitioner_count = await count_petitioner_appearances(team1_id, db)
        team2_petitioner_count = await count_petitioner_appearances(opponent_id, db)
        
        # Team with fewer petitions gets to petition
        # Tie → lower team_id petitions
        if team1_petitioner_count < team2_petitioner_count:
            petitioner_id = team1_id
            respondent_id = opponent_id
        elif team2_petitioner_count < team1_petitioner_count:
            petitioner_id = opponent_id
            respondent_id = team1_id
        else:
            # Tie - lower ID petitions
            if team1_id < opponent_id:
                petitioner_id = team1_id
                respondent_id = opponent_id
            else:
                petitioner_id = opponent_id
                respondent_id = team1_id
        
        # Create pairing
        pairing = RoundPairing(
            round_id=round_id,
            petitioner_team_id=petitioner_id,
            respondent_team_id=respondent_id,
            table_number=table_number,
            pairing_hash="",  # Will compute
            created_at=datetime.utcnow()
        )
        
        # Compute hash
        pairing.pairing_hash = pairing.compute_pairing_hash()
        
        db.add(pairing)
        created_pairings.append(pairing)
        
        # Record in pairing_history (team_a_id always smaller)
        team_a_id, team_b_id = normalize_team_ids(team1_id, opponent_id)
        history = PairingHistory(
            tournament_id=tournament_id,
            team_a_id=team_a_id,
            team_b_id=team_b_id,
            round_id=round_id
        )
        db.add(history)
        
        # Mark as paired
        paired_teams.add(team1_id)
        paired_teams.add(opponent_id)
        
        table_number += 1
    
    await db.flush()
    
    return created_pairings


# =============================================================================
# Knockout Engine (Deterministic)
# =============================================================================

async def generate_knockout_pairings(
    round_id: int,
    db: AsyncSession
) -> List[RoundPairing]:
    """
    Generate knockout bracket pairings.
    
    Algorithm:
    1. Sort teams by seed (lower seed = higher ranked)
    2. Apply standard bracket pattern:
       - 1 vs N (top vs bottom)
       - 2 vs N-1
       - 3 vs N-2
       - etc.
    3. Side assignment: lower seed petitions
    
    Args:
        round_id: Round to generate pairings for
        db: Database session
        
    Returns:
        List of created RoundPairing objects
    """
    # Get round
    round_obj = await get_round_by_id(round_id, db)
    if not round_obj:
        raise RoundNotFoundError(f"Round {round_id} not found")
    
    if round_obj.status == RoundStatus.FINALIZED:
        raise RoundFinalizedError("Cannot generate pairings for finalized round")
    
    tournament_id = round_obj.tournament_id
    
    # Get teams sorted by seed (deterministic)
    result = await db.execute(
        select(TournamentTeam.id, TournamentTeam.team_code)
        .where(TournamentTeam.tournament_id == tournament_id)
        .order_by(TournamentTeam.id.asc())  # Using ID as seed proxy
    )
    teams = result.all()
    
    if len(teams) < 2:
        raise InsufficientTeamsError("Need at least 2 teams for knockout")
    
    # Sort by seed (using ID as deterministic seed)
    sorted_teams = sorted(teams, key=lambda t: t[0])  # team_id as seed
    team_ids = [t[0] for t in sorted_teams]
    
    n = len(team_ids)
    created_pairings: List[RoundPairing] = []
    
    # Standard bracket pattern: 1 vs N, 2 vs N-1, etc.
    table_number = 1
    
    for i in range(n // 2):
        team1_id = team_ids[i]           # Top half
        team2_id = team_ids[n - 1 - i]   # Bottom half (mirror)
        
        # Lower seed (lower ID) petitions
        if team1_id < team2_id:
            petitioner_id = team1_id
            respondent_id = team2_id
        else:
            petitioner_id = team2_id
            respondent_id = team1_id
        
        # Create pairing
        pairing = RoundPairing(
            round_id=round_id,
            petitioner_team_id=petitioner_id,
            respondent_team_id=respondent_id,
            table_number=table_number,
            pairing_hash="",
            created_at=datetime.utcnow()
        )
        
        pairing.pairing_hash = pairing.compute_pairing_hash()
        db.add(pairing)
        created_pairings.append(pairing)
        
        # Record pairing history
        team_a_id, team_b_id = normalize_team_ids(team1_id, team2_id)
        history = PairingHistory(
            tournament_id=tournament_id,
            team_a_id=team_a_id,
            team_b_id=team_b_id,
            round_id=round_id
        )
        db.add(history)
        
        table_number += 1
    
    await db.flush()
    
    return created_pairings


# =============================================================================
# Publish (Freeze) Logic
# =============================================================================

async def publish_round(
    round_id: int,
    user_id: int,
    db: AsyncSession
) -> RoundFreeze:
    """
    Publish (freeze) a round with SERIALIZABLE isolation.
    
    Steps:
    1. SET TRANSACTION ISOLATION LEVEL SERIALIZABLE
    2. LOCK tournament_round FOR UPDATE
    3. Check existing freeze → idempotent return
    4. Fetch all pairings sorted by table_number ASC
    5. Build snapshot with sort_keys=True JSON
    6. Compute checksum from sorted pairing_hashes
    7. Insert round_freeze
    8. Update round.status → published
    9. Commit atomically
    
    Args:
        round_id: Round to publish
        user_id: User publishing the round
        db: Database session
        
    Returns:
        RoundFreeze record
    """
    # Set SERIALIZABLE isolation
    await db.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
    
    # Lock round for update
    result = await db.execute(
        select(TournamentRound)
        .where(TournamentRound.id == round_id)
        .with_for_update()
    )
    round_obj = result.scalar_one_or_none()
    
    if not round_obj:
        raise RoundNotFoundError(f"Round {round_id} not found")
    
    # Check if freeze already exists (idempotency)
    result = await db.execute(
        select(RoundFreeze).where(RoundFreeze.round_id == round_id)
    )
    existing_freeze = result.scalar_one_or_none()
    
    if existing_freeze:
        return existing_freeze
    
    if round_obj.status == RoundStatus.FINALIZED:
        raise RoundFinalizedError("Round already finalized")
    
    # Fetch all pairings sorted by table_number (deterministic)
    result = await db.execute(
        select(RoundPairing)
        .where(RoundPairing.round_id == round_id)
        .order_by(RoundPairing.table_number.asc())
    )
    pairings = result.scalars().all()
    
    if not pairings:
        raise RoundPairingError("No pairings to publish")
    
    # Build snapshot (deterministic with sorted keys)
    snapshot = []
    pairing_hashes = []
    
    for pairing in pairings:
        entry = {
            "petitioner_team_id": pairing.petitioner_team_id,
            "respondent_team_id": pairing.respondent_team_id,
            "table_number": pairing.table_number,
            "pairing_hash": pairing.pairing_hash
        }
        snapshot.append(entry)
        pairing_hashes.append(pairing.pairing_hash)
    
    # JSON dump with sort_keys for determinism
    snapshot_json = json.loads(json.dumps(snapshot, sort_keys=True))
    
    # Compute checksum from sorted hashes
    freeze = RoundFreeze(
        round_id=round_id,
        pairing_snapshot_json=snapshot_json,
        round_checksum="",  # Will compute
        frozen_by=user_id,
        frozen_at=datetime.utcnow(),
        created_at=datetime.utcnow()
    )
    
    freeze.round_checksum = freeze.compute_round_checksum(pairing_hashes)
    
    # Update round
    round_obj.status = RoundStatus.PUBLISHED
    round_obj.published_at = datetime.utcnow()
    round_obj.pairing_checksum = freeze.round_checksum
    
    db.add(freeze)
    
    try:
        await db.flush()
    except IntegrityError:
        # Another process published concurrently - fetch existing
        result = await db.execute(
            select(RoundFreeze).where(RoundFreeze.round_id == round_id)
        )
        return result.scalar_one()
    
    return freeze


# =============================================================================
# Verify Integrity
# =============================================================================

async def verify_round_integrity(
    round_id: int,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Verify round integrity by comparing snapshot to current DB state.
    
    Checks:
    - Each pairing in snapshot exists and hash matches
    - No pairings deleted
    - No new pairings added after freeze
    
    Args:
        round_id: Round to verify
        db: Database session
        
    Returns:
        Verification result dictionary
    """
    # Get round
    result = await db.execute(
        select(TournamentRound).where(TournamentRound.id == round_id)
    )
    round_obj = result.scalar_one_or_none()
    
    if not round_obj:
        return {
            "round_id": round_id,
            "found": False,
            "valid": False,
            "error": "Round not found"
        }
    
    # Get freeze record
    result = await db.execute(
        select(RoundFreeze).where(RoundFreeze.round_id == round_id)
    )
    freeze = result.scalar_one_or_none()
    
    if not freeze:
        return {
            "round_id": round_id,
            "found": True,
            "frozen": False,
            "valid": False,
            "error": "Round not yet frozen"
        }
    
    # Get all current pairings
    result = await db.execute(
        select(
            RoundPairing.id,
            RoundPairing.petitioner_team_id,
            RoundPairing.respondent_team_id,
            RoundPairing.table_number,
            RoundPairing.pairing_hash
        )
        .where(RoundPairing.round_id == round_id)
    )
    current_pairings = {
        row[0]: {
            "petitioner_team_id": row[1],
            "respondent_team_id": row[2],
            "table_number": row[3],
            "pairing_hash": row[4]
        }
        for row in result.all()
    }
    
    # Build lookup by table number for comparison
    current_by_table = {
        p["table_number"]: p for p in current_pairings.values()
    }
    
    # Check each snapshot entry
    tampered_pairings = []
    
    for snapshot_entry in freeze.pairing_snapshot_json:
        table_num = snapshot_entry["table_number"]
        stored_hash = snapshot_entry["pairing_hash"]
        
        current = current_by_table.get(table_num)
        
        if current is None:
            tampered_pairings.append({
                "table_number": table_num,
                "issue": "Pairing missing (deleted)"
            })
        elif current["pairing_hash"] != stored_hash:
            tampered_pairings.append({
                "table_number": table_num,
                "issue": "Hash mismatch (modified)",
                "stored_hash": stored_hash,
                "current_hash": current["pairing_hash"]
            })
    
    # Check for new pairings added after freeze
    snapshot_tables = {e["table_number"] for e in freeze.pairing_snapshot_json}
    new_pairings = [
        table_num for table_num in current_by_table.keys()
        if table_num not in snapshot_tables
    ]
    
    is_valid = len(tampered_pairings) == 0 and len(new_pairings) == 0
    
    return {
        "round_id": round_id,
        "found": True,
        "frozen": True,
        "valid": is_valid,
        "stored_checksum": freeze.round_checksum,
        "total_pairings": len(freeze.pairing_snapshot_json),
        "frozen_at": freeze.frozen_at.isoformat() if freeze.frozen_at else None,
        "tampered_pairings": tampered_pairings if tampered_pairings else None,
        "new_pairings_added": new_pairings if new_pairings else None,
        "tamper_detected": len(tampered_pairings) > 0 or len(new_pairings) > 0
    }


# =============================================================================
# Query Functions
# =============================================================================

async def get_pairings_by_round(
    round_id: int,
    db: AsyncSession
) -> List[RoundPairing]:
    """Get all pairings for a round (sorted by table_number)."""
    result = await db.execute(
        select(RoundPairing)
        .where(RoundPairing.round_id == round_id)
        .order_by(RoundPairing.table_number.asc())
    )
    return list(result.scalars().all())


async def get_pairing_history(
    tournament_id: int,
    db: AsyncSession
) -> List[PairingHistory]:
    """Get all pairing history for a tournament."""
    result = await db.execute(
        select(PairingHistory)
        .where(PairingHistory.tournament_id == tournament_id)
        .order_by(PairingHistory.id.asc())
    )
    return list(result.scalars().all())
