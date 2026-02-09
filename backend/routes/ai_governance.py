"""
backend/routes/ai_governance.py
Phase 8: AI Governance, Safety & Explainability Layer Routes

Provides endpoints for:
- AI usage audit viewing
- AI policy information
- AI governance status checks
"""
import logging
from typing import Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, func

from backend.database import get_db
from backend.rbac import get_current_user
from backend.orm.user import User, UserRole
from backend.orm.ai_usage_log import AIUsageLog, AIFeatureType
from backend.services.ai_governance import AIGovernanceService, AI_ACCESS_POLICY

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai-governance", tags=["AI Governance"])


# ================= PERMISSION DECORATORS =================

async def require_admin_or_super(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 8: Only Admin and Super Admin can view AI governance audit logs.
    Faculty cannot access AI governance data.
    """
    if current_user.role not in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(
            status_code=403,
            detail="Access denied. AI governance audit requires Admin or Super Admin role."
        )
    return current_user


async def require_any_user(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 8: Any authenticated user can check AI policy info.
    """
    return current_user


# ================= SCHEMAS =================

class AIPolicyInfo(BaseModel):
    """AI policy information for a feature"""
    feature: str
    allowed_roles: list
    category: str
    advisory_only: bool
    not_evaluative: bool
    human_decision_required: bool


class AIUsageStats(BaseModel):
    """AI usage statistics"""
    total_invocations: int
    blocked_count: int
    allowed_count: int
    block_rate_percentage: float
    by_feature: dict


# ================= AI POLICY INFORMATION =================

@router.get("/policy", status_code=200)
async def get_ai_policy(
    feature: Optional[str] = Query(None, description="Specific feature to query"),
    current_user: User = Depends(require_any_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 8: Get AI governance policy information.
    
    Returns the access policy matrix showing which roles can use which AI features.
    This is for transparency and explainability.
    """
    if feature:
        # Return specific feature info
        try:
            feature_type = AIFeatureType(feature)
            policy_info = AIGovernanceService.get_feature_access_info(feature_type)
            
            # Add current user's access status
            can_access = await AIGovernanceService.can_access_feature(current_user, feature_type)
            
            return {
                "success": True,
                "feature": policy_info,
                "your_access": {
                    "role": current_user.role.value,
                    "can_access": can_access,
                    "reason": "Role permitted" if can_access else "Role not permitted for this feature"
                },
                "disclaimer": "All AI features are advisory only and not evaluative."
            }
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Unknown feature: {feature}")
    
    # Return all policies
    all_policies = {}
    for feature_type in AIFeatureType:
        all_policies[feature_type.value] = AIGovernanceService.get_feature_access_info(feature_type)
    
    return {
        "success": True,
        "policies": all_policies,
        "global_rules": {
            "faculty_blocked_from_all": True,
            "advisory_only": True,
            "not_evaluative": True,
            "human_decision_required": True,
            "content_not_logged": True,
            "prompts_not_stored": True,
            "responses_not_stored": True,
        },
        "your_role": current_user.role.value,
        "disclaimer": "All AI features are advisory only. Human decision is always required."
    }


@router.get("/can-use/{feature}", status_code=200)
async def check_ai_access(
    feature: str,
    current_user: User = Depends(require_any_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 8: Check if current user can use a specific AI feature.
    
    Returns explainability information about why access is allowed or denied.
    """
    try:
        feature_type = AIFeatureType(feature)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown feature: {feature}")
    
    can_access = await AIGovernanceService.can_access_feature(current_user, feature_type)
    
    # Get detailed reason
    _, block_reason = await AIGovernanceService.validate_ai_access(
        current_user, feature_type
    )
    
    allowed_roles = AI_ACCESS_POLICY.get(feature_type, [])
    
    return {
        "success": True,
        "feature": feature,
        "can_access": can_access,
        "reason": "Access permitted" if can_access else block_reason,
        "your_role": current_user.role.value,
        "allowed_roles": [r.value for r in allowed_roles],
        "explainability": {
            "why": "Role-based access control enforced by AI Governance Service",
            "what": feature_type.value,
            "who": f"user_id:{current_user.id},role:{current_user.role.value}",
            "category": "student_learning_assistance" if feature_type in [
                AIFeatureType.AI_COACH, AIFeatureType.AI_REVIEW, AIFeatureType.COUNTER_ARGUMENT
            ] else "judicial_support_tool",
        },
        "advisory_only": True,
        "not_evaluative": True,
        "human_decision_required": True,
    }


# ================= AI USAGE AUDIT (ADMIN/SUPER ONLY) =================

@router.get("/audit/logs", status_code=200)
async def get_ai_usage_logs(
    institution_id: Optional[int] = Query(None),
    feature: Optional[str] = Query(None),
    was_blocked: Optional[bool] = Query(None),
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_admin_or_super),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 8: View AI usage audit logs.
    
    Admin and Super Admin only.
    Faculty cannot access this endpoint.
    
    Shows WHO used AI, WHEN, and WHY.
    Does NOT show prompts or responses.
    """
    # Build query
    query = select(AIUsageLog)
    
    # Institution filtering
    if current_user.role == UserRole.ADMIN:
        # Admin can only see their own institution
        query = query.where(AIUsageLog.institution_id == current_user.institution_id)
    elif institution_id:
        # Super Admin can filter by institution
        query = query.where(AIUsageLog.institution_id == institution_id)
    
    # Feature filter
    if feature:
        try:
            feature_type = AIFeatureType(feature)
            query = query.where(AIUsageLog.feature_name == feature_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Unknown feature: {feature}")
    
    # Blocked status filter
    if was_blocked is not None:
        query = query.where(AIUsageLog.was_blocked == was_blocked)
    
    # Date range (default: last N days)
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    query = query.where(AIUsageLog.timestamp >= cutoff_date)
    
    # Order by timestamp desc
    query = query.order_by(desc(AIUsageLog.timestamp))
    
    # Pagination
    query = query.offset(offset).limit(limit)
    
    result = await db.execute(query)
    logs = [log.to_dict(include_user=True) for log in result.scalars().all()]
    
    # Get total count
    count_query = select(func.count(AIUsageLog.id))
    if current_user.role == UserRole.ADMIN:
        count_query = count_query.where(AIUsageLog.institution_id == current_user.institution_id)
    elif institution_id:
        count_query = count_query.where(AIUsageLog.institution_id == institution_id)
    if feature:
        count_query = count_query.where(AIUsageLog.feature_name == feature_type)
    if was_blocked is not None:
        count_query = count_query.where(AIUsageLog.was_blocked == was_blocked)
    count_query = count_query.where(AIUsageLog.timestamp >= cutoff_date)
    
    count_result = await db.execute(count_query)
    total_count = count_result.scalar() or 0
    
    return {
        "success": True,
        "logs": logs,
        "pagination": {
            "limit": limit,
            "offset": offset,
            "total": total_count,
            "has_more": (offset + limit) < total_count,
        },
        "filters": {
            "institution_id": institution_id if current_user.role == UserRole.SUPER_ADMIN else current_user.institution_id,
            "feature": feature,
            "was_blocked": was_blocked,
            "days": days,
        },
        "privacy_notice": "This log contains governance metadata only. No prompts or AI responses are stored.",
    }


@router.get("/audit/stats", status_code=200)
async def get_ai_usage_stats(
    institution_id: Optional[int] = Query(None),
    days: int = Query(30, ge=1, le=90),
    current_user: User = Depends(require_admin_or_super),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 8: Get AI usage statistics.
    
    Admin and Super Admin only.
    Shows aggregated usage patterns without content.
    """
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    # Base query conditions
    base_conditions = [AIUsageLog.timestamp >= cutoff_date]
    if current_user.role == UserRole.ADMIN:
        base_conditions.append(AIUsageLog.institution_id == current_user.institution_id)
    elif institution_id:
        base_conditions.append(AIUsageLog.institution_id == institution_id)
    
    # Total invocations
    total_query = select(func.count(AIUsageLog.id)).where(and_(*base_conditions))
    total_result = await db.execute(total_query)
    total_invocations = total_result.scalar() or 0
    
    # Blocked count
    blocked_conditions = base_conditions + [AIUsageLog.was_blocked == True]
    blocked_query = select(func.count(AIUsageLog.id)).where(and_(*blocked_conditions))
    blocked_result = await db.execute(blocked_query)
    blocked_count = blocked_result.scalar() or 0
    
    # By feature breakdown
    feature_stats = {}
    for feature_type in AIFeatureType:
        feature_conditions = base_conditions + [AIUsageLog.feature_name == feature_type]
        
        # Total for this feature
        feat_total_query = select(func.count(AIUsageLog.id)).where(and_(*feature_conditions))
        feat_total_result = await db.execute(feat_total_query)
        feat_total = feat_total_result.scalar() or 0
        
        # Blocked for this feature
        feat_blocked_conditions = feature_conditions + [AIUsageLog.was_blocked == True]
        feat_blocked_query = select(func.count(AIUsageLog.id)).where(and_(*feat_blocked_conditions))
        feat_blocked_result = await db.execute(feat_blocked_query)
        feat_blocked = feat_blocked_result.scalar() or 0
        
        feature_stats[feature_type.value] = {
            "total": feat_total,
            "blocked": feat_blocked,
            "allowed": feat_total - feat_blocked,
        }
    
    # Calculate block rate
    block_rate = (blocked_count / total_invocations * 100) if total_invocations > 0 else 0
    
    return {
        "success": True,
        "stats": {
            "total_invocations": total_invocations,
            "blocked_count": blocked_count,
            "allowed_count": total_invocations - blocked_count,
            "block_rate_percentage": round(block_rate, 2),
            "by_feature": feature_stats,
        },
        "period_days": days,
        "institution_id": institution_id if current_user.role == UserRole.SUPER_ADMIN else current_user.institution_id,
        "compliance_notes": [
            "All AI usage is logged for governance purposes",
            "No prompts or responses are stored",
            "Faculty are blocked from all AI features",
            "All AI features are advisory only",
        ],
    }


@router.get("/audit/blocks", status_code=200)
async def get_blocked_attempts(
    institution_id: Optional[int] = Query(None),
    days: int = Query(7, ge=1, le=30),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(require_admin_or_super),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 8: View blocked AI attempts.
    
    Useful for detecting:
    - Faculty trying to access AI
    - Students trying to access judge tools
    - Cross-institution access attempts
    """
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    # Build query
    query = select(AIUsageLog).where(
        and_(
            AIUsageLog.was_blocked == True,
            AIUsageLog.timestamp >= cutoff_date
        )
    )
    
    # Institution filtering
    if current_user.role == UserRole.ADMIN:
        query = query.where(AIUsageLog.institution_id == current_user.institution_id)
    elif institution_id:
        query = query.where(AIUsageLog.institution_id == institution_id)
    
    query = query.order_by(desc(AIUsageLog.timestamp)).limit(limit)
    
    result = await db.execute(query)
    blocked_attempts = [log.to_dict(include_user=True) for log in result.scalars().all()]
    
    # Group by block reason
    by_reason = {}
    for log in blocked_attempts:
        reason = log.get("block_reason", "Unknown")
        category = reason.split(":")[0] if ":" in reason else reason
        if category not in by_reason:
            by_reason[category] = 0
        by_reason[category] += 1
    
    return {
        "success": True,
        "blocked_attempts": blocked_attempts,
        "summary_by_reason": by_reason,
        "period_days": days,
        "alert_threshold": "Review if FACULTY_BLOCKED count is high",
    }
