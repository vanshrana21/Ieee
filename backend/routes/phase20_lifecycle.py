"""
Phase 20 — Tournament Lifecycle Orchestrator API Routes.

Global deterministic tournament state machine with cross-phase governance.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.rbac import require_role, get_current_user
from backend.orm.user import UserRole
from backend.config.feature_flags import feature_flags

from backend.services.phase20_lifecycle_service import (
    LifecycleService, LifecycleError, LifecycleNotFoundError,
    InvalidTransitionError, CrossPhaseValidationError, TournamentClosedError
)
from backend.orm.phase20_tournament_lifecycle import TournamentLifecycle, TournamentStatus


router = APIRouter(prefix="/api/lifecycle", tags=["tournament-lifecycle"])


# =============================================================================
# Pydantic Request/Response Models
# =============================================================================

class CreateLifecycleRequest(BaseModel):
    tournament_id: UUID


class TransitionRequest(BaseModel):
    new_status: TournamentStatus


class LifecycleResponse(BaseModel):
    id: UUID
    tournament_id: UUID
    status: str
    final_standings_hash: Optional[str]
    archived_at: Optional[str]
    created_at: str
    updated_at: str


class TransitionResponse(BaseModel):
    success: bool
    message: str
    lifecycle: LifecycleResponse


class VerifyResponse(BaseModel):
    tournament_id: UUID
    is_valid: bool
    stored_hash: Optional[str]
    computed_hash: Optional[str]
    message: str


class StandingsHashResponse(BaseModel):
    tournament_id: UUID
    final_standings_hash: Optional[str]
    computed_at: Optional[str]


class OperationCheckResponse(BaseModel):
    tournament_id: UUID
    operation: str
    allowed: bool
    reason: str


# =============================================================================
# Feature Flag Check
# =============================================================================

def check_lifecycle_enabled():
    """Check if tournament lifecycle is enabled."""
    if not feature_flags.FEATURE_TOURNAMENT_LIFECYCLE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tournament lifecycle orchestrator is disabled"
        )


# =============================================================================
# Lifecycle Management Routes
# =============================================================================

@router.post("/create/{tournament_id}", response_model=LifecycleResponse)
async def create_lifecycle(
    tournament_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role([UserRole.ADMIN, UserRole.SUPER_ADMIN]))
):
    """
    Create lifecycle record for tournament.
    
    **Roles:** Admin, SuperAdmin
    
    Initializes tournament in DRAFT status.
    """
    check_lifecycle_enabled()
    
    try:
        lifecycle = await LifecycleService.create_lifecycle(
            db=db,
            tournament_id=tournament_id
        )
        
        return LifecycleResponse(
            id=lifecycle.id,
            tournament_id=lifecycle.tournament_id,
            status=lifecycle.status,
            final_standings_hash=lifecycle.final_standings_hash,
            archived_at=lifecycle.archived_at.isoformat() if lifecycle.archived_at else None,
            created_at=lifecycle.created_at.isoformat() if lifecycle.created_at else "",
            updated_at=lifecycle.updated_at.isoformat() if lifecycle.updated_at else ""
        )
    except LifecycleError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/{tournament_id}", response_model=LifecycleResponse)
async def get_lifecycle(
    tournament_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role([UserRole.ADMIN, UserRole.SUPER_ADMIN]))
):
    """
    Get lifecycle status for tournament.
    
    **Roles:** Admin, SuperAdmin
    """
    check_lifecycle_enabled()
    
    lifecycle = await LifecycleService.get_lifecycle(db, tournament_id)
    
    if not lifecycle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lifecycle not found"
        )
    
    return LifecycleResponse(
        id=lifecycle.id,
        tournament_id=lifecycle.tournament_id,
        status=lifecycle.status,
        final_standings_hash=lifecycle.final_standings_hash,
        archived_at=lifecycle.archived_at.isoformat() if lifecycle.archived_at else None,
        created_at=lifecycle.created_at.isoformat() if lifecycle.created_at else "",
        updated_at=lifecycle.updated_at.isoformat() if lifecycle.updated_at else ""
    )


@router.post("/{tournament_id}/transition", response_model=TransitionResponse)
async def transition_status(
    tournament_id: UUID,
    request: TransitionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role([UserRole.ADMIN, UserRole.SUPER_ADMIN]))
):
    """
    Transition tournament to new lifecycle status.
    
    **Roles:** Admin, SuperAdmin
    
    Validates state machine and cross-phase invariants.
    """
    check_lifecycle_enabled()
    
    try:
        lifecycle, success, message = await LifecycleService.transition_status(
            db=db,
            tournament_id=tournament_id,
            new_status=request.new_status,
            transitioned_by_user_id=current_user["id"]
        )
        
        if not lifecycle:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lifecycle not found"
            )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=message
            )
        
        return TransitionResponse(
            success=success,
            message=message,
            lifecycle=LifecycleResponse(
                id=lifecycle.id,
                tournament_id=lifecycle.tournament_id,
                status=lifecycle.status,
                final_standings_hash=lifecycle.final_standings_hash,
                archived_at=lifecycle.archived_at.isoformat() if lifecycle.archived_at else None,
                created_at=lifecycle.created_at.isoformat() if lifecycle.created_at else "",
                updated_at=lifecycle.updated_at.isoformat() if lifecycle.updated_at else ""
            )
        )
    except (InvalidTransitionError, CrossPhaseValidationError) as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except TournamentClosedError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )


@router.get("/{tournament_id}/verify", response_model=VerifyResponse)
async def verify_standings_integrity(
    tournament_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role([UserRole.SUPER_ADMIN]))
):
    """
    Verify integrity of final standings hash.
    
    **Roles:** SuperAdmin only
    
    Recomputes hash and compares to stored value.
    """
    check_lifecycle_enabled()
    
    lifecycle = await LifecycleService.get_lifecycle(db, tournament_id)
    
    if not lifecycle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lifecycle not found"
        )
    
    if not lifecycle.final_standings_hash:
        return VerifyResponse(
            tournament_id=tournament_id,
            is_valid=False,
            stored_hash=None,
            computed_hash=None,
            message="No final standings hash stored"
        )
    
    is_valid, computed_hash = await LifecycleService.verify_standings_integrity(
        db=db,
        tournament_id=tournament_id
    )
    
    if is_valid:
        message = "Final standings integrity verified - hash matches"
    else:
        message = "Final standings integrity FAILED - hash mismatch detected"
    
    return VerifyResponse(
        tournament_id=tournament_id,
        is_valid=is_valid,
        stored_hash=lifecycle.final_standings_hash,
        computed_hash=computed_hash,
        message=message
    )


@router.get("/{tournament_id}/standings-hash", response_model=StandingsHashResponse)
async def get_standings_hash(
    tournament_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role([UserRole.ADMIN, UserRole.SUPER_ADMIN]))
):
    """
    Get final standings hash for tournament.
    
    **Roles:** Admin, SuperAdmin
    """
    check_lifecycle_enabled()
    
    lifecycle = await LifecycleService.get_lifecycle(db, tournament_id)
    
    if not lifecycle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lifecycle not found"
        )
    
    return StandingsHashResponse(
        tournament_id=tournament_id,
        final_standings_hash=lifecycle.final_standings_hash,
        computed_at=lifecycle.updated_at.isoformat() if lifecycle.final_standings_hash else None
    )


@router.get("/{tournament_id}/check-operation/{operation}", response_model=OperationCheckResponse)
async def check_operation(
    tournament_id: UUID,
    operation: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role([UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.JUDGE]))
):
    """
    Check if an operation is allowed on tournament.
    
    **Roles:** Admin, SuperAdmin, Judge
    
    Operations: appeal, schedule, ranking_recompute, score
    """
    check_lifecycle_enabled()
    
    allowed, reason = await LifecycleService.check_operation_allowed(
        db=db,
        tournament_id=tournament_id,
        operation=operation
    )
    
    return OperationCheckResponse(
        tournament_id=tournament_id,
        operation=operation,
        allowed=allowed,
        reason=reason
    )


# =============================================================================
# Cross-Phase Guard Enforcement
# =============================================================================

@router.get("/{tournament_id}/guards", response_model=dict)
async def get_lifecycle_guards(
    tournament_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role([UserRole.ADMIN, UserRole.SUPER_ADMIN]))
):
    """
    Get active lifecycle guards for tournament.
    
    **Roles:** Admin, SuperAdmin
    
    Returns which operations are currently blocked.
    """
    check_lifecycle_enabled()
    
    lifecycle = await LifecycleService.get_lifecycle(db, tournament_id)
    
    if not lifecycle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lifecycle not found"
        )
    
    # Check various operations
    operations = ["appeal", "schedule", "ranking_recompute", "score"]
    guards = {}
    
    for op in operations:
        allowed, reason = await LifecycleService.check_operation_allowed(
            db=db,
            tournament_id=tournament_id,
            operation=op
        )
        guards[op] = {
            "allowed": allowed,
            "blocked": not allowed,
            "reason": reason if not allowed else None
        }
    
    return {
        "tournament_id": str(tournament_id),
        "status": lifecycle.status,
        "is_closed": lifecycle.status in [
            TournamentStatus.COMPLETED,
            TournamentStatus.ARCHIVED
        ],
        "guards": guards
    }
