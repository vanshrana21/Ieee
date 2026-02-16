"""
Phase 17 — Appeals & Governance Override Routes.

FastAPI router for appeal processing with RBAC enforcement.
"""
from decimal import Decimal
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.rbac import get_current_user, require_role
from backend.orm.user import UserRole
from backend.config.feature_flags import feature_flags

from backend.services.phase17_appeal_service import AppealService, AppealValidationError, InvalidTransitionError, ConcurrencyError
from backend.orm.phase17_appeals import (
    AppealReasonCode, AppealStatus, RecommendedAction, WinnerSide
)


router = APIRouter(prefix="/api/appeals", tags=["Appeals"])


# =============================================================================
# Pydantic Models
# =============================================================================

class FileAppealRequest(BaseModel):
    """Request to file a new appeal."""
    team_id: str = Field(..., description="ID of the team filing the appeal")
    reason_code: str = Field(..., description="Reason: scoring_error, procedural_error, judge_bias, technical_issue")
    detailed_reason: Optional[str] = Field(None, description="Detailed explanation")
    
    @field_validator('reason_code')
    def validate_reason_code(cls, v):
        valid_codes = ['scoring_error', 'procedural_error', 'judge_bias', 'technical_issue']
        if v not in valid_codes:
            raise ValueError(f'Invalid reason_code. Must be one of: {valid_codes}')
        return v


class SubmitReviewRequest(BaseModel):
    """Request to submit a judge review."""
    recommended_action: str = Field(..., description="Action: uphold, modify_score, reverse_winner")
    justification: str = Field(..., min_length=10, description="Justification for recommendation")
    confidence_score: float = Field(0.5, ge=0.0, le=1.0, description="Confidence in recommendation (0-1)")
    
    @field_validator('recommended_action')
    def validate_action(cls, v):
        valid_actions = ['uphold', 'modify_score', 'reverse_winner']
        if v not in valid_actions:
            raise ValueError(f'Invalid action. Must be one of: {valid_actions}')
        return v


class FinalizeDecisionRequest(BaseModel):
    """Request to finalize an appeal decision."""
    final_action: str = Field(..., description="Final action: uphold, modify_score, reverse_winner")
    final_petitioner_score: Optional[float] = Field(None, ge=0, le=100, description="Modified petitioner score")
    final_respondent_score: Optional[float] = Field(None, ge=0, le=100, description="Modified respondent score")
    new_winner: Optional[str] = Field(None, description="New winner: petitioner, respondent")
    decision_summary: Optional[str] = Field(None, description="Summary of decision rationale")
    
    @field_validator('final_action')
    def validate_action(cls, v):
        valid_actions = ['uphold', 'modify_score', 'reverse_winner']
        if v not in valid_actions:
            raise ValueError(f'Invalid action. Must be one of: {valid_actions}')
        return v
    
    @field_validator('new_winner')
    def validate_winner(cls, v):
        if v is not None and v not in ['petitioner', 'respondent']:
            raise ValueError('Winner must be petitioner or respondent')
        return v


class AppealResponse(BaseModel):
    """Response for appeal operations."""
    success: bool
    appeal_id: Optional[str] = None
    status: Optional[str] = None
    message: str


# =============================================================================
# Helper Functions
# =============================================================================

def check_appeals_enabled():
    """Check if appeals engine is enabled."""
    if not feature_flags.FEATURE_APPEALS_ENGINE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Appeals engine is disabled"
        )


def map_string_to_reason_code(code: str) -> AppealReasonCode:
    """Map string reason code to enum."""
    mapping = {
        'scoring_error': AppealReasonCode.SCORING_ERROR,
        'procedural_error': AppealReasonCode.PROCEDURAL_ERROR,
        'judge_bias': AppealReasonCode.JUDGE_BIAS,
        'technical_issue': AppealReasonCode.TECHNICAL_ISSUE
    }
    return mapping.get(code, AppealReasonCode.SCORING_ERROR)


def map_string_to_action(action: str) -> RecommendedAction:
    """Map string action to enum."""
    mapping = {
        'uphold': RecommendedAction.UPHOLD,
        'modify_score': RecommendedAction.MODIFY_SCORE,
        'reverse_winner': RecommendedAction.REVERSE_WINNER
    }
    return mapping.get(action, RecommendedAction.UPHOLD)


def map_string_to_winner(winner: Optional[str]) -> Optional[WinnerSide]:
    """Map string winner to enum."""
    if winner is None:
        return None
    mapping = {
        'petitioner': WinnerSide.PETITIONER,
        'respondent': WinnerSide.RESPONDENT
    }
    return mapping.get(winner)


# =============================================================================
# Routes
# =============================================================================

@router.post("/file/{match_id}", response_model=AppealResponse)
async def file_appeal(
    match_id: str,
    request: FileAppealRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role([UserRole.student, UserRole.teacher, UserRole.teacher]))
):
    """
    File a new appeal for a match.
    
    **Roles:** Team Member, Admin, SuperAdmin
    
    Validations:
    - Match must be FROZEN
    - Appeal window not expired
    - Team belongs to match
    - No existing appeal from same team
    """
    check_appeals_enabled()
    
    try:
        result = await AppealService.file_appeal(
            db=db,
            match_id=match_id,
            filed_by_user_id=current_user["id"],
            team_id=request.team_id,
            reason_code=map_string_to_reason_code(request.reason_code),
            detailed_reason=request.detailed_reason
        )
        return AppealResponse(**result)
    except AppealValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/match/{match_id}")
async def get_match_appeals(
    match_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role([UserRole.teacher, UserRole.teacher, UserRole.teacher]))
):
    """
    Get all appeals for a match.
    
    **Roles:** Judge, Admin, SuperAdmin
    """
    check_appeals_enabled()
    
    try:
        appeals = await AppealService.get_match_appeals(db, match_id)
        return {
            "match_id": match_id,
            "appeals": appeals,
            "count": len(appeals)
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/{appeal_id}")
async def get_appeal_details(
    appeal_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role([UserRole.teacher, UserRole.teacher, UserRole.teacher]))
):
    """
    Get detailed appeal information including reviews and decision.
    
    **Roles:** Judge, Admin, SuperAdmin
    """
    check_appeals_enabled()
    
    try:
        appeal = await AppealService.get_appeal_with_details(db, appeal_id)
        if not appeal:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appeal not found")
        return appeal
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/assign-review/{appeal_id}", response_model=AppealResponse)
async def assign_for_review(
    appeal_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role([UserRole.teacher, UserRole.teacher]))
):
    """
    Assign appeal for review (Admin only).
    Transitions: FILED → UNDER_REVIEW
    
    **Roles:** Admin, SuperAdmin
    """
    check_appeals_enabled()
    
    try:
        result = await AppealService.assign_under_review(
            db=db,
            appeal_id=appeal_id,
            admin_user_id=current_user["id"]
        )
        return AppealResponse(**result)
    except InvalidTransitionError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except AppealValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/review/{appeal_id}", response_model=AppealResponse)
async def submit_review(
    appeal_id: str,
    request: SubmitReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role([UserRole.teacher, UserRole.teacher, UserRole.teacher]))
):
    """
    Submit a judge review for an appeal.
    
    **Roles:** Judge, Admin, SuperAdmin
    
    Validations:
    - Appeal status must be UNDER_REVIEW
    - Judge cannot submit duplicate review
    """
    check_appeals_enabled()
    
    try:
        result = await AppealService.submit_review(
            db=db,
            appeal_id=appeal_id,
            judge_user_id=current_user["id"],
            recommended_action=map_string_to_action(request.recommended_action),
            justification=request.justification,
            confidence_score=Decimal(str(request.confidence_score))
        )
        return AppealResponse(**result)
    except AppealValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/decide/{appeal_id}", response_model=AppealResponse)
async def finalize_decision(
    appeal_id: str,
    request: FinalizeDecisionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role([UserRole.teacher, UserRole.teacher]))
):
    """
    Finalize appeal decision (Admin only).
    
    **Roles:** Admin, SuperAdmin
    
    Steps:
    1. Lock appeal row
    2. Ensure status == UNDER_REVIEW
    3. Count reviews
    4. If FEATURE_MULTI_JUDGE_APPEALS: require ≥3 reviews, majority vote
    5. Validate score modifications
    6. Compute integrity hash
    7. Insert appeal_decisions
    8. Create override record if winner changes
    9. Set appeal.status = DECIDED
    
    Immutable after decision.
    """
    check_appeals_enabled()
    
    try:
        result = await AppealService.finalize_decision(
            db=db,
            appeal_id=appeal_id,
            decided_by_user_id=current_user["id"],
            final_action=map_string_to_action(request.final_action),
            final_petitioner_score=Decimal(str(request.final_petitioner_score)) if request.final_petitioner_score is not None else None,
            final_respondent_score=Decimal(str(request.final_respondent_score)) if request.final_respondent_score is not None else None,
            new_winner=map_string_to_winner(request.new_winner),
            decision_summary=request.decision_summary
        )
        return AppealResponse(**result)
    except InvalidTransitionError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ConcurrencyError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except AppealValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/override/{match_id}")
async def get_override(
    match_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role([UserRole.teacher, UserRole.teacher]))
):
    """
    Get override record for a match.
    
    **Roles:** Admin, SuperAdmin
    """
    check_appeals_enabled()
    
    try:
        from sqlalchemy import select
        from backend.orm.phase17_appeals import AppealOverrideResult
        
        result = await db.execute(
            select(AppealOverrideResult).where(
                AppealOverrideResult.match_id == match_id
            )
        )
        override = result.scalar_one_or_none()
        
        if not override:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No override found for this match")
        
        return override.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/auto-close")
async def auto_close_expired(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role([UserRole.teacher, UserRole.teacher]))
):
    """
    Auto-close appeals past their review deadline.
    
    **Roles:** Admin, SuperAdmin (typically run by system cron)
    
    If deadline < now AND status != DECIDED → CLOSED
    """
    check_appeals_enabled()
    
    if not feature_flags.FEATURE_APPEAL_AUTO_CLOSE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Auto-close feature is disabled"
        )
    
    try:
        result = await AppealService.auto_close_expired(db)
        return result
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/{appeal_id}/close")
async def close_appeal(
    appeal_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role([UserRole.teacher, UserRole.teacher]))
):
    """
    Manually close an appeal (Admin only).
    
    **Roles:** Admin, SuperAdmin
    """
    check_appeals_enabled()
    
    try:
        from sqlalchemy import select
        from backend.orm.phase17_appeals import Appeal, AppealStatus
        
        result = await db.execute(
            select(Appeal).where(Appeal.id == appeal_id).with_for_update()
        )
        appeal = result.scalar_one_or_none()
        
        if not appeal:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appeal not found")
        
        if appeal.status == AppealStatus.CLOSED:
            return {"success": True, "message": "Appeal already closed"}
        
        appeal.status = AppealStatus.CLOSED
        appeal.updated_at = datetime.utcnow()
        await db.commit()
        
        return {"success": True, "message": "Appeal closed successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
