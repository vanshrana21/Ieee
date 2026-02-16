"""
Phase 2 — Hardened Oral Rounds API Routes

Security features:
- Institution scoping on all endpoints
- RBAC enforcement
- 404 on cross-tenant access (no information leakage)
- Deterministic responses

Endpoints:
- POST /oral/sessions - Create new session
- POST /oral/sessions/{id}/activate - Activate session from template
- POST /oral/sessions/{id}/evaluate - Submit evaluation
- POST /oral/sessions/{id}/finalize - Finalize session
- GET /oral/sessions/{id}/verify - Verify session integrity
"""
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.dependencies import get_current_user, require_role
from backend.orm.user import User, UserRole
from backend.orm.oral_rounds import (
    OralSession, OralTurn, OralEvaluation, OralSessionFreeze,
    OralSessionStatus, OralSide, OralTurnType
)
from backend.services.oral_service import (
    create_oral_session, activate_oral_session, create_oral_evaluation,
    finalize_oral_session, verify_oral_session_integrity,
    get_oral_session_by_id, get_evaluations_by_session, get_turns_by_session,
    SessionNotFoundError, SessionFinalizedError, EvaluationExistsError,
    OralServiceError, InstitutionScopeError
)

router = APIRouter(prefix="/oral", tags=["Phase 2 — Hardened Oral Rounds"])


# =============================================================================
# Session Management Endpoints
# =============================================================================

@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(
    petitioner_team_id: int,
    respondent_team_id: int,
    round_template_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.teacher, UserRole.teacher, UserRole.teacher]))
) -> Dict[str, Any]:
    """
    Create new oral session in DRAFT status.
    
    Both teams must belong to user's institution.
    """
    try:
        session = await create_oral_session(
            institution_id=current_user.institution_id,
            petitioner_team_id=petitioner_team_id,
            respondent_team_id=respondent_team_id,
            round_template_id=round_template_id,
            db=db,
            created_by=current_user.id
        )
        
        return {
            "id": session.id,
            "institution_id": session.institution_id,
            "petitioner_team_id": session.petitioner_team_id,
            "respondent_team_id": session.respondent_team_id,
            "round_template_id": session.round_template_id,
            "status": session.status.value,
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "message": "Oral session created successfully"
        }
        
    except InstitutionScopeError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except OralServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/sessions/{session_id}/activate", status_code=status.HTTP_200_OK)
async def activate_session(
    session_id: int,
    petitioner_participants: List[int],
    respondent_participants: List[int],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.teacher, UserRole.teacher, UserRole.teacher]))
) -> Dict[str, Any]:
    """
    Activate oral session and create turns from template.
    
    Session must be in DRAFT status. Transitions to ACTIVE.
    """
    participant_assignments = {
        OralSide.PETITIONER.value: petitioner_participants,
        OralSide.RESPONDENT.value: respondent_participants
    }
    
    try:
        session = await activate_oral_session(
            session_id=session_id,
            institution_id=current_user.institution_id,
            participant_assignments=participant_assignments,
            db=db
        )
        
        # Get created turns
        turns = await get_turns_by_session(session_id, current_user.institution_id, db)
        
        return {
            "id": session.id,
            "status": session.status.value,
            "turns_created": len(turns),
            "turns": [t.to_dict() for t in turns],
            "message": "Session activated successfully"
        }
        
    except SessionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    except OralServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/sessions/{session_id}/evaluate", status_code=status.HTTP_201_CREATED)
async def evaluate_session(
    session_id: int,
    speaker_id: int,
    legal_reasoning_score: float,
    structure_score: float,
    responsiveness_score: float,
    courtroom_control_score: float,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.teacher, UserRole.teacher, UserRole.teacher]))
) -> Dict[str, Any]:
    """
    Submit oral evaluation for a speaker.
    
    Session must be ACTIVE (not FINALIZED).
    Each judge can evaluate each speaker only once.
    """
    # Convert float inputs to Decimal (will be quantized in service)
    try:
        evaluation = await create_oral_evaluation(
            session_id=session_id,
            judge_id=current_user.id,
            speaker_id=speaker_id,
            legal_reasoning_score=Decimal(str(legal_reasoning_score)),
            structure_score=Decimal(str(structure_score)),
            responsiveness_score=Decimal(str(responsiveness_score)),
            courtroom_control_score=Decimal(str(courtroom_control_score)),
            institution_id=current_user.institution_id,
            db=db
        )
        
        return {
            "id": evaluation.id,
            "session_id": evaluation.session_id,
            "judge_id": evaluation.judge_id,
            "speaker_id": evaluation.speaker_id,
            "legal_reasoning_score": str(evaluation.legal_reasoning_score),
            "structure_score": str(evaluation.structure_score),
            "responsiveness_score": str(evaluation.responsiveness_score),
            "courtroom_control_score": str(evaluation.courtroom_control_score),
            "total_score": str(evaluation.total_score),
            "evaluation_hash": evaluation.evaluation_hash,
            "hash_valid": evaluation.verify_hash(),
            "created_at": evaluation.created_at.isoformat() if evaluation.created_at else None,
            "message": "Evaluation submitted successfully"
        }
        
    except SessionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    except SessionFinalizedError:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Cannot evaluate finalized session"
        )
    except EvaluationExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Evaluation already exists for this judge and speaker"
        )
    except OralServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/sessions/{session_id}/finalize", status_code=status.HTTP_200_OK)
async def finalize_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.teacher, UserRole.teacher]))
) -> Dict[str, Any]:
    """
    Finalize oral session (irreversible).
    
    Steps:
    1. SERIALIZABLE transaction
    2. Verify all expected evaluations exist
    3. Compute session checksum
    4. Store immutable snapshot
    5. Lock session (FINALIZED status)
    
    Idempotent: Returns existing freeze if already finalized.
    """
    try:
        freeze = await finalize_oral_session(
            session_id=session_id,
            institution_id=current_user.institution_id,
            finalized_by=current_user.id,
            db=db
        )
        
        return {
            "session_id": session_id,
            "freeze_id": freeze.id,
            "session_checksum": freeze.session_checksum,
            "total_evaluations": len(freeze.evaluation_snapshot_json),
            "frozen_at": freeze.frozen_at.isoformat() if freeze.frozen_at else None,
            "frozen_by": freeze.frozen_by,
            "message": "Session finalized successfully"
        }
        
    except SessionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    except OralServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/sessions/{session_id}/verify", status_code=status.HTTP_200_OK)
async def verify_session_integrity(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.teacher, UserRole.teacher, UserRole.teacher]))
) -> Dict[str, Any]:
    """
    Verify oral session integrity.
    
    Compares stored snapshot hashes to current evaluation data.
    Detects any tampering, deletion, or addition of evaluations.
    """
    result = await verify_oral_session_integrity(
        session_id=session_id,
        institution_id=current_user.institution_id,
        db=db
    )
    
    if not result["found"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    
    return result


# =============================================================================
# Query Endpoints
# =============================================================================

@router.get("/sessions/{session_id}", status_code=status.HTTP_200_OK)
async def get_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get oral session details (institution-scoped).
    
    Returns 404 if session not in user's institution.
    """
    session = await get_oral_session_by_id(
        session_id=session_id,
        institution_id=current_user.institution_id,
        db=db
    )
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    
    # Get turns
    turns = await get_turns_by_session(session_id, current_user.institution_id, db)
    
    # Get evaluations
    evaluations = await get_evaluations_by_session(session_id, current_user.institution_id, db)
    
    return {
        "session": session.to_dict(include_teams=True),
        "turns": [t.to_dict() for t in turns],
        "evaluations": [e.to_dict() for e in evaluations],
        "evaluation_count": len(evaluations)
    }


@router.get("/sessions", status_code=status.HTTP_200_OK)
async def list_sessions(
    status: Optional[OralSessionStatus] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    List oral sessions for user's institution.
    
    Optional status filter.
    """
    from backend.services.oral_service import get_sessions_by_institution
    
    sessions = await get_sessions_by_institution(
        institution_id=current_user.institution_id,
        status=status,
        db=db
    )
    
    return {
        "sessions": [s.to_dict(include_teams=True) for s in sessions],
        "total_count": len(sessions),
        "status_filter": status.value if status else None
    }
