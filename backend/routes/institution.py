"""
Phase 13 — Institution Routes

Institution admin API for SaaS governance.

Security Level: Maximum
Isolation Level: Hard Multi-Tenant
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from backend.database import get_db
from backend.auth import get_current_user, require_admin
from backend.core.tenant_guard import (
    require_institution_scope,
    require_role,
    require_active_institution,
    is_super_admin,
    ROLE_INSTITUTION_ADMIN,
    ROLE_FACULTY
)
from backend.services.institution_service import InstitutionService
from backend.orm.tournament_results import (
    Institution,
    InstitutionRole,
    InstitutionAuditLog
)

router = APIRouter(prefix="/institutions", tags=["institutions"])


def require_super_admin(current_user: dict = Depends(get_current_user)):
    """Dependency to require super admin."""
    if not is_super_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin access required"
        )
    return current_user


def require_institution_admin(current_user: dict = Depends(get_current_user)):
    """Dependency to require institution admin."""
    if is_super_admin(current_user):
        return current_user
    
    roles = current_user.get("roles", [])
    if ROLE_INSTITUTION_ADMIN not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Institution admin access required"
        )
    return current_user


@router.post("/")
async def create_institution(
    name: str,
    max_tournaments: int = 5,
    max_concurrent_sessions: int = 10,
    allow_audit_export: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_super_admin)
) -> Dict[str, Any]:
    """
    Create new institution.
    
    RBAC: super_admin only.
    
    Args:
        name: Institution name
        max_tournaments: Plan limit
        max_concurrent_sessions: Plan limit
        allow_audit_export: Feature flag
        
    Returns:
        Created institution details
    """
    service = InstitutionService(db)
    
    # Set SERIALIZABLE isolation for governance mutation
    await db.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
    
    try:
        institution = await service.create_institution(
            name=name,
            created_by_user_id=current_user["id"],
            max_tournaments=max_tournaments,
            max_concurrent_sessions=max_concurrent_sessions,
            allow_audit_export=allow_audit_export
        )
        
        await db.commit()
        
        return {
            "success": True,
            "institution": {
                "id": institution.id,
                "name": institution.name,
                "slug": institution.slug,
                "status": institution.status,
                "max_tournaments": institution.max_tournaments,
                "max_concurrent_sessions": institution.max_concurrent_sessions,
                "allow_audit_export": institution.allow_audit_export,
                "created_at": institution.created_at.isoformat() if institution.created_at else None
            }
        }
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/{institution_id}")
async def get_institution(
    institution_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get institution details.
    
    RBAC: institution_admin or super_admin.
    
    Args:
        institution_id: Institution ID
        
    Returns:
        Institution details
    """
    # Check scope
    if not is_super_admin(current_user):
        if current_user.get("institution_id") != institution_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Resource not found"
            )
    
    # Get institution
    result = await db.execute(
        select(Institution).where(Institution.id == institution_id)
    )
    institution = result.scalar_one_or_none()
    
    if institution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Institution not found"
        )
    
    # Get usage stats
    from backend.services.plan_enforcement_service import PlanEnforcementService
    plan_service = PlanEnforcementService(db)
    usage = await plan_service.get_usage_stats(institution_id)
    
    return {
        "id": institution.id,
        "name": institution.name,
        "slug": institution.slug,
        "status": institution.status,
        "limits": {
            "max_tournaments": institution.max_tournaments,
            "max_concurrent_sessions": institution.max_concurrent_sessions,
            "allow_audit_export": institution.allow_audit_export
        },
        "usage": usage,
        "created_at": institution.created_at.isoformat() if institution.created_at else None
    }


@router.patch("/{institution_id}/plan")
async def update_plan(
    institution_id: int,
    max_tournaments: Optional[int] = None,
    max_concurrent_sessions: Optional[int] = None,
    allow_audit_export: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_super_admin)
) -> Dict[str, Any]:
    """
    Update institution plan limits.
    
    RBAC: super_admin only.
    
    Args:
        institution_id: Institution ID
        max_tournaments: New limit
        max_concurrent_sessions: New limit
        allow_audit_export: New flag
        
    Returns:
        Updated institution details
    """
    service = InstitutionService(db)
    
    # Set SERIALIZABLE isolation
    await db.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
    
    try:
        institution = await service.update_plan_limits(
            institution_id=institution_id,
            updated_by_user_id=current_user["id"],
            max_tournaments=max_tournaments,
            max_concurrent_sessions=max_concurrent_sessions,
            allow_audit_export=allow_audit_export
        )
        
        await db.commit()
        
        return {
            "success": True,
            "institution": {
                "id": institution.id,
                "name": institution.name,
                "max_tournaments": institution.max_tournaments,
                "max_concurrent_sessions": institution.max_concurrent_sessions,
                "allow_audit_export": institution.allow_audit_export
            }
        }
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/{institution_id}/users")
async def get_institution_users(
    institution_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get all users in institution with their roles.
    
    RBAC: institution_admin or super_admin.
    
    Args:
        institution_id: Institution ID
        
    Returns:
        List of users with roles
    """
    # Check scope
    if not is_super_admin(current_user):
        if current_user.get("institution_id") != institution_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Resource not found"
            )
        
        # Check role
        await require_role(ROLE_INSTITUTION_ADMIN, current_user, db)
    
    service = InstitutionService(db)
    users = await service.get_institution_users(institution_id)
    
    return {
        "institution_id": institution_id,
        "users": users,
        "count": len(users)
    }


@router.post("/{institution_id}/assign-role")
async def assign_role(
    institution_id: int,
    user_id: int,
    role: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_institution_admin)
) -> Dict[str, Any]:
    """
    Assign role to user in institution.
    
    RBAC: institution_admin or super_admin.
    
    Args:
        institution_id: Institution ID
        user_id: User to assign role
        role: Role to assign
        
    Returns:
        Assignment details
    """
    # Check scope
    if not is_super_admin(current_user):
        if current_user.get("institution_id") != institution_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Resource not found"
            )
    
    # Check institution is active
    await require_active_institution(institution_id, db)
    
    service = InstitutionService(db)
    
    try:
        role_assignment = await service.assign_role(
            institution_id=institution_id,
            user_id=user_id,
            role=role,
            assigned_by_user_id=current_user["id"]
        )
        
        await db.commit()
        
        return {
            "success": True,
            "assignment": {
                "id": role_assignment.id,
                "user_id": role_assignment.user_id,
                "institution_id": role_assignment.institution_id,
                "role": role_assignment.role,
                "assigned_at": role_assignment.created_at.isoformat() if role_assignment.created_at else None
            }
        }
    except ValueError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/{institution_id}/users/{user_id}")
async def remove_user(
    institution_id: int,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_institution_admin)
) -> Dict[str, Any]:
    """
    Remove user from institution.
    
    RBAC: institution_admin or super_admin.
    
    Args:
        institution_id: Institution ID
        user_id: User to remove
        
    Returns:
        Removal confirmation
    """
    # Check scope
    if not is_super_admin(current_user):
        if current_user.get("institution_id") != institution_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Resource not found"
            )
    
    service = InstitutionService(db)
    
    try:
        await service.remove_user_from_institution(
            institution_id=institution_id,
            user_id=user_id,
            removed_by_user_id=current_user["id"]
        )
        
        await db.commit()
        
        return {
            "success": True,
            "message": f"User {user_id} removed from institution {institution_id}"
        }
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/{institution_id}/audit-log")
async def get_audit_log(
    institution_id: int,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_institution_admin)
) -> Dict[str, Any]:
    """
    Get institution audit log.
    
    RBAC: institution_admin or super_admin.
    
    Args:
        institution_id: Institution ID
        limit: Maximum entries
        
    Returns:
        Audit log entries
    """
    # Check scope
    if not is_super_admin(current_user):
        if current_user.get("institution_id") != institution_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Resource not found"
            )
    
    service = InstitutionService(db)
    entries = await service.get_audit_log(institution_id, limit)
    
    return {
        "institution_id": institution_id,
        "entries": [
            {
                "id": entry.id,
                "actor_user_id": entry.actor_user_id,
                "action_type": entry.action_type,
                "entity_type": entry.entity_type,
                "entity_id": entry.entity_id,
                "payload": entry.payload_json,
                "payload_hash": entry.payload_hash,
                "created_at": entry.created_at.isoformat() if entry.created_at else None
            }
            for entry in entries
        ],
        "count": len(entries)
    }


@router.post("/{institution_id}/verify-audit")
async def verify_audit_integrity(
    institution_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_institution_admin)
) -> Dict[str, Any]:
    """
    Verify institution audit log integrity.
    
    RBAC: institution_admin or super_admin.
    
    Args:
        institution_id: Institution ID
        
    Returns:
        Verification report
    """
    # Check scope
    if not is_super_admin(current_user):
        if current_user.get("institution_id") != institution_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Resource not found"
            )
    
    service = InstitutionService(db)
    result = await service.verify_audit_log_integrity(institution_id)
    
    return result
