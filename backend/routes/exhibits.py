"""
Phase 7 — Evidence & Exhibit Management HTTP Routes

Server-authoritative with:
- Institution scoping
- RBAC enforcement
- No client trust
- Deterministic responses
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.dependencies import get_current_user, require_role
from backend.orm.user import User, UserRole
from backend.orm.live_court import LiveCourtSession, LiveCourtStatus
from backend.orm.exhibit import SessionExhibit, ExhibitState
from backend.services.exhibit_service import (
    upload_exhibit, mark_exhibit, tender_exhibit, rule_exhibit,
    get_exhibits_by_session, get_exhibit_by_id, verify_exhibit_integrity,
    ExhibitNotFoundError, ExhibitAlreadyRuledError,
    InvalidStateTransitionError, NotPresidingJudgeError,
    SessionNotLiveError, SessionCompletedError, InvalidFileError
)

router = APIRouter(prefix="/live/sessions/{session_id}/exhibits", tags=["Phase 7 — Exhibits"])


# =============================================================================
# Pydantic Schemas
# =============================================================================

class MarkExhibitRequest(BaseModel):
    exhibit_id: int


class TenderExhibitRequest(BaseModel):
    turn_id: int


class RuleExhibitRequest(BaseModel):
    decision: str  # "admitted" or "rejected"
    ruling_reason_text: Optional[str] = None


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

    For now, checks if user has JUDGE role or higher.
    In production, would check specific presiding assignment.
    """
    return user.role in [UserRole.teacher, UserRole.teacher, UserRole.teacher]


# =============================================================================
# POST /live/sessions/{id}/exhibits/upload — Upload Exhibit
# =============================================================================

@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_exhibit_endpoint(
    session_id: int,
    side: str = Form(..., description="petitioner or respondent"),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.teacher, UserRole.teacher, UserRole.teacher, UserRole.teacher]))
) -> Dict[str, Any]:
    """
    Upload an exhibit file (PDF only).

    Rules:
    - File must be valid PDF
    - Session must not be completed
    - File hash computed for integrity
    - State = uploaded (no exhibit_number yet)

    Roles: ADMIN, HOD, FACULTY, JUDGE
    """
    session = await verify_session_access(session_id, current_user, db)

    if session.is_completed():
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Cannot upload exhibit after session completed"
        )

    # Validate side
    if side not in ["petitioner", "respondent"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Side must be 'petitioner' or 'respondent'"
        )

    # Validate file type
    if not file.filename.endswith('.pdf'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are allowed"
        )

    # Read file content
    content = await file.read()

    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is empty"
        )

    try:
        exhibit = await upload_exhibit(
            session_id=session_id,
            institution_id=current_user.institution_id,
            side=side,
            original_filename=file.filename,
            file_content=content,
            uploaded_by_user_id=current_user.id,
            db=db
        )

        return {
            "exhibit_id": exhibit.id,
            "session_id": session_id,
            "side": side,
            "original_filename": exhibit.original_filename,
            "file_hash": exhibit.file_hash_sha256,
            "state": exhibit.state.value,
            "message": "Exhibit uploaded successfully - awaiting marking"
        }

    except InvalidFileError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except SessionCompletedError as e:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=str(e)
        )


# =============================================================================
# POST /live/sessions/{id}/exhibits/{id}/mark — Mark Exhibit
# =============================================================================

@router.post("/{exhibit_id}/mark", status_code=status.HTTP_200_OK)
async def mark_exhibit_endpoint(
    session_id: int,
    exhibit_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.teacher, UserRole.teacher, UserRole.teacher, UserRole.teacher]))
) -> Dict[str, Any]:
    """
    Mark an exhibit with deterministic numbering.

    Rules:
    - Exhibit state must be 'uploaded'
    - Session must be LIVE
    - Exhibit number assigned: P-1, P-2... or R-1, R-2...
    - Exhibit hash computed
    - Append EXHIBIT_MARKED event

    Roles: ADMIN, HOD, FACULTY, JUDGE
    """
    await verify_session_access(session_id, current_user, db)

    try:
        exhibit = await mark_exhibit(
            exhibit_id=exhibit_id,
            marked_by_user_id=current_user.id,
            db=db
        )

        return {
            "exhibit_id": exhibit.id,
            "session_id": session_id,
            "exhibit_number": exhibit.exhibit_number,
            "formatted_number": exhibit.get_formatted_number(),
            "side": exhibit.side,
            "state": exhibit.state.value,
            "exhibit_hash": exhibit.exhibit_hash,
            "message": f"Exhibit marked as {exhibit.get_formatted_number()}"
        }

    except ExhibitNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except InvalidStateTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
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


# =============================================================================
# POST /live/sessions/{id}/exhibits/{id}/tender — Tender Exhibit
# =============================================================================

@router.post("/{exhibit_id}/tender", status_code=status.HTTP_200_OK)
async def tender_exhibit_endpoint(
    session_id: int,
    exhibit_id: int,
    request: TenderExhibitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.teacher, UserRole.teacher, UserRole.teacher, UserRole.teacher]))
) -> Dict[str, Any]:
    """
    Tender an exhibit during a turn.

    Rules:
    - Exhibit state must be 'marked'
    - Turn must be ACTIVE
    - Append EXHIBIT_TENDERED event

    Roles: ADMIN, HOD, FACULTY, JUDGE
    """
    await verify_session_access(session_id, current_user, db)

    try:
        exhibit = await tender_exhibit(
            exhibit_id=exhibit_id,
            turn_id=request.turn_id,
            tendered_by_user_id=current_user.id,
            db=db
        )

        return {
            "exhibit_id": exhibit.id,
            "turn_id": request.turn_id,
            "formatted_number": exhibit.get_formatted_number(),
            "state": exhibit.state.value,
            "message": f"Exhibit {exhibit.get_formatted_number()} tendered"
        }

    except ExhibitNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except InvalidStateTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# =============================================================================
# POST /live/sessions/{id}/exhibits/{id}/rule — Rule on Exhibit
# =============================================================================

@router.post("/{exhibit_id}/rule", status_code=status.HTTP_200_OK)
async def rule_exhibit_endpoint(
    session_id: int,
    exhibit_id: int,
    request: RuleExhibitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.teacher, UserRole.teacher, UserRole.teacher]))
) -> Dict[str, Any]:
    """
    Rule on a tendered exhibit (admit or reject).

    Rules:
    - Only presiding judge can rule
    - Exhibit state must be 'tendered'
    - Session must be LIVE
    - Decision: 'admitted' or 'rejected'
    - Idempotent: second ruling fails cleanly

    Roles: JUDGE, ADMIN, HOD (presiding only)
    """
    await verify_session_access(session_id, current_user, db)

    # Validate decision
    try:
        decision = ExhibitState(request.decision)
        if decision not in (ExhibitState.ADMITTED, ExhibitState.REJECTED):
            raise ValueError
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Decision must be 'admitted' or 'rejected'"
        )

    # Check presiding judge
    is_presiding = await verify_presiding_judge(session_id, current_user, db)
    if not is_presiding:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the presiding judge can rule on exhibits"
        )

    try:
        exhibit = await rule_exhibit(
            exhibit_id=exhibit_id,
            decision=decision,
            ruling_reason_text=request.ruling_reason_text,
            ruled_by_user_id=current_user.id,
            is_presiding_judge=is_presiding,
            db=db
        )

        return {
            "exhibit_id": exhibit.id,
            "formatted_number": exhibit.get_formatted_number(),
            "ruling": decision.value,
            "state": exhibit.state.value,
            "ruling_reason_text": request.ruling_reason_text,
            "ruled_at": exhibit.ruled_at.isoformat() if exhibit.ruled_at else None,
            "message": f"Exhibit {exhibit.get_formatted_number()} {decision.value}"
        }

    except ExhibitNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except ExhibitAlreadyRuledError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except InvalidStateTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except NotPresidingJudgeError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
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


# =============================================================================
# GET /live/sessions/{id}/exhibits — List Exhibits
# =============================================================================

@router.get("", status_code=status.HTTP_200_OK)
async def get_exhibits_endpoint(
    session_id: int,
    state: Optional[str] = None,
    side: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get all exhibits for a session.

    Query params:
    - state: Filter by state ('uploaded', 'marked', 'tendered', 'admitted', 'rejected')
    - side: Filter by side ('petitioner' or 'respondent')
    """
    await verify_session_access(session_id, current_user, db)

    # Validate state filter
    state_filter = None
    if state:
        try:
            state_filter = ExhibitState(state)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid state: {state}"
            )

    # Validate side filter
    if side and side not in ["petitioner", "respondent"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Side must be 'petitioner' or 'respondent'"
        )

    exhibits = await get_exhibits_by_session(
        session_id=session_id,
        db=db,
        state=state_filter,
        side=side
    )

    return {
        "session_id": session_id,
        "total": len(exhibits),
        "filter": {"state": state, "side": side},
        "exhibits": [ex.to_dict() for ex in exhibits]
    }


# =============================================================================
# GET /live/sessions/{id}/exhibits/{id} — Get Exhibit Details
# =============================================================================

@router.get("/{exhibit_id}", status_code=status.HTTP_200_OK)
async def get_exhibit_endpoint(
    session_id: int,
    exhibit_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get details of a specific exhibit."""
    await verify_session_access(session_id, current_user, db)

    exhibit = await get_exhibit_by_id(exhibit_id, db)

    if not exhibit or exhibit.session_id != session_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Exhibit not found"
        )

    return {
        "exhibit": exhibit.to_dict()
    }


# =============================================================================
# GET /live/sessions/{id}/exhibits/verify — Verify All Exhibits
# =============================================================================

@router.get("/verify", status_code=status.HTTP_200_OK)
async def verify_exhibits_endpoint(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.teacher, UserRole.teacher, UserRole.teacher, UserRole.teacher]))
) -> Dict[str, Any]:
    """
    Verify integrity of all exhibits in a session.

    Checks:
    - Exhibit hashes match computed hashes
    - File hashes match stored hashes
    - Files exist on disk

    Roles: JUDGE, ADMIN, HOD, FACULTY
    """
    await verify_session_access(session_id, current_user, db)

    exhibits = await get_exhibits_by_session(session_id, db)

    verification_results = []
    all_valid = True

    for exhibit in exhibits:
        result = await verify_exhibit_integrity(exhibit.id, db)
        verification_results.append(result)
        if not result["valid"]:
            all_valid = False

    return {
        "session_id": session_id,
        "total_exhibits": len(exhibits),
        "all_valid": all_valid,
        "verifications": verification_results,
        "message": "All exhibits verified" if all_valid else "Some exhibits have integrity issues"
    }
