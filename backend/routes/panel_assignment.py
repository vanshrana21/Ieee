"""
Phase 4 — Hardened Judge Panel Assignment API Routes

Conflict Detection + Immutability endpoints with:
- RBAC enforcement (ADMIN, HOD only for critical ops)
- Tournament scoping
- 404 on cross-tenant access
- Deterministic responses
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.dependencies import get_current_user, require_role
from backend.orm.user import User, UserRole
from backend.orm.panel_assignment import (
    JudgePanel, PanelMember, PanelMemberRole, JudgeAssignmentHistory, PanelFreeze
)
from backend.orm.round_pairing import TournamentRound, RoundPairing, RoundStatus
from backend.orm.national_network import NationalTournament
from backend.services.panel_assignment_service import (
    generate_panels_for_round, publish_panels, verify_panel_integrity,
    get_panels_by_round, get_assignment_history,
    has_judge_conflict, check_institution_conflict,
    PanelNotFoundError, PanelFrozenError, JudgeConflictError,
    InsufficientJudgesError, PanelAssignmentError, TournamentScopeError
)

router = APIRouter(prefix="/panels", tags=["Phase 4 — Judge Panel Assignment"])


# =============================================================================
# Panel Generation Endpoints
# =============================================================================

@router.post("/rounds/{round_id}/generate-panels", status_code=status.HTTP_201_CREATED)
async def generate_panels(
    round_id: int,
    panel_size: int = Query(default=3, ge=1, le=5, description="Number of judges per panel"),
    strict_mode: bool = Query(default=False, description="Block repeat judging"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.HOD]))
) -> Dict[str, Any]:
    """
    Generate judge panels for all pairings in a round.
    
    Algorithm:
    1. Fetch pairings sorted by table_number
    2. Select conflict-free judges deterministically
       - Fewer assignments first
       - No institution conflict
       - No coaching conflict
       - No repeat judging (if strict_mode)
    3. Assign first judge as presiding, others as members
    4. Record in assignment history
    
    Args:
        round_id: Round to generate panels for
        panel_size: Number of judges per panel (default 3)
        strict_mode: If True, block repeat judging
    
    Roles: ADMIN, HOD only
    """
    try:
        # Verify round access
        result = await db.execute(
            select(TournamentRound)
            .join(NationalTournament, TournamentRound.tournament_id == NationalTournament.id)
            .where(
                and_(
                    TournamentRound.id == round_id,
                    NationalTournament.host_institution_id == current_user.institution_id
                )
            )
        )
        round_obj = result.scalar_one_or_none()
        
        if not round_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Round not found"
            )
        
        panels = await generate_panels_for_round(
            round_id=round_id,
            db=db,
            panel_size=panel_size,
            strict_mode=strict_mode
        )
        
        return {
            "round_id": round_id,
            "panels_generated": len(panels),
            "panel_size": panel_size,
            "strict_mode": strict_mode,
            "panels": [p.to_dict(include_members=True) for p in panels],
            "message": "Panels generated successfully"
        }
        
    except PanelNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Round not found"
        )
    except PanelFrozenError:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Cannot modify finalized round"
        )
    except InsufficientJudgesError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except PanelAssignmentError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# =============================================================================
# Publish (Freeze) Endpoint
# =============================================================================

@router.post("/rounds/{round_id}/publish-panels", status_code=status.HTTP_200_OK)
async def publish_panels_endpoint(
    round_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.HOD]))
) -> Dict[str, Any]:
    """
    Publish (freeze) panels for a round.
    
    Steps:
    1. SERIALIZABLE transaction
    2. Build immutable snapshot
    3. Compute checksum
    4. Lock panel assignments
    
    Idempotent: Returns existing freeze if already published.
    
    Roles: ADMIN, HOD only
    """
    try:
        # Verify round access
        result = await db.execute(
            select(TournamentRound)
            .join(NationalTournament, TournamentRound.tournament_id == NationalTournament.id)
            .where(
                and_(
                    TournamentRound.id == round_id,
                    NationalTournament.host_institution_id == current_user.institution_id
                )
            )
        )
        round_obj = result.scalar_one_or_none()
        
        if not round_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Round not found"
            )
        
        freeze = await publish_panels(
            round_id=round_id,
            user_id=current_user.id,
            db=db
        )
        
        return {
            "round_id": round_id,
            "freeze_id": freeze.id,
            "panel_checksum": freeze.panel_checksum,
            "total_panels": len(freeze.panel_snapshot_json),
            "frozen_at": freeze.frozen_at.isoformat() if freeze.frozen_at else None,
            "frozen_by": freeze.frozen_by,
            "status": "published",
            "message": "Panels published successfully"
        }
        
    except PanelNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Round not found"
        )
    except PanelFrozenError:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Round already finalized"
        )
    except PanelAssignmentError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# =============================================================================
# Get Panels Endpoint
# =============================================================================

@router.get("/rounds/{round_id}/panels", status_code=status.HTTP_200_OK)
async def get_panels(
    round_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get all panels for a round with member details.
    
    Returns 404 if round not in user's tournament/institution.
    """
    # Verify round access
    result = await db.execute(
        select(TournamentRound)
        .join(NationalTournament, TournamentRound.tournament_id == NationalTournament.id)
        .where(
            and_(
                TournamentRound.id == round_id,
                NationalTournament.host_institution_id == current_user.institution_id
            )
        )
    )
    round_obj = result.scalar_one_or_none()
    
    if not round_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Round not found"
        )
    
    # Get panels
    panels = await get_panels_by_round(round_id, db)
    
    return {
        "round_id": round_id,
        "round_status": round_obj.status.value,
        "total_panels": len(panels),
        "panels": [p.to_dict(include_members=True) for p in panels]
    }


# =============================================================================
# Verify Integrity Endpoint
# =============================================================================

@router.get("/rounds/{round_id}/panels/verify", status_code=status.HTTP_200_OK)
async def verify_panels(
    round_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.HOD, UserRole.FACULTY]))
) -> Dict[str, Any]:
    """
    Verify panel integrity.
    
    Compares stored snapshot to current panel assignments.
    Detects any tampering, judge removal/addition, or reordering.
    
    Roles: ADMIN, HOD, FACULTY
    """
    # Verify round access
    result = await db.execute(
        select(TournamentRound)
        .join(NationalTournament, TournamentRound.tournament_id == NationalTournament.id)
        .where(
            and_(
                TournamentRound.id == round_id,
                NationalTournament.host_institution_id == current_user.institution_id
            )
        )
    )
    round_obj = result.scalar_one_or_none()
    
    if not round_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Round not found"
        )
    
    result = await verify_panel_integrity(round_id, db)
    
    return result


# =============================================================================
# Check Judge Conflict Endpoint
# =============================================================================

@router.get("/rounds/{round_id}/check-conflict", status_code=status.HTTP_200_OK)
async def check_judge_conflict(
    round_id: int,
    judge_id: int,
    petitioner_team_id: int,
    respondent_team_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.HOD, UserRole.FACULTY]))
) -> Dict[str, Any]:
    """
    Check if a judge has conflicts with a specific pairing.
    
    Checks:
    - Institution conflict (judge same institution as either team)
    - Coaching conflict (placeholder for future)
    - Repeat judging (if strict mode enabled)
    
    Returns detailed conflict information.
    """
    # Verify round access
    result = await db.execute(
        select(TournamentRound)
        .join(NationalTournament, TournamentRound.tournament_id == NationalTournament.id)
        .where(
            and_(
                TournamentRound.id == round_id,
                NationalTournament.host_institution_id == current_user.institution_id
            )
        )
    )
    round_obj = result.scalar_one_or_none()
    
    if not round_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Round not found"
        )
    
    # Get tournament_id from round
    tournament_id = round_obj.tournament_id
    
    # Check for conflicts
    has_conflict, reason = await has_judge_conflict(
        tournament_id=tournament_id,
        judge_id=judge_id,
        petitioner_team_id=petitioner_team_id,
        respondent_team_id=respondent_team_id,
        db=db,
        strict_mode=False  # Normal check, not strict
    )
    
    # Also check institution conflict specifically
    inst_conflict_petitioner = await check_institution_conflict(
        judge_id=judge_id,
        team_id=petitioner_team_id,
        db=db
    )
    
    inst_conflict_respondent = await check_institution_conflict(
        judge_id=judge_id,
        team_id=respondent_team_id,
        db=db
    )
    
    return {
        "round_id": round_id,
        "judge_id": judge_id,
        "petitioner_team_id": petitioner_team_id,
        "respondent_team_id": respondent_team_id,
        "has_conflict": has_conflict,
        "conflict_reason": reason,
        "institution_conflict_petitioner": inst_conflict_petitioner,
        "institution_conflict_respondent": inst_conflict_respondent,
        "can_assign": not has_conflict
    }


# =============================================================================
# Assignment History Endpoint
# =============================================================================

@router.get("/tournaments/{tournament_id}/assignment-history", status_code=status.HTTP_200_OK)
async def get_judge_assignment_history(
    tournament_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get judge assignment history for a tournament (conflict detection data).
    
    Shows all judge-team assignments to prevent conflicts.
    """
    # Verify tournament access
    result = await db.execute(
        select(NationalTournament).where(
            and_(
                NationalTournament.id == tournament_id,
                NationalTournament.host_institution_id == current_user.institution_id
            )
        )
    )
    tournament = result.scalar_one_or_none()
    
    if not tournament:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tournament not found"
        )
    
    history = await get_assignment_history(tournament_id, db)
    
    return {
        "tournament_id": tournament_id,
        "total_assignments": len(history),
        "history": [h.to_dict() for h in history]
    }


# =============================================================================
# Panel Details Endpoint
# =============================================================================

@router.get("/panels/{panel_id}", status_code=status.HTTP_200_OK)
async def get_panel(
    panel_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get panel details with member information.
    
    Returns 404 if panel not in user's tournament/institution.
    """
    # Get panel with scoping
    result = await db.execute(
        select(JudgePanel)
        .join(TournamentRound, JudgePanel.round_id == TournamentRound.id)
        .join(NationalTournament, TournamentRound.tournament_id == NationalTournament.id)
        .where(
            and_(
                JudgePanel.id == panel_id,
                NationalTournament.host_institution_id == current_user.institution_id
            )
        )
    )
    panel = result.scalar_one_or_none()
    
    if not panel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Panel not found"
        )
    
    return {
        "panel": panel.to_dict(include_members=True)
    }
