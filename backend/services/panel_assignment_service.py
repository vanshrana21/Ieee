"""
Phase 4 — Hardened Judge Panel Assignment Service Layer

Conflict Detection + Immutability with:
- Deterministic panel assignment algorithm
- Institution conflict detection
- Repeat judging prevention
- SERIALIZABLE publish with freeze
- No float(), no random(), no datetime.now()
"""
import hashlib
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import select, and_, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from backend.orm.panel_assignment import (
    JudgePanel, PanelMember, PanelMemberRole, JudgeAssignmentHistory, PanelFreeze
)
from backend.orm.round_pairing import TournamentRound, RoundPairing, RoundStatus
from backend.orm.national_network import TournamentTeam, NationalTournament
from backend.orm.user import User, UserRole


# =============================================================================
# Custom Exceptions
# =============================================================================

class PanelAssignmentError(Exception):
    """Base exception for panel assignment errors."""
    pass


class PanelNotFoundError(PanelAssignmentError):
    """Raised when panel is not found."""
    pass


class PanelFrozenError(PanelAssignmentError):
    """Raised when trying to modify frozen panel."""
    pass


class JudgeConflictError(PanelAssignmentError):
    """Raised when judge has conflict with team."""
    pass


class InsufficientJudgesError(PanelAssignmentError):
    """Raised when not enough judges available."""
    pass


class TournamentScopeError(PanelAssignmentError):
    """Raised when tournament access is denied."""
    pass


# =============================================================================
# Conflict Detection
# =============================================================================

async def check_institution_conflict(
    judge_id: int,
    team_id: int,
    db: AsyncSession
) -> bool:
    """
    Check if judge and team are from the same institution.
    
    Returns True if conflict exists (same institution).
    """
    result = await db.execute(
        select(User.institution_id, TournamentTeam.institution_id)
        .select_from(User)
        .join(TournamentTeam, TournamentTeam.id == team_id)
        .where(User.id == judge_id)
    )
    row = result.one_or_none()
    
    if not row:
        return True  # Missing data = conflict
    
    judge_institution, team_institution = row
    return judge_institution == team_institution


async def check_repeat_judging(
    tournament_id: int,
    judge_id: int,
    team_id: int,
    db: AsyncSession
) -> bool:
    """
    Check if judge has already judged this team in this tournament.
    
    Returns True if repeat judging exists.
    """
    result = await db.execute(
        select(JudgeAssignmentHistory.id)
        .where(
            and_(
                JudgeAssignmentHistory.tournament_id == tournament_id,
                JudgeAssignmentHistory.judge_id == judge_id,
                JudgeAssignmentHistory.team_id == team_id
            )
        )
    )
    return result.scalar_one_or_none() is not None


async def check_coaching_conflict(
    judge_id: int,
    team_id: int,
    db: AsyncSession
) -> bool:
    """
    Check if judge previously coached this team.
    
    Returns True if conflict exists.
    
    NOTE: This is a placeholder for future extension when
    coaching history is implemented.
    """
    # TODO: Implement when coaching history table is available
    return False


async def has_judge_conflict(
    tournament_id: int,
    judge_id: int,
    petitioner_team_id: int,
    respondent_team_id: int,
    db: AsyncSession,
    strict_mode: bool = False
) -> Tuple[bool, Optional[str]]:
    """
    Comprehensive conflict check for a judge against a pairing.
    
    Args:
        tournament_id: Tournament ID
        judge_id: Judge to check
        petitioner_team_id: Petitioner team ID
        respondent_team_id: Respondent team ID
        db: Database session
        strict_mode: If True, also check repeat judging
        
    Returns:
        Tuple of (has_conflict, reason)
    """
    # Check institution conflict with petitioner
    if await check_institution_conflict(judge_id, petitioner_team_id, db):
        return (True, "Judge and petitioner team from same institution")
    
    # Check institution conflict with respondent
    if await check_institution_conflict(judge_id, respondent_team_id, db):
        return (True, "Judge and respondent team from same institution")
    
    # Check coaching conflict with petitioner
    if await check_coaching_conflict(judge_id, petitioner_team_id, db):
        return (True, "Judge previously coached petitioner team")
    
    # Check coaching conflict with respondent
    if await check_coaching_conflict(judge_id, respondent_team_id, db):
        return (True, "Judge previously coached respondent team")
    
    # Check repeat judging (if strict mode)
    if strict_mode:
        if await check_repeat_judging(tournament_id, judge_id, petitioner_team_id, db):
            return (True, "Judge already evaluated petitioner team in this tournament")
        if await check_repeat_judging(tournament_id, judge_id, respondent_team_id, db):
            return (True, "Judge already evaluated respondent team in this tournament")
    
    return (False, None)


# =============================================================================
# Judge Availability
# =============================================================================

async def get_available_judges(
    tournament_id: int,
    round_id: int,
    db: AsyncSession
) -> List[Dict[str, Any]]:
    """
    Get list of available judges sorted deterministically:
    1. total_assignments ASC (judges with fewer assignments first)
    2. institution_id ASC
    3. user_id ASC (final tiebreaker)
    """
    # Get all judges in the system with role JUDGE
    result = await db.execute(
        select(
            User.id,
            User.institution_id,
            func.coalesce(func.count(PanelMember.id), 0).label("total_assignments")
        )
        .outerjoin(
            PanelMember,
            and_(
                PanelMember.judge_id == User.id,
                PanelMember.panel_id.in_(
                    select(JudgePanel.id).where(JudgePanel.round_id == round_id)
                )
            )
        )
        .where(User.role == UserRole.JUDGE)
        .where(User.is_active == True)
        .group_by(User.id, User.institution_id)
        .order_by(
            func.coalesce(func.count(PanelMember.id), 0).asc(),
            User.institution_id.asc(),
            User.id.asc()
        )
    )
    
    rows = result.all()
    
    judges = []
    for row in rows:
        judges.append({
            "judge_id": row[0],
            "institution_id": row[1],
            "total_assignments": row[2] or 0,
        })
    
    return judges


async def get_judges_already_assigned_to_round(
    round_id: int,
    db: AsyncSession
) -> Set[int]:
    """Get set of judge IDs already assigned to any panel in this round."""
    result = await db.execute(
        select(PanelMember.judge_id)
        .join(JudgePanel, PanelMember.panel_id == JudgePanel.id)
        .where(JudgePanel.round_id == round_id)
    )
    
    return set(row[0] for row in result.all())


# =============================================================================
# Panel Generation
# =============================================================================

async def generate_panels_for_round(
    round_id: int,
    db: AsyncSession,
    panel_size: int = 3,
    strict_mode: bool = False
) -> List[JudgePanel]:
    """
    Generate judge panels for all pairings in a round.
    
    Algorithm:
    1. Fetch pairings sorted by table_number (deterministic)
    2. Fetch available judges sorted by assignments, institution, id
    3. For each pairing:
       - Select first N judges who:
         * Not already assigned in this round
         * No institution conflict
         * No coaching conflict
         * No repeat judging (if strict_mode)
       - Assign first judge as presiding, others as members
       - Record in assignment history
    
    Args:
        round_id: Round to generate panels for
        db: Database session
        panel_size: Number of judges per panel (default 3)
        strict_mode: If True, block repeat judging
        
    Returns:
        List of created JudgePanel objects
    """
    # Get round
    result = await db.execute(
        select(TournamentRound).where(TournamentRound.id == round_id)
    )
    round_obj = result.scalar_one_or_none()
    
    if not round_obj:
        raise PanelNotFoundError(f"Round {round_id} not found")
    
    if round_obj.status == RoundStatus.FINALIZED:
        raise PanelFrozenError("Cannot generate panels for finalized round")
    
    tournament_id = round_obj.tournament_id
    
    # Get pairings sorted by table_number (deterministic)
    result = await db.execute(
        select(RoundPairing)
        .where(RoundPairing.round_id == round_id)
        .order_by(RoundPairing.table_number.asc())
    )
    pairings = result.scalars().all()
    
    if not pairings:
        raise PanelAssignmentError("No pairings found for this round")
    
    # Get available judges (deterministically sorted)
    available_judges = await get_available_judges(tournament_id, round_id, db)
    
    # Track judges already assigned in this round
    assigned_judges = await get_judges_already_assigned_to_round(round_id, db)
    
    created_panels: List[JudgePanel] = []
    
    for pairing in pairings:
        # Create panel
        panel = JudgePanel(
            round_id=round_id,
            table_number=pairing.table_number,
            panel_hash="",  # Will compute after members added
            created_at=datetime.utcnow()
        )
        db.add(panel)
        await db.flush()  # Get panel.id
        
        # Select judges for this panel
        selected_judges: List[int] = []
        
        for judge in available_judges:
            judge_id = judge["judge_id"]
            
            # Skip if already assigned in this round
            if judge_id in assigned_judges:
                continue
            
            # Check for conflicts
            has_conflict, reason = await has_judge_conflict(
                tournament_id=tournament_id,
                judge_id=judge_id,
                petitioner_team_id=pairing.petitioner_team_id,
                respondent_team_id=pairing.respondent_team_id,
                db=db,
                strict_mode=strict_mode
            )
            
            if has_conflict:
                continue
            
            # Valid judge found
            selected_judges.append(judge_id)
            assigned_judges.add(judge_id)
            
            if len(selected_judges) >= panel_size:
                break
        
        if len(selected_judges) < panel_size:
            raise InsufficientJudgesError(
                f"Could not find {panel_size} conflict-free judges for table {pairing.table_number}"
            )
        
        # Assign roles: first judge presiding, others members
        for i, judge_id in enumerate(selected_judges):
            role = PanelMemberRole.PRESIDING if i == 0 else PanelMemberRole.MEMBER
            
            member = PanelMember(
                panel_id=panel.id,
                judge_id=judge_id,
                role=role,
                created_at=datetime.utcnow()
            )
            db.add(member)
            
            # Record in assignment history for both teams
            for team_id in [pairing.petitioner_team_id, pairing.respondent_team_id]:
                history = JudgeAssignmentHistory(
                    tournament_id=tournament_id,
                    judge_id=judge_id,
                    team_id=team_id,
                    round_id=round_id
                )
                db.add(history)
        
        # Compute panel hash
        panel.update_hash()
        created_panels.append(panel)
    
    await db.flush()
    return created_panels


# =============================================================================
# Publish (Freeze) Logic
# =============================================================================

async def publish_panels(
    round_id: int,
    user_id: int,
    db: AsyncSession
) -> PanelFreeze:
    """
    Publish (freeze) panels for a round with SERIALIZABLE isolation.
    
    Steps:
    1. SET TRANSACTION ISOLATION LEVEL SERIALIZABLE
    2. LOCK tournament_round FOR UPDATE
    3. Check existing freeze → idempotent return
    4. Fetch all panels sorted by table_number ASC
    5. Build snapshot with judge IDs sorted
    6. JSON dump with sort_keys=True
    7. Compute checksum from sorted panel_hashes
    8. Insert panel_freeze
    9. Update round.status → published
    10. Commit atomically
    
    Args:
        round_id: Round to publish
        user_id: User publishing
        db: Database session
        
    Returns:
        PanelFreeze record
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
        raise PanelNotFoundError(f"Round {round_id} not found")
    
    # Check if freeze already exists (idempotency)
    result = await db.execute(
        select(PanelFreeze).where(PanelFreeze.round_id == round_id)
    )
    existing_freeze = result.scalar_one_or_none()
    
    if existing_freeze:
        return existing_freeze
    
    if round_obj.status == RoundStatus.FINALIZED:
        raise PanelFrozenError("Round already finalized")
    
    # Fetch all panels sorted by table_number
    result = await db.execute(
        select(JudgePanel)
        .where(JudgePanel.round_id == round_id)
        .order_by(JudgePanel.table_number.asc())
    )
    panels = result.scalars().all()
    
    if not panels:
        raise PanelAssignmentError("No panels to publish")
    
    # Build snapshot (deterministic)
    snapshot = []
    panel_hashes = []
    
    for panel in panels:
        # Get sorted judge IDs
        result = await db.execute(
            select(PanelMember.judge_id, PanelMember.role)
            .where(PanelMember.panel_id == panel.id)
            .order_by(PanelMember.judge_id.asc())
        )
        members = result.all()
        
        judge_ids = sorted([m[0] for m in members])
        
        entry = {
            "table_number": panel.table_number,
            "judges": judge_ids,
            "panel_hash": panel.panel_hash
        }
        snapshot.append(entry)
        panel_hashes.append(panel.panel_hash)
    
    # JSON dump with sort_keys for determinism
    snapshot_json = json.loads(json.dumps(snapshot, sort_keys=True))
    
    # Compute checksum
    freeze = PanelFreeze(
        round_id=round_id,
        panel_snapshot_json=snapshot_json,
        panel_checksum="",  # Will compute
        frozen_by=user_id,
        frozen_at=datetime.utcnow(),
        created_at=datetime.utcnow()
    )
    
    freeze.panel_checksum = freeze.compute_panel_checksum(panel_hashes)
    
    # Update round
    round_obj.status = RoundStatus.PUBLISHED
    round_obj.published_at = datetime.utcnow()
    
    db.add(freeze)
    
    try:
        await db.flush()
    except IntegrityError:
        # Another process published concurrently - fetch existing
        result = await db.execute(
            select(PanelFreeze).where(PanelFreeze.round_id == round_id)
        )
        return result.scalar_one()
    
    return freeze


# =============================================================================
# Verify Integrity
# =============================================================================

async def verify_panel_integrity(
    round_id: int,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Verify panel integrity by comparing snapshot to current DB state.
    
    Checks:
    - Each panel in snapshot exists and hash matches
    - Judges match exactly
    - No panels deleted
    - No new panels added after freeze
    
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
        select(PanelFreeze).where(PanelFreeze.round_id == round_id)
    )
    freeze = result.scalar_one_or_none()
    
    if not freeze:
        return {
            "round_id": round_id,
            "found": True,
            "frozen": False,
            "valid": False,
            "error": "Panels not yet frozen"
        }
    
    # Get all current panels
    result = await db.execute(
        select(JudgePanel).where(JudgePanel.round_id == round_id)
    )
    current_panels = {p.table_number: p for p in result.scalars().all()}
    
    # Get current members for each panel
    current_panel_data = {}
    for table_num, panel in current_panels.items():
        result = await db.execute(
            select(PanelMember.judge_id)
            .where(PanelMember.panel_id == panel.id)
            .order_by(PanelMember.judge_id.asc())
        )
        judge_ids = [row[0] for row in result.all()]
        current_panel_data[table_num] = {
            "judge_ids": judge_ids,
            "panel_hash": panel.panel_hash
        }
    
    # Check each snapshot entry
    tampered_panels = []
    
    for snapshot_entry in freeze.panel_snapshot_json:
        table_num = snapshot_entry["table_number"]
        stored_judges = snapshot_entry["judges"]
        stored_hash = snapshot_entry["panel_hash"]
        
        current = current_panel_data.get(table_num)
        
        if current is None:
            tampered_panels.append({
                "table_number": table_num,
                "issue": "Panel missing (deleted)"
            })
        else:
            issues = []
            if current["panel_hash"] != stored_hash:
                issues.append("Hash mismatch")
            if current["judge_ids"] != stored_judges:
                issues.append(f"Judge mismatch: stored {stored_judges}, current {current['judge_ids']}")
            
            if issues:
                tampered_panels.append({
                    "table_number": table_num,
                    "issue": "; ".join(issues),
                    "stored_hash": stored_hash,
                    "current_hash": current["panel_hash"]
                })
    
    # Check for new panels added after freeze
    snapshot_tables = {e["table_number"] for e in freeze.panel_snapshot_json}
    new_panels = [
        table_num for table_num in current_panel_data.keys()
        if table_num not in snapshot_tables
    ]
    
    is_valid = len(tampered_panels) == 0 and len(new_panels) == 0
    
    return {
        "round_id": round_id,
        "found": True,
        "frozen": True,
        "valid": is_valid,
        "stored_checksum": freeze.panel_checksum,
        "total_panels": len(freeze.panel_snapshot_json),
        "frozen_at": freeze.frozen_at.isoformat() if freeze.frozen_at else None,
        "tampered_panels": tampered_panels if tampered_panels else None,
        "new_panels_added": new_panels if new_panels else None,
        "tamper_detected": len(tampered_panels) > 0 or len(new_panels) > 0
    }


# =============================================================================
# Query Functions
# =============================================================================

async def get_panels_by_round(
    round_id: int,
    db: AsyncSession
) -> List[JudgePanel]:
    """Get all panels for a round (sorted by table_number)."""
    result = await db.execute(
        select(JudgePanel)
        .where(JudgePanel.round_id == round_id)
        .order_by(JudgePanel.table_number.asc())
    )
    return list(result.scalars().all())


async def get_panel_by_id(
    panel_id: int,
    db: AsyncSession
) -> Optional[JudgePanel]:
    """Get panel by ID."""
    result = await db.execute(
        select(JudgePanel).where(JudgePanel.id == panel_id)
    )
    return result.scalar_one_or_none()


async def get_assignment_history(
    tournament_id: int,
    db: AsyncSession
) -> List[JudgeAssignmentHistory]:
    """Get all judge assignment history for a tournament."""
    result = await db.execute(
        select(JudgeAssignmentHistory)
        .where(JudgeAssignmentHistory.tournament_id == tournament_id)
        .order_by(JudgeAssignmentHistory.id.asc())
    )
    return list(result.scalars().all())
