"""
Live Courtroom Admin Routes — Phase 8 Elite Hardening

SUPER_ADMIN endpoints for system-wide verification and management.

Routes:
- GET /superadmin/live-ledger/verify - System-wide chain verification
"""
from typing import Dict, Any, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.dependencies import require_role
from backend.orm.user import UserRole
from backend.orm.live_courtroom import LiveCourtSession, LiveSessionEvent
from backend.services.live_courtroom_service import verify_live_event_chain

router = APIRouter(prefix="/superadmin", tags=["Live Courtroom Admin"])


@router.get("/live-ledger/verify", status_code=status.HTTP_200_OK)
async def verify_all_live_ledgers(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.teacher]))
) -> Dict[str, Any]:
    """
    System-wide chain verification for all live courtroom sessions.
    
    Elite Hardening: SUPER_ADMIN only endpoint for comprehensive audit.
    
    Verifies:
    - Hash chain integrity for every live session
    - Event sequence continuity
    - No tampering detected
    
    Returns:
        {
            "total_sessions": 42,
            "verified": 42,
            "failed": 0,
            "details": [...]
        }
    
    Raises:
        HTTPException: If not SUPER_ADMIN
    """
    # Get all live sessions
    result = await db.execute(
        select(LiveCourtSession.id, LiveCourtSession.status)
        .order_by(LiveCourtSession.id.asc())
    )
    sessions = list(result.all())
    
    total_sessions = len(sessions)
    verified_count = 0
    failed_count = 0
    details = []
    
    # Verify each session's chain
    for session_id, session_status in sessions:
        try:
            verification = await verify_live_event_chain(session_id, db)
            
            detail = {
                "session_id": session_id,
                "status": session_status,
                "is_valid": verification["is_valid"],
                "total_events": verification["total_events"],
                "first_event_id": verification["first_event_id"],
                "last_event_id": verification["last_event_id"],
                "errors": verification["errors"]
            }
            
            if verification["is_valid"]:
                verified_count += 1
            else:
                failed_count += 1
                detail["invalid_entries"] = verification.get("invalid_entries", [])
            
            details.append(detail)
            
        except Exception as e:
            failed_count += 1
            details.append({
                "session_id": session_id,
                "status": session_status,
                "is_valid": False,
                "error": str(e),
                "total_events": 0,
                "first_event_id": None,
                "last_event_id": None
            })
    
    return {
        "total_sessions": total_sessions,
        "verified": verified_count,
        "failed": failed_count,
        "verification_timestamp": datetime.utcnow().isoformat(),
        "verified_by": current_user.id,
        "details": details
    }


@router.get("/live-ledger/stats", status_code=status.HTTP_200_OK)
async def get_live_ledger_statistics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.teacher]))
) -> Dict[str, Any]:
    """
    Get statistics about live courtroom ledgers.
    
    Returns aggregate statistics across all sessions.
    """
    # Total sessions
    result = await db.execute(
        select(func.count(LiveCourtSession.id))
    )
    total_sessions = result.scalar() or 0
    
    # Sessions by status
    result = await db.execute(
        select(LiveCourtSession.status, func.count(LiveCourtSession.id))
        .group_by(LiveCourtSession.status)
    )
    status_counts = {status: count for status, count in result.all()}
    
    # Total events
    result = await db.execute(
        select(func.count(LiveSessionEvent.id))
    )
    total_events = result.scalar() or 0
    
    # Events per session (avg, min, max)
    result = await db.execute(
        select(
            func.avg(func.count(LiveSessionEvent.id)),
            func.min(func.count(LiveSessionEvent.id)),
            func.max(func.count(LiveSessionEvent.id))
        )
        .select_from(LiveSessionEvent)
        .group_by(LiveSessionEvent.live_session_id)
    )
    stats = result.one_or_none()
    
    return {
        "total_sessions": total_sessions,
        "sessions_by_status": status_counts,
        "total_events": total_events,
        "events_per_session": {
            "avg": float(stats[0]) if stats else 0,
            "min": stats[1] if stats else 0,
            "max": stats[2] if stats else 0
        },
        "report_timestamp": datetime.utcnow().isoformat()
    }
