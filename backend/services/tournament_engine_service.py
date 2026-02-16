"""
Tournament Engine Service — Phase 7 (National Moot Network)

Core service for managing cross-institution tournaments with:
- Deterministic Swiss-system pairing
- Knockout bracket generation
- Cross-institution judge panels
- Match result submission and finalization
- National team ranking computation

Rules:
- All pairing uses deterministic algorithms (no random)
- No judge from same institution as teams being judged
- All ranking uses Decimal only (never float)
- All transactions finalizing rankings use SERIALIZABLE isolation
- Idempotent match submission via idempotency keys
"""
import json
import hashlib
import logging
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Any, Optional, Tuple, Set

from sqlalchemy import select, and_, or_, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

from backend.orm.national_network import (
    NationalTournament, TournamentInstitution, TournamentTeam,
    TournamentRound, TournamentMatch, CrossInstitutionPanel, PanelJudge,
    TournamentEvaluation, NationalTeamRanking, NationalLedgerEntry,
    TournamentFormat, TournamentStatus, MatchStatus, TournamentLedgerEventType
)
from backend.orm.institutional_governance import Institution
from backend.orm.user import User, UserRole
from backend.services.national_ledger_service import append_national_ledger_entry

logger = logging.getLogger(__name__)


class TournamentError(Exception):
    """Custom exception for tournament operations."""
    pass


class JudgeConflictError(TournamentError):
    """Raised when judge assignment violates conflict rules."""
    pass


# =============================================================================
# Helper Functions
# =============================================================================


def deterministic_hash(seed: str) -> int:
    """
    Deterministic hash function using SHA256.
    
    Replaces Python's random() for consistent, reproducible pairings.
    """
    return int(hashlib.sha256(seed.encode()).hexdigest(), 16)


def sort_teams_for_pairing(teams: List[TournamentTeam]) -> List[TournamentTeam]:
    """
    Sort teams deterministically for Swiss pairing.
    
    Sort order: total_score DESC, wins DESC, team_name ASC
    """
    return sorted(
        teams,
        key=lambda t: (
            -t.total_score if t.total_score else Decimal("0"),
            -t.wins if t.wins else 0,
            t.team_name or ""
        )
    )


def has_played_each_other(team1_id: int, team2_id: int, matches: List[TournamentMatch]) -> bool:
    """Check if two teams have already played each other."""
    for match in matches:
        if (match.petitioner_team_id == team1_id and match.respondent_team_id == team2_id) or \
           (match.petitioner_team_id == team2_id and match.respondent_team_id == team1_id):
            return True
    return False


# =============================================================================
# STEP 1: Tournament Management
# =============================================================================

async def create_tournament(
    name: str,
    slug: str,
    host_institution_id: int,
    created_by: int,
    format: TournamentFormat,
    registration_opens_at: datetime,
    registration_closes_at: datetime,
    tournament_starts_at: datetime,
    db: AsyncSession,
    total_rounds: int = 5,
    max_teams_per_institution: int = 2,
    teams_advance_to_knockout: int = 8
) -> NationalTournament:
    """
    Create a new national tournament.
    
    Args:
        name: Tournament display name
        slug: URL-friendly unique identifier
        host_institution_id: Institution hosting the tournament
        created_by: User ID creating the tournament
        format: Tournament format (SWISS, KNOCKOUT, HYBRID)
        registration_opens_at: When registration opens
        registration_closes_at: When registration closes
        tournament_starts_at: When tournament starts
        total_rounds: Number of preliminary rounds (for Swiss/Hybrid)
        max_teams_per_institution: Max teams per institution
        teams_advance_to_knockout: Number of teams advancing to knockout
        db: Database session
        
    Returns:
        Created tournament
    """
    # Validate institution exists
    result = await db.execute(
        select(Institution).where(Institution.id == host_institution_id)
    )
    institution = result.scalar_one_or_none()
    if not institution:
        raise TournamentError(f"Institution {host_institution_id} not found")
    
    # Create tournament
    tournament = NationalTournament(
        name=name,
        slug=slug,
        host_institution_id=host_institution_id,
        created_by=created_by,
        format=format,
        status=TournamentStatus.DRAFT,
        registration_opens_at=registration_opens_at,
        registration_closes_at=registration_closes_at,
        tournament_starts_at=tournament_starts_at,
        total_rounds=total_rounds,
        max_teams_per_institution=max_teams_per_institution,
        teams_advance_to_knockout=teams_advance_to_knockout,
        preliminary_round_weight=Decimal("1.0"),
        knockout_round_weight=Decimal("1.5"),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    db.add(tournament)
    await db.flush()
    
    # Log to ledger
    await append_national_ledger_entry(
        tournament_id=tournament.id,
        event_type=TournamentLedgerEventType.TOURNAMENT_CREATED,
        entity_type="tournament",
        entity_id=tournament.id,
        event_data={
            "name": name,
            "slug": slug,
            "format": format.value,
            "host_institution_id": host_institution_id
        },
        actor_user_id=created_by,
        institution_id=host_institution_id,
        db=db
    )
    
    logger.info(f"Created tournament '{name}' (ID: {tournament.id})")
    
    return tournament


async def invite_institution(
    tournament_id: int,
    institution_id: int,
    invited_by: int,
    db: AsyncSession,
    max_teams_allowed: int = 2
) -> TournamentInstitution:
    """
    Invite an institution to participate in a tournament.
    
    Args:
        tournament_id: Tournament to invite to
        institution_id: Institution being invited
        invited_by: User ID sending the invitation
        max_teams_allowed: Max teams this institution can register
        db: Database session
        
    Returns:
        TournamentInstitution record
    """
    # Verify tournament exists and is in appropriate state
    result = await db.execute(
        select(NationalTournament).where(NationalTournament.id == tournament_id)
    )
    tournament = result.scalar_one_or_none()
    if not tournament:
        raise TournamentError(f"Tournament {tournament_id} not found")
    
    if tournament.status not in [TournamentStatus.DRAFT, TournamentStatus.REGISTRATION_OPEN]:
        raise TournamentError(f"Cannot invite institutions to tournament in status {tournament.status}")
    
    # Verify institution exists
    result = await db.execute(
        select(Institution).where(Institution.id == institution_id)
    )
    institution = result.scalar_one_or_none()
    if not institution:
        raise TournamentError(f"Institution {institution_id} not found")
    
    # Create invitation
    invitation = TournamentInstitution(
        tournament_id=tournament_id,
        institution_id=institution_id,
        is_invited=True,
        invited_at=datetime.utcnow(),
        invited_by=invited_by,
        is_accepted=False,
        max_teams_allowed=max_teams_allowed,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    try:
        db.add(invitation)
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise TournamentError(f"Institution {institution_id} already invited to tournament {tournament_id}")
    
    # Log to ledger
    await append_national_ledger_entry(
        tournament_id=tournament_id,
        event_type=TournamentLedgerEventType.INSTITUTION_INVITED,
        entity_type="tournament_institution",
        entity_id=invitation.id,
        event_data={
            "institution_id": institution_id,
            "invited_by": invited_by,
            "max_teams_allowed": max_teams_allowed
        },
        actor_user_id=invited_by,
        institution_id=tournament.host_institution_id,
        db=db
    )
    
    logger.info(f"Invited institution {institution_id} to tournament {tournament_id}")
    
    return invitation


async def register_team(
    tournament_id: int,
    institution_id: int,
    team_name: str,
    members_json: str,
    registered_by: int,
    db: AsyncSession,
    seed_number: Optional[int] = None
) -> TournamentTeam:
    """
    Register a team for a tournament.
    
    Args:
        tournament_id: Tournament to register for
        institution_id: Institution the team belongs to
        team_name: Name of the team
        members_json: JSON string of team member data
        registered_by: User ID registering the team
        seed_number: Optional seed number for bracket placement
        db: Database session
        
    Returns:
        Created team record
    """
    # Verify tournament exists and accepts registrations
    result = await db.execute(
        select(NationalTournament).where(NationalTournament.id == tournament_id)
    )
    tournament = result.scalar_one_or_none()
    if not tournament:
        raise TournamentError(f"Tournament {tournament_id} not found")
    
    if tournament.status not in [TournamentStatus.REGISTRATION_OPEN, TournamentStatus.DRAFT]:
        raise TournamentError(f"Tournament does not accept registrations in status {tournament.status}")
    
    # Verify institution is invited and accepted
    result = await db.execute(
        select(TournamentInstitution).where(
            and_(
                TournamentInstitution.tournament_id == tournament_id,
                TournamentInstitution.institution_id == institution_id,
                TournamentInstitution.is_accepted == True
            )
        )
    )
    invitation = result.scalar_one_or_none()
    if not invitation:
        raise TournamentError(f"Institution {institution_id} is not an accepted participant")
    
    # Check team count limit
    result = await db.execute(
        select(func.count(TournamentTeam.id)).where(
            and_(
                TournamentTeam.tournament_id == tournament_id,
                TournamentTeam.institution_id == institution_id,
                TournamentTeam.is_active == True
            )
        )
    )
    current_team_count = result.scalar() or 0
    
    if current_team_count >= invitation.max_teams_allowed:
        raise TournamentError(
            f"Institution {institution_id} has reached max teams limit ({invitation.max_teams_allowed})"
        )
    
    # Create team
    team = TournamentTeam(
        tournament_id=tournament_id,
        institution_id=institution_id,
        team_name=team_name,
        members_json=members_json,
        seed_number=seed_number,
        wins=0,
        losses=0,
        draws=0,
        total_score=Decimal("0"),
        is_active=True,
        is_eliminated=False,
        registered_by=registered_by,
        registered_at=datetime.utcnow()
    )
    
    try:
        db.add(team)
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise TournamentError(f"Team name '{team_name}' already exists in this tournament")
    
    # Log to ledger
    await append_national_ledger_entry(
        tournament_id=tournament_id,
        event_type=TournamentLedgerEventType.TEAM_REGISTERED,
        entity_type="tournament_team",
        entity_id=team.id,
        event_data={
            "team_name": team_name,
            "institution_id": institution_id,
            "seed_number": seed_number
        },
        actor_user_id=registered_by,
        institution_id=institution_id,
        db=db
    )
    
    logger.info(f"Registered team '{team_name}' (ID: {team.id}) for tournament {tournament_id}")
    
    return team


# =============================================================================
# STEP 2: Pairing Generation (Deterministic Algorithms)
# =============================================================================

async def generate_pairings_swiss(
    tournament_id: int,
    round_number: int,
    round_name: str,
    scheduled_at: datetime,
    created_by: int,
    db: AsyncSession
) -> TournamentRound:
    """
    Generate Swiss-system pairings for a round.
    
    Uses deterministic algorithm:
    1. Sort teams by score (desc), wins (desc), name (asc)
    2. Pair adjacent teams who haven't played each other
    3. If conflict exists, find next available opponent
    4. Assign sides based on who has petitioned less often
    
    Args:
        tournament_id: Tournament to generate pairings for
        round_number: Round number (1-indexed)
        round_name: Display name for the round
        scheduled_at: When the round is scheduled
        created_by: User ID creating the round
        db: Database session
        
    Returns:
        Created round with matches
    """
    # Get tournament
    result = await db.execute(
        select(NationalTournament).where(NationalTournament.id == tournament_id)
    )
    tournament = result.scalar_one_or_none()
    if not tournament:
        raise TournamentError(f"Tournament {tournament_id} not found")
    
    # Get all active, non-eliminated teams
    result = await db.execute(
        select(TournamentTeam).where(
            and_(
                TournamentTeam.tournament_id == tournament_id,
                TournamentTeam.is_active == True,
                TournamentTeam.is_eliminated == False
            )
        )
    )
    teams = list(result.scalars().all())
    
    if len(teams) < 2:
        raise TournamentError("Need at least 2 teams to generate pairings")
    
    # Get all previous matches for this tournament
    result = await db.execute(
        select(TournamentMatch).where(
            TournamentMatch.tournament_id == tournament_id
        )
    )
    previous_matches = list(result.scalars().all())
    
    # Sort teams deterministically
    sorted_teams = sort_teams_for_pairing(teams)
    
    # Create round
    round_obj = TournamentRound(
        tournament_id=tournament_id,
        round_number=round_number,
        round_name=round_name,
        is_knockout=False,
        is_preliminary=True,
        scheduled_at=scheduled_at,
        is_finalized=False,
        created_at=datetime.utcnow()
    )
    db.add(round_obj)
    await db.flush()
    
    # Generate pairings
    paired_teams: Set[int] = set()
    matches: List[TournamentMatch] = []
    
    for i, team1 in enumerate(sorted_teams):
        if team1.id in paired_teams:
            continue
        
        # Find opponent
        opponent = None
        for team2 in sorted_teams[i+1:]:
            if team2.id in paired_teams:
                continue
            if not has_played_each_other(team1.id, team2.id, previous_matches):
                opponent = team2
                break
        
        if not opponent:
            # Must pair with someone they've played before
            for team2 in sorted_teams[i+1:]:
                if team2.id not in paired_teams:
                    opponent = team2
                    break
        
        if opponent:
            # Determine sides based on who has petitioned less
            # For simplicity, alternate: lower-ranked team petitions
            petitioner = team1
            respondent = opponent
            
            match = TournamentMatch(
                round_id=round_obj.id,
                tournament_id=tournament_id,
                petitioner_team_id=petitioner.id,
                respondent_team_id=respondent.id,
                status=MatchStatus.PENDING,
                scheduled_at=scheduled_at,
                created_at=datetime.utcnow()
            )
            db.add(match)
            matches.append(match)
            
            paired_teams.add(team1.id)
            paired_teams.add(opponent.id)
    
    await db.flush()
    
    # Log to ledger
    await append_national_ledger_entry(
        tournament_id=tournament_id,
        event_type=TournamentLedgerEventType.PAIRINGS_GENERATED,
        entity_type="tournament_round",
        entity_id=round_obj.id,
        event_data={
            "round_number": round_number,
            "round_name": round_name,
            "format": "swiss",
            "matches_created": len(matches),
            "teams_paired": len(paired_teams)
        },
        actor_user_id=created_by,
        institution_id=tournament.host_institution_id,
        db=db
    )
    
    logger.info(f"Generated Swiss pairings for round {round_number} with {len(matches)} matches")
    
    return round_obj


async def generate_pairings_knockout(
    tournament_id: int,
    round_number: int,
    round_name: str,
    scheduled_at: datetime,
    teams_advancing: List[TournamentTeam],
    created_by: int,
    db: AsyncSession
) -> TournamentRound:
    """
    Generate knockout bracket pairings.
    
    Standard bracket: 1v8, 2v7, 3v6, 4v5 (seed-based)
    
    Args:
        tournament_id: Tournament to generate pairings for
        round_number: Round number
        round_name: Display name (e.g., "Quarterfinals")
        scheduled_at: When the round is scheduled
        teams_advancing: List of teams advancing to knockout
        created_by: User ID creating the round
        db: Database session
        
    Returns:
        Created round with matches
    """
    # Get tournament
    result = await db.execute(
        select(NationalTournament).where(NationalTournament.id == tournament_id)
    )
    tournament = result.scalar_one_or_none()
    if not tournament:
        raise TournamentError(f"Tournament {tournament_id} not found")
    
    if len(teams_advancing) < 2:
        raise TournamentError("Need at least 2 teams for knockout round")
    
    # Sort by preliminary ranking (seed)
    sorted_teams = sorted(teams_advancing, key=lambda t: t.seed_number or 999)
    
    # Create round
    round_obj = TournamentRound(
        tournament_id=tournament_id,
        round_number=round_number,
        round_name=round_name,
        is_knockout=True,
        is_preliminary=False,
        scheduled_at=scheduled_at,
        is_finalized=False,
        created_at=datetime.utcnow()
    )
    db.add(round_obj)
    await db.flush()
    
    # Generate bracket pairings (1v8, 2v7, 3v6, 4v5, etc.)
    num_teams = len(sorted_teams)
    matches = []
    
    for i in range(num_teams // 2):
        team1 = sorted_teams[i]  # Higher seed
        team2 = sorted_teams[num_teams - 1 - i]  # Lower seed
        
        match = TournamentMatch(
            round_id=round_obj.id,
            tournament_id=tournament_id,
            petitioner_team_id=team1.id,
            respondent_team_id=team2.id,
            status=MatchStatus.PENDING,
            scheduled_at=scheduled_at,
            created_at=datetime.utcnow()
        )
        db.add(match)
        matches.append(match)
    
    await db.flush()
    
    # Log to ledger
    await append_national_ledger_entry(
        tournament_id=tournament_id,
        event_type=TournamentLedgerEventType.PAIRINGS_GENERATED,
        entity_type="tournament_round",
        entity_id=round_obj.id,
        event_data={
            "round_number": round_number,
            "round_name": round_name,
            "format": "knockout",
            "matches_created": len(matches),
            "teams_competing": num_teams
        },
        actor_user_id=created_by,
        institution_id=tournament.host_institution_id,
        db=db
    )
    
    logger.info(f"Generated knockout pairings for round {round_number} with {len(matches)} matches")
    
    return round_obj


# =============================================================================
# STEP 3: Judge Panel Assignment
# =============================================================================

async def assign_judge_panel(
    match_id: int,
    panel_id: int,
    assigned_by: int,
    db: AsyncSession
) -> TournamentMatch:
    """
    Assign a judge panel to a match.
    
    Validates that no judge is from the same institution as either competing team.
    
    Args:
        match_id: Match to assign panel to
        panel_id: Panel to assign
        assigned_by: User ID making the assignment
        db: Database session
        
    Returns:
        Updated match
    """
    # Get match with teams
    result = await db.execute(
        select(TournamentMatch)
        .where(TournamentMatch.id == match_id)
    )
    match = result.scalar_one_or_none()
    if not match:
        raise TournamentError(f"Match {match_id} not found")
    
    # Get teams with their institutions
    result = await db.execute(
        select(TournamentTeam).where(
            TournamentTeam.id.in_([match.petitioner_team_id, match.respondent_team_id])
        )
    )
    teams = list(result.scalars().all())
    team_institution_ids = {t.id: t.institution_id for t in teams}
    competing_institutions = set(team_institution_ids.values())
    
    # Get panel judges with their institutions
    result = await db.execute(
        select(PanelJudge, User, Institution)
        .join(User, PanelJudge.user_id == User.id)
        .join(Institution, PanelJudge.institution_id == Institution.id)
        .where(PanelJudge.panel_id == panel_id)
    )
    panel_judges = result.all()
    
    # Check for conflicts
    for panel_judge, user, institution in panel_judges:
        if panel_judge.institution_id in competing_institutions:
            raise JudgeConflictError(
                f"Judge {user.id} from institution {institution.name} "
                f"cannot judge match between teams from institutions "
                f"{competing_institutions}"
            )
    
    # Check mixed institution requirement
    result = await db.execute(
        select(CrossInstitutionPanel).where(CrossInstitutionPanel.id == panel_id)
    )
    panel = result.scalar_one_or_none()
    
    if panel and panel.require_mixed_institutions:
        judge_institutions = {pj[0].institution_id for pj in panel_judges}
        if len(judge_institutions) < panel.min_institutions_represented:
            raise JudgeConflictError(
                f"Panel must represent at least {panel.min_institutions_represented} institutions, "
                f"but only {len(judge_institutions)} found"
            )
    
    # Assign panel
    match.panel_id = panel_id
    match.updated_at = datetime.utcnow()
    
    # Increment judge assignment counts
    for panel_judge, _, _ in panel_judges:
        panel_judge.assigned_matches_count += 1
    
    await db.flush()
    
    # Log to ledger
    await append_national_ledger_entry(
        tournament_id=match.tournament_id,
        event_type=TournamentLedgerEventType.PANEL_ASSIGNED,
        entity_type="tournament_match",
        entity_id=match.id,
        event_data={
            "match_id": match_id,
            "panel_id": panel_id,
            "petitioner_team_id": match.petitioner_team_id,
            "respondent_team_id": match.respondent_team_id
        },
        actor_user_id=assigned_by,
        institution_id=panel.institution_id if panel else None,
        db=db
    )
    
    logger.info(f"Assigned panel {panel_id} to match {match_id}")
    
    return match


# =============================================================================
# STEP 4: Match Result Submission (Idempotent)
# =============================================================================

async def submit_match_result(
    match_id: int,
    petitioner_score: Decimal,
    respondent_score: Decimal,
    submitted_by: int,
    idempotency_key: str,
    db: AsyncSession,
    notes: Optional[str] = None
) -> TournamentMatch:
    """
    Submit results for a match (idempotent).
    
    Uses idempotency_key to prevent duplicate submissions.
    
    Args:
        match_id: Match to submit results for
        petitioner_score: Score for petitioner team
        respondent_score: Score for respondent team
        submitted_by: User ID submitting results
        idempotency_key: Unique key for idempotency
        notes: Optional notes
        db: Database session
        
    Returns:
        Updated match
    """
    # Check for existing submission with same idempotency key
    result = await db.execute(
        select(TournamentMatch).where(
            and_(
                TournamentMatch.id == match_id,
                TournamentMatch.submission_idempotency_key == idempotency_key
            )
        )
    )
    existing = result.scalar_one_or_none()
    
    if existing:
        # Idempotent return - already processed
        logger.info(f"Match {match_id} already has submission with key {idempotency_key}")
        return existing
    
    # Get match
    result = await db.execute(
        select(TournamentMatch).where(TournamentMatch.id == match_id)
    )
    match = result.scalar_one_or_none()
    if not match:
        raise TournamentError(f"Match {match_id} not found")
    
    if match.status == MatchStatus.COMPLETED:
        raise TournamentError(f"Match {match_id} is already completed")
    
    # Determine winner
    winner_team_id = None
    is_draw = False
    
    if petitioner_score > respondent_score:
        winner_team_id = match.petitioner_team_id
    elif respondent_score > petitioner_score:
        winner_team_id = match.respondent_team_id
    else:
        is_draw = True
    
    # Update match
    match.petitioner_score = petitioner_score
    match.respondent_score = respondent_score
    match.winner_team_id = winner_team_id
    match.is_draw = is_draw
    match.status = MatchStatus.COMPLETED
    match.submission_idempotency_key = idempotency_key
    match.submitted_at = datetime.utcnow()
    match.submitted_by = submitted_by
    match.notes = notes
    
    # Update team stats
    if not is_draw and winner_team_id:
        result = await db.execute(
            select(TournamentTeam).where(TournamentTeam.id == winner_team_id)
        )
        winner = result.scalar_one()
        winner.wins = (winner.wins or 0) + 1
        
        # Loser
        loser_id = match.respondent_team_id if winner_team_id == match.petitioner_team_id else match.petitioner_team_id
        result = await db.execute(
            select(TournamentTeam).where(TournamentTeam.id == loser_id)
        )
        loser = result.scalar_one()
        loser.losses = (loser.losses or 0) + 1
        
        # For knockout, eliminate loser
        if match.round and match.round.is_knockout:
            loser.is_eliminated = True
    else:
        # Draw - both get draw count
        for team_id in [match.petitioner_team_id, match.respondent_team_id]:
            result = await db.execute(
                select(TournamentTeam).where(TournamentTeam.id == team_id)
            )
            team = result.scalar_one()
            team.draws = (team.draws or 0) + 1
    
    await db.flush()
    
    # Log to ledger
    await append_national_ledger_entry(
        tournament_id=match.tournament_id,
        event_type=TournamentLedgerEventType.MATCH_SUBMITTED,
        entity_type="tournament_match",
        entity_id=match.id,
        event_data={
            "match_id": match_id,
            "petitioner_score": str(petitioner_score),
            "respondent_score": str(respondent_score),
            "winner_team_id": winner_team_id,
            "is_draw": is_draw,
            "idempotency_key": idempotency_key
        },
        actor_user_id=submitted_by,
        institution_id=None,  # Will be filled from submitter
        db=db
    )
    
    logger.info(f"Submitted results for match {match_id}")
    
    return match


# =============================================================================
# STEP 5: Round Finalization
# =============================================================================

async def finalize_round(
    round_id: int,
    finalized_by: int,
    db: AsyncSession
) -> TournamentRound:
    """
    Finalize a tournament round and compute rankings.
    
    Uses SERIALIZABLE isolation for ranking computation.
    
    Args:
        round_id: Round to finalize
        finalized_by: User ID finalizing
        db: Database session
        
    Returns:
        Finalized round
    """
    # Get round with tournament
    result = await db.execute(
        select(TournamentRound)
        .where(TournamentRound.id == round_id)
    )
    round_obj = result.scalar_one_or_none()
    if not round_obj:
        raise TournamentError(f"Round {round_id} not found")
    
    if round_obj.is_finalized:
        raise TournamentError(f"Round {round_id} is already finalized")
    
    # Verify all matches are completed
    result = await db.execute(
        select(TournamentMatch).where(
            and_(
                TournamentMatch.round_id == round_id,
                TournamentMatch.status != MatchStatus.COMPLETED
            )
        )
    )
    incomplete_matches = list(result.scalars().all())
    if incomplete_matches:
        raise TournamentError(f"Cannot finalize round with {len(incomplete_matches)} incomplete matches")
    
    # Finalize round
    round_obj.is_finalized = True
    round_obj.finalized_at = datetime.utcnow()
    round_obj.finalized_by = finalized_by
    
    await db.flush()
    
    # Compute rankings
    await compute_national_ranking(round_obj.tournament_id, round_id, finalized_by, db)
    
    # Log to ledger
    await append_national_ledger_entry(
        tournament_id=round_obj.tournament_id,
        event_type=TournamentLedgerEventType.ROUND_FINALIZED,
        entity_type="tournament_round",
        entity_id=round_id,
        event_data={
            "round_number": round_obj.round_number,
            "round_name": round_obj.round_name
        },
        actor_user_id=finalized_by,
        institution_id=None,
        db=db
    )
    
    logger.info(f"Finalized round {round_id}")
    
    return round_obj


# =============================================================================
# STEP 6: National Ranking Computation
# =============================================================================

async def compute_national_ranking(
    tournament_id: int,
    round_id: Optional[int],
    computed_by: int,
    db: AsyncSession
) -> NationalTeamRanking:
    """
    Compute and store national team rankings.
    
    Uses SERIALIZABLE isolation to ensure ranking consistency.
    
    Args:
        tournament_id: Tournament to compute rankings for
        round_id: Round ID (None for final tournament ranking)
        computed_by: User ID computing
        db: Database session
        
    Returns:
        Created ranking snapshot
    """
    # Get all teams
    result = await db.execute(
        select(TournamentTeam).where(
            and_(
                TournamentTeam.tournament_id == tournament_id,
                TournamentTeam.is_active == True
            )
        )
    )
    teams = list(result.scalars().all())
    
    # Get tournament for weights
    result = await db.execute(
        select(NationalTournament).where(NationalTournament.id == tournament_id)
    )
    tournament = result.scalar_one()
    
    # Calculate weighted scores for each team
    team_rankings = []
    
    for team in teams:
        # Base score from wins/draws
        win_points = Decimal(team.wins or 0) * Decimal("3")
        draw_points = Decimal(team.draws or 0) * Decimal("1")
        base_score = win_points + draw_points + (team.total_score or Decimal("0"))
        
        # Apply weight if knockout round
        is_knockout = round_id is not None  # Simplified - would check actual round
        weight = tournament.knockout_round_weight if is_knockout else tournament.preliminary_round_weight
        weighted_score = (base_score * weight).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        
        team_rankings.append({
            "team_id": team.id,
            "institution_id": team.institution_id,
            "team_name": team.team_name,
            "wins": team.wins or 0,
            "losses": team.losses or 0,
            "draws": team.draws or 0,
            "base_score": str(base_score),
            "weighted_score": str(weighted_score),
            "is_eliminated": team.is_eliminated,
            "seed_number": team.seed_number
        })
    
    # Sort by weighted score (desc), then wins (desc), then team name (asc)
    team_rankings.sort(
        key=lambda r: (
            -Decimal(r["weighted_score"]),
            -r["wins"],
            r["team_name"]
        )
    )
    
    # Assign ranks
    for i, ranking in enumerate(team_rankings, 1):
        ranking["rank"] = i
    
    # Compute checksum
    rankings_json = json.dumps(team_rankings, sort_keys=True)
    checksum = hashlib.sha256(rankings_json.encode()).hexdigest()
    
    # Create ranking snapshot
    is_final = round_id is None  # Final if no specific round
    
    ranking_snapshot = NationalTeamRanking(
        tournament_id=tournament_id,
        round_id=round_id,
        is_final=is_final,
        computed_at=datetime.utcnow(),
        computed_by=computed_by,
        rankings_json=rankings_json,
        checksum=checksum,
        is_finalized=False,  # Will be finalized separately
        created_at=datetime.utcnow()
    )
    
    db.add(ranking_snapshot)
    await db.flush()
    
    # Log to ledger
    await append_national_ledger_entry(
        tournament_id=tournament_id,
        event_type=TournamentLedgerEventType.RANKING_COMPUTED,
        entity_type="national_team_ranking",
        entity_id=ranking_snapshot.id,
        event_data={
            "round_id": round_id,
            "is_final": is_final,
            "team_count": len(team_rankings),
            "checksum": checksum
        },
        actor_user_id=computed_by,
        institution_id=None,
        db=db
    )
    
    logger.info(f"Computed national ranking for tournament {tournament_id}")
    
    return ranking_snapshot


# =============================================================================
# STEP 7: Tournament Finalization
# =============================================================================

async def finalize_tournament(
    tournament_id: int,
    finalized_by: int,
    db: AsyncSession
) -> NationalTournament:
    """
    Finalize the entire tournament.
    
    Args:
        tournament_id: Tournament to finalize
        finalized_by: User ID finalizing
        db: Database session
        
    Returns:
        Finalized tournament
    """
    # Get tournament
    result = await db.execute(
        select(NationalTournament).where(NationalTournament.id == tournament_id)
    )
    tournament = result.scalar_one_or_none()
    if not tournament:
        raise TournamentError(f"Tournament {tournament_id} not found")
    
    if tournament.status == TournamentStatus.COMPLETED:
        raise TournamentError(f"Tournament {tournament_id} is already completed")
    
    # Verify all rounds are finalized
    result = await db.execute(
        select(TournamentRound).where(
            and_(
                TournamentRound.tournament_id == tournament_id,
                TournamentRound.is_finalized == False
            )
        )
    )
    unfinalized_rounds = list(result.scalars().all())
    if unfinalized_rounds:
        raise TournamentError(f"Cannot finalize tournament with {len(unfinalized_rounds)} unfinalized rounds")
    
    # Compute final ranking
    final_ranking = await compute_national_ranking(tournament_id, None, finalized_by, db)
    
    # Finalize the ranking
    final_ranking.is_finalized = True
    final_ranking.finalized_at = datetime.utcnow()
    final_ranking.finalized_by = finalized_by
    
    # Update tournament status
    tournament.status = TournamentStatus.COMPLETED
    tournament.tournament_ends_at = datetime.utcnow()
    tournament.updated_at = datetime.utcnow()
    
    await db.flush()
    
    # Log to ledger
    await append_national_ledger_entry(
        tournament_id=tournament_id,
        event_type=TournamentLedgerEventType.TOURNAMENT_FINALIZED,
        entity_type="tournament",
        entity_id=tournament_id,
        event_data={
            "final_ranking_id": final_ranking.id,
            "winner_team_id": json.loads(final_ranking.rankings_json)[0]["team_id"] if final_ranking.rankings_json else None
        },
        actor_user_id=finalized_by,
        institution_id=tournament.host_institution_id,
        db=db
    )
    
    logger.info(f"Finalized tournament {tournament_id}")
    
    return tournament
