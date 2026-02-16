"""
Phase 21 — Admin Command Center Routes.

Operational control layer endpoints.
Base path: /api/admin

RBAC: ADMIN, SUPER_ADMIN only.
All routes check FEATURE_ADMIN_COMMAND_CENTER.
"""
from typing import Optional, List, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field

from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.config.feature_flags import feature_flags
from backend.orm.phase20_tournament_lifecycle import TournamentStatus
from backend.routes.auth import get_current_user
from backend.orm.user import User

from backend.services.phase21_admin_service import (
    AdminDashboardService,
    GuardInspectorService,
    AppealsQueueService,
    SessionMonitorService,
    IntegrityCenterService,
    AdminActionLoggerService,
    _generate_action_hash,
)


router = APIRouter(prefix="/api/admin", tags=["Phase 21 - Admin Command Center"])
security = HTTPBearer()


# =============================================================================
# Helper: Feature Flag Check
# =============================================================================

def require_feature_enabled():
    """Check if Phase 21 feature flag is enabled."""
    if not feature_flags.FEATURE_ADMIN_COMMAND_CENTER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Phase 21 Admin Command Center is disabled. Enable FEATURE_ADMIN_COMMAND_CENTER."
        )


def require_admin_role(current_user: User) -> User:
    """Check if user has admin role."""
    if current_user.role not in ["admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


# =============================================================================
# Request/Response Models
# =============================================================================

class TournamentOverviewResponse(BaseModel):
    tournament_id: str
    lifecycle: Dict[str, Any]
    matches: Dict[str, int]
    appeals: Dict[str, int]
    sessions: Dict[str, int]
    rankings: Dict[str, bool]
    guards: Dict[str, Any]
    timestamp: str


class GuardStatusResponse(BaseModel):
    scheduling_blocked: bool
    appeals_blocked: bool
    ranking_blocked: bool
    session_blocked: bool
    reason: List[str]


class AppealsListResponse(BaseModel):
    appeals: List[Dict[str, Any]]
    count: int


class SessionsListResponse(BaseModel):
    sessions: List[Dict[str, Any]]
    count: int


class SessionSummaryResponse(BaseModel):
    tournament_id: str
    by_status: Dict[str, int]
    total: int
    active: int


class SessionVerifyResponse(BaseModel):
    session_id: str
    valid: bool
    log_count: int
    errors: List[str]
    session_hash: Optional[str] = None


class IntegrityCheckResponse(BaseModel):
    lifecycle_valid: bool
    sessions_valid: bool
    ai_valid: bool
    appeals_valid: bool
    standings_hash_valid: bool
    overall_status: str
    warnings: List[str]
    criticals: List[str]


class IntegrityReportResponse(BaseModel):
    lifecycle_valid: bool
    sessions_valid: bool
    ai_valid: bool
    appeals_valid: bool
    standings_hash_valid: bool
    overall_status: str
    warnings: List[str]
    criticals: List[str]
    generated_at: str
    tournament_id: str


class StandingsSnapshotResponse(BaseModel):
    tournament_id: str
    lifecycle_status: str
    final_standings_hash: Optional[str]
    rankings: List[Dict[str, Any]]
    frozen: bool


class AdminActionsListResponse(BaseModel):
    actions: List[Dict[str, Any]]
    total: int
    offset: int
    limit: int


class LogActionRequest(BaseModel):
    action_type: str = Field(..., min_length=1, max_length=50)
    target_id: Optional[UUID] = None
    payload: Dict[str, Any] = Field(default_factory=dict)


class LogActionResponse(BaseModel):
    log_id: str
    integrity_hash: str
    created_at: str


class LogVerifyResponse(BaseModel):
    log_id: str
    valid: bool
    stored_hash: str
    computed_hash: str


# =============================================================================
# Dashboard Routes
# =============================================================================

@router.get(
    "/tournament/{tournament_id}/overview",
    response_model=TournamentOverviewResponse,
    summary="Get tournament overview"
)
async def get_tournament_overview(
    tournament_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get comprehensive tournament overview."""
    require_feature_enabled()
    require_admin_role(current_user)
    
    overview = await AdminDashboardService.get_tournament_overview(db, tournament_id)
    return overview


@router.get(
    "/tournament/{tournament_id}/summary",
    response_model=Dict[str, str],
    summary="Get quick status summary"
)
async def get_tournament_summary(
    tournament_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get quick status summary for dashboard."""
    require_feature_enabled()
    require_admin_role(current_user)
    
    summary = await AdminDashboardService.get_dashboard_summary(db, tournament_id)
    return summary


# =============================================================================
# Guard Routes
# =============================================================================

@router.get(
    "/tournament/{tournament_id}/guards",
    response_model=GuardStatusResponse,
    summary="Get active guard status"
)
async def get_active_guards(
    tournament_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get active guard status for tournament."""
    require_feature_enabled()
    require_admin_role(current_user)
    
    guards = await GuardInspectorService.get_active_guards(db, tournament_id)
    return guards


# =============================================================================
# Appeals Queue Routes
# =============================================================================

@router.get(
    "/tournament/{tournament_id}/appeals/pending",
    response_model=AppealsListResponse,
    summary="Get pending appeals"
)
async def get_pending_appeals(
    tournament_id: UUID,
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get appeals with FILED status."""
    require_feature_enabled()
    require_admin_role(current_user)
    
    appeals = await AppealsQueueService.get_pending_appeals(db, tournament_id, limit)
    return {"appeals": appeals, "count": len(appeals)}


@router.get(
    "/tournament/{tournament_id}/appeals/under-review",
    response_model=AppealsListResponse,
    summary="Get appeals under review"
)
async def get_under_review_appeals(
    tournament_id: UUID,
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get appeals with UNDER_REVIEW status."""
    require_feature_enabled()
    require_admin_role(current_user)
    
    appeals = await AppealsQueueService.get_under_review(db, tournament_id, limit)
    return {"appeals": appeals, "count": len(appeals)}


@router.get(
    "/tournament/{tournament_id}/appeals/expired",
    response_model=AppealsListResponse,
    summary="Get expired appeals"
)
async def get_expired_appeals(
    tournament_id: UUID,
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get appeals that have exceeded review timeout."""
    require_feature_enabled()
    require_admin_role(current_user)
    
    appeals = await AppealsQueueService.get_expired(db, tournament_id, limit)
    return {"appeals": appeals, "count": len(appeals)}


@router.get(
    "/tournament/{tournament_id}/appeals",
    response_model=AppealsListResponse,
    summary="Get all appeals summary"
)
async def get_appeals_summary(
    tournament_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get summary of all appeals by status."""
    require_feature_enabled()
    require_admin_role(current_user)
    
    pending = await AppealsQueueService.get_pending_appeals(db, tournament_id, 1000)
    under_review = await AppealsQueueService.get_under_review(db, tournament_id, 1000)
    expired = await AppealsQueueService.get_expired(db, tournament_id, 1000)
    
    all_appeals = pending + under_review + expired
    
    return {"appeals": all_appeals, "count": len(all_appeals)}


# =============================================================================
# Session Monitor Routes
# =============================================================================

@router.get(
    "/tournament/{tournament_id}/sessions",
    response_model=SessionsListResponse,
    summary="Get live sessions"
)
async def get_live_sessions(
    tournament_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get currently active courtroom sessions."""
    require_feature_enabled()
    require_admin_role(current_user)
    
    sessions = await SessionMonitorService.get_live_sessions(db, tournament_id, limit)
    return {"sessions": sessions, "count": len(sessions)}


@router.get(
    "/tournament/{tournament_id}/sessions/summary",
    response_model=SessionSummaryResponse,
    summary="Get session summary"
)
async def get_session_summary(
    tournament_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get summary of all sessions by status."""
    require_feature_enabled()
    require_admin_role(current_user)
    
    summary = await SessionMonitorService.get_session_summary(db, tournament_id)
    return summary


@router.get(
    "/session/{session_id}/monitor",
    response_model=Dict[str, Any],
    summary="Monitor specific session"
)
async def monitor_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get monitoring data for specific session."""
    require_feature_enabled()
    require_admin_role(current_user)
    
    # Get session details
    from backend.orm.phase19_moot_operations import CourtroomSession
    from sqlalchemy import select
    
    result = await db.execute(
        select(CourtroomSession).where(CourtroomSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    
    return {
        "session_id": str(session_id),
        "status": session.status.value if session.status else None,
        "match_id": str(session.match_id) if session.match_id else None,
        "judge_id": str(session.judge_id) if session.judge_id else None,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "session_hash": session.session_hash,
    }


@router.get(
    "/session/{session_id}/verify",
    response_model=SessionVerifyResponse,
    summary="Verify session integrity"
)
async def verify_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Verify integrity of a courtroom session."""
    require_feature_enabled()
    require_admin_role(current_user)
    
    verify_result = await SessionMonitorService.verify_session_integrity(db, session_id)
    return verify_result


# =============================================================================
# Integrity Routes
# =============================================================================

@router.get(
    "/tournament/{tournament_id}/integrity",
    response_model=IntegrityCheckResponse,
    summary="Verify tournament integrity"
)
async def verify_tournament_integrity(
    tournament_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Comprehensive integrity check across all phases."""
    require_feature_enabled()
    require_admin_role(current_user)
    
    integrity = await IntegrityCenterService.verify_tournament_integrity(db, tournament_id)
    return integrity


@router.get(
    "/tournament/{tournament_id}/integrity/report",
    response_model=IntegrityReportResponse,
    summary="Get detailed integrity report"
)
async def get_integrity_report(
    tournament_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Generate detailed integrity report."""
    require_feature_enabled()
    require_admin_role(current_user)
    
    report = await IntegrityCenterService.get_integrity_report(db, tournament_id)
    return report


# =============================================================================
# Standings Routes
# =============================================================================

@router.get(
    "/tournament/{tournament_id}/standings",
    response_model=StandingsSnapshotResponse,
    summary="Get standings snapshot"
)
async def get_standings_snapshot(
    tournament_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get frozen standings (no recompute)."""
    require_feature_enabled()
    require_admin_role(current_user)
    
    from backend.services.phase20_lifecycle_service import LifecycleService
    from backend.services.phase16_ranking_engine import RankingEngineService
    
    # Get lifecycle
    lifecycle = await LifecycleService.get_lifecycle(db, tournament_id)
    if not lifecycle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tournament lifecycle not found"
        )
    
    # Get rankings (read-only, no recompute)
    from backend.orm.phase16_ranking_system import TournamentRanking
    from sqlalchemy import select
    
    result = await db.execute(
        select(TournamentRanking).where(
            TournamentRanking.tournament_id == tournament_id
        ).order_by(TournamentRanking.rank.asc())
    )
    rankings = result.scalars().all()
    
    frozen = lifecycle.status in [
        TournamentStatus.COMPLETED,
        TournamentStatus.ARCHIVED
    ]
    
    return {
        "tournament_id": str(tournament_id),
        "lifecycle_status": lifecycle.status.value,
        "final_standings_hash": lifecycle.final_standings_hash,
        "rankings": [
            {
                "rank": r.rank,
                "entity_id": str(r.entity_id),
                "elo_rating": r.elo_rating,
                "wins": r.wins,
                "losses": r.losses,
            }
            for r in rankings
        ],
        "frozen": frozen,
    }


# =============================================================================
# Admin Actions Routes
# =============================================================================

@router.get(
    "/tournament/{tournament_id}/actions",
    response_model=AdminActionsListResponse,
    summary="Get admin action history"
)
async def get_admin_actions(
    tournament_id: UUID,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get paginated admin action history for tournament."""
    require_feature_enabled()
    require_admin_role(current_user)
    
    actions = await AdminActionLoggerService.get_action_history(
        db, tournament_id, offset, limit
    )
    
    return {
        "actions": actions,
        "total": len(actions),  # Simplified; in production would get total count
        "offset": offset,
        "limit": limit,
    }


@router.post(
    "/tournament/{tournament_id}/actions/log",
    response_model=LogActionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Log admin action"
)
async def log_admin_action(
    tournament_id: UUID,
    request: LogActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Log an administrative action with integrity hash."""
    require_feature_enabled()
    require_admin_role(current_user)
    
    log_id = await AdminActionLoggerService.log_action(
        db=db,
        tournament_id=tournament_id,
        actor_user_id=current_user.id,
        action_type=request.action_type,
        target_id=request.target_id,
        payload=request.payload
    )
    
    # Generate hash for response
    integrity_hash = _generate_action_hash(
        actor_user_id=current_user.id,
        action_type=request.action_type,
        target_id=request.target_id,
        payload_snapshot=request.payload
    )
    
    return {
        "log_id": str(log_id),
        "integrity_hash": integrity_hash,
        "created_at": datetime.utcnow().isoformat(),
    }


@router.get(
    "/actions/{log_id}/verify",
    response_model=LogVerifyResponse,
    summary="Verify action log integrity"
)
async def verify_action_log(
    log_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Verify integrity of a specific admin action log."""
    require_feature_enabled()
    require_admin_role(current_user)
    
    verify_result = await AdminActionLoggerService.verify_log_integrity(db, log_id)
    
    if not verify_result.get("valid") and verify_result.get("error"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=verify_result["error"]
        )
    
    return verify_result


# =============================================================================
# Health Check
# =============================================================================

@router.get(
    "/health",
    response_model=Dict[str, str],
    summary="Admin center health check"
)
async def health_check(
    current_user: User = Depends(get_current_user)
):
    """Check if admin center is operational."""
    require_feature_enabled()
    require_admin_role(current_user)
    
    return {
        "status": "healthy",
        "phase": "21",
        "feature": "admin_command_center",
    }
