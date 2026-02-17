"""
Phase 13 — Plan Enforcement Service

Hard multi-tenant plan limits and quota enforcement.

Security Level: Maximum
Determinism: Mandatory
"""
from datetime import datetime
from typing import Dict, Any
from decimal import Decimal

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.orm.institution import Institution


# Plan Limit Exceptions
class PlanLimitExceededError(Exception):
    """Raised when plan limit would be exceeded."""
    
    def __init__(self, limit_type: str, current: int, maximum: int):
        self.limit_type = limit_type
        self.current = current
        self.maximum = maximum
        super().__init__(
            f"Plan limit exceeded: {limit_type} ({current}/{maximum})"
        )


class PlanEnforcementService:
    """
    Service for enforcing SaaS plan limits.
    
    All methods must be deterministic and use SERIALIZABLE isolation
    when modifying institution plan limits.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def enforce_tournament_limit(self, institution_id: int) -> None:
        """
        Enforce tournament count limit.
        
        Rules:
        - SELECT COUNT(*) FROM national_tournaments WHERE institution_id = :id
        - If count >= max_tournaments → raise PlanLimitExceededError
        - Lock institution row FOR UPDATE when checking
        
        Args:
            institution_id: Institution to check
            
        Raises:
            PlanLimitExceededError: If limit would be exceeded
        """
        # Lock institution row
        result = await self.db.execute(
            select(Institution).where(
                Institution.id == institution_id
            ).with_for_update()
        )
        institution = result.scalar_one_or_none()
        
        if institution is None:
            raise ValueError(f"Institution {institution_id} not found")
        
        # Count tournaments (deterministic)
        from backend.orm.national_network import NationalTournament
        
        count_result = await self.db.execute(
            select(func.count(NationalTournament.id)).where(
                NationalTournament.institution_id == institution_id
            )
        )
        current_count = count_result.scalar() or 0
        
        max_tournaments = institution.max_tournaments
        
        # Use Decimal for deterministic comparison
        current_d = Decimal(str(current_count))
        max_d = Decimal(str(max_tournaments))
        
        if current_d >= max_d:
            raise PlanLimitExceededError(
                "tournaments",
                int(current_count),
                max_tournaments
            )
    
    async def enforce_concurrent_sessions_limit(self, institution_id: int) -> None:
        """
        Enforce concurrent live sessions limit.
        
        Rules:
        - Count live sessions where status IN ('live', 'paused')
        - Compare with max_concurrent_sessions
        
        Args:
            institution_id: Institution to check
            
        Raises:
            PlanLimitExceededError: If limit would be exceeded
        """
        # Lock institution row
        result = await self.db.execute(
            select(Institution).where(
                Institution.id == institution_id
            ).with_for_update()
        )
        institution = result.scalar_one_or_none()
        
        if institution is None:
            raise ValueError(f"Institution {institution_id} not found")
        
        # Count live/paused sessions
        from backend.orm.tournament_results import LiveSession
        
        count_result = await self.db.execute(
            select(func.count(LiveSession.id)).where(
                and_(
                    LiveSession.institution_id == institution_id,
                    LiveSession.status.in_(["live", "paused"])
                )
            )
        )
        current_count = count_result.scalar() or 0
        
        max_sessions = institution.max_concurrent_sessions
        
        # Use Decimal for deterministic comparison
        current_d = Decimal(str(current_count))
        max_d = Decimal(str(max_sessions))
        
        if current_d >= max_d:
            raise PlanLimitExceededError(
                "concurrent_sessions",
                int(current_count),
                max_sessions
            )
    
    async def enforce_audit_export_permission(self, institution_id: int) -> None:
        """
        Enforce audit export permission.
        
        Rules:
        - Check allow_audit_export flag
        - If False → raise PermissionError
        
        Args:
            institution_id: Institution to check
            
        Raises:
            PermissionError: If export not allowed
        """
        result = await self.db.execute(
            select(Institution).where(Institution.id == institution_id)
        )
        institution = result.scalar_one_or_none()
        
        if institution is None:
            raise ValueError(f"Institution {institution_id} not found")
        
        if not institution.allow_audit_export:
            raise PermissionError(
                f"Audit export not allowed for institution {institution_id}"
            )
    
    async def get_usage_stats(self, institution_id: int) -> Dict[str, Any]:
        """
        Get current usage statistics for institution.
        
        Args:
            institution_id: Institution to check
            
        Returns:
            Usage statistics dictionary
        """
        result = await self.db.execute(
            select(Institution).where(Institution.id == institution_id)
        )
        institution = result.scalar_one_or_none()
        
        if institution is None:
            raise ValueError(f"Institution {institution_id} not found")
        
        # Count tournaments
        from backend.orm.tournament_results import NationalTournament
        
        tournament_count = await self.db.execute(
            select(func.count(NationalTournament.id)).where(
                NationalTournament.institution_id == institution_id
            )
        )
        tournaments_used = tournament_count.scalar() or 0
        
        # Count concurrent sessions
        from backend.orm.tournament_results import LiveSession
        
        session_count = await self.db.execute(
            select(func.count(LiveSession.id)).where(
                and_(
                    LiveSession.institution_id == institution_id,
                    LiveSession.status.in_(["live", "paused"])
                )
            )
        )
        sessions_used = session_count.scalar() or 0
        
        # Calculate percentages (as Decimal for precision)
        tournaments_pct = Decimal(str(tournaments_used)) / Decimal(str(institution.max_tournaments)) * Decimal("100")
        sessions_pct = Decimal(str(sessions_used)) / Decimal(str(institution.max_concurrent_sessions)) * Decimal("100")
        
        return {
            "institution_id": institution_id,
            "institution_name": institution.name,
            "status": institution.status,
            "tournaments": {
                "used": int(tournaments_used),
                "limit": institution.max_tournaments,
                "remaining": max(0, institution.max_tournaments - int(tournaments_used)),
                "percentage": f"{tournaments_pct:.1f}"
            },
            "concurrent_sessions": {
                "used": int(sessions_used),
                "limit": institution.max_concurrent_sessions,
                "remaining": max(0, institution.max_concurrent_sessions - int(sessions_used)),
                "percentage": f"{sessions_pct:.1f}"
            },
            "audit_export_allowed": institution.allow_audit_export,
            "checked_at": datetime.utcnow().isoformat()
        }
    
    async def check_all_limits(self, institution_id: int) -> Dict[str, bool]:
        """
        Check all plan limits without raising exceptions.
        
        Args:
            institution_id: Institution to check
            
        Returns:
            Dictionary of limit name → within_limit boolean
        """
        results = {}
        
        # Check tournament limit
        try:
            await self.enforce_tournament_limit(institution_id)
            results["tournaments"] = True
        except PlanLimitExceededError:
            results["tournaments"] = False
        
        # Check session limit
        try:
            await self.enforce_concurrent_sessions_limit(institution_id)
            results["concurrent_sessions"] = True
        except PlanLimitExceededError:
            results["concurrent_sessions"] = False
        
        # Check audit export permission
        try:
            await self.enforce_audit_export_permission(institution_id)
            results["audit_export"] = True
        except PermissionError:
            results["audit_export"] = False
        
        return results
    
    async def can_create_tournament(self, institution_id: int) -> bool:
        """
        Check if tournament can be created without raising.
        
        Args:
            institution_id: Institution to check
            
        Returns:
            True if tournament can be created
        """
        try:
            await self.enforce_tournament_limit(institution_id)
            return True
        except PlanLimitExceededError:
            return False
    
    async def can_start_session(self, institution_id: int) -> bool:
        """
        Check if live session can be started without raising.
        
        Args:
            institution_id: Institution to check
            
        Returns:
            True if session can be started
        """
        try:
            await self.enforce_concurrent_sessions_limit(institution_id)
            return True
        except PlanLimitExceededError:
            return False


async def check_plan_limits_before_mutation(
    institution_id: int,
    mutation_type: str,
    db: AsyncSession
) -> None:
    """
    Pre-mutation plan limit check helper.
    
    Call this before any mutation that consumes plan resources.
    
    Args:
        institution_id: Institution performing mutation
        mutation_type: Type of mutation ("create_tournament", "start_session", etc.)
        db: Database session
        
    Raises:
        PlanLimitExceededError: If limit would be exceeded
        ValueError: If mutation_type unknown
    """
    service = PlanEnforcementService(db)
    
    if mutation_type == "create_tournament":
        await service.enforce_tournament_limit(institution_id)
    elif mutation_type == "start_session":
        await service.enforce_concurrent_sessions_limit(institution_id)
    elif mutation_type == "audit_export":
        await service.enforce_audit_export_permission(institution_id)
    else:
        raise ValueError(f"Unknown mutation type: {mutation_type}")
