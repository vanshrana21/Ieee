"""
Phase 20 — Tournament Lifecycle Orchestrator Service.

Global deterministic tournament state machine with cross-phase governance.
"""
import hashlib
import json
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload

from backend.orm.phase20_tournament_lifecycle import TournamentLifecycle, TournamentStatus


class LifecycleError(Exception):
    """Base exception for lifecycle errors."""
    pass


class LifecycleNotFoundError(LifecycleError):
    """Raised when lifecycle is not found."""
    pass


class InvalidTransitionError(LifecycleError):
    """Raised when invalid status transition is attempted."""
    pass


class CrossPhaseValidationError(LifecycleError):
    """Raised when cross-phase validation fails."""
    pass


class TournamentClosedError(LifecycleError):
    """Raised when tournament is closed for modifications."""
    pass


class LifecycleService:
    """
    Global tournament lifecycle orchestrator.
    
    Enforces deterministic state transitions and cross-phase invariants.
    ARCHIVED status is terminal - no further modifications allowed.
    """
    
    # State machine valid transitions
    VALID_TRANSITIONS = {
        TournamentStatus.DRAFT: [TournamentStatus.REGISTRATION_OPEN],
        TournamentStatus.REGISTRATION_OPEN: [TournamentStatus.REGISTRATION_CLOSED],
        TournamentStatus.REGISTRATION_CLOSED: [TournamentStatus.SCHEDULING],
        TournamentStatus.SCHEDULING: [TournamentStatus.ROUNDS_RUNNING],
        TournamentStatus.ROUNDS_RUNNING: [TournamentStatus.SCORING_LOCKED],
        TournamentStatus.SCORING_LOCKED: [TournamentStatus.COMPLETED],
        TournamentStatus.COMPLETED: [TournamentStatus.ARCHIVED],
        TournamentStatus.ARCHIVED: [],  # Terminal state
    }
    
    # Statuses that block most operations
    CLOSED_STATUSES = [
        TournamentStatus.COMPLETED,
        TournamentStatus.ARCHIVED
    ]
    
    @staticmethod
    def _is_valid_transition(current: TournamentStatus, new: TournamentStatus) -> bool:
        """Check if status transition is valid."""
        return new in LifecycleService.VALID_TRANSITIONS.get(current, [])
    
    @staticmethod
    def _compute_standings_hash(tournament_id: UUID, rankings_data: List[Dict[str, Any]]) -> str:
        """
        Compute SHA256 hash of final standings.
        
        Deterministic serialization for verification.
        """
        # Sort rankings by rank for determinism
        sorted_rankings = sorted(rankings_data, key=lambda x: x.get("rank", 0))
        
        # Build data with tournament_id
        data = {
            "tournament_id": str(tournament_id),
            "rankings": [
                {
                    "entity_id": str(r.get("entity_id")),
                    "rank": r.get("rank"),
                    "elo_rating": r.get("elo_rating"),
                    "wins": r.get("wins"),
                    "losses": r.get("losses"),
                }
                for r in sorted_rankings
            ]
        }
        
        # Deterministic JSON
        json_str = json.dumps(data, sort_keys=True, separators=(',', ':'))
        
        # SHA256 hash
        return hashlib.sha256(json_str.encode('utf-8')).hexdigest()
    
    @staticmethod
    def _constant_time_compare(a: str, b: str) -> bool:
        """Constant-time string comparison to prevent timing attacks."""
        if len(a) != len(b):
            return False
        result = 0
        for x, y in zip(a, b):
            result |= ord(x) ^ ord(y)
        return result == 0
    
    # ==========================================================================
    # Lifecycle Operations
    # ==========================================================================
    
    @staticmethod
    async def create_lifecycle(
        db: AsyncSession,
        tournament_id: UUID
    ) -> TournamentLifecycle:
        """
        Create lifecycle record for tournament.
        
        Args:
            db: Database session
            tournament_id: Tournament UUID
            
        Returns:
            Created TournamentLifecycle
        """
        lifecycle = TournamentLifecycle(
            tournament_id=tournament_id,
            status=TournamentStatus.DRAFT,
            final_standings_hash=None,
            archived_at=None
        )
        
        db.add(lifecycle)
        await db.flush()
        
        return lifecycle
    
    @staticmethod
    async def get_lifecycle(
        db: AsyncSession,
        tournament_id: UUID,
        lock: bool = False
    ) -> Optional[TournamentLifecycle]:
        """
        Get lifecycle for tournament.
        
        Args:
            db: Database session
            tournament_id: Tournament UUID
            lock: Whether to use FOR UPDATE locking
            
        Returns:
            TournamentLifecycle or None
        """
        query = select(TournamentLifecycle).where(
            TournamentLifecycle.tournament_id == tournament_id
        )
        
        if lock:
            query = query.with_for_update()
        
        result = await db.execute(query)
        return result.scalar_one_or_none()
    
    @staticmethod
    async def validate_cross_phase_rules(
        db: AsyncSession,
        tournament_id: UUID,
        target_status: TournamentStatus
    ) -> Tuple[bool, str]:
        """
        Validate cross-phase invariants before transition.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        # To SCHEDULING: At least 2 teams registered
        if target_status == TournamentStatus.SCHEDULING:
            # Query team count
            from backend.orm.tournament_team import TournamentTeam
            team_query = (
                select(func.count(TournamentTeam.id))
                .where(TournamentTeam.tournament_id == tournament_id)
            )
            team_result = await db.execute(team_query)
            team_count = team_result.scalar()
            
            if team_count < 2:
                return False, f"Need at least 2 teams, found {team_count}"
        
        # To ROUNDS_RUNNING: At least 1 scheduled match exists
        if target_status == TournamentStatus.ROUNDS_RUNNING:
            from backend.orm.phase18_scheduling import MatchScheduleAssignment
            match_query = (
                select(func.count(MatchScheduleAssignment.id))
                .where(MatchScheduleAssignment.courtroom_id.isnot(None))  # Scheduled
            )
            # Join with courtrooms to filter by tournament
            from backend.orm.phase18_scheduling import Courtroom
            match_query = (
                select(func.count(MatchScheduleAssignment.id))
                .join(Courtroom)
                .where(Courtroom.tournament_id == tournament_id)
            )
            match_result = await db.execute(match_query)
            match_count = match_result.scalar()
            
            if match_count < 1:
                return False, "Need at least 1 scheduled match"
        
        # To SCORING_LOCKED: All matches frozen, no pending appeals, no active sessions
        if target_status == TournamentStatus.SCORING_LOCKED:
            # Check all matches frozen (Phase 14)
            from backend.orm.tournament_matches import TournamentMatch
            from backend.orm.phase14_match_result import MatchScoreLock
            
            # Query unfrozen matches
            unfrozen_query = (
                select(func.count(TournamentMatch.id))
                .join(MatchScoreLock, MatchScoreLock.match_id == TournamentMatch.id)
                .where(
                    TournamentMatch.tournament_id == tournament_id,
                    MatchScoreLock.is_final == False  # Not frozen
                )
            )
            unfrozen_result = await db.execute(unfrozen_query)
            unfrozen_count = unfrozen_result.scalar()
            
            if unfrozen_count > 0:
                return False, f"{unfrozen_count} matches not frozen"
            
            # Check no pending appeals (Phase 17)
            from backend.orm.phase17_appeals import Appeal, AppealStatus
            pending_appeals_query = (
                select(func.count(Appeal.id))
                .join(TournamentMatch)
                .where(
                    TournamentMatch.tournament_id == tournament_id,
                    Appeal.status.notin_([
                        AppealStatus.DECIDED,
                        AppealStatus.REJECTED,
                        AppealStatus.WITHDRAWN
                    ])
                )
            )
            pending_result = await db.execute(pending_appeals_query)
            pending_count = pending_result.scalar()
            
            if pending_count > 0:
                return False, f"{pending_count} appeals pending"
            
            # Check no active sessions (Phase 19)
            from backend.orm.phase19_moot_operations import CourtroomSession, SessionStatus
            active_sessions_query = (
                select(func.count(CourtroomSession.id))
                .join(MatchScheduleAssignment, MatchScheduleAssignment.id == CourtroomSession.assignment_id)
                .join(Courtroom)
                .where(
                    Courtroom.tournament_id == tournament_id,
                    CourtroomSession.status == SessionStatus.ACTIVE
                )
            )
            active_result = await db.execute(active_sessions_query)
            active_count = active_result.scalar()
            
            if active_count > 0:
                return False, f"{active_count} active sessions"
        
        # To COMPLETED: Rankings computed
        if target_status == TournamentStatus.COMPLETED:
            from backend.orm.phase16_analytics import TeamPerformanceStats
            rankings_query = (
                select(func.count(TeamPerformanceStats.id))
                .where(TeamPerformanceStats.tournament_id == tournament_id)
            )
            rankings_result = await db.execute(rankings_query)
            rankings_count = rankings_result.scalar()
            
            if rankings_count < 1:
                return False, "Rankings not computed"
        
        # To ARCHIVED: Tournament already completed
        if target_status == TournamentStatus.ARCHIVED:
            lifecycle = await LifecycleService.get_lifecycle(db, tournament_id)
            if not lifecycle or lifecycle.status != TournamentStatus.COMPLETED:
                return False, "Must be COMPLETED before ARCHIVED"
            
            # Check no active sessions
            from backend.orm.phase19_moot_operations import CourtroomSession, SessionStatus
            from backend.orm.phase18_scheduling import MatchScheduleAssignment, Courtroom
            
            active_query = (
                select(func.count(CourtroomSession.id))
                .join(MatchScheduleAssignment)
                .join(Courtroom)
                .where(
                    Courtroom.tournament_id == tournament_id,
                    CourtroomSession.status == SessionStatus.ACTIVE
                )
            )
            active_result = await db.execute(active_query)
            active_count = active_result.scalar()
            
            if active_count > 0:
                return False, f"{active_count} active sessions must close"
        
        return True, ""
    
    @staticmethod
    async def transition_status(
        db: AsyncSession,
        tournament_id: UUID,
        new_status: TournamentStatus,
        transitioned_by_user_id: UUID
    ) -> Tuple[TournamentLifecycle, bool, str]:
        """
        Attempt to transition tournament lifecycle status.
        
        Args:
            db: Database session
            tournament_id: Tournament UUID
            new_status: Target status
            transitioned_by_user_id: User making the transition
            
        Returns:
            Tuple of (lifecycle, success, message)
        """
        # Lock lifecycle row
        lifecycle = await LifecycleService.get_lifecycle(db, tournament_id, lock=True)
        
        if not lifecycle:
            return None, False, "Lifecycle not found"
        
        # Check if already target status
        if lifecycle.status == new_status:
            return lifecycle, True, "Already in target status"
        
        # Validate state machine transition
        if not LifecycleService._is_valid_transition(lifecycle.status, new_status):
            return lifecycle, False, f"Cannot transition from {lifecycle.status} to {new_status}"
        
        # Validate cross-phase rules
        is_valid, error_message = await LifecycleService.validate_cross_phase_rules(
            db, tournament_id, new_status
        )
        if not is_valid:
            return lifecycle, False, error_message
        
        # Special handling for COMPLETED
        if new_status == TournamentStatus.COMPLETED:
            # Compute final standings hash
            from backend.orm.phase16_analytics import TeamPerformanceStats
            
            rankings_query = (
                select(TeamPerformanceStats)
                .where(TeamPerformanceStats.tournament_id == tournament_id)
                .order_by(TeamPerformanceStats.rank)
            )
            rankings_result = await db.execute(rankings_query)
            rankings = rankings_result.scalars().all()
            
            rankings_data = [
                {
                    "entity_id": r.team_id,
                    "rank": r.rank,
                    "elo_rating": r.elo_rating,
                    "wins": r.wins,
                    "losses": r.losses,
                }
                for r in rankings
            ]
            
            final_hash = LifecycleService._compute_standings_hash(
                tournament_id, rankings_data
            )
            lifecycle.final_standings_hash = final_hash
        
        # Special handling for ARCHIVED
        if new_status == TournamentStatus.ARCHIVED:
            lifecycle.archived_at = datetime.utcnow()
        
        # Update status
        lifecycle.status = new_status
        lifecycle.updated_at = datetime.utcnow()
        
        await db.flush()
        
        return lifecycle, True, f"Transitioned to {new_status}"
    
    @staticmethod
    async def verify_standings_integrity(
        db: AsyncSession,
        tournament_id: UUID
    ) -> Tuple[bool, Optional[str]]:
        """
        Verify integrity of final standings.
        
        Recomputes hash and compares to stored value.
        
        Returns:
            Tuple of (is_valid, computed_hash)
        """
        lifecycle = await LifecycleService.get_lifecycle(db, tournament_id)
        
        if not lifecycle:
            return False, None
        
        if not lifecycle.final_standings_hash:
            return False, None
        
        # Get current rankings
        from backend.orm.phase16_analytics import TeamPerformanceStats
        
        rankings_query = (
            select(TeamPerformanceStats)
            .where(TeamPerformanceStats.tournament_id == tournament_id)
            .order_by(TeamPerformanceStats.rank)
        )
        rankings_result = await db.execute(rankings_query)
        rankings = rankings_result.scalars().all()
        
        rankings_data = [
            {
                "entity_id": r.team_id,
                "rank": r.rank,
                "elo_rating": r.elo_rating,
                "wins": r.wins,
                "losses": r.losses,
            }
            for r in rankings
        ]
        
        # Recompute hash
        computed_hash = LifecycleService._compute_standings_hash(
            tournament_id, rankings_data
        )
        
        # Constant-time compare
        is_valid = LifecycleService._constant_time_compare(
            computed_hash, lifecycle.final_standings_hash
        )
        
        return is_valid, computed_hash
    
    @staticmethod
    async def check_operation_allowed(
        db: AsyncSession,
        tournament_id: UUID,
        operation: str
    ) -> Tuple[bool, str]:
        """
        Check if an operation is allowed on tournament.
        
        Used by other phases to enforce lifecycle guards.
        
        Args:
            db: Database session
            tournament_id: Tournament UUID
            operation: Operation name (e.g., "appeal", "schedule", "score")
            
        Returns:
            Tuple of (allowed, reason)
        """
        lifecycle = await LifecycleService.get_lifecycle(db, tournament_id)
        
        if not lifecycle:
            # No lifecycle means DRAFT
            return True, ""
        
        # Check if tournament is closed
        if lifecycle.status in LifecycleService.CLOSED_STATUSES:
            return False, f"Tournament is {lifecycle.status}"
        
        # Operation-specific checks
        if operation == "appeal":
            if lifecycle.status == TournamentStatus.SCORING_LOCKED:
                return False, "Appeals blocked after scoring locked"
        
        if operation == "schedule":
            if lifecycle.status in [
                TournamentStatus.ROUNDS_RUNNING,
                TournamentStatus.SCORING_LOCKED
            ]:
                return False, "Scheduling closed"
        
        if operation == "ranking_recompute":
            if lifecycle.status == TournamentStatus.COMPLETED:
                return False, "Rankings frozen at completion"
        
        return True, ""
