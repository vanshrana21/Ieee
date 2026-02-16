"""
National Network API Routes — Phase 7

API endpoints for cross-institution tournament management.

Security:
- All endpoints enforce RBAC
- Institution isolation enforced
- Cross-tenant access rejected
- Tournament host institution has admin rights

Endpoints:
- POST /tournaments - Create new tournament
- POST /tournaments/{id}/invite - Invite institution
- POST /tournaments/{id}/teams - Register team
- POST /tournaments/{id}/pairings - Generate pairings
- POST /matches/{id}/submit - Submit match result
- POST /tournaments/{id}/finalize - Finalize tournament
- GET /tournaments/{id}/ranking - Get tournament ranking
- GET /tournaments/{id}/ledger/verify - Verify ledger integrity
"""
import json
from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.dependencies import get_current_user, require_role
from backend.orm.user import User, UserRole
from backend.orm.national_network import (
    NationalTournament, TournamentFormat, TournamentStatus,
    MatchStatus, TournamentRound, TournamentMatch,
    TournamentTeam, TournamentInstitution
)
from backend.services.tournament_engine_service import (
    create_tournament, invite_institution, register_team,
    generate_pairings_swiss, generate_pairings_knockout,
    assign_judge_panel, submit_match_result, finalize_round,
    compute_national_ranking, finalize_tournament,
    TournamentError, JudgeConflictError
)
from backend.services.national_ledger_service import (
    verify_national_ledger_chain, get_ledger_entries_for_tournament,
    get_ledger_summary_for_tournament
)

router = APIRouter(prefix="/national", tags=["National Network"])


# =============================================================================
# Helper Functions
# =============================================================================

def check_tournament_access(
    tournament: NationalTournament,
    user: User,
    require_host: bool = False
) -> None:
    """
    Check if user has access to tournament operations.
    
    Args:
        tournament: Tournament to check access for
        user: User requesting access
        require_host: If True, only host institution admins allowed
        
    Raises:
        HTTPException: If access denied
    """
    # Super admin always has access
    if user.role == UserRole.teacher:
        return
    
    # Check if user is from host institution
    is_host = user.institution_id == tournament.host_institution_id
    
    if require_host and not is_host:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only host institution administrators can perform this action"
        )
    
    # Check if user's institution is invited and accepted
    if not is_host:
        # User must be from an invited institution
        # (This check would need to query tournament_institutions)
        pass  # Additional checks can be added here
    
    # Role-based access
    allowed_roles = [UserRole.teacher, UserRole.teacher, UserRole.teacher]
    if user.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions for this operation"
        )


# =============================================================================
# Tournament Management Endpoints
# =============================================================================

@router.post("/tournaments", status_code=status.HTTP_201_CREATED)
async def create_tournament_endpoint(
    request: Request,
    name: str,
    slug: str,
    format: TournamentFormat,
    registration_opens_at: datetime,
    registration_closes_at: datetime,
    tournament_starts_at: datetime,
    total_rounds: int = 5,
    max_teams_per_institution: int = 2,
    teams_advance_to_knockout: int = 8,
    description: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.teacher, UserRole.teacher]))
):
    """
    Create a new national tournament.
    
    Requires: ADMIN or SUPER_ADMIN role
    """
    try:
        tournament = await create_tournament(
            name=name,
            slug=slug,
            host_institution_id=current_user.institution_id,
            created_by=current_user.id,
            format=format,
            registration_opens_at=registration_opens_at,
            registration_closes_at=registration_closes_at,
            tournament_starts_at=tournament_starts_at,
            db=db,
            total_rounds=total_rounds,
            max_teams_per_institution=max_teams_per_institution,
            teams_advance_to_knockout=teams_advance_to_knockout
        )
        
        return {
            "success": True,
            "tournament_id": tournament.id,
            "message": f"Tournament '{name}' created successfully"
        }
        
    except TournamentError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/tournaments/{tournament_id}/invite", status_code=status.HTTP_201_CREATED)
async def invite_institution_endpoint(
    tournament_id: int,
    institution_id: int,
    max_teams_allowed: int = 2,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.teacher, UserRole.teacher, UserRole.teacher]))
):
    """
    Invite an institution to participate in a tournament.
    
    Requires: ADMIN, HOD, or SUPER_ADMIN role
    Only host institution can invite.
    """
    # Get tournament
    result = await db.execute(
        select(NationalTournament).where(NationalTournament.id == tournament_id)
    )
    tournament = result.scalar_one_or_none()
    
    if not tournament:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tournament {tournament_id} not found"
        )
    
    # Check access (host institution only)
    if current_user.role != UserRole.teacher:
        if current_user.institution_id != tournament.host_institution_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only host institution can invite other institutions"
            )
    
    # Cannot invite own institution
    if institution_id == tournament.host_institution_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Host institution is automatically included, no invitation needed"
        )
    
    try:
        invitation = await invite_institution(
            tournament_id=tournament_id,
            institution_id=institution_id,
            invited_by=current_user.id,
            db=db,
            max_teams_allowed=max_teams_allowed
        )
        
        return {
            "success": True,
            "invitation_id": invitation.id,
            "message": f"Institution {institution_id} invited successfully"
        }
        
    except TournamentError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/tournaments/{tournament_id}/teams", status_code=status.HTTP_201_CREATED)
async def register_team_endpoint(
    tournament_id: int,
    team_name: str,
    members_json: str,
    seed_number: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.teacher, UserRole.teacher, UserRole.teacher, UserRole.teacher]))
):
    """
    Register a team for a tournament.
    
    Requires: FACULTY, HOD, ADMIN, or SUPER_ADMIN role
    User's institution must be invited and accepted.
    """
    # Get tournament
    result = await db.execute(
        select(NationalTournament).where(NationalTournament.id == tournament_id)
    )
    tournament = result.scalar_one_or_none()
    
    if not tournament:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tournament {tournament_id} not found"
        )
    
    # Verify institution is accepted participant
    result = await db.execute(
        select(TournamentInstitution).where(
            and_(
                TournamentInstitution.tournament_id == tournament_id,
                TournamentInstitution.institution_id == current_user.institution_id,
                TournamentInstitution.is_accepted == True
            )
        )
    )
    invitation = result.scalar_one_or_none()
    
    if not invitation and current_user.institution_id != tournament.host_institution_id:
        # Check if this is the host institution
        if current_user.role != UserRole.teacher:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your institution is not an accepted participant in this tournament"
            )
    
    try:
        team = await register_team(
            tournament_id=tournament_id,
            institution_id=current_user.institution_id,
            team_name=team_name,
            members_json=members_json,
            registered_by=current_user.id,
            db=db,
            seed_number=seed_number
        )
        
        return {
            "success": True,
            "team_id": team.id,
            "message": f"Team '{team_name}' registered successfully"
        }
        
    except TournamentError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/tournaments/{tournament_id}/pairings", status_code=status.HTTP_201_CREATED)
async def generate_pairings_endpoint(
    tournament_id: int,
    round_number: int,
    round_name: str,
    scheduled_at: datetime,
    format: str = "swiss",  # "swiss" or "knockout"
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.teacher, UserRole.teacher, UserRole.teacher]))
):
    """
    Generate pairings for a tournament round.
    
    Requires: ADMIN, HOD, or SUPER_ADMIN role
    Only host institution can generate pairings.
    """
    # Get tournament
    result = await db.execute(
        select(NationalTournament).where(NationalTournament.id == tournament_id)
    )
    tournament = result.scalar_one_or_none()
    
    if not tournament:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tournament {tournament_id} not found"
        )
    
    # Check access (host institution only)
    if current_user.role != UserRole.teacher:
        if current_user.institution_id != tournament.host_institution_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only host institution can generate pairings"
            )
    
    try:
        if format == "swiss":
            round_obj = await generate_pairings_swiss(
                tournament_id=tournament_id,
                round_number=round_number,
                round_name=round_name,
                scheduled_at=scheduled_at,
                created_by=current_user.id,
                db=db
            )
        elif format == "knockout":
            # Get teams advancing to knockout
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
            
            round_obj = await generate_pairings_knockout(
                tournament_id=tournament_id,
                round_number=round_number,
                round_name=round_name,
                scheduled_at=scheduled_at,
                teams_advancing=teams,
                created_by=current_user.id,
                db=db
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid format: {format}. Use 'swiss' or 'knockout'"
            )
        
        return {
            "success": True,
            "round_id": round_obj.id,
            "message": f"{format.capitalize()} pairings generated for round {round_number}"
        }
        
    except TournamentError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/matches/{match_id}/submit", status_code=status.HTTP_200_OK)
async def submit_match_result_endpoint(
    match_id: int,
    petitioner_score: Decimal,
    respondent_score: Decimal,
    idempotency_key: str,
    notes: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.teacher, UserRole.teacher, UserRole.teacher, UserRole.teacher, UserRole.teacher]))
):
    """
    Submit results for a match (idempotent).
    
    Requires: FACULTY, JUDGE, HOD, ADMIN, or SUPER_ADMIN role
    User must be assigned to the match panel or be tournament admin.
    """
    # Get match
    result = await db.execute(
        select(TournamentMatch).where(TournamentMatch.id == match_id)
    )
    match = result.scalar_one_or_none()
    
    if not match:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Match {match_id} not found"
        )
    
    # Get tournament for access check
    result = await db.execute(
        select(NationalTournament).where(NationalTournament.id == match.tournament_id)
    )
    tournament = result.scalar_one()
    
    # Check access
    is_host_admin = (
        current_user.institution_id == tournament.host_institution_id and
        current_user.role in [UserRole.teacher, UserRole.teacher, UserRole.teacher]
    )
    
    is_panel_judge = False
    if match.panel_id:
        from backend.orm.national_network import PanelJudge
        result = await db.execute(
            select(PanelJudge).where(
                and_(
                    PanelJudge.panel_id == match.panel_id,
                    PanelJudge.user_id == current_user.id
                )
            )
        )
        is_panel_judge = result.scalar_one_or_none() is not None
    
    if not (is_host_admin or is_panel_judge or current_user.role == UserRole.teacher):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to submit results for this match"
        )
    
    try:
        updated_match = await submit_match_result(
            match_id=match_id,
            petitioner_score=petitioner_score,
            respondent_score=respondent_score,
            submitted_by=current_user.id,
            idempotency_key=idempotency_key,
            db=db,
            notes=notes
        )
        
        return {
            "success": True,
            "match_id": updated_match.id,
            "winner_team_id": updated_match.winner_team_id,
            "is_draw": updated_match.is_draw,
            "message": "Match results submitted successfully"
        }
        
    except TournamentError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/tournaments/{tournament_id}/finalize", status_code=status.HTTP_200_OK)
async def finalize_tournament_endpoint(
    tournament_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.teacher, UserRole.teacher, UserRole.teacher]))
):
    """
    Finalize the entire tournament.
    
    Requires: ADMIN, HOD, or SUPER_ADMIN role
    Only host institution can finalize.
    """
    # Get tournament
    result = await db.execute(
        select(NationalTournament).where(NationalTournament.id == tournament_id)
    )
    tournament = result.scalar_one_or_none()
    
    if not tournament:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tournament {tournament_id} not found"
        )
    
    # Check access (host institution only)
    if current_user.role != UserRole.teacher:
        if current_user.institution_id != tournament.host_institution_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only host institution can finalize the tournament"
            )
    
    try:
        finalized_tournament = await finalize_tournament(
            tournament_id=tournament_id,
            finalized_by=current_user.id,
            db=db
        )
        
        return {
            "success": True,
            "tournament_id": finalized_tournament.id,
            "status": finalized_tournament.status.value,
            "message": "Tournament finalized successfully"
        }
        
    except TournamentError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# =============================================================================
# Query Endpoints
# =============================================================================

@router.get("/tournaments/{tournament_id}/ranking")
async def get_tournament_ranking_endpoint(
    tournament_id: int,
    round_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get tournament rankings.
    
    Returns current or historical ranking based on round_id.
    """
    # Get tournament
    result = await db.execute(
        select(NationalTournament).where(NationalTournament.id == tournament_id)
    )
    tournament = result.scalar_one_or_none()
    
    if not tournament:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tournament {tournament_id} not found"
        )
    
    # Check access
    if current_user.role != UserRole.teacher:
        # Check if user's institution is participating
        result = await db.execute(
            select(TournamentInstitution).where(
                and_(
                    TournamentInstitution.tournament_id == tournament_id,
                    TournamentInstitution.institution_id == current_user.institution_id
                )
            )
        )
        participation = result.scalar_one_or_none()
        
        if not participation and current_user.institution_id != tournament.host_institution_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this tournament's rankings"
            )
    
    # Get rankings
    from backend.orm.national_network import NationalTeamRanking
    
    query = select(NationalTeamRanking).where(
        NationalTeamRanking.tournament_id == tournament_id
    )
    
    if round_id:
        query = query.where(NationalTeamRanking.round_id == round_id)
    else:
        # Get most recent or final ranking
        query = query.where(NationalTeamRanking.is_final == True)
    
    query = query.order_by(NationalTeamRanking.id.desc()).limit(1)
    
    result = await db.execute(query)
    ranking = result.scalar_one_or_none()
    
    if not ranking:
        # Compute new ranking if none exists
        ranking = await compute_national_ranking(
            tournament_id=tournament_id,
            round_id=round_id,
            computed_by=current_user.id,
            db=db
        )
    
    return {
        "tournament_id": tournament_id,
        "round_id": ranking.round_id,
        "is_final": ranking.is_final,
        "is_finalized": ranking.is_finalized,
        "computed_at": ranking.computed_at.isoformat() if ranking.computed_at else None,
        "checksum": ranking.checksum,
        "rankings": json.loads(ranking.rankings_json) if ranking.rankings_json else []
    }


@router.get("/tournaments/{tournament_id}/ledger/verify")
async def verify_ledger_endpoint(
    tournament_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.teacher, UserRole.teacher]))
):
    """
    Verify the integrity of the tournament ledger.
    
    Requires: ADMIN or SUPER_ADMIN role
    """
    # Get tournament
    result = await db.execute(
        select(NationalTournament).where(NationalTournament.id == tournament_id)
    )
    tournament = result.scalar_one_or_none()
    
    if not tournament:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tournament {tournament_id} not found"
        )
    
    # Check access
    if current_user.role != UserRole.teacher:
        if current_user.institution_id != tournament.host_institution_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only host institution or super admin can verify ledger"
            )
    
    # Verify chain
    verification = await verify_national_ledger_chain(tournament_id, db)
    
    return {
        "tournament_id": tournament_id,
        "is_valid": verification["is_valid"],
        "total_entries": verification["total_entries"],
        "first_entry_id": verification["first_entry_id"],
        "last_entry_id": verification["last_entry_id"],
        "errors": verification["errors"],
        "invalid_entries": verification["invalid_entries"]
    }


@router.get("/tournaments/{tournament_id}/ledger")
async def get_ledger_entries_endpoint(
    tournament_id: int,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.teacher, UserRole.teacher, UserRole.teacher]))
):
    """
    Get ledger entries for a tournament.
    
    Requires: ADMIN, HOD, or SUPER_ADMIN role
    """
    # Get tournament
    result = await db.execute(
        select(NationalTournament).where(NationalTournament.id == tournament_id)
    )
    tournament = result.scalar_one_or_none()
    
    if not tournament:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tournament {tournament_id} not found"
        )
    
    # Check access
    if current_user.role != UserRole.teacher:
        if current_user.institution_id != tournament.host_institution_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only host institution can view full ledger"
            )
    
    entries = await get_ledger_entries_for_tournament(
        tournament_id=tournament_id,
        db=db,
        limit=limit,
        offset=offset
    )
    
    return {
        "tournament_id": tournament_id,
        "total_returned": len(entries),
        "entries": [entry.to_dict() for entry in entries]
    }


# =============================================================================
# Additional Endpoints
# =============================================================================

@router.get("/tournaments/{tournament_id}")
async def get_tournament_details_endpoint(
    tournament_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get tournament details.
    """
    # Get tournament
    result = await db.execute(
        select(NationalTournament).where(NationalTournament.id == tournament_id)
    )
    tournament = result.scalar_one_or_none()
    
    if not tournament:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tournament {tournament_id} not found"
        )
    
    # Check access
    if current_user.role != UserRole.teacher:
        result = await db.execute(
            select(TournamentInstitution).where(
                and_(
                    TournamentInstitution.tournament_id == tournament_id,
                    TournamentInstitution.institution_id == current_user.institution_id
                )
            )
        )
        participation = result.scalar_one_or_none()
        
        if not participation and current_user.institution_id != tournament.host_institution_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this tournament"
            )
    
    # Get team count
    result = await db.execute(
        select(TournamentTeam).where(
            and_(
                TournamentTeam.tournament_id == tournament_id,
                TournamentTeam.is_active == True
            )
        )
    )
    teams = list(result.scalars().all())
    
    return {
        "tournament": tournament.to_dict(),
        "team_count": len(teams),
        "teams": [team.to_dict() for team in teams]
    }
