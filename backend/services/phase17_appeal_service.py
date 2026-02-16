"""
Phase 17 — Appeals & Governance Override Service.

Server-authoritative appeal processing with deterministic state machine,
integrity hashing, and concurrency safety.

Phase 20 Integration: Lifecycle guards prevent appeal filing on closed tournaments.
"""
import uuid
import hashlib
from decimal import Decimal
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from collections import Counter

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.orm.phase17_appeals import (
    Appeal, AppealReview, AppealDecision, AppealOverrideResult,
    AppealReasonCode, AppealStatus, RecommendedAction, WinnerSide
)
from backend.orm.phase14_round_engine import (
    TournamentMatch, MatchStatus, MatchScoreLock
)
from backend.config.feature_flags import feature_flags


async def _check_lifecycle_guard(tournament_id: str) -> bool:
    """Phase 20: Check if appeal filing is allowed."""
    try:
        from backend.config.feature_flags import feature_flags as ff
        if not ff.FEATURE_TOURNAMENT_LIFECYCLE:
            return True
        
        from backend.services.phase20_lifecycle_service import LifecycleService
        from backend.database import async_session_maker
        from uuid import UUID
        
        async with async_session_maker() as db:
            allowed, _ = await LifecycleService.check_operation_allowed(
                db, UUID(tournament_id), "appeal"
            )
            return allowed
    except Exception:
        return True  # Fail open


class AppealServiceError(Exception):
    """Base exception for appeal service errors."""
    pass


class InvalidTransitionError(AppealServiceError):
    """Raised when an invalid state transition is attempted."""
    pass


class AppealValidationError(AppealServiceError):
    """Raised when appeal validation fails."""
    pass


class ConcurrencyError(AppealServiceError):
    """Raised when concurrent modification is detected."""
    pass


class AppealService:
    """
    Service for processing appeals with deterministic state machine.
    All operations are server-authoritative and concurrency-safe.
    """
    
    # Valid state transitions
    VALID_TRANSITIONS = {
        AppealStatus.FILED: [AppealStatus.UNDER_REVIEW, AppealStatus.REJECTED, AppealStatus.CLOSED],
        AppealStatus.UNDER_REVIEW: [AppealStatus.DECIDED, AppealStatus.REJECTED, AppealStatus.CLOSED],
        AppealStatus.DECIDED: [AppealStatus.CLOSED],
        AppealStatus.REJECTED: [AppealStatus.CLOSED],
        AppealStatus.CLOSED: [],  # Terminal state
    }
    
    # Appeal window in hours (configurable)
    APPEAL_WINDOW_HOURS = 24
    
    @staticmethod
    def _compute_integrity_hash(
        appeal_id: str,
        final_action: RecommendedAction,
        final_petitioner_score: Optional[Decimal],
        final_respondent_score: Optional[Decimal],
        new_winner: Optional[WinnerSide]
    ) -> str:
        """
        Compute deterministic SHA256 hash for decision integrity.
        Same inputs always produce same hash.
        """
        data = (
            f"{appeal_id}|"
            f"{final_action.value}|"
            f"{final_petitioner_score if final_petitioner_score else ''}|"
            f"{final_respondent_score if final_respondent_score else ''}|"
            f"{new_winner.value if new_winner else ''}"
        )
        return hashlib.sha256(data.encode()).hexdigest()
    
    @staticmethod
    def _compute_override_hash(
        match_id: str,
        original_winner: WinnerSide,
        overridden_winner: WinnerSide,
        decision_id: str
    ) -> str:
        """Compute hash for override record."""
        data = f"{match_id}|{original_winner.value}|{overridden_winner.value}|{decision_id}"
        return hashlib.sha256(data.encode()).hexdigest()
    
    @staticmethod
    def _is_valid_transition(current: AppealStatus, new: AppealStatus) -> bool:
        """Check if state transition is valid."""
        return new in AppealService.VALID_TRANSITIONS.get(current, [])
    
    @classmethod
    async def file_appeal(
        cls,
        db: AsyncSession,
        match_id: str,
        filed_by_user_id: str,
        team_id: str,
        reason_code: AppealReasonCode,
        detailed_reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        File a new appeal for a match.
        
        Validations:
        - Match must be FROZEN
        - Appeal window must not have expired
        - Team must belong to the match
        - No existing appeal from same team for this match
        """
        # Check feature flag
        if not feature_flags.FEATURE_APPEALS_ENGINE:
            raise AppealValidationError("Appeals engine is disabled")
        
        # Get match with locking
        match_result = await db.execute(
            select(TournamentMatch).where(
                TournamentMatch.id == match_id
            ).with_for_update()
        )
        match = match_result.scalar_one_or_none()
        
        if not match:
            raise AppealValidationError("Match not found")
        
        if match.status != MatchStatus.FROZEN:
            raise AppealValidationError(f"Cannot appeal match with status: {match.status.value}")
        
        # Check appeal window
        freeze_time = match.frozen_at if hasattr(match, 'frozen_at') else match.updated_at
        if freeze_time:
            deadline = freeze_time + timedelta(hours=cls.APPEAL_WINDOW_HOURS)
            if datetime.utcnow() > deadline:
                raise AppealValidationError("Appeal window has expired")
        
        # Verify team belongs to match
        if team_id not in [match.petitioner_id, match.respondent_id]:
            raise AppealValidationError("Team did not participate in this match")
        
        # Check for existing appeal
        existing_result = await db.execute(
            select(Appeal).where(
                and_(
                    Appeal.match_id == match_id,
                    Appeal.team_id == team_id
                )
            )
        )
        if existing_result.scalar_one_or_none():
            raise AppealValidationError("Appeal already filed for this match by this team")
        
        # Create appeal
        appeal = Appeal(
            id=str(uuid.uuid4()),
            match_id=match_id,
            filed_by_user_id=filed_by_user_id,
            team_id=team_id,
            reason_code=reason_code,
            detailed_reason=detailed_reason,
            status=AppealStatus.FILED,
            review_deadline=freeze_time + timedelta(hours=cls.APPEAL_WINDOW_HOURS) if freeze_time else None
        )
        
        db.add(appeal)
        await db.commit()
        
        return {
            "success": True,
            "appeal_id": appeal.id,
            "status": appeal.status.value,
            "message": "Appeal filed successfully"
        }
    
    @classmethod
    async def assign_under_review(
        cls,
        db: AsyncSession,
        appeal_id: str,
        admin_user_id: str
    ) -> Dict[str, Any]:
        """
        Assign appeal for review (Admin only).
        Transitions: FILED → UNDER_REVIEW
        """
        # Get appeal with locking
        result = await db.execute(
            select(Appeal).where(
                Appeal.id == appeal_id
            ).with_for_update()
        )
        appeal = result.scalar_one_or_none()
        
        if not appeal:
            raise AppealValidationError("Appeal not found")
        
        if not cls._is_valid_transition(appeal.status, AppealStatus.UNDER_REVIEW):
            raise InvalidTransitionError(
                f"Cannot transition from {appeal.status.value} to under_review"
            )
        
        appeal.status = AppealStatus.UNDER_REVIEW
        appeal.updated_at = datetime.utcnow()
        
        await db.commit()
        
        return {
            "success": True,
            "appeal_id": appeal_id,
            "status": appeal.status.value,
            "message": "Appeal assigned for review"
        }
    
    @classmethod
    async def submit_review(
        cls,
        db: AsyncSession,
        appeal_id: str,
        judge_user_id: str,
        recommended_action: RecommendedAction,
        justification: str,
        confidence_score: Decimal = Decimal("0.500")
    ) -> Dict[str, Any]:
        """
        Submit a judge review for an appeal.
        
        Validations:
        - Appeal status must be UNDER_REVIEW
        - Judge cannot submit duplicate review
        - Uses FOR UPDATE locking
        """
        # Check feature flag
        if not feature_flags.FEATURE_APPEALS_ENGINE:
            raise AppealValidationError("Appeals engine is disabled")
        
        # Get appeal with locking
        result = await db.execute(
            select(Appeal).where(
                Appeal.id == appeal_id
            ).with_for_update()
        )
        appeal = result.scalar_one_or_none()
        
        if not appeal:
            raise AppealValidationError("Appeal not found")
        
        if appeal.status != AppealStatus.UNDER_REVIEW:
            raise AppealValidationError(f"Cannot review appeal with status: {appeal.status.value}")
        
        # Check for duplicate review
        existing_review = await db.execute(
            select(AppealReview).where(
                and_(
                    AppealReview.appeal_id == appeal_id,
                    AppealReview.judge_user_id == judge_user_id
                )
            )
        )
        if existing_review.scalar_one_or_none():
            raise AppealValidationError("Judge has already submitted a review for this appeal")
        
        # Create review
        review = AppealReview(
            id=str(uuid.uuid4()),
            appeal_id=appeal_id,
            judge_user_id=judge_user_id,
            recommended_action=recommended_action,
            justification=justification,
            confidence_score=confidence_score
        )
        
        db.add(review)
        await db.commit()
        
        return {
            "success": True,
            "review_id": review.id,
            "message": "Review submitted successfully"
        }
    
    @classmethod
    async def finalize_decision(
        cls,
        db: AsyncSession,
        appeal_id: str,
        decided_by_user_id: str,
        final_action: RecommendedAction,
        final_petitioner_score: Optional[Decimal] = None,
        final_respondent_score: Optional[Decimal] = None,
        new_winner: Optional[WinnerSide] = None,
        decision_summary: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Finalize appeal decision (Admin only).
        
        Steps:
        1. Lock appeal row
        2. Ensure status == UNDER_REVIEW
        3. Count reviews
        4. If FEATURE_MULTI_JUDGE_APPEALS: require >=3 reviews, majority vote
        5. Validate score modifications
        6. Compute integrity hash
        7. Insert appeal_decisions
        8. Create override record if winner changes
        9. Set appeal.status = DECIDED
        
        Immutable after decision.
        """
        # Check feature flag
        if not feature_flags.FEATURE_APPEALS_ENGINE:
            raise AppealValidationError("Appeals engine is disabled")
        
        # Get appeal with locking
        result = await db.execute(
            select(Appeal).where(
                Appeal.id == appeal_id
            ).with_for_update()
        )
        appeal = result.scalar_one_or_none()
        
        if not appeal:
            raise AppealValidationError("Appeal not found")
        
        if appeal.status != AppealStatus.UNDER_REVIEW:
            raise InvalidTransitionError(
                f"Cannot finalize appeal with status: {appeal.status.value}"
            )
        
        # Check if decision already exists (concurrency protection)
        existing_decision = await db.execute(
            select(AppealDecision).where(
                AppealDecision.appeal_id == appeal_id
            )
        )
        if existing_decision.scalar_one_or_none():
            raise ConcurrencyError("Decision already exists for this appeal")
        
        # Get all reviews
        reviews_result = await db.execute(
            select(AppealReview).where(
                AppealReview.appeal_id == appeal_id
            )
        )
        reviews = reviews_result.scalars().all()
        
        # Multi-judge appeals logic
        if feature_flags.FEATURE_MULTI_JUDGE_APPEALS:
            if len(reviews) < 3:
                raise AppealValidationError(
                    f"Multi-judge appeals require at least 3 reviews, found: {len(reviews)}"
                )
            
            # Majority vote logic
            actions = [r.recommended_action for r in reviews]
            action_counts = Counter(actions)
            majority_action, majority_count = action_counts.most_common(1)[0]
            
            # Tie-breaking: if no clear majority, default to UPHOLD
            if majority_count <= len(reviews) / 2:
                final_action = RecommendedAction.UPHOLD
            else:
                final_action = majority_action
        
        # Validate score modifications
        if final_action == RecommendedAction.MODIFY_SCORE:
            if final_petitioner_score is None or final_respondent_score is None:
                raise AppealValidationError("Score modification requires both petitioner and respondent scores")
            
            if not (0 <= final_petitioner_score <= 100) or not (0 <= final_respondent_score <= 100):
                raise AppealValidationError("Scores must be between 0 and 100")
        
        # Compute integrity hash
        integrity_hash = cls._compute_integrity_hash(
            appeal_id=appeal_id,
            final_action=final_action,
            final_petitioner_score=final_petitioner_score,
            final_respondent_score=final_respondent_score,
            new_winner=new_winner
        )
        
        # Create decision
        decision = AppealDecision(
            id=str(uuid.uuid4()),
            appeal_id=appeal_id,
            final_action=final_action,
            final_petitioner_score=final_petitioner_score,
            final_respondent_score=final_respondent_score,
            new_winner=new_winner,
            decided_by_user_id=decided_by_user_id,
            decision_summary=decision_summary,
            integrity_hash=integrity_hash
        )
        
        db.add(decision)
        
        # Create override record if winner changes or action is REVERSE_WINNER
        if final_action == RecommendedAction.REVERSE_WINNER or (
            final_action == RecommendedAction.MODIFY_SCORE and new_winner
        ):
            # Get original match to determine original winner
            match_result = await db.execute(
                select(TournamentMatch, MatchScoreLock).join(
                    MatchScoreLock,
                    TournamentMatch.id == MatchScoreLock.match_id
                ).where(
                    TournamentMatch.id == appeal.match_id
                )
            )
            match_row = match_result.one_or_none()
            
            if match_row:
                match, score_lock = match_row
                
                # Determine original winner
                if score_lock.petitioner_total and score_lock.respondent_total:
                    if float(score_lock.petitioner_total) > float(score_lock.respondent_total):
                        original_winner = WinnerSide.PETITIONER
                    else:
                        original_winner = WinnerSide.RESPONDENT
                else:
                    original_winner = WinnerSide.PETITIONER  # Default
                
                # Determine overridden winner
                if new_winner:
                    overridden_winner = new_winner
                else:
                    # Reverse the winner
                    overridden_winner = (
                        WinnerSide.RESPONDENT if original_winner == WinnerSide.PETITIONER
                        else WinnerSide.PETITIONER
                    )
                
                # Check if override already exists
                existing_override = await db.execute(
                    select(AppealOverrideResult).where(
                        AppealOverrideResult.match_id == appeal.match_id
                    )
                )
                
                if not existing_override.scalar_one_or_none():
                    # Create override record
                    override = AppealOverrideResult(
                        id=str(uuid.uuid4()),
                        match_id=appeal.match_id,
                        original_winner=original_winner,
                        overridden_winner=overridden_winner,
                        override_reason=f"Appeal {appeal_id} decision",
                        override_hash=cls._compute_override_hash(
                            match_id=appeal.match_id,
                            original_winner=original_winner,
                            overridden_winner=overridden_winner,
                            decision_id=decision.id
                        ),
                        applied_to_rankings="N"
                    )
                    db.add(override)
        
        # Update appeal status
        appeal.status = AppealStatus.DECIDED
        appeal.decision_hash = integrity_hash
        appeal.updated_at = datetime.utcnow()
        
        await db.commit()
        
        return {
            "success": True,
            "decision_id": decision.id,
            "appeal_id": appeal_id,
            "final_action": final_action.value,
            "integrity_hash": integrity_hash,
            "message": "Decision finalized successfully"
        }
    
    @classmethod
    async def auto_close_expired(cls, db: AsyncSession) -> Dict[str, Any]:
        """
        Auto-close appeals past their review deadline.
        If deadline < now AND status != DECIDED → CLOSED
        """
        if not feature_flags.FEATURE_APPEAL_AUTO_CLOSE:
            return {"closed": 0, "message": "Auto-close is disabled"}
        
        result = await db.execute(
            select(Appeal).where(
                and_(
                    Appeal.review_deadline < datetime.utcnow(),
                    Appeal.status.notin_([AppealStatus.DECIDED, AppealStatus.CLOSED])
                )
            ).with_for_update()
        )
        
        expired_appeals = result.scalars().all()
        closed_count = 0
        
        for appeal in expired_appeals:
            appeal.status = AppealStatus.CLOSED
            appeal.updated_at = datetime.utcnow()
            closed_count += 1
        
        await db.commit()
        
        return {
            "closed": closed_count,
            "message": f"Closed {closed_count} expired appeals"
        }
    
    @classmethod
    async def get_effective_winner(cls, db: AsyncSession, match_id: str) -> Optional[str]:
        """
        Get the effective winner for a match.
        If override exists → return overridden_winner
        Else → return original winner from match_score_lock
        
        Used by Phase 16 ranking engine.
        """
        # Check for override
        override_result = await db.execute(
            select(AppealOverrideResult).where(
                AppealOverrideResult.match_id == match_id
            )
        )
        override = override_result.scalar_one_or_none()
        
        if override:
            return override.overridden_winner.value
        
        # No override, get original winner from match
        match_result = await db.execute(
            select(TournamentMatch, MatchScoreLock).join(
                MatchScoreLock,
                TournamentMatch.id == MatchScoreLock.match_id
            ).where(
                TournamentMatch.id == match_id
            )
        )
        match_row = match_result.one_or_none()
        
        if match_row:
            match, score_lock = match_row
            if score_lock.petitioner_total and score_lock.respondent_total:
                if float(score_lock.petitioner_total) > float(score_lock.respondent_total):
                    return WinnerSide.PETITIONER.value
                else:
                    return WinnerSide.RESPONDENT.value
        
        return None
    
    @classmethod
    async def get_appeal_by_match_and_team(
        cls,
        db: AsyncSession,
        match_id: str,
        team_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get appeal by match and team."""
        result = await db.execute(
            select(Appeal).where(
                and_(
                    Appeal.match_id == match_id,
                    Appeal.team_id == team_id
                )
            )
        )
        appeal = result.scalar_one_or_none()
        
        if appeal:
            return appeal.to_dict()
        return None
    
    @classmethod
    async def get_match_appeals(
        cls,
        db: AsyncSession,
        match_id: str
    ) -> List[Dict[str, Any]]:
        """Get all appeals for a match."""
        result = await db.execute(
            select(Appeal).where(
                Appeal.match_id == match_id
            ).order_by(Appeal.filed_at)
        )
        appeals = result.scalars().all()
        
        return [a.to_dict() for a in appeals]
    
    @classmethod
    async def get_appeal_with_details(
        cls,
        db: AsyncSession,
        appeal_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get appeal with reviews and decision."""
        result = await db.execute(
            select(Appeal).where(
                Appeal.id == appeal_id
            )
        )
        appeal = result.scalar_one_or_none()
        
        if not appeal:
            return None
        
        data = appeal.to_dict()
        
        # Get reviews
        reviews_result = await db.execute(
            select(AppealReview).where(
                AppealReview.appeal_id == appeal_id
            )
        )
        reviews = reviews_result.scalars().all()
        data["reviews"] = [r.to_dict() for r in reviews]
        
        # Get decision
        if appeal.decision:
            data["decision"] = appeal.decision.to_dict()
        
        return data
