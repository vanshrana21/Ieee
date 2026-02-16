"""
Phase 6 — Objection & Procedural Control HTTP Routes

Server-authoritative with:
- Institution scoping
- RBAC enforcement
- No client trust
- Deterministic responses
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.dependencies import get_current_user, require_role
from backend.orm.user import User, UserRole
from backend.orm.live_court import (
    LiveCourtSession, LiveTurn, LiveCourtStatus, LiveTurnState
)
from backend.orm.live_objection import (
    LiveObjection, ObjectionType, ObjectionState, ProceduralViolation
)
from backend.services.live_objection_service import (
    raise_objection, rule_objection, record_procedural_violation,
    get_objections_by_session, get_objections_by_turn,
    get_pending_objection_for_turn,
    ObjectionNotFoundError, ObjectionAlreadyRuledError,
    ObjectionAlreadyPendingError, NotPresidingJudgeError,
    TurnNotActiveError, SessionNotLiveError, SessionCompletedError
)

router = APIRouter(prefix="/live/sessions/{session_id}/objections", tags=["Phase 6 — Objections"])


# =============================================================================
# Pydantic Schemas
# =============================================================================

class RaiseObjectionRequest(BaseModel):
    turn_id: int
    objection_type: str
    reason_text: Optional[str] = None


class RuleObjectionRequest(BaseModel):
    decision: str  # "sustained" or "overruled"
    ruling_reason_text: Optional[str] = None


class RecordViolationRequest(BaseModel):
    turn_id: int
    user_id: int
    violation_type: str
    description: Optional[str] = None


# =============================================================================
# Helper: Verify Session Access
# =============================================================================

async def verify_session_access(
    session_id: int,
    user: User,
    db: AsyncSession
) -> LiveCourtSession:
    """Verify user has access to session and return session."""
    result = await db.execute(
        select(LiveCourtSession)
        .where(
            and_(
                LiveCourtSession.id == session_id,
                LiveCourtSession.institution_id == user.institution_id
            )
        )
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    
    return session


async def verify_presiding_judge(
    session_id: int,
    user: User,
    db: AsyncSession
) -> bool:
    """
    Verify user is presiding judge for the session.
    
    For now, checks if user has JUDGE role.
    In production, would check specific presiding assignment.
    """
    return user.role == UserRole.JUDGE or user.role in [UserRole.ADMIN, UserRole.HOD]


# =============================================================================
# POST /live/sessions/{id}/objections — Raise Objection
# =============================================================================

@router.post("", status_code=status.HTTP_201_CREATED)
async def raise_objection_endpoint(
    session_id: int,
    request: RaiseObjectionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.HOD, UserRole.FACULTY, UserRole.JUDGE]))
) -> Dict[str, Any]:
    """
    Raise an objection during a turn.
    
    Rules:
    - Session must be LIVE
    - Turn must be ACTIVE
    - No pending objection already exists
    - Timer pauses automatically
    
    Roles: ADMIN, HOD, FACULTY, JUDGE
    """
    await verify_session_access(session_id, current_user, db)
    
    # Validate objection type
    try:
        obj_type = ObjectionType(request.objection_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid objection type: {request.objection_type}"
        )
    
    try:
        objection, turn = await raise_objection(
            session_id=session_id,
            turn_id=request.turn_id,
            raised_by_user_id=current_user.id,
            objection_type=obj_type,
            reason_text=request.reason_text,
            db=db
        )
        
        return {
            "objection_id": objection.id,
            "turn_id": request.turn_id,
            "objection_type": obj_type.value,
            "state": objection.state.value,
            "reason_text": request.reason_text,
            "is_timer_paused": turn.is_timer_paused,
            "raised_at": objection.raised_at.isoformat(),
            "objection_hash": objection.objection_hash,
            "message": "Objection raised - timer paused"
        }
        
    except SessionNotLiveError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except TurnNotActiveError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except ObjectionAlreadyPendingError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except SessionCompletedError as e:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=str(e)
        )
    except ObjectionNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


# =============================================================================
# POST /live/sessions/{id}/objections/{id}/rule — Rule on Objection
# =============================================================================

@router.post("/{objection_id}/rule", status_code=status.HTTP_200_OK)
async def rule_objection_endpoint(
    session_id: int,
    objection_id: int,
    request: RuleObjectionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.JUDGE, UserRole.ADMIN, UserRole.HOD]))
) -> Dict[str, Any]:
    """
    Rule on a pending objection.
    
    Rules:
    - Only presiding judge can rule
    - Objection must be in PENDING state
    - Session must be LIVE
    - Timer resumes automatically
    - Idempotent: second ruling fails cleanly
    
    Roles: JUDGE, ADMIN, HOD (presiding only)
    """
    await verify_session_access(session_id, current_user, db)
    
    # Validate decision
    try:
        decision = ObjectionState(request.decision)
        if decision not in (ObjectionState.SUSTAINED, ObjectionState.OVERRULED):
            raise ValueError
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Decision must be 'sustained' or 'overruled'"
        )
    
    # Check presiding judge
    is_presiding = await verify_presiding_judge(session_id, current_user, db)
    if not is_presiding:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the presiding judge can rule on objections"
        )
    
    try:
        objection, turn = await rule_objection(
            objection_id=objection_id,
            decision=decision,
            ruling_reason_text=request.ruling_reason_text,
            ruled_by_user_id=current_user.id,
            is_presiding_judge=is_presiding,
            db=db
        )
        
        return {
            "objection_id": objection.id,
            "turn_id": objection.turn_id,
            "decision": decision.value,
            "state": objection.state.value,
            "ruling_reason_text": request.ruling_reason_text,
            "is_timer_paused": turn.is_timer_paused,
            "ruled_at": objection.ruled_at.isoformat() if objection.ruled_at else None,
            "message": f"Objection {decision.value} - timer resumed"
        }
        
    except ObjectionNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except ObjectionAlreadyRuledError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except SessionNotLiveError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except SessionCompletedError as e:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=str(e)
        )
    except NotPresidingJudgeError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )


# =============================================================================
# GET /live/sessions/{id}/objections — List Objections
# =============================================================================

@router.get("", status_code=status.HTTP_200_OK)
async def get_objections_endpoint(
    session_id: int,
    state: Optional[str] = None,
    turn_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get all objections for a session.
    
    Query params:
    - state: Filter by 'pending', 'sustained', or 'overruled'
    - turn_id: Filter by specific turn
    """
    await verify_session_access(session_id, current_user, db)
    
    # Validate state filter
    state_filter = None
    if state:
        try:
            state_filter = ObjectionState(state)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid state: {state}"
            )
    
    # Get objections
    if turn_id:
        objections = await get_objections_by_turn(turn_id, db)
    else:
        objections = await get_objections_by_session(session_id, db, state_filter)
    
    return {
        "session_id": session_id,
        "total": len(objections),
        "filter": {"state": state, "turn_id": turn_id},
        "objections": [obj.to_dict() for obj in objections]
    }


# =============================================================================
# GET /live/sessions/{id}/turns/{id}/pending-objection — Get Pending
# =============================================================================

@router.get("/turn/{turn_id}/pending", status_code=status.HTTP_200_OK)
async def get_pending_objection_endpoint(
    session_id: int,
    turn_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get the pending objection for a turn (if any).
    """
    await verify_session_access(session_id, current_user, db)
    
    objection = await get_pending_objection_for_turn(turn_id, db)
    
    if not objection:
        return {
            "session_id": session_id,
            "turn_id": turn_id,
            "has_pending_objection": False,
            "objection": None
        }
    
    return {
        "session_id": session_id,
        "turn_id": turn_id,
        "has_pending_objection": True,
        "objection": objection.to_dict()
    }


# =============================================================================
# POST /live/sessions/{id}/violations — Record Procedural Violation
# =============================================================================

@router.post("/violations", status_code=status.HTTP_201_CREATED)
async def record_violation_endpoint(
    session_id: int,
    request: RecordViolationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.JUDGE, UserRole.ADMIN, UserRole.HOD, UserRole.FACULTY]))
) -> Dict[str, Any]:
    """
    Record a procedural violation.
    
    Creates violation record and appends to event chain.
    
    Roles: JUDGE, ADMIN, HOD, FACULTY
    """
    await verify_session_access(session_id, current_user, db)
    
    try:
        violation = await record_procedural_violation(
            session_id=session_id,
            turn_id=request.turn_id,
            user_id=request.user_id,
            recorded_by_user_id=current_user.id,
            violation_type=request.violation_type,
            description=request.description,
            db=db
        )
        
        return {
            "violation_id": violation.id,
            "turn_id": request.turn_id,
            "user_id": request.user_id,
            "violation_type": request.violation_type,
            "description": request.description,
            "recorded_at": violation.recorded_at.isoformat(),
            "message": "Procedural violation recorded"
        }
        
    except SessionCompletedError as e:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=str(e)
        )
    except ObjectionNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
