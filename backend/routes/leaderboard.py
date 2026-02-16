"""
Leaderboard Router — Phase 5 (Immutable Leaderboard Engine)

API endpoints for leaderboard management.

Security:
- Freeze requires FACULTY role
- Read endpoints available to authenticated users
- All operations audited
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.orm.user import User, UserRole
from backend.orm.ai_evaluations import AIEvaluationAudit
from backend.routes.auth import get_current_user
from backend.services import leaderboard_service as lb_svc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sessions", tags=["leaderboard"])


def _is_faculty(user: User) -> bool:
    """Check if user has faculty or admin role."""
    return user.role in (UserRole.teacher, UserRole.teacher)


def _make_error_response(error: str, message: str, details: Optional[dict] = None) -> dict:
    """Create standardized error response."""
    return {
        "success": False,
        "error": error,
        "message": message,
        "details": details
    }


# =============================================================================
# Leaderboard Freeze Endpoint (Faculty Only)
# =============================================================================

@router.post("/{session_id}/leaderboard/freeze")
async def freeze_leaderboard(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Freeze immutable leaderboard for a completed session.
    
    Requirements:
    - Session must be COMPLETED
    - All participants must have COMPLETED evaluations
    - No existing frozen leaderboard
    - Faculty-only access
    
    Returns:
        Snapshot metadata including checksum for integrity verification
    """
    # Verify faculty authorization
    if not _is_faculty(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_make_error_response("FORBIDDEN", "Only faculty can freeze leaderboards")
        )
    
    try:
        # Execute freeze operation
        snapshot = await lb_svc.freeze_leaderboard(
            session_id=session_id,
            faculty_id=current_user.id,
            db=db
        )
        
        return {
            "success": True,
            "snapshot_id": snapshot.id,
            "session_id": snapshot.session_id,
            "frozen_at": snapshot.frozen_at.isoformat() if snapshot.frozen_at else None,
            "frozen_by_faculty_id": snapshot.frozen_by_faculty_id,
            "rubric_version_id": snapshot.rubric_version_id,
            "ai_model_version": snapshot.ai_model_version,
            "total_participants": snapshot.total_participants,
            "checksum_hash": snapshot.checksum_hash,
            "integrity_verified": True,
            "message": "Leaderboard frozen successfully"
        }
        
    except lb_svc.UnauthorizedFreezeError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_make_error_response(e.code, e.message)
        )
    except lb_svc.AlreadyFrozenError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_make_error_response(e.code, e.message)
        )
    except lb_svc.SessionNotCompleteError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_make_error_response(e.code, e.message)
        )
    except lb_svc.IncompleteEvaluationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_make_error_response(e.code, e.message)
        )
    except lb_svc.RequiresReviewError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_make_error_response(e.code, e.message)
        )
    except lb_svc.MissingEvaluationsError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_make_error_response(e.code, e.message)
        )
    except lb_svc.LeaderboardError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_make_error_response(e.code, e.message)
        )
    except Exception as e:
        await db.rollback()
        logger.exception(f"Failed to freeze leaderboard for session {session_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_make_error_response("INTERNAL_ERROR", "Failed to freeze leaderboard")
        )


# =============================================================================
# Leaderboard Retrieval Endpoints
# =============================================================================

@router.get("/{session_id}/leaderboard")
async def get_leaderboard(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve frozen leaderboard for a session.
    
    Returns complete leaderboard with rankings and integrity status.
    """
    try:
        # Retrieve with integrity check
        snapshot, is_valid = await lb_svc.get_leaderboard_with_integrity_check(
            session_id=session_id,
            db=db
        )
        
        if not snapshot:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_make_error_response("NOT_FOUND", f"No frozen leaderboard for session {session_id}")
            )
        
        # Build response with entries
        entries = []
        for entry in snapshot.entries:
            entries.append({
                "rank": entry.rank,
                "participant_id": entry.participant_id,
                "side": entry.side.value if entry.side else None,
                "speaker_number": entry.speaker_number,
                "total_score": float(entry.total_score) if entry.total_score else 0.0,
                "tie_breaker_score": float(entry.tie_breaker_score) if entry.tie_breaker_score else 0.0,
                "score_breakdown": entry.to_dict().get("score_breakdown", {}),
                "evaluation_ids": entry.to_dict().get("evaluation_ids", [])
            })
        
        return {
            "success": True,
            "snapshot_id": snapshot.id,
            "session_id": snapshot.session_id,
            "frozen_at": snapshot.frozen_at.isoformat() if snapshot.frozen_at else None,
            "frozen_by_faculty_id": snapshot.frozen_by_faculty_id,
            "rubric_version_id": snapshot.rubric_version_id,
            "ai_model_version": snapshot.ai_model_version,
            "total_participants": snapshot.total_participants,
            "checksum_hash": snapshot.checksum_hash,
            "integrity_verified": is_valid,
            "entries": entries
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get leaderboard for session {session_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_make_error_response("INTERNAL_ERROR", "Failed to retrieve leaderboard")
        )


@router.get("/{session_id}/leaderboard/status")
async def get_leaderboard_status(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Check if leaderboard can be frozen for this session.
    
    Returns readiness status and any blocking conditions.
    """
    try:
        can_freeze, reason = await lb_svc.can_freeze_leaderboard(session_id, db)
        
        # Check if already frozen
        existing = await lb_svc.get_leaderboard(session_id, db)
        
        return {
            "success": True,
            "session_id": session_id,
            "can_freeze": can_freeze,
            "reason": reason,
            "is_frozen": existing is not None,
            "frozen_at": existing.frozen_at.isoformat() if existing else None
        }
        
    except Exception as e:
        logger.exception(f"Failed to check leaderboard status for session {session_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_make_error_response("INTERNAL_ERROR", "Failed to check leaderboard status")
        )


# =============================================================================
# Snapshot Detail Endpoint
# =============================================================================

@router.get("/leaderboard/snapshots/{snapshot_id}")
async def get_snapshot_by_id(
    snapshot_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve specific leaderboard snapshot by ID.
    
    Useful for historical leaderboard retrieval.
    """
    try:
        from sqlalchemy import select
        from backend.orm.session_leaderboard import SessionLeaderboardSnapshot
        
        result = await db.execute(
            select(SessionLeaderboardSnapshot).where(
                SessionLeaderboardSnapshot.id == snapshot_id
            )
        )
        snapshot = result.scalar_one_or_none()
        
        if not snapshot:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_make_error_response("NOT_FOUND", f"Snapshot {snapshot_id} not found")
            )
        
        # Load entries
        from backend.orm.session_leaderboard import SessionLeaderboardEntry
        entries_result = await db.execute(
            select(SessionLeaderboardEntry).where(
                SessionLeaderboardEntry.snapshot_id == snapshot_id
            ).order_by(SessionLeaderboardEntry.rank)
        )
        entries = entries_result.scalars().all()
        
        # Verify integrity
        computed_checksum = lb_svc._compute_checksum_from_entries(entries)
        is_valid = computed_checksum == snapshot.checksum_hash
        
        return {
            "success": True,
            "snapshot": {
                "id": snapshot.id,
                "session_id": snapshot.session_id,
                "frozen_at": snapshot.frozen_at.isoformat() if snapshot.frozen_at else None,
                "frozen_by_faculty_id": snapshot.frozen_by_faculty_id,
                "rubric_version_id": snapshot.rubric_version_id,
                "ai_model_version": snapshot.ai_model_version,
                "total_participants": snapshot.total_participants,
                "checksum_hash": snapshot.checksum_hash,
                "integrity_verified": is_valid,
                "entries": [e.to_dict() for e in entries]
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get snapshot {snapshot_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_make_error_response("INTERNAL_ERROR", "Failed to retrieve snapshot")
        )


@router.get("/{session_id}/leaderboard/verify")
async def verify_leaderboard_integrity(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Verify leaderboard integrity (admin-only).
    
    Recomputes checksum and compares with stored value.
    Logs any mismatches for audit trail.
    
    Returns:
        Integrity status with detailed verification results
    """
    # Verify admin authorization
    if current_user.role != UserRole.teacher:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_make_error_response("FORBIDDEN", "Only admins can verify leaderboard integrity")
        )
    
    try:
        # Retrieve with integrity check
        snapshot, is_valid = await lb_svc.get_leaderboard_with_integrity_check(
            session_id=session_id,
            db=db
        )
        
        if not snapshot:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_make_error_response("NOT_FOUND", f"No frozen leaderboard for session {session_id}")
            )
        
        # Log integrity failure
        if not is_valid:
            logger.error(
                f"LEADERBOARD INTEGRITY FAILED: session={session_id}, "
                f"snapshot={snapshot.id}, stored={snapshot.checksum_hash}"
            )
        
        return {
            "success": True,
            "session_id": session_id,
            "snapshot_id": snapshot.id,
            "integrity_verified": is_valid,
            "stored_checksum": snapshot.checksum_hash,
            "is_invalidated": snapshot.is_invalidated,
            "invalidated_reason": snapshot.invalidated_reason,
            "message": "Integrity verified" if is_valid else "INTEGRITY CHECKSUM MISMATCH - Investigation required"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to verify leaderboard integrity for session {session_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_make_error_response("INTERNAL_ERROR", "Failed to verify leaderboard integrity")
        )
