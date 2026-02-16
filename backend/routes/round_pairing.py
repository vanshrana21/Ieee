"""
Phase 3 — Hardened Round Pairing API Routes

Swiss + Knockout Pairing endpoints with:
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
from backend.orm.round_pairing import (
    TournamentRound, RoundPairing, PairingHistory, RoundFreeze,
    RoundType, RoundStatus
)
from backend.orm.national_network import NationalTournament
from backend.services.round_pairing_service import (
    create_round, get_round_by_id, get_rounds_by_tournament,
    generate_swiss_pairings, generate_knockout_pairings, publish_round,
    verify_round_integrity, get_pairings_by_round, get_pairing_history,
    RoundNotFoundError, RoundFinalizedError, RematchError,
    InsufficientTeamsError, RoundPairingError, TournamentScopeError
)

router = APIRouter(prefix="/rounds", tags=["Phase 3 — Round Pairing"])


# =============================================================================
# Round CRUD Endpoints
# =============================================================================

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_tournament_round(
    tournament_id: int,
    round_number: int,
    round_type: RoundType,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.HOD]))
) -> Dict[str, Any]:
    """
    Create new tournament round.
    
    Only ADMIN and HOD can create rounds.
    """
    try:
        # Verify tournament belongs to user's institution
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
        
        round_obj = await create_round(
            tournament_id=tournament_id,
            round_number=round_number,
            round_type=round_type,
            db=db
        )
        
        return {
            "id": round_obj.id,
            "tournament_id": round_obj.tournament_id,
            "round_number": round_obj.round_number,
            "round_type": round_obj.round_type.value,
            "status": round_obj.status.value,
            "created_at": round_obj.created_at.isoformat() if round_obj.created_at else None,
            "message": "Round created successfully"
        }
        
    except RoundPairingError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/{round_id}", status_code=status.HTTP_200_OK)
async def get_round(
    round_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get round details with pairings.
    
    Returns 404 if round not in user's tournament/institution.
    """
    # Get round with institution scoping
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
    
    # Get pairings
    pairings = await get_pairings_by_round(round_id, db)
    
    return {
        "round": round_obj.to_dict(),
        "pairings": [p.to_dict() for p in pairings],
        "total_pairings": len(pairings)
    }


@router.get("", status_code=status.HTTP_200_OK)
async def list_rounds(
    tournament_id: int,
    status: Optional[RoundStatus] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    List rounds for tournament (institution-scoped).
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
    
    rounds = await get_rounds_by_tournament(tournament_id, status, db)
    
    return {
        "tournament_id": tournament_id,
        "rounds": [r.to_dict() for r in rounds],
        "total_count": len(rounds),
        "status_filter": status.value if status else None
    }


# =============================================================================
# Pairing Generation Endpoints
# =============================================================================

@router.post("/{round_id}/generate", status_code=status.HTTP_201_CREATED)
async def generate_pairings(
    round_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.HOD]))
) -> Dict[str, Any]:
    """
    Generate pairings for a round (Swiss or Knockout).
    
    Algorithm is determined by round_type:
    - swiss: standings-based with rematch prevention
    - knockout: bracket pattern
    
    Only ADMIN and HOD can generate pairings.
    """
    try:
        # Get round with scoping
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
        
        # Generate based on round type
        if round_obj.round_type == RoundType.SWISS:
            pairings = await generate_swiss_pairings(round_id, db)
        elif round_obj.round_type == RoundType.KNOCKOUT:
            pairings = await generate_knockout_pairings(round_id, db)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown round type: {round_obj.round_type}"
            )
        
        return {
            "round_id": round_id,
            "round_type": round_obj.round_type.value,
            "pairings_generated": len(pairings),
            "pairings": [p.to_dict() for p in pairings],
            "message": "Pairings generated successfully"
        }
        
    except RoundNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Round not found"
        )
    except RoundFinalizedError:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Cannot modify finalized round"
        )
    except RematchError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except InsufficientTeamsError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except RoundPairingError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# =============================================================================
# Publish (Freeze) Endpoint
# =============================================================================

@router.post("/{round_id}/publish", status_code=status.HTTP_200_OK)
async def publish_round_endpoint(
    round_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.HOD]))
) -> Dict[str, Any]:
    """
    Publish (freeze) a round.
    
    Steps:
    1. SERIALIZABLE transaction
    2. Build immutable snapshot
    3. Compute checksum
    4. Lock round status
    
    Idempotent: Returns existing freeze if already published.
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
        
        freeze = await publish_round(
            round_id=round_id,
            user_id=current_user.id,
            db=db
        )
        
        return {
            "round_id": round_id,
            "freeze_id": freeze.id,
            "round_checksum": freeze.round_checksum,
            "total_pairings": len(freeze.pairing_snapshot_json),
            "frozen_at": freeze.frozen_at.isoformat() if freeze.frozen_at else None,
            "frozen_by": freeze.frozen_by,
            "status": "published",
            "message": "Round published successfully"
        }
        
    except RoundNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Round not found"
        )
    except RoundFinalizedError:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Round already finalized"
        )
    except RoundPairingError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# =============================================================================
# Verify Integrity Endpoint
# =============================================================================

@router.get("/{round_id}/verify", status_code=status.HTTP_200_OK)
async def verify_round(
    round_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.HOD, UserRole.FACULTY]))
) -> Dict[str, Any]:
    """
    Verify round integrity.
    
    Compares stored snapshot hashes to current pairing data.
    Detects any tampering, deletion, or addition of pairings.
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
    
    result = await verify_round_integrity(round_id, db)
    
    return result


# =============================================================================
# Pairing History Endpoint
# =============================================================================

@router.get("/{round_id}/history", status_code=status.HTTP_200_OK)
async def get_history(
    round_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get pairing history for tournament (rematch prevention data).
    
    Shows all historical pairings to prevent rematches.
    """
    # Get round with scoping
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
    
    history = await get_pairing_history(round_obj.tournament_id, db)
    
    return {
        "tournament_id": round_obj.tournament_id,
        "round_id": round_id,
        "total_historical_pairings": len(history),
        "history": [h.to_dict() for h in history]
    }
