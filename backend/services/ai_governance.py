"""
backend/services/ai_governance.py
Phase 8: AI Governance, Safety & Explainability Layer

Central governance service for ALL AI invocations in Juris AI.
Enforces role-based access, project state checks, and mandatory safety headers.
NO AI endpoint may bypass this layer.
"""
import logging
from typing import Dict, Any, Optional, Tuple
from datetime import datetime
from enum import Enum
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from backend.orm.user import User, UserRole
from backend.orm.moot_project import MootProject
from backend.orm.ai_usage_log import AIUsageLog, AIFeatureType

logger = logging.getLogger(__name__)


class AIGovernanceError(Exception):
    """Raised when AI governance check fails"""
    def __init__(self, reason: str, code: str = "GOVERNANCE_DENIED"):
        self.reason = reason
        self.code = code
        super().__init__(f"AI Governance Blocked: {reason}")


# AI ACCESS POLICY MATRIX (Hard-coded, non-negotiable)
# Faculty is BLOCKED from ALL AI features
AI_ACCESS_POLICY = {
    # Student AI Tools
    AIFeatureType.AI_COACH: [UserRole.STUDENT],
    AIFeatureType.AI_REVIEW: [UserRole.STUDENT],
    AIFeatureType.COUNTER_ARGUMENT: [UserRole.STUDENT],
    
    # Judge AI Tools
    AIFeatureType.JUDGE_ASSIST: [UserRole.JUDGE, UserRole.ADMIN, UserRole.SUPER_ADMIN],
    AIFeatureType.BENCH_QUESTIONS: [UserRole.JUDGE, UserRole.ADMIN, UserRole.SUPER_ADMIN],
    AIFeatureType.FEEDBACK_SUGGEST: [UserRole.JUDGE, UserRole.ADMIN, UserRole.SUPER_ADMIN],
}


@dataclass
class AIGovernanceResult:
    """Result of AI governance check and invocation"""
    allowed: bool
    feature: AIFeatureType
    advisory_only: bool
    not_evaluative: bool
    human_decision_required: bool
    metadata: Dict[str, Any]
    response_data: Optional[Any] = None
    block_reason: Optional[str] = None
    log_id: Optional[int] = None


class AIGovernanceService:
    """
    Phase 8: Central AI Governance Service
    
    ALL AI calls MUST route through this service.
    
    Responsibilities:
    1. Validate user role is allowed for the AI tool
    2. Validate project state (locks, deadlines)
    3. Validate institution context
    4. Attach mandatory safety headers/metadata
    5. Log AI usage (governance logging, not content logging)
    6. Return AI output with disclaimer metadata
    """
    
    @staticmethod
    async def validate_ai_access(
        user: User,
        feature: AIFeatureType,
        project: Optional[MootProject] = None,
        purpose: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate if user can access the AI feature.
        
        Returns: (is_allowed, block_reason)
        """
        # Check 1: Role-based access
        allowed_roles = AI_ACCESS_POLICY.get(feature, [])
        if user.role not in allowed_roles:
            if user.role == UserRole.FACULTY:
                return False, f"FACULTY_BLOCKED: Faculty are prohibited from using AI features"
            return False, f"ROLE_DENIED: {user.role.value} cannot use {feature.value}"
        
        # Check 2: Faculty absolute block (double-check)
        if user.role == UserRole.FACULTY:
            return False, "FACULTY_ABSOLUTE_BLOCK: Faculty cannot invoke any AI tools"
        
        # Check 3: Project state (if applicable)
        if project:
            # Phase 5D: Locked projects block AI
            if project.is_locked:
                return False, "PROJECT_LOCKED: AI access blocked for locked projects"
            
            # Phase 6B: Institution mismatch
            if user.institution_id != project.institution_id:
                return False, "INSTITUTION_MISMATCH: Cross-institution AI access denied"
            
            # Deadline check (optional, configurable)
            if hasattr(project, 'deadline') and project.deadline:
                if project.deadline < datetime.utcnow():
                    # Allow judges after deadline, not students
                    if user.role == UserRole.STUDENT:
                        return False, "DEADLINE_PASSED: AI access blocked after deadline for students"
        
        # Check 4: Institution context
        if not user.institution_id:
            return False, "NO_INSTITUTION: User must belong to an institution"
        
        return True, None
    
    @staticmethod
    async def invoke_ai(
        db: AsyncSession,
        user: User,
        feature: AIFeatureType,
        ai_callback: callable,
        project: Optional[MootProject] = None,
        purpose: Optional[str] = None,
        ip_address: Optional[str] = None,
        **ai_kwargs
    ) -> AIGovernanceResult:
        """
        Central AI invocation method.
        
        ALL AI calls MUST use this method.
        
        Args:
            db: Database session
            user: User invoking AI
            feature: Which AI feature
            ai_callback: The actual AI function to call
            project: Optional project context
            purpose: High-level purpose description
            ip_address: Client IP for logging
            **ai_kwargs: Arguments to pass to ai_callback
        
        Returns:
            AIGovernanceResult with metadata and AI response
        """
        # Step 1: Validate access
        is_allowed, block_reason = await AIGovernanceService.validate_ai_access(
            user, feature, project, purpose
        )
        
        # Step 2: Log the attempt (allowed or blocked)
        log_entry = await AIGovernanceService._log_ai_usage(
            db=db,
            user=user,
            feature=feature,
            project=project,
            purpose=purpose,
            ip_address=ip_address,
            was_blocked=not is_allowed,
            block_reason=block_reason if not is_allowed else None
        )
        
        # Step 3: If blocked, return blocked result
        if not is_allowed:
            logger.warning(f"AI {feature.value} blocked for user {user.id}: {block_reason}")
            return AIGovernanceResult(
                allowed=False,
                feature=feature,
                advisory_only=True,
                not_evaluative=True,
                human_decision_required=True,
                metadata={
                    "reason": block_reason,
                    "role": user.role.value,
                    "timestamp": datetime.utcnow().isoformat(),
                },
                block_reason=block_reason,
                log_id=log_entry.id if log_entry else None
            )
        
        # Step 4: Attach mandatory safety metadata to AI call
        safety_metadata = {
            "advisory_only": True,
            "not_evaluative": True,
            "human_decision_required": True,
            "role": user.role.value,
            "feature": feature.value,
            "institution_id": user.institution_id,
            "governance_version": "phase8",
        }
        
        # Merge safety metadata into AI kwargs
        ai_kwargs['_governance_metadata'] = safety_metadata
        
        # Step 5: Invoke the actual AI
        try:
            ai_response = await ai_callback(**ai_kwargs)
            
            # Step 6: Return governed result
            return AIGovernanceResult(
                allowed=True,
                feature=feature,
                advisory_only=True,
                not_evaluative=True,
                human_decision_required=True,
                metadata={
                    "role": user.role.value,
                    "feature": feature.value,
                    "institution_id": user.institution_id,
                    "purpose": purpose,
                    "timestamp": datetime.utcnow().isoformat(),
                    "explainability": {
                        "why_allowed": f"Role {user.role.value} is permitted for {feature.value}",
                        "what_category": _get_feature_category(feature),
                        "who_invoked": f"user_id:{user.id},role:{user.role.value}",
                    }
                },
                response_data=ai_response,
                log_id=log_entry.id if log_entry else None
            )
            
        except Exception as e:
            logger.error(f"AI invocation failed for {feature.value}: {e}")
            # Log the failure
            await AIGovernanceService._log_ai_usage(
                db=db,
                user=user,
                feature=feature,
                project=project,
                purpose=f"{purpose} [FAILED: {str(e)}]" if purpose else f"[FAILED: {str(e)}]",
                ip_address=ip_address,
                was_blocked=True,
                block_reason=f"AI_INVOCATION_ERROR: {str(e)}"
            )
            
            raise AIGovernanceError(f"AI invocation failed: {str(e)}", "AI_ERROR")
    
    @staticmethod
    async def _log_ai_usage(
        db: AsyncSession,
        user: User,
        feature: AIFeatureType,
        project: Optional[MootProject],
        purpose: Optional[str],
        ip_address: Optional[str],
        was_blocked: bool,
        block_reason: Optional[str] = None
    ) -> Optional[AIUsageLog]:
        """
        Log AI usage for governance auditing.
        
        Does NOT log prompts or responses.
        Only logs: who, when, what feature, and why.
        """
        try:
            log_entry = AIUsageLog(
                institution_id=user.institution_id,
                user_id=user.id,
                role_at_time=user.role.value if user.role else "unknown",
                project_id=project.id if project else None,
                feature_name=feature,
                purpose=purpose[:255] if purpose else None,  # Truncate if too long
                ip_address=ip_address,
                was_blocked=was_blocked,
                block_reason=block_reason[:255] if block_reason else None,
                advisory_only_enforced=True,
                not_evaluative_enforced=True,
                human_decision_required_enforced=True,
            )
            
            db.add(log_entry)
            await db.commit()
            await db.refresh(log_entry)
            
            logger.debug(f"AI usage logged: {feature.value}, blocked={was_blocked}, user={user.id}")
            
            return log_entry
            
        except Exception as e:
            # Logging failure should not block the AI call
            logger.error(f"Failed to log AI usage: {e}")
            return None
    
    @staticmethod
    def get_feature_access_info(feature: AIFeatureType) -> Dict[str, Any]:
        """
        Get information about which roles can access a feature.
        Used for explainability and documentation.
        """
        allowed_roles = AI_ACCESS_POLICY.get(feature, [])
        return {
            "feature": feature.value,
            "allowed_roles": [r.value for r in allowed_roles],
            "category": _get_feature_category(feature),
            "advisory_only": True,
            "not_evaluative": True,
            "human_decision_required": True,
        }
    
    @staticmethod
    async def can_access_feature(user: User, feature: AIFeatureType) -> bool:
        """Quick check if user can access a feature (no logging)"""
        is_allowed, _ = await AIGovernanceService.validate_ai_access(user, feature)
        return is_allowed


def _get_feature_category(feature: AIFeatureType) -> str:
    """Categorize AI feature for explainability"""
    student_tools = [AIFeatureType.AI_COACH, AIFeatureType.AI_REVIEW, AIFeatureType.COUNTER_ARGUMENT]
    judge_tools = [AIFeatureType.JUDGE_ASSIST, AIFeatureType.BENCH_QUESTIONS, AIFeatureType.FEEDBACK_SUGGEST]
    
    if feature in student_tools:
        return "student_learning_assistance"
    elif feature in judge_tools:
        return "judicial_support_tool"
    return "unknown"


# Convenience decorator for AI endpoints
import functools

def ai_governed(feature: AIFeatureType, purpose_template: Optional[str] = None):
    """
    Decorator to apply AI governance to an endpoint.
    
    Usage:
        @router.post("/ai-coach")
        @ai_governed(AIFeatureType.AI_COACH, purpose_template="Student coaching for {project_id}")
        async def ai_coach_endpoint(...):
            # Actual AI logic here
            pass
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Governance will be applied at route level
            # This decorator marks the endpoint for documentation/auditing
            kwargs['_ai_governance'] = {
                "feature": feature,
                "purpose_template": purpose_template,
                "governed": True,
            }
            return await func(*args, **kwargs)
        return wrapper
    return decorator
