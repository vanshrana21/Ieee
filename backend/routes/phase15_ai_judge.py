"""
Phase 15 — AI Judge Routes

API routes for AI judge intelligence layer.
All routes enforce RBAC and feature flags.
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from backend.database import get_db
from backend.rbac import get_current_user, require_role
from backend.orm.user import UserRole

from backend.services.phase15_shadow_service import ShadowScoringService
from backend.services.phase15_official_service import OfficialEvaluationService
from backend.services.phase15_snapshot_builder import SnapshotBuilderService
from backend.services.phase15_model_router import ModelRouterService

router = APIRouter(prefix="/api/ai", tags=["AI Judge"])


# =============================================================================
# Pydantic Schemas
# =============================================================================

class ShadowScoreResponse(BaseModel):
    match_id: str
    mode: str
    heuristic_version: str
    used_llm: bool
    provisional_winner: str
    petitioner_provisional_score: float
    respondent_provisional_score: float
    turn_scores: list
    generated_at: str


class OfficialEvaluationResponse(BaseModel):
    match_id: str
    snapshot_hash: str
    evaluation_hash: str
    model_name: str
    mode: str
    cached: bool
    petitioner_score: Optional[dict]
    respondent_score: Optional[dict]
    winner: Optional[str]
    reasoning_summary: Optional[str]
    confidence_score: Optional[float]
    token_usage: Optional[int]
    created_at: Optional[str]


class EvaluationHistoryResponse(BaseModel):
    match_id: str
    evaluation_count: int
    evaluations: list


class VerificationResponse(BaseModel):
    match_id: str
    evaluation_id: Optional[str]
    snapshot_valid: bool
    evaluation_valid: bool
    verified: bool
    snapshot_hash_stored: Optional[str]
    snapshot_hash_current: Optional[str]
    evaluation_hash_stored: Optional[str]
    evaluation_hash_computed: Optional[str]
    match_frozen: bool


class SnapshotResponse(BaseModel):
    match_id: str
    snapshot_hash: str
    snapshot: dict
    turn_count: int
    is_frozen: bool


class ModelInfoResponse(BaseModel):
    available_models: dict
    default_shadow: str
    default_official: str
    finals_model: str


# =============================================================================
# Routes
# =============================================================================

@router.post(
    "/shadow/{match_id}",
    response_model=ShadowScoreResponse,
    summary="Generate shadow scoring for LIVE match",
    dependencies=[Depends(require_role([UserRole.JUDGE, UserRole.ADMIN]))]
)
async def generate_shadow_score(
    match_id: uuid.UUID,
    use_llm: bool = Query(default=False, description="Use LLM instead of heuristics"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Generate provisional shadow scoring for a LIVE match.

    - Requires JUDGE or ADMIN role
    - Match must be in LIVE status
    - Feature flag FEATURE_AI_JUDGE_SHADOW must be enabled
    - Shadow scores are temporary and auto-deleted on freeze
    """
    result = await ShadowScoringService.evaluate_match_shadow(
        db=db,
        match_id=match_id,
        use_llm=use_llm
    )
    return ShadowScoreResponse(**result)


@router.post(
    "/evaluate/{match_id}",
    response_model=OfficialEvaluationResponse,
    summary="Generate official AI evaluation for FROZEN match",
    dependencies=[Depends(require_role([UserRole.JUDGE, UserRole.ADMIN]))]
)
async def generate_official_evaluation(
    match_id: uuid.UUID,
    force_refresh: bool = Query(default=False, description="Ignore cache and generate new evaluation"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Generate official AI evaluation for a FROZEN match.

    - Requires JUDGE or ADMIN role
    - Match must be in FROZEN status
    - Feature flag FEATURE_AI_JUDGE_OFFICIAL must be enabled
    - Results are cached for 24 hours (unless force_refresh=True)
    - All evaluations are hash-verified
    """
    result = await OfficialEvaluationService.evaluate_match_official(
        db=db,
        match_id=match_id,
        force_refresh=force_refresh
    )
    return OfficialEvaluationResponse(**result)


@router.get(
    "/result/{match_id}",
    response_model=EvaluationHistoryResponse,
    summary="Get AI evaluation history for match",
    dependencies=[Depends(require_role([UserRole.JUDGE, UserRole.ADMIN, UserRole.STUDENT]))]
)
async def get_evaluation_result(
    match_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Get evaluation history for a match.

    - Accessible to JUDGE, ADMIN, and STUDENT roles
    - Returns all AI evaluations for the match
    """
    result = await OfficialEvaluationService.get_evaluation_history(
        db=db,
        match_id=match_id
    )
    return EvaluationHistoryResponse(**result)


@router.post(
    "/verify/{match_id}",
    response_model=VerificationResponse,
    summary="Verify integrity of AI evaluation",
    dependencies=[Depends(require_role([UserRole.SUPER_ADMIN]))]
)
async def verify_evaluation_integrity(
    match_id: uuid.UUID,
    evaluation_id: Optional[uuid.UUID] = Query(None, description="Specific evaluation to verify"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Verify integrity of AI evaluation using hash verification.

    - Requires SUPER_ADMIN role
    - Compares stored snapshot hash with current match state
    - Verifies evaluation hash integrity
    - Returns detailed verification report
    """
    result = await OfficialEvaluationService.verify_evaluation(
        db=db,
        match_id=match_id,
        evaluation_id=evaluation_id
    )
    return VerificationResponse(**result)


@router.get(
    "/snapshot/{match_id}",
    response_model=SnapshotResponse,
    summary="Get match snapshot for AI evaluation",
    dependencies=[Depends(require_role([UserRole.JUDGE, UserRole.ADMIN]))]
)
async def get_match_snapshot(
    match_id: uuid.UUID,
    validate_frozen: bool = Query(default=True, description="Validate match is frozen"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Get deterministic snapshot of match state.

    - Requires JUDGE or ADMIN role
    - Returns hash-verified match snapshot
    - Used for debugging and verification
    """
    result = await SnapshotBuilderService.build_match_snapshot(
        db=db,
        match_id=match_id,
        validate_frozen=validate_frozen
    )
    return SnapshotResponse(
        match_id=str(match_id),
        snapshot_hash=result["snapshot_hash"],
        snapshot=result["snapshot"],
        turn_count=result["turn_count"],
        is_frozen=result["is_frozen"]
    )


@router.get(
    "/models",
    response_model=ModelInfoResponse,
    summary="Get available AI models",
    dependencies=[Depends(require_role([UserRole.JUDGE, UserRole.ADMIN, UserRole.SUPER_ADMIN]))]
)
async def get_available_models(
    current_user=Depends(get_current_user)
):
    """
    Get list of available AI models and their configurations.

    - Accessible to JUDGE, ADMIN, and SUPER_ADMIN roles
    - Returns model configurations and routing defaults
    """
    models = ModelRouterService.get_available_models()
    return ModelInfoResponse(
        available_models=models,
        default_shadow="gpt-3.5-turbo",
        default_official="gpt-4",
        finals_model="gpt-4-turbo"
    )


@router.get(
    "/shadow-scores/{match_id}",
    summary="Get shadow scores for match",
    dependencies=[Depends(require_role([UserRole.JUDGE, UserRole.ADMIN]))]
)
async def get_shadow_scores(
    match_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Get all shadow scores for a LIVE match.

    - Requires JUDGE or ADMIN role
    - Returns provisional scores during match
    """
    scores = await ShadowScoringService.get_shadow_scores(
        db=db,
        match_id=match_id
    )
    return {
        "match_id": str(match_id),
        "shadow_scores": scores
    }


@router.delete(
    "/shadow-scores/{match_id}",
    summary="Delete shadow scores for match",
    dependencies=[Depends(require_role([UserRole.ADMIN, UserRole.SUPER_ADMIN]))]
)
async def delete_shadow_scores(
    match_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Manually delete shadow scores for a match.

    - Requires ADMIN or SUPER_ADMIN role
    - Normally auto-deleted on match freeze
    """
    deleted_count = await ShadowScoringService.delete_shadow_scores(
        db=db,
        match_id=match_id
    )
    return {
        "match_id": str(match_id),
        "deleted_count": deleted_count
    }
