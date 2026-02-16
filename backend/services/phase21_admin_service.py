"""
Phase 21 — Admin Command Center Services.

Operational control layer for governance, monitoring, and audit.
Read-heavy, deterministic, lifecycle-aware, integrity-aware.

Services:
- AdminDashboardService: Tournament overview aggregation
- GuardInspectorService: Cross-phase guard inspection
- AppealsQueueService: Appeals queue wrapper
- SessionMonitorService: Live session monitoring
- IntegrityCenterService: Tournament integrity verification
- AdminActionLoggerService: Deterministic action logging
"""
import hashlib
import json
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, and_
from sqlalchemy.orm import selectinload

from backend.config.feature_flags import feature_flags
from backend.orm.phase21_admin_center import AdminActionLog


# =============================================================================
# Integrity Hash Generation
# =============================================================================

def _generate_action_hash(
    actor_user_id: Optional[UUID],
    action_type: str,
    target_id: Optional[UUID],
    payload_snapshot: Dict[str, Any]
) -> str:
    """
    Generate deterministic integrity hash for admin action.
    
    Hash covers:
    - actor_user_id
    - action_type
    - target_id
    - payload_snapshot (with sorted_keys)
    
    Returns: 64-character SHA256 hex digest
    """
    # Normalize None to empty string for consistent hashing
    actor_str = str(actor_user_id) if actor_user_id else ""
    target_str = str(target_id) if target_id else ""
    
    # Deterministic JSON serialization
    payload_str = json.dumps(
        payload_snapshot,
        sort_keys=True,
        separators=(',', ':')
    )
    
    # Concatenate with delimiter
    hash_input = f"{actor_str}|{action_type}|{target_str}|{payload_str}"
    
    # Generate SHA256 hash
    return hashlib.sha256(hash_input.encode('utf-8')).hexdigest()


# =============================================================================
# Service 1: AdminDashboardService
# =============================================================================

class AdminDashboardService:
    """
    Aggregate tournament overview data.
    
    Read-only service that collects lifecycle status, match counts,
    appeals, sessions, and integrity information.
    """
    
    @staticmethod
    async def get_tournament_overview(
        db: AsyncSession,
        tournament_id: UUID
    ) -> Dict[str, Any]:
        """
        Get comprehensive tournament overview.
        
        Returns deterministic sorted dict with:
        - lifecycle status
        - match counts
        - pending appeals
        - active sessions
        - ranking presence
        - final_standings_hash
        - guard snapshot
        """
        # Import Phase 20 lifecycle service
        from backend.services.phase20_lifecycle_service import LifecycleService
        from backend.orm.phase20_tournament_lifecycle import TournamentStatus
        
        # Get lifecycle status
        lifecycle = await LifecycleService.get_lifecycle(db, tournament_id)
        
        lifecycle_data = {
            "status": lifecycle.status.value if lifecycle else None,
            "final_standings_hash": lifecycle.final_standings_hash if lifecycle else None,
            "archived_at": lifecycle.archived_at.isoformat() if lifecycle and lifecycle.archived_at else None,
        }
        
        # Aggregate match counts (Phase 14)
        from backend.orm.phase14_deterministic_rounds import Match
        match_result = await db.execute(
            select(
                func.count(Match.id).label("total"),
                func.sum(func.case((Match.is_frozen == True, 1), else_=0)).label("frozen")
            ).where(Match.tournament_id == tournament_id)
        )
        match_counts = match_result.fetchone()
        
        # Count pending appeals (Phase 17)
        from backend.orm.phase17_appeals import Appeal, AppealStatus
        appeals_result = await db.execute(
            select(func.count(Appeal.id)).where(
                and_(
                    Appeal.tournament_id == tournament_id,
                    Appeal.status.in_([AppealStatus.FILED, AppealStatus.UNDER_REVIEW])
                )
            )
        )
        pending_appeals = appeals_result.scalar() or 0
        
        # Count active sessions (Phase 19)
        from backend.orm.phase19_moot_operations import CourtroomSession, SessionStatus
        sessions_result = await db.execute(
            select(func.count(CourtroomSession.id)).where(
                and_(
                    CourtroomSession.tournament_id == tournament_id,
                    CourtroomSession.status.in_([
                        SessionStatus.PENDING,
                        SessionStatus.IN_PROGRESS,
                        SessionStatus.PAUSED
                    ])
                )
            )
        )
        active_sessions = sessions_result.scalar() or 0
        
        # Check ranking presence (Phase 16)
        from backend.orm.phase16_ranking_system import TournamentRanking
        ranking_result = await db.execute(
            select(func.count(TournamentRanking.id)).where(
                TournamentRanking.tournament_id == tournament_id
            )
        )
        has_rankings = (ranking_result.scalar() or 0) > 0
        
        # Get guard snapshot
        guards = await GuardInspectorService.get_active_guards(db, tournament_id)
        
        # Build deterministic sorted output
        overview = {
            "tournament_id": str(tournament_id),
            "lifecycle": lifecycle_data,
            "matches": {
                "total": match_counts.total if match_counts else 0,
                "frozen": match_counts.frozen if match_counts else 0,
            },
            "appeals": {
                "pending": pending_appeals,
            },
            "sessions": {
                "active": active_sessions,
            },
            "rankings": {
                "computed": has_rankings,
            },
            "guards": guards,
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        # Sort keys recursively for determinism
        return _sort_dict_keys(overview)
    
    @staticmethod
    async def get_dashboard_summary(
        db: AsyncSession,
        tournament_id: UUID
    ) -> Dict[str, str]:
        """Get quick status summary for dashboard display."""
        overview = await AdminDashboardService.get_tournament_overview(db, tournament_id)
        
        lifecycle_status = overview["lifecycle"]["status"] or "unknown"
        total_matches = overview["matches"]["total"]
        pending_appeals = overview["appeals"]["pending"]
        active_sessions = overview["sessions"]["active"]
        has_rankings = overview["rankings"]["computed"]
        
        # Determine overall health
        if lifecycle_status == "archived":
            health = "archived"
        elif pending_appeals > 0 or active_sessions > 0:
            health = "active"
        elif lifecycle_status in ["completed", "scoring_locked"]:
            health = "finalizing"
        else:
            health = "in_progress"
        
        return {
            "lifecycle_status": lifecycle_status,
            "total_matches": str(total_matches),
            "pending_appeals": str(pending_appeals),
            "active_sessions": str(active_sessions),
            "rankings_ready": str(has_rankings).lower(),
            "overall_health": health,
        }


# =============================================================================
# Service 2: GuardInspectorService
# =============================================================================

class GuardInspectorService:
    """
    Inspect and report on cross-phase guard statuses.
    
    Checks lifecycle guards and returns deterministic summary.
    """
    
    @staticmethod
    async def get_active_guards(
        db: AsyncSession,
        tournament_id: UUID
    ) -> Dict[str, Any]:
        """
        Get active guard status for tournament.
        
        Returns:
        {
            "scheduling_blocked": bool,
            "appeals_blocked": bool,
            "ranking_blocked": bool,
            "session_blocked": bool,
            "reason": [list of deterministic strings]
        }
        """
        from backend.services.phase20_lifecycle_service import LifecycleService
        from backend.orm.phase20_tournament_lifecycle import TournamentStatus
        
        guards = {
            "scheduling_blocked": False,
            "appeals_blocked": False,
            "ranking_blocked": False,
            "session_blocked": False,
            "reason": [],
        }
        
        # Get current lifecycle status
        try:
            lifecycle = await LifecycleService.get_lifecycle(db, tournament_id)
            if not lifecycle:
                guards["reason"].append("no_lifecycle_found")
                return guards
            
            status = lifecycle.status
            
            # Scheduling blocked in ROUNDS_RUNNING or later
            if status in [
                TournamentStatus.ROUNDS_RUNNING,
                TournamentStatus.SCORING_LOCKED,
                TournamentStatus.COMPLETED,
                TournamentStatus.ARCHIVED,
            ]:
                guards["scheduling_blocked"] = True
                guards["reason"].append(f"lifecycle_{status.value}")
            
            # Appeals blocked in SCORING_LOCKED or later
            if status in [
                TournamentStatus.SCORING_LOCKED,
                TournamentStatus.COMPLETED,
                TournamentStatus.ARCHIVED,
            ]:
                guards["appeals_blocked"] = True
                if f"lifecycle_{status.value}" not in guards["reason"]:
                    guards["reason"].append(f"lifecycle_{status.value}")
            
            # Ranking recompute blocked when COMPLETED
            if status in [TournamentStatus.COMPLETED, TournamentStatus.ARCHIVED]:
                guards["ranking_blocked"] = True
                if f"lifecycle_{status.value}" not in guards["reason"]:
                    guards["reason"].append(f"lifecycle_{status.value}")
            
            # Sessions blocked when COMPLETED or ARCHIVED
            if status in [TournamentStatus.COMPLETED, TournamentStatus.ARCHIVED]:
                guards["session_blocked"] = True
                if f"lifecycle_{status.value}" not in guards["reason"]:
                    guards["reason"].append(f"lifecycle_{status.value}")
            
            # Sort reasons for determinism
            guards["reason"] = sorted(set(guards["reason"]))
            
        except Exception:
            # Fail open - don't block on inspection errors
            guards["reason"].append("inspection_error")
        
        return _sort_dict_keys(guards)


# =============================================================================
# Service 3: AppealsQueueService
# =============================================================================

class AppealsQueueService:
    """
    Read-only wrapper for Phase 17 appeals.
    
    Provides queue views for admin dashboard.
    """
    
    @staticmethod
    async def get_pending_appeals(
        db: AsyncSession,
        tournament_id: UUID,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get appeals with FILED status."""
        from backend.orm.phase17_appeals import Appeal, AppealStatus
        
        result = await db.execute(
            select(Appeal).where(
                and_(
                    Appeal.tournament_id == tournament_id,
                    Appeal.status == AppealStatus.FILED
                )
            ).order_by(Appeal.filed_at.asc()).limit(limit)
        )
        
        appeals = result.scalars().all()
        
        return [
            _sort_dict_keys({
                "id": str(a.id),
                "match_id": str(a.match_id),
                "status": a.status.value,
                "filed_at": a.filed_at.isoformat() if a.filed_at else None,
                "grounds": a.grounds,
            })
            for a in appeals
        ]
    
    @staticmethod
    async def get_under_review(
        db: AsyncSession,
        tournament_id: UUID,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get appeals with UNDER_REVIEW status."""
        from backend.orm.phase17_appeals import Appeal, AppealStatus
        
        result = await db.execute(
            select(Appeal).where(
                and_(
                    Appeal.tournament_id == tournament_id,
                    Appeal.status == AppealStatus.UNDER_REVIEW
                )
            ).order_by(Appeal.review_started_at.asc()).limit(limit)
        )
        
        appeals = result.scalars().all()
        
        return [
            _sort_dict_keys({
                "id": str(a.id),
                "match_id": str(a.match_id),
                "status": a.status.value,
                "reviewer_id": str(a.reviewer_id) if a.reviewer_id else None,
                "review_started_at": a.review_started_at.isoformat() if a.review_started_at else None,
            })
            for a in appeals
        ]
    
    @staticmethod
    async def get_expired(
        db: AsyncSession,
        tournament_id: UUID,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get appeals that have exceeded review timeout."""
        from backend.orm.phase17_appeals import Appeal, AppealStatus
        from backend.config.config import get_config
        
        config = get_config()
        appeal_timeout_hours = getattr(config, 'APPEAL_REVIEW_TIMEOUT_HOURS', 48)
        
        timeout_threshold = datetime.utcnow() - timedelta(hours=appeal_timeout_hours)
        
        result = await db.execute(
            select(Appeal).where(
                and_(
                    Appeal.tournament_id == tournament_id,
                    Appeal.status == AppealStatus.UNDER_REVIEW,
                    Appeal.review_started_at < timeout_threshold
                )
            ).order_by(Appeal.review_started_at.asc()).limit(limit)
        )
        
        appeals = result.scalars().all()
        
        return [
            _sort_dict_keys({
                "id": str(a.id),
                "match_id": str(a.match_id),
                "reviewer_id": str(a.reviewer_id) if a.reviewer_id else None,
                "review_started_at": a.review_started_at.isoformat() if a.review_started_at else None,
                "expired": True,
            })
            for a in appeals
        ]


# =============================================================================
# Service 4: SessionMonitorService
# =============================================================================

class SessionMonitorService:
    """
    Monitor live courtroom sessions.
    
    Read-only wrapper for Phase 19 session operations.
    """
    
    @staticmethod
    async def get_live_sessions(
        db: AsyncSession,
        tournament_id: UUID,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get currently active courtroom sessions."""
        from backend.orm.phase19_moot_operations import (
            CourtroomSession, SessionStatus
        )
        
        result = await db.execute(
            select(CourtroomSession).where(
                and_(
                    CourtroomSession.tournament_id == tournament_id,
                    CourtroomSession.status == SessionStatus.IN_PROGRESS
                )
            ).order_by(CourtroomSession.started_at.asc()).limit(limit)
        )
        
        sessions = result.scalars().all()
        
        return [
            _sort_dict_keys({
                "id": str(s.id),
                "match_id": str(s.match_id),
                "status": s.status.value,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "judge_id": str(s.judge_id) if s.judge_id else None,
            })
            for s in sessions
        ]
    
    @staticmethod
    async def get_session_summary(
        db: AsyncSession,
        tournament_id: UUID
    ) -> Dict[str, Any]:
        """Get summary of all sessions by status."""
        from backend.orm.phase19_moot_operations import (
            CourtroomSession, SessionStatus
        )
        
        result = await db.execute(
            select(
                CourtroomSession.status,
                func.count(CourtroomSession.id).label("count")
            ).where(
                CourtroomSession.tournament_id == tournament_id
            ).group_by(CourtroomSession.status)
        )
        
        counts = {row.status.value: row.count for row in result.fetchall()}
        
        return _sort_dict_keys({
            "tournament_id": str(tournament_id),
            "by_status": counts,
            "total": sum(counts.values()),
            "active": counts.get("in_progress", 0),
        })
    
    @staticmethod
    async def verify_session_integrity(
        db: AsyncSession,
        session_id: UUID
    ) -> Dict[str, Any]:
        """Verify integrity of a courtroom session."""
        from backend.orm.phase19_moot_operations import (
            CourtroomSession, SessionLogEntry
        )
        
        # Get session
        result = await db.execute(
            select(CourtroomSession).where(CourtroomSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        
        if not session:
            return {
                "valid": False,
                "error": "session_not_found",
            }
        
        # Get log entries
        logs_result = await db.execute(
            select(SessionLogEntry).where(
                SessionLogEntry.session_id == session_id
            ).order_by(SessionLogEntry.sequence_number.asc())
        )
        logs = logs_result.scalars().all()
        
        # Verify hash chain
        is_valid = True
        errors = []
        
        for i, log in enumerate(logs):
            # Verify sequence
            if log.sequence_number != i:
                is_valid = False
                errors.append(f"sequence_mismatch_at_{i}")
            
            # Verify prev_hash chain (if not first)
            if i > 0:
                prev_log = logs[i - 1]
                if log.prev_hash != prev_log.entry_hash:
                    is_valid = False
                    errors.append(f"hash_chain_break_at_{i}")
        
        return _sort_dict_keys({
            "session_id": str(session_id),
            "valid": is_valid,
            "log_count": len(logs),
            "errors": sorted(errors),
            "session_hash": session.session_hash if session.session_hash else None,
        })


# =============================================================================
# Service 5: IntegrityCenterService
# =============================================================================

class IntegrityCenterService:
    """
    Central integrity verification for entire tournament.
    
    Cross-phase verification covering:
    - Lifecycle standings hash
    - Session log chains
    - AI evaluation hashes
    - Appeal override hashes
    - Lifecycle violations
    """
    
    @staticmethod
    async def verify_tournament_integrity(
        db: AsyncSession,
        tournament_id: UUID
    ) -> Dict[str, Any]:
        """
        Comprehensive integrity check across all phases.
        
        Returns:
        {
          "lifecycle_valid": bool,
          "sessions_valid": bool,
          "ai_valid": bool,
          "appeals_valid": bool,
          "standings_hash_valid": bool,
          "overall_status": "healthy" | "warning" | "critical"
        }
        """
        from backend.services.phase20_lifecycle_service import LifecycleService
        from backend.orm.phase20_tournament_lifecycle import TournamentStatus
        
        checks = {
            "lifecycle_valid": True,
            "sessions_valid": True,
            "ai_valid": True,
            "appeals_valid": True,
            "standings_hash_valid": True,
        }
        
        warnings = []
        criticals = []
        
        # 1. Verify lifecycle
        try:
            lifecycle = await LifecycleService.get_lifecycle(db, tournament_id)
            if not lifecycle:
                checks["lifecycle_valid"] = False
                criticals.append("no_lifecycle")
            elif lifecycle.status == TournamentStatus.ARCHIVED and not lifecycle.archived_at:
                checks["lifecycle_valid"] = False
                criticals.append("archived_no_timestamp")
        except Exception:
            checks["lifecycle_valid"] = False
            criticals.append("lifecycle_check_failed")
        
        # 2. Verify sessions
        try:
            from backend.orm.phase19_moot_operations import (
                CourtroomSession, SessionLogEntry
            )
            
            # Check for broken hash chains
            sessions_result = await db.execute(
                select(CourtroomSession).where(
                    CourtroomSession.tournament_id == tournament_id
                )
            )
            sessions = sessions_result.scalars().all()
            
            for session in sessions:
                logs_result = await db.execute(
                    select(SessionLogEntry).where(
                        SessionLogEntry.session_id == session.id
                    ).order_by(SessionLogEntry.sequence_number.asc())
                )
                logs = logs_result.scalars().all()
                
                for i, log in enumerate(logs):
                    if i > 0:
                        prev_log = logs[i - 1]
                        if log.prev_hash != prev_log.entry_hash:
                            checks["sessions_valid"] = False
                            criticals.append(f"session_chain_break_{session.id}")
                            break
        except Exception:
            checks["sessions_valid"] = False
            criticals.append("session_check_failed")
        
        # 3. Verify AI evaluations
        try:
            from backend.orm.phase15_ai_judge import AIEvaluation
            
            ai_result = await db.execute(
                select(AIEvaluation).where(
                    AIEvaluation.tournament_id == tournament_id
                )
            )
            evaluations = ai_result.scalars().all()
            
            for eval in evaluations:
                if not eval.integrity_hash:
                    checks["ai_valid"] = False
                    criticals.append(f"ai_missing_hash_{eval.id}")
        except Exception:
            checks["ai_valid"] = False
            criticals.append("ai_check_failed")
        
        # 4. Verify appeals
        try:
            from backend.orm.phase17_appeals import Appeal, AppealStatus
            
            # Check for appeals with invalid override hashes
            appeals_result = await db.execute(
                select(Appeal).where(
                    Appeal.tournament_id == tournament_id
                )
            )
            appeals = appeals_result.scalars().all()
            
            for appeal in appeals:
                if appeal.status == AppealStatus.OVERRIDDEN and not appeal.override_hash:
                    checks["appeals_valid"] = False
                    criticals.append(f"appeal_missing_override_hash_{appeal.id}")
            
            # Check for pending appeals in SCORING_LOCKED (warning)
            if lifecycle and lifecycle.status == TournamentStatus.SCORING_LOCKED:
                pending_result = await db.execute(
                    select(func.count(Appeal.id)).where(
                        and_(
                            Appeal.tournament_id == tournament_id,
                            Appeal.status.in_([AppealStatus.FILED, AppealStatus.UNDER_REVIEW])
                        )
                    )
                )
                pending_count = pending_result.scalar() or 0
                if pending_count > 0:
                    warnings.append(f"pending_appeals_in_scoring_locked_{pending_count}")
        except Exception:
            checks["appeals_valid"] = False
            criticals.append("appeal_check_failed")
        
        # 5. Verify standings hash (if COMPLETED)
        try:
            if lifecycle and lifecycle.status in [
                TournamentStatus.COMPLETED, TournamentStatus.ARCHIVED
            ]:
                if not lifecycle.final_standings_hash:
                    checks["standings_hash_valid"] = False
                    criticals.append("completed_no_standings_hash")
                elif len(lifecycle.final_standings_hash) != 64:
                    checks["standings_hash_valid"] = False
                    criticals.append("invalid_hash_length")
        except Exception:
            checks["standings_hash_valid"] = False
            criticals.append("standings_check_failed")
        
        # Determine overall status
        if criticals:
            overall_status = "critical"
        elif warnings:
            overall_status = "warning"
        else:
            overall_status = "healthy"
        
        result = {
            **checks,
            "overall_status": overall_status,
            "warnings": sorted(warnings),
            "criticals": sorted(criticals),
        }
        
        return _sort_dict_keys(result)
    
    @staticmethod
    async def get_integrity_report(
        db: AsyncSession,
        tournament_id: UUID
    ) -> Dict[str, Any]:
        """Generate detailed integrity report."""
        basic = await IntegrityCenterService.verify_tournament_integrity(
            db, tournament_id
        )
        
        # Add timestamp
        report = {
            **basic,
            "generated_at": datetime.utcnow().isoformat(),
            "tournament_id": str(tournament_id),
        }
        
        return _sort_dict_keys(report)


# =============================================================================
# Service 6: AdminActionLoggerService
# =============================================================================

class AdminActionLoggerService:
    """
    Deterministic action logging for admin operations.
    
    Only write operation in Phase 21.
    All writes include integrity hash for audit.
    """
    
    @staticmethod
    async def log_action(
        db: AsyncSession,
        tournament_id: UUID,
        actor_user_id: Optional[UUID],
        action_type: str,
        target_id: Optional[UUID],
        payload: Dict[str, Any]
    ) -> UUID:
        """
        Log an administrative action.
        
        Generates integrity hash and inserts record.
        Returns the log entry ID.
        """
        # Generate deterministic integrity hash
        integrity_hash = _generate_action_hash(
            actor_user_id=actor_user_id,
            action_type=action_type,
            target_id=target_id,
            payload_snapshot=payload
        )
        
        # Create log entry
        log_entry = AdminActionLog(
            id=uuid4(),
            tournament_id=tournament_id,
            action_type=action_type,
            actor_user_id=actor_user_id,
            target_id=target_id,
            payload_snapshot=payload,
            integrity_hash=integrity_hash,
            created_at=datetime.utcnow(),
        )
        
        db.add(log_entry)
        await db.commit()
        await db.refresh(log_entry)
        
        return log_entry.id
    
    @staticmethod
    async def get_action_history(
        db: AsyncSession,
        tournament_id: UUID,
        offset: int = 0,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get paginated action history for tournament."""
        result = await db.execute(
            select(AdminActionLog).where(
                AdminActionLog.tournament_id == tournament_id
            ).order_by(
                AdminActionLog.created_at.asc()
            ).offset(offset).limit(limit)
        )
        
        logs = result.scalars().all()
        
        return [
            _sort_dict_keys({
                "id": str(log.id),
                "action_type": log.action_type,
                "actor_user_id": str(log.actor_user_id) if log.actor_user_id else None,
                "target_id": str(log.target_id) if log.target_id else None,
                "integrity_hash": log.integrity_hash,
                "created_at": log.created_at.isoformat(),
            })
            for log in logs
        ]
    
    @staticmethod
    async def verify_log_integrity(
        db: AsyncSession,
        log_id: UUID
    ) -> Dict[str, Any]:
        """Verify integrity of a specific log entry."""
        result = await db.execute(
            select(AdminActionLog).where(AdminActionLog.id == log_id)
        )
        log = result.scalar_one_or_none()
        
        if not log:
            return {
                "valid": False,
                "error": "log_not_found",
            }
        
        # Regenerate hash
        computed_hash = _generate_action_hash(
            actor_user_id=log.actor_user_id,
            action_type=log.action_type,
            target_id=log.target_id,
            payload_snapshot=log.payload_snapshot
        )
        
        # Compare (constant-time)
        is_valid = _constant_time_compare(computed_hash, log.integrity_hash)
        
        return _sort_dict_keys({
            "log_id": str(log_id),
            "valid": is_valid,
            "stored_hash": log.integrity_hash,
            "computed_hash": computed_hash,
        })


# =============================================================================
# Helper Functions
# =============================================================================

from datetime import timedelta


def _sort_dict_keys(obj: Any) -> Any:
    """Recursively sort dictionary keys for deterministic output."""
    if isinstance(obj, dict):
        return {k: _sort_dict_keys(v) for k, v in sorted(obj.items())}
    elif isinstance(obj, list):
        return [_sort_dict_keys(item) for item in obj]
    else:
        return obj


def _constant_time_compare(a: str, b: str) -> bool:
    """Constant-time string comparison to prevent timing attacks."""
    if len(a) != len(b):
        return False
    
    result = 0
    for x, y in zip(a, b):
        result |= ord(x) ^ ord(y)
    
    return result == 0
