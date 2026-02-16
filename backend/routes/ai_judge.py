"""
AI Judge Router — Phase 4

API endpoints for AI evaluation, rubrics, faculty overrides, and leaderboards.
"""
import logging
from decimal import Decimal
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.orm.user import User, UserRole
from backend.orm.ai_evaluations import AIEvaluation
from backend.routes.auth import get_current_user
from backend.schemas.ai_judge import (
    RubricCreateRequest, RubricResponse, RubricListResponse,
    EvaluationTriggerRequest, EvaluationResponse, EvaluationDetailResponse,
    EvaluationListResponse, FacultyOverrideRequest, FacultyOverrideResponse,
    LeaderboardResponse, EvaluationErrorResponse
)
from backend.services import ai_evaluation_service as eval_svc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ai-judge", tags=["ai-judge"])


def _is_faculty(user: User) -> bool:
    """Check if user has faculty role."""
    return user.role in (UserRole.teacher, UserRole.teacher)


def _make_error_response(error: str, message: str, details: Optional[dict] = None) -> dict:
    """Create standardized error response."""
    return {
        "success": False,
        "error": error,
        "message": message,
        "details": details
    }


# ============================================================================
# Rubric Routes
# ============================================================================

@router.post("/rubrics", response_model=RubricResponse, status_code=status.HTTP_201_CREATED)
async def create_rubric(
    request: RubricCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new rubric with automatic version snapshot.
    
    Faculty only. Validates rubric definition and creates frozen version.
    """
    if not _is_faculty(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_make_error_response("FORBIDDEN", "Only faculty can create rubrics")
        )
    
    try:
        rubric = await eval_svc.create_rubric(
            name=request.name,
            description=request.description,
            rubric_type=request.rubric_type,
            definition=request.definition.model_dump(),
            created_by_faculty_id=current_user.id,
            db=db
        )
        
        await db.commit()
        
        return RubricResponse(
            id=rubric.id,
            name=rubric.name,
            description=rubric.description,
            rubric_type=rubric.rubric_type,
            current_version=rubric.current_version,
            definition=rubric.definition_json,  # Will be parsed by pydantic
            created_at=rubric.created_at.isoformat() if rubric.created_at else None,
            is_active=bool(rubric.is_active)
        )
        
    except eval_svc.AIJudgeError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_make_error_response(e.code, e.message)
        )
    except Exception as e:
        await db.rollback()
        logger.exception("Failed to create rubric")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_make_error_response("INTERNAL_ERROR", "Failed to create rubric")
        )


@router.get("/rubrics", response_model=RubricListResponse)
async def list_rubrics(
    rubric_type: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List available rubrics with optional filtering."""
    try:
        rubrics = await eval_svc.list_rubrics(
            db=db,
            rubric_type=rubric_type,
            is_active=True
        )
        
        return RubricListResponse(
            rubrics=[
                RubricResponse(
                    id=r.id,
                    name=r.name,
                    description=r.description,
                    rubric_type=r.rubric_type,
                    current_version=r.current_version,
                    definition={},  # Don't include full definition in list
                    created_at=r.created_at.isoformat() if r.created_at else None,
                    is_active=bool(r.is_active)
                )
                for r in rubrics
            ],
            total=len(rubrics)
        )
        
    except Exception as e:
        logger.exception("Failed to list rubrics")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_make_error_response("INTERNAL_ERROR", "Failed to list rubrics")
        )


# ============================================================================
# Evaluation Routes
# ============================================================================

@router.post("/sessions/{session_id}/rounds/{round_id}/evaluate")
async def trigger_evaluation(
    session_id: int,
    round_id: int,
    request: EvaluationTriggerRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Trigger AI evaluation for a participant in a round.
    
    PHASE 2: Runs asynchronously using BackgroundTasks.
    Returns immediately with evaluation_id, processing happens in background.
    """
    # Check authorization (teacher only after Phase 1)
    if current_user.role != UserRole.teacher:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only teachers can trigger evaluations"
        )
    
    try:
        # STEP 1: Create evaluation record and set to PROCESSING
        result = await eval_svc.evaluate(
            session_id=session_id,
            round_id=round_id,
            participant_id=request.participant_id,
            rubric_version_id=request.rubric_version_id,
            db=db,
            user_id=current_user.id,
            is_faculty=True,
            turn_id=request.turn_id,
            transcript_text=request.transcript_text
        )
        
        evaluation_id = result.get("evaluation_id")
        
        # STEP 2: Commit initial state (processing)
        await db.commit()
        
        # STEP 3: Add background task (non-blocking)
        db_url = str(db.bind.url)
        background_tasks.add_task(
            eval_svc.process_ai_evaluation_background,
            evaluation_id,
            db_url
        )
        
        # STEP 4: Return immediately (do not wait)
        return {
            "status": "processing",
            "evaluation_id": evaluation_id,
            "message": "AI evaluation started in background"
        }
        
    except eval_svc.InvalidStateError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_make_error_response(e.code, e.message)
        )
    except eval_svc.RubricNotFoundError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_make_error_response(e.code, e.message)
        )
    except Exception as e:
        await db.rollback()
        logger.exception(f"Failed to start evaluation for round {round_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_make_error_response("INTERNAL_ERROR", "Failed to start evaluation")
        )


@router.get("/evaluations/{evaluation_id}/status")
async def get_evaluation_status(
    evaluation_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    PHASE 2: Get evaluation status for polling.
    
    Frontend polls this endpoint every 3-5 seconds to check evaluation progress.
    """
    try:
        status = await eval_svc.get_evaluation_status(evaluation_id, db)
        return status
    except Exception as e:
        logger.exception(f"Failed to get status for evaluation {evaluation_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get evaluation status"
        )


@router.get("/evaluations/{evaluation_id}", response_model=EvaluationDetailResponse)
async def get_evaluation(
    evaluation_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get detailed evaluation with attempts, overrides, and audit trail."""
    try:
        details = await eval_svc.get_evaluation_with_details(evaluation_id, db)
        
        if not details:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_make_error_response("NOT_FOUND", f"Evaluation {evaluation_id} not found")
            )
        
        evaluation = details["evaluation"]
        
        return EvaluationDetailResponse(
            id=evaluation.id,
            session_id=evaluation.session_id,
            round_id=evaluation.round_id,
            participant_id=evaluation.participant_id,
            turn_id=evaluation.turn_id,
            rubric_version_id=evaluation.rubric_version_id,
            status=evaluation.status,
            final_score=float(evaluation.final_score) if evaluation.final_score else None,
            score_breakdown=evaluation.score_breakdown,  # Will be parsed from JSON
            weights_used=evaluation.weights_used,  # Will be parsed from JSON
            ai_model=evaluation.ai_model,
            ai_model_version=evaluation.ai_model_version,
            evaluation_timestamp=evaluation.evaluation_timestamp.isoformat() if evaluation.evaluation_timestamp else None,
            finalized_by_faculty_id=evaluation.finalized_by_faculty_id,
            finalized_at=evaluation.finalized_at.isoformat() if evaluation.finalized_at else None,
            created_at=evaluation.created_at.isoformat() if evaluation.created_at else None,
            attempts=[],  # Simplified - would convert from ORM
            overrides=[],  # Simplified - would convert from ORM
            audit_entries=[]  # Simplified - would convert from ORM
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get evaluation {evaluation_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_make_error_response("INTERNAL_ERROR", "Failed to get evaluation")
        )


@router.get("/sessions/{session_id}/evaluations", response_model=EvaluationListResponse)
async def list_session_evaluations(
    session_id: int,
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all evaluations for a session."""
    try:
        evaluations = await eval_svc.list_evaluations_for_session(
            session_id=session_id,
            db=db,
            status=status
        )
        
        return EvaluationListResponse(
            evaluations=[
                EvaluationResponse(
                    id=e.id,
                    session_id=e.session_id,
                    round_id=e.round_id,
                    participant_id=e.participant_id,
                    turn_id=e.turn_id,
                    rubric_version_id=e.rubric_version_id,
                    status=e.status,
                    final_score=float(e.final_score) if e.final_score else None,
                    score_breakdown={},  # Would parse from JSON
                    weights_used={},  # Would parse from JSON
                    ai_model=e.ai_model,
                    ai_model_version=e.ai_model_version,
                    evaluation_timestamp=e.evaluation_timestamp.isoformat() if e.evaluation_timestamp else None,
                    finalized_by_faculty_id=e.finalized_by_faculty_id,
                    finalized_at=e.finalized_at.isoformat() if e.finalized_at else None,
                    created_at=e.created_at.isoformat() if e.created_at else None
                )
                for e in evaluations
            ],
            total=len(evaluations)
        )
        
    except Exception as e:
        logger.exception(f"Failed to list evaluations for session {session_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_make_error_response("INTERNAL_ERROR", "Failed to list evaluations")
        )


# ============================================================================
# Faculty Override Routes
# ============================================================================

@router.post("/evaluations/{evaluation_id}/override", response_model=FacultyOverrideResponse)
async def create_override(
    evaluation_id: int,
    request: FacultyOverrideRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Faculty override of AI evaluation score.
    
    Never modifies original evaluation. Creates separate override record.
    """
    if not _is_faculty(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_make_error_response("FORBIDDEN", "Only faculty can override evaluations")
        )
    
    try:
        override = await eval_svc.create_override(
            evaluation_id=evaluation_id,
            new_score=Decimal(str(request.new_score)),
            new_breakdown=request.new_breakdown,
            reason=request.reason,
            faculty_id=current_user.id,
            db=db,
            is_faculty=True
        )
        
        await db.commit()
        
        return FacultyOverrideResponse(
            id=override.id,
            ai_evaluation_id=override.ai_evaluation_id,
            previous_score=float(override.previous_score),
            new_score=float(override.new_score),
            previous_breakdown={},  # Would parse from JSON
            new_breakdown={},  # Would parse from JSON
            faculty_id=override.faculty_id,
            reason=override.reason,
            created_at=override.created_at.isoformat() if override.created_at else None
        )
        
    except eval_svc.EvaluationNotFoundError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_make_error_response(e.code, e.message)
        )
    except Exception as e:
        await db.rollback()
        logger.exception(f"Failed to create override for evaluation {evaluation_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_make_error_response("INTERNAL_ERROR", "Failed to create override")
        )


# ============================================================================
# Leaderboard Routes
# ============================================================================

@router.get("/sessions/{session_id}/leaderboard", response_model=LeaderboardResponse)
async def get_leaderboard(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get session leaderboard with aggregated scores."""
    try:
        entries = await eval_svc.get_session_leaderboard(session_id, db)
        
        from datetime import datetime
        
        return LeaderboardResponse(
            session_id=session_id,
            entries=[
                {
                    "participant_id": e["participant_id"],
                    "user_id": e["user_id"],
                    "user_name": None,  # Would fetch from User table
                    "side": e["side"],
                    "speaker_number": e["speaker_number"],
                    "final_score": e["final_score"],
                    "rank": e["rank"],
                    "evaluations_count": e["evaluations_count"],
                    "has_override": e["has_override"]
                }
                for e in entries
            ],
            generated_at=datetime.utcnow().isoformat()
        )
        
    except Exception as e:
        logger.exception(f"Failed to get leaderboard for session {session_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_make_error_response("INTERNAL_ERROR", "Failed to get leaderboard")
        )
