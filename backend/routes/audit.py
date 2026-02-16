"""
Phase 10 — Audit Routes

HTTP endpoints for audit log access and security monitoring.
Admin-only access to sensitive audit data.
"""
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc

from backend.database import get_db
from backend.auth import require_admin, get_current_user
from backend.security.audit_logger import AuditLogEntry, AuditLogger

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/logs")
async def get_audit_logs(
    user_id: Optional[int] = Query(None, description="Filter by user ID"),
    institution_id: Optional[int] = Query(None, description="Filter by institution ID"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    event_category: Optional[str] = Query(None, description="Filter by event category"),
    start_time: Optional[datetime] = Query(None, description="Start time filter"),
    end_time: Optional[datetime] = Query(None, description="End time filter"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin)
) -> List[Dict[str, Any]]:
    """
    Get audit logs with filtering.
    
    RBAC: ADMIN only.
    
    Returns:
        List of audit log entries
    """
    # Build query
    query = select(AuditLogEntry)
    
    if user_id:
        query = query.where(AuditLogEntry.user_id == user_id)
    
    if institution_id:
        query = query.where(AuditLogEntry.institution_id == institution_id)
    
    if event_type:
        query = query.where(AuditLogEntry.event_type == event_type)
    
    if event_category:
        query = query.where(AuditLogEntry.event_category == event_category)
    
    if start_time:
        query = query.where(AuditLogEntry.timestamp >= start_time)
    
    if end_time:
        query = query.where(AuditLogEntry.timestamp <= end_time)
    
    # Sort by timestamp descending
    query = query.order_by(desc(AuditLogEntry.timestamp)).limit(limit)
    
    result = await db.execute(query)
    entries = result.scalars().all()
    
    # Serialize
    return [
        {
            "id": entry.id,
            "request_id": entry.request_id,
            "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
            "user_id": entry.user_id,
            "institution_id": entry.institution_id,
            "method": entry.method,
            "path": entry.path,
            "client_ip": entry.client_ip,
            "user_agent": entry.user_agent,
            "status_code": entry.status_code,
            "duration_ms": entry.duration_ms,
            "event_type": entry.event_type,
            "event_category": entry.event_category,
            "details_json": entry.details_json,
            "entry_hash": entry.entry_hash,
        }
        for entry in entries
    ]


@router.get("/logs/verify")
async def verify_audit_chain(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Verify audit log chain integrity.
    
    Checks cryptographic hashes and chain links.
    
    RBAC: ADMIN only.
    
    Returns:
        Verification report
    """
    logger = AuditLogger(db)
    result = await logger.verify_chain_integrity()
    
    return result


@router.get("/logs/security-events")
async def get_security_events(
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin)
) -> List[Dict[str, Any]]:
    """
    Get security-related audit events.
    
    RBAC: ADMIN only.
    
    Returns:
        List of security events
    """
    if not start_time:
        start_time = datetime.utcnow() - timedelta(days=7)
    
    if not end_time:
        end_time = datetime.utcnow()
    
    result = await db.execute(
        select(AuditLogEntry)
        .where(
            and_(
                AuditLogEntry.event_type == "SECURITY_EVENT",
                AuditLogEntry.timestamp >= start_time,
                AuditLogEntry.timestamp <= end_time
            )
        )
        .order_by(desc(AuditLogEntry.timestamp))
        .limit(limit)
    )
    
    entries = result.scalars().all()
    
    return [
        {
            "id": entry.id,
            "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
            "event_type": entry.event_type,
            "event_category": entry.event_category,
            "client_ip": entry.client_ip,
            "path": entry.path,
            "details": entry.details_json,
            "entry_hash": entry.entry_hash,
        }
        for entry in entries
    ]


@router.get("/logs/user/{user_id}")
async def get_user_audit_logs(
    user_id: int,
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin)
) -> List[Dict[str, Any]]:
    """
    Get audit logs for specific user.
    
    RBAC: ADMIN only.
    
    Returns:
        List of user's audit log entries
    """
    result = await db.execute(
        select(AuditLogEntry)
        .where(AuditLogEntry.user_id == user_id)
        .order_by(desc(AuditLogEntry.timestamp))
        .limit(limit)
    )
    
    entries = result.scalars().all()
    
    return [
        {
            "id": entry.id,
            "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
            "method": entry.method,
            "path": entry.path,
            "status_code": entry.status_code,
            "event_type": entry.event_type,
            "details": entry.details_json,
        }
        for entry in entries
    ]


@router.get("/stats")
async def get_audit_stats(
    days: int = Query(7, ge=1, le=30, description="Number of days to analyze"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Get audit log statistics.
    
    RBAC: ADMIN only.
    
    Returns:
        Statistics summary
    """
    from sqlalchemy import func
    
    start_time = datetime.utcnow() - timedelta(days=days)
    
    # Total entries
    total_result = await db.execute(
        select(func.count(AuditLogEntry.id))
        .where(AuditLogEntry.timestamp >= start_time)
    )
    total_entries = total_result.scalar()
    
    # Entries by event type
    type_result = await db.execute(
        select(AuditLogEntry.event_type, func.count(AuditLogEntry.id))
        .where(AuditLogEntry.timestamp >= start_time)
        .group_by(AuditLogEntry.event_type)
    )
    entries_by_type = {row[0]: row[1] for row in type_result.all()}
    
    # Security events
    security_result = await db.execute(
        select(func.count(AuditLogEntry.id))
        .where(
            and_(
                AuditLogEntry.event_type == "SECURITY_EVENT",
                AuditLogEntry.timestamp >= start_time
            )
        )
    )
    security_count = security_result.scalar()
    
    # Unique users
    users_result = await db.execute(
        select(func.count(func.distinct(AuditLogEntry.user_id)))
        .where(AuditLogEntry.timestamp >= start_time)
    )
    unique_users = users_result.scalar()
    
    # Unique IPs
    ips_result = await db.execute(
        select(func.count(func.distinct(AuditLogEntry.client_ip)))
        .where(AuditLogEntry.timestamp >= start_time)
    )
    unique_ips = ips_result.scalar()
    
    return {
        "period_days": days,
        "total_entries": total_entries,
        "entries_by_type": entries_by_type,
        "security_events": security_count,
        "unique_users": unique_users,
        "unique_ips": unique_ips,
        "generated_at": datetime.utcnow().isoformat()
    }


# =============================================================================
# Phase 12 — Tournament Compliance & Audit Ledger
# =============================================================================

from backend.services.audit_service import (
    generate_tournament_audit_snapshot,
    verify_audit_snapshot
)
from backend.services.audit_export_service import export_tournament_bundle
from backend.services.certificate_service import (
    generate_tournament_certificate,
    verify_certificate,
    format_certificate_text
)
from backend.orm.tournament_results import TournamentAuditSnapshot


@router.post("/tournaments/{tournament_id}/snapshot")
async def create_tournament_snapshot(
    tournament_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Generate audit snapshot for tournament.
    
    Creates immutable Merkle root of all tournament data.
    Idempotent: returns existing snapshot if already created.
    
    RBAC: ADMIN, HOD only.
    
    Args:
        tournament_id: Tournament ID to snapshot
        
    Returns:
        Snapshot details with audit root hash
    """
    try:
        result = await generate_tournament_audit_snapshot(
            tournament_id=tournament_id,
            user_id=current_user["id"],
            db=db
        )
        
        return {
            "success": True,
            "tournament_id": result["tournament_id"],
            "snapshot_id": result["snapshot_id"],
            "audit_root_hash": result["audit_root_hash"],
            "signature_hmac": result["signature_hmac"],
            "is_new": result["is_new"]
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/tournaments/{tournament_id}/verify")
async def verify_tournament_snapshot(
    tournament_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Verify tournament audit snapshot integrity.
    
    Recomputes all component hashes and compares with stored values.
    Detects any tampering of tournament data.
    
    RBAC: ADMIN, HOD, FACULTY allowed.
    
    Args:
        tournament_id: Tournament ID to verify
        
    Returns:
        Verification report with tamper detection status
    """
    result = await verify_audit_snapshot(tournament_id, db)
    
    return result


@router.get("/tournaments/{tournament_id}/export")
async def export_tournament_audit_bundle(
    tournament_id: int,
    include_events: bool = Query(True, description="Include live session events"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Export complete tournament audit bundle as ZIP.
    
    Bundle contains all tournament data with cryptographic verification.
    
    RBAC: ADMIN, HOD only.
    
    Args:
        tournament_id: Tournament ID to export
        include_events: Whether to include live session events
        
    Returns:
        Export metadata with download URL
    """
    try:
        # Generate bundle
        bundle_bytes = await export_tournament_bundle(
            tournament_id=tournament_id,
            db=db,
            include_events=include_events
        )
        
        # Get snapshot info
        snapshot = await db.execute(
            select(TournamentAuditSnapshot)
            .where(TournamentAuditSnapshot.tournament_id == tournament_id)
        )
        snapshot = snapshot.scalar_one_or_none()
        
        # Store bundle (in production, save to S3 or similar)
        # For now, return metadata
        return {
            "success": True,
            "tournament_id": tournament_id,
            "bundle_size_bytes": len(bundle_bytes),
            "audit_root_hash": snapshot.audit_root_hash if snapshot else None,
            "signature": snapshot.signature_hmac if snapshot else None,
            "filename": f"tournament_{tournament_id}_audit_bundle.zip",
            "download_url": f"/audit/tournaments/{tournament_id}/download"
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.get("/tournaments/{tournament_id}/certificate")
async def get_tournament_certificate(
    tournament_id: int,
    format: str = Query("json", description="Output format: json or text"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Generate tournament completion certificate.
    
    Cryptographically signed certificate with winner details.
    
    RBAC: ADMIN, HOD, FACULTY allowed.
    
    Args:
        tournament_id: Tournament ID
        format: Output format (json or text)
        
    Returns:
        Certificate data
    """
    try:
        certificate = await generate_tournament_certificate(tournament_id, db)
        
        if format == "text":
            return {
                "format": "text",
                "content": format_certificate_text(certificate)
            }
        
        return {
            "format": "json",
            "certificate": certificate
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.post("/tournaments/{tournament_id}/certificate/verify")
async def verify_tournament_certificate(
    tournament_id: int,
    certificate: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Verify tournament certificate authenticity.
    
    Checks signature and audit root hash.
    
    RBAC: ADMIN, HOD, FACULTY allowed.
    
    Args:
        tournament_id: Tournament ID
        certificate: Certificate to verify
        
    Returns:
        Verification result
    """
    # Get expected root hash from snapshot
    snapshot = await db.execute(
        select(TournamentAuditSnapshot)
        .where(TournamentAuditSnapshot.tournament_id == tournament_id)
    )
    snapshot = snapshot.scalar_one_or_none()
    
    if not snapshot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No audit snapshot found for tournament"
        )
    
    result = await verify_certificate(
        certificate,
        expected_root_hash=snapshot.audit_root_hash
    )
    
    return result
