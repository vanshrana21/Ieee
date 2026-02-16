"""
Phase 16 — Performance Analytics & Ranking API Routes.

Endpoints for analytics aggregation, rankings, judge profiles, and trends.
All routes enforce RBAC and feature flag checks.
"""
import uuid
from typing import Optional, List
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from backend.database import get_db
from backend.rbac import get_current_user, require_role
from backend.orm.user import UserRole
from backend.config.feature_flags import feature_flags

from backend.services.phase16_analytics_service import AnalyticsAggregatorService
from backend.services.phase16_ranking_engine import RankingEngineService
from backend.services.phase16_judge_analytics_service import JudgeAnalyticsService
from backend.services.phase16_trend_engine import TrendEngineService
from backend.orm.phase16_analytics import EntityType, RankingTier, StreakType

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])


# =============================================================================
# Request/Response Models
# =============================================================================

class RecomputeSpeakerResponse(BaseModel):
    id: str
    user_id: str
    total_matches: int
    wins: int
    losses: int
    win_rate: float
    avg_score: float
    avg_ai_score: float
    confidence_weighted_score: float
    peak_score: float
    lowest_score: float
    consistency_index: float
    improvement_trend: float
    last_updated: Optional[str]


class RecomputeTeamResponse(BaseModel):
    id: str
    team_id: str
    total_matches: int
    wins: int
    losses: int
    win_rate: float
    avg_score: float
    avg_ai_score: float
    team_synergy_index: float
    comeback_index: float
    freeze_integrity_score: float
    rank_points: float
    national_rank: int
    institution_rank: int
    last_updated: Optional[str]


class BatchRecomputeResponse(BaseModel):
    speakers: int
    teams: int
    errors: int
    message: str


class RankingResponse(BaseModel):
    id: str
    entity_type: Optional[str]
    entity_id: str
    rating_score: float
    elo_rating: float
    volatility: float
    confidence_score: float
    tier: Optional[str]
    rank_position: int
    previous_rank: int
    rank_movement: int
    season: str
    last_calculated: Optional[str]


class RankingsListResponse(BaseModel):
    rankings: List[RankingResponse]
    total: int
    entity_type: str
    season: str


class TierDistributionResponse(BaseModel):
    S: int
    A: int
    B: int
    C: int


class JudgeProfileResponse(BaseModel):
    id: str
    judge_user_id: str
    total_matches_scored: int
    avg_score_given: float
    score_variance: float
    ai_deviation_index: float
    confidence_alignment_score: float
    bias_petitioner_ratio: float
    bias_respondent_ratio: float
    strictness_index: float
    last_updated: Optional[str]


class JudgeBiasReportResponse(BaseModel):
    total_judges: int
    avg_strictness: float
    biased_judges_count: int
    biased_judges: List[dict]
    high_deviation_count: int
    high_deviation_judges: List[dict]


class TrendsResponse(BaseModel):
    id: str
    entity_type: Optional[str]
    entity_id: str
    last_5_avg: float
    last_10_avg: float
    improvement_velocity: float
    volatility_index: float
    streak_type: Optional[str]
    streak_count: int
    momentum_score: float
    risk_index: float
    last_updated: Optional[str]


class HotStreaksResponse(BaseModel):
    streaks: List[TrendsResponse]
    total: int


# =============================================================================
# Speaker Analytics Routes
# =============================================================================

@router.post(
    "/recompute/speaker/{user_id}",
    response_model=RecomputeSpeakerResponse,
    summary="Recompute speaker analytics",
    dependencies=[Depends(require_role([UserRole.ADMIN]))]
)
async def recompute_speaker(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Recompute performance analytics for a speaker.
    - Requires ADMIN role
    - Feature flag FEATURE_ANALYTICS_ENGINE must be enabled
    - Uses FOR UPDATE locking for concurrency safety
    """
    if not feature_flags.FEATURE_ANALYTICS_ENGINE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Analytics engine feature is disabled"
        )
    
    result = await AnalyticsAggregatorService.recompute_speaker(
        db=db,
        user_id=str(user_id),
        force=True
    )
    
    return RecomputeSpeakerResponse(**result)


@router.post(
    "/recompute/team/{team_id}",
    response_model=RecomputeTeamResponse,
    summary="Recompute team analytics",
    dependencies=[Depends(require_role([UserRole.ADMIN]))]
)
async def recompute_team(
    team_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Recompute performance analytics for a team.
    - Requires ADMIN role
    - Feature flag FEATURE_ANALYTICS_ENGINE must be enabled
    - Computes synergy, comeback, and freeze integrity indices
    """
    if not feature_flags.FEATURE_ANALYTICS_ENGINE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Analytics engine feature is disabled"
        )
    
    result = await AnalyticsAggregatorService.recompute_team(
        db=db,
        team_id=str(team_id),
        force=True
    )
    
    return RecomputeTeamResponse(**result)


@router.post(
    "/recompute/all",
    response_model=BatchRecomputeResponse,
    summary="Batch recompute all analytics",
    dependencies=[Depends(require_role([UserRole.SUPER_ADMIN]))]
)
async def batch_recompute_all(
    batch_size: int = Query(default=100, ge=10, le=500),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Batch recompute analytics for all speakers and teams.
    - Requires SUPER_ADMIN role
    - Processes in batches to avoid memory issues
    - Commits per batch
    """
    if not feature_flags.FEATURE_ANALYTICS_ENGINE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Analytics engine feature is disabled"
        )
    
    result = await AnalyticsAggregatorService.batch_recompute_all(
        db=db,
        batch_size=batch_size
    )
    
    return BatchRecomputeResponse(
        speakers=result["speakers"],
        teams=result["teams"],
        errors=result["errors"],
        message=f"Processed {result['speakers']} speakers and {result['teams']} teams"
    )


# =============================================================================
# Rankings Routes
# =============================================================================

@router.post(
    "/rankings/recompute/{entity_type}",
    summary="Recompute rankings for entity type",
    dependencies=[Depends(require_role([UserRole.ADMIN]))]
)
async def recompute_rankings(
    entity_type: str,
    season: str = Query(default="2026"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Recompute ELO rankings for speakers or teams.
    - Requires ADMIN role
    - Feature flag FEATURE_RANKING_ENGINE must be enabled
    - Processes matches chronologically
    """
    if not feature_flags.FEATURE_RANKING_ENGINE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ranking engine feature is disabled"
        )
    
    try:
        entity_enum = EntityType(entity_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid entity type: {entity_type}"
        )
    
    result = await RankingEngineService.recompute_rankings(
        db=db,
        entity_type=entity_enum,
        season=season
    )
    
    return result


@router.get(
    "/rankings/{entity_type}",
    response_model=RankingsListResponse,
    summary="Get rankings for entity type"
)
async def get_rankings(
    entity_type: str,
    season: str = Query(default="2026"),
    tier: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """
    Get rankings for speakers or teams.
    - Public endpoint (no auth required)
    - Deterministic ordering: rating DESC, confidence DESC, entity_id ASC
    - Supports filtering by tier
    """
    if not feature_flags.FEATURE_RANKING_ENGINE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ranking engine feature is disabled"
        )
    
    try:
        entity_enum = EntityType(entity_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid entity type: {entity_type}"
        )
    
    # Parse tier if provided
    tier_enum = None
    if tier:
        try:
            tier_enum = RankingTier(tier.upper())
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid tier: {tier}"
            )
    
    rankings = await RankingEngineService.get_rankings(
        db=db,
        entity_type=entity_enum,
        season=season,
        tier=tier_enum,
        limit=limit,
        offset=offset
    )
    
    return RankingsListResponse(
        rankings=[RankingResponse(**r) for r in rankings],
        total=len(rankings),
        entity_type=entity_type,
        season=season
    )


@router.get(
    "/rankings/{entity_type}/distribution",
    response_model=TierDistributionResponse,
    summary="Get tier distribution"
)
async def get_tier_distribution(
    entity_type: str,
    season: str = Query(default="2026"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get distribution of entities across tiers.
    """
    if not feature_flags.FEATURE_RANKING_ENGINE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ranking engine feature is disabled"
        )
    
    try:
        entity_enum = EntityType(entity_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid entity type: {entity_type}"
        )
    
    distribution = await RankingEngineService.get_tier_distribution(
        db=db,
        entity_type=entity_enum,
        season=season
    )
    
    return TierDistributionResponse(
        S=distribution.get('S', 0),
        A=distribution.get('A', 0),
        B=distribution.get('B', 0),
        C=distribution.get('C', 0)
    )


# =============================================================================
# Judge Analytics Routes
# =============================================================================

@router.post(
    "/judge/{judge_id}/recompute",
    response_model=JudgeProfileResponse,
    summary="Recompute judge profile",
    dependencies=[Depends(require_role([UserRole.ADMIN]))]
)
async def recompute_judge_profile(
    judge_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Recompute judge behavior profile.
    - Requires ADMIN role
    - Feature flag FEATURE_JUDGE_ANALYTICS must be enabled
    """
    if not feature_flags.FEATURE_JUDGE_ANALYTICS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Judge analytics feature is disabled"
        )
    
    result = await JudgeAnalyticsService.recompute_judge_profile(
        db=db,
        judge_user_id=str(judge_id),
        force=True
    )
    
    if "error" in result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )
    
    return JudgeProfileResponse(**result)


@router.get(
    "/judge/{judge_id}",
    response_model=JudgeProfileResponse,
    summary="Get judge profile",
    dependencies=[Depends(require_role([UserRole.ADMIN]))]
)
async def get_judge_profile(
    judge_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Get judge behavior profile.
    - Requires ADMIN role
    - Returns scoring patterns and bias metrics
    """
    if not feature_flags.FEATURE_JUDGE_ANALYTICS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Judge analytics feature is disabled"
        )
    
    result = await JudgeAnalyticsService.get_judge_profile(
        db=db,
        judge_user_id=str(judge_id)
    )
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Judge profile not found"
        )
    
    return JudgeProfileResponse(**result)


@router.get(
    "/judge/bias-report",
    response_model=JudgeBiasReportResponse,
    summary="Get judge bias report",
    dependencies=[Depends(require_role([UserRole.ADMIN]))]
)
async def get_judge_bias_report(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Get aggregate judge bias report.
    - Requires ADMIN role
    - Identifies judges with systematic bias patterns
    """
    if not feature_flags.FEATURE_JUDGE_ANALYTICS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Judge analytics feature is disabled"
        )
    
    result = await JudgeAnalyticsService.get_judge_bias_report(db=db)
    
    return JudgeBiasReportResponse(**result)


# =============================================================================
# Trends Routes
# =============================================================================

@router.get(
    "/trends/{entity_type}/{entity_id}",
    response_model=TrendsResponse,
    summary="Get trends for entity",
    dependencies=[Depends(require_role([UserRole.ADMIN]))]
)
async def get_trends(
    entity_type: str,
    entity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Get performance trends for an entity.
    - Requires ADMIN role
    - Feature flag FEATURE_TREND_ENGINE must be enabled
    """
    if not feature_flags.FEATURE_TREND_ENGINE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Trend engine feature is disabled"
        )
    
    try:
        entity_enum = EntityType(entity_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid entity type: {entity_type}"
        )
    
    result = await TrendEngineService.get_trends(
        db=db,
        entity_type=entity_enum,
        entity_id=str(entity_id)
    )
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trends not found"
        )
    
    return TrendsResponse(**result)


@router.post(
    "/trends/{entity_type}/{entity_id}/compute",
    response_model=TrendsResponse,
    summary="Compute trends for entity",
    dependencies=[Depends(require_role([UserRole.ADMIN]))]
)
async def compute_trends(
    entity_type: str,
    entity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Compute and update trends for an entity.
    - Requires ADMIN role
    - Calculates moving averages, streaks, and momentum
    """
    if not feature_flags.FEATURE_TREND_ENGINE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Trend engine feature is disabled"
        )
    
    try:
        entity_enum = EntityType(entity_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid entity type: {entity_type}"
        )
    
    result = await TrendEngineService.compute_trends(
        db=db,
        entity_type=entity_enum,
        entity_id=str(entity_id),
        force=True
    )
    
    return TrendsResponse(**result)


@router.get(
    "/trends/hot-streaks/{entity_type}",
    response_model=HotStreaksResponse,
    summary="Get entities on hot streaks",
    dependencies=[Depends(require_role([UserRole.ADMIN]))]
)
async def get_hot_streaks(
    entity_type: str,
    min_streak: int = Query(default=3, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Get entities currently on winning streaks.
    - Requires ADMIN role
    - Minimum streak length configurable
    """
    if not feature_flags.FEATURE_TREND_ENGINE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Trend engine feature is disabled"
        )
    
    try:
        entity_enum = EntityType(entity_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid entity type: {entity_type}"
        )
    
    streaks = await TrendEngineService.get_hot_streaks(
        db=db,
        entity_type=entity_enum,
        min_streak=min_streak,
        limit=limit
    )
    
    return HotStreaksResponse(
        streaks=[TrendsResponse(**s) for s in streaks],
        total=len(streaks)
    )


@router.get(
    "/trends/momentum/{entity_type}",
    response_model=List[TrendsResponse],
    summary="Get trending entities",
    dependencies=[Depends(require_role([UserRole.ADMIN]))]
)
async def get_trending_entities(
    entity_type: str,
    min_momentum: float = Query(default=0.5, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Get entities with positive momentum.
    - Requires ADMIN role
    - Momentum = improvement_velocity / volatility
    """
    if not feature_flags.FEATURE_TREND_ENGINE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Trend engine feature is disabled"
        )
    
    try:
        entity_enum = EntityType(entity_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid entity type: {entity_type}"
        )
    
    trends = await TrendEngineService.get_trending_entities(
        db=db,
        entity_type=entity_enum,
        min_momentum=min_momentum,
        limit=limit
    )
    
    return [TrendsResponse(**t) for t in trends]
