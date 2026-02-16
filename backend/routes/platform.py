"""
Phase 13 — Platform Routes

Super admin API for platform-wide governance.

Security Level: Maximum
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from backend.database import get_db
from backend.auth import get_current_user
from backend.core.tenant_guard import is_super_admin
from backend.services.institution_service import InstitutionService
from backend.orm.tournament_results import (
    Institution,
    InstitutionRole,
    InstitutionAuditLog
)

router = APIRouter(prefix="/platform", tags=["platform"])


def require_super_admin(current_user: dict = Depends(get_current_user)):
    """Dependency to require super admin."""
    if not is_super_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin access required"
        )
    return current_user


@router.get("/institutions")
async def list_institutions(
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_super_admin)
) -> Dict[str, Any]:
    """
    List all institutions on platform.
    
    RBAC: super_admin only.
    
    Args:
        status: Filter by status (active, suspended, archived)
        limit: Maximum results
        offset: Pagination offset
        
    Returns:
        List of institutions
    """
    query = select(Institution)
    
    if status:
        query = query.where(Institution.status == status)
    
    # Count total
    count_result = await db.execute(
        select(func.count(Institution.id))
    )
    total = count_result.scalar() or 0
    
    # Get paginated results
    query = query.order_by(Institution.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    institutions = result.scalars().all()
    
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "institutions": [
            {
                "id": inst.id,
                "name": inst.name,
                "slug": inst.slug,
                "status": inst.status,
                "max_tournaments": inst.max_tournaments,
                "max_concurrent_sessions": inst.max_concurrent_sessions,
                "allow_audit_export": inst.allow_audit_export,
                "created_at": inst.created_at.isoformat() if inst.created_at else None
            }
            for inst in institutions
        ]
    }


@router.patch("/institutions/{institution_id}/status")
async def update_institution_status(
    institution_id: int,
    status: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_super_admin)
) -> Dict[str, Any]:
    """
    Update institution status.
    
    RBAC: super_admin only.
    
    Args:
        institution_id: Institution ID
        status: New status (active, suspended, archived)
        
    Returns:
        Updated institution details
    """
    service = InstitutionService(db)
    
    # Set SERIALIZABLE isolation
    await db.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
    
    try:
        institution = await service.update_institution_status(
            institution_id=institution_id,
            new_status=status,
            updated_by_user_id=current_user["id"]
        )
        
        await db.commit()
        
        return {
            "success": True,
            "institution": {
                "id": institution.id,
                "name": institution.name,
                "slug": institution.slug,
                "status": institution.status,
                "updated_at": datetime.utcnow().isoformat()
            }
        }
    except ValueError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/institutions/{institution_id}/force-freeze")
async def force_freeze_institution(
    institution_id: int,
    reason: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_super_admin)
) -> Dict[str, Any]:
    """
    Force freeze an institution - immediate suspension with audit.
    
    RBAC: super_admin only.
    
    Args:
        institution_id: Institution ID to freeze
        reason: Reason for freeze
        
    Returns:
        Freeze confirmation
    """
    service = InstitutionService(db)
    
    # Set SERIALIZABLE isolation
    await db.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
    
    try:
        # First change status to suspended
        institution = await service.update_institution_status(
            institution_id=institution_id,
            new_status="suspended",
            updated_by_user_id=current_user["id"]
        )
        
        # Log the force freeze action separately
        await service._log_action(
            institution_id=institution_id,
            actor_user_id=current_user["id"],
            action_type="force_freeze",
            entity_type="institution",
            entity_id=institution_id,
            payload={
                "reason": reason,
                "previous_status": institution.status,
                "frozen_by": current_user["id"],
                "frozen_at": datetime.utcnow().isoformat()
            }
        )
        
        await db.commit()
        
        return {
            "success": True,
            "message": f"Institution {institution_id} frozen",
            "reason": reason,
            "frozen_at": datetime.utcnow().isoformat()
        }
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/stats")
async def get_platform_stats(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_super_admin)
) -> Dict[str, Any]:
    """
    Get platform-wide statistics.
    
    RBAC: super_admin only.
    
    Returns:
        Platform statistics
    """
    # Institution counts by status
    status_counts = await db.execute(
        select(Institution.status, func.count(Institution.id))
        .group_by(Institution.status)
    )
    
    status_breakdown = {
        row[0]: row[1] for row in status_counts.all()
    }
    
    # Total users across all institutions
    user_count = await db.execute(
        select(func.count(InstitutionRole.user_id))
    )
    total_users = user_count.scalar() or 0
    
    # Role distribution
    role_counts = await db.execute(
        select(InstitutionRole.role, func.count(InstitutionRole.id))
        .group_by(InstitutionRole.role)
    )
    
    role_breakdown = {
        row[0]: row[1] for row in role_counts.all()
    }
    
    # Total audit log entries
    audit_count = await db.execute(
        select(func.count(InstitutionAuditLog.id))
    )
    total_audit_entries = audit_count.scalar() or 0
    
    return {
        "generated_at": datetime.utcnow().isoformat(),
        "institutions": {
            "total": sum(status_breakdown.values()),
            "by_status": status_breakdown
        },
        "users": {
            "total": total_users,
            "by_role": role_breakdown
        },
        "governance": {
            "total_audit_entries": total_audit_entries
        }
    }


@router.get("/audit-log")
async def get_platform_audit_log(
    institution_id: Optional[int] = None,
    action_type: Optional[str] = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_super_admin)
) -> Dict[str, Any]:
    """
    Get platform-wide audit log.
    
    RBAC: super_admin only.
    
    Args:
        institution_id: Filter by institution
        action_type: Filter by action type
        limit: Maximum entries
        
    Returns:
        Audit log entries
    """
    query = select(InstitutionAuditLog).order_by(InstitutionAuditLog.created_at.desc())
    
    if institution_id:
        query = query.where(InstitutionAuditLog.institution_id == institution_id)
    
    if action_type:
        query = query.where(InstitutionAuditLog.action_type == action_type)
    
    result = await db.execute(query.limit(limit))
    entries = result.scalars().all()
    
    return {
        "filters": {
            "institution_id": institution_id,
            "action_type": action_type
        },
        "entries": [
            {
                "id": entry.id,
                "institution_id": entry.institution_id,
                "actor_user_id": entry.actor_user_id,
                "action_type": entry.action_type,
                "entity_type": entry.entity_type,
                "entity_id": entry.entity_id,
                "payload_hash": entry.payload_hash,
                "created_at": entry.created_at.isoformat() if entry.created_at else None
            }
            for entry in entries
        ],
        "count": len(entries)
    }


@router.post("/verify-all-audits")
async def verify_all_institution_audits(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_super_admin)
) -> Dict[str, Any]:
    """
    Verify audit log integrity for all institutions.
    
    RBAC: super_admin only.
    
    Returns:
        Verification report for all institutions
    """
    # Get all institution IDs
    result = await db.execute(select(Institution.id))
    institution_ids = [row[0] for row in result.all()]
    
    service = InstitutionService(db)
    
    reports = []
    total_valid = 0
    total_invalid = 0
    
    for inst_id in institution_ids:
        report = await service.verify_audit_log_integrity(inst_id)
        reports.append(report)
        
        if report["valid"]:
            total_valid += 1
        else:
            total_invalid += 1
    
    return {
        "generated_at": datetime.utcnow().isoformat(),
        "summary": {
            "total_institutions": len(institution_ids),
            "valid": total_valid,
            "invalid": total_invalid
        },
        "institutions": reports
    }
