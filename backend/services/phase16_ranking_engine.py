"""
Phase 16 — Ranking Engine with ELO Formula.

Deterministic ranking system using ELO ratings.
All calculations are mathematical - no LLM calls.

Phase 20 Integration: Lifecycle guards prevent recompute on completed tournaments.
"""
import uuid
import math
import asyncio
from decimal import Decimal
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from sqlalchemy import select, func, and_, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.orm.phase16_analytics import (
    NationalRankings, EntityType, RankingTier,
    SpeakerPerformanceStats, TeamPerformanceStats
)
from backend.orm.phase14_round_engine import (
    TournamentMatch, MatchStatus, MatchScoreLock
)
from backend.orm.phase15_ai_evaluation import AIMatchEvaluation

# Global lock for preventing concurrent recompute operations
_recompute_lock = asyncio.Lock()


async def _check_lifecycle_guard(tournament_id: str) -> bool:
    """Phase 20: Check if ranking recompute is allowed."""
    try:
        from backend.config.feature_flags import feature_flags
        if not feature_flags.FEATURE_TOURNAMENT_LIFECYCLE:
            return True
        
        from backend.services.phase20_lifecycle_service import LifecycleService
        from backend.database import async_session_maker
        from uuid import UUID
        
        async with async_session_maker() as db:
            allowed, _ = await LifecycleService.check_operation_allowed(
                db, UUID(tournament_id), "ranking_recompute"
            )
            return allowed
    except Exception:
        return True  # Fail open


class RankingEngineService:
    """
    Service for computing ELO rankings and tier assignments.
    All operations are deterministic and reproducible.
    """
    
    # ELO constants
    DEFAULT_RATING = 1500.0
    DEFAULT_VOLATILITY = 0.06
    K_FACTOR_HIGH = 40.0  # For volatile players
    K_FACTOR_LOW = 20.0   # For stable players
    VOLATILITY_THRESHOLD = 0.2
    
    # Tier thresholds
    TIER_S_THRESHOLD = 2400.0
    TIER_A_THRESHOLD = 2000.0
    TIER_B_THRESHOLD = 1600.0
    
    @staticmethod
    def calculate_expected_score(rating_a: float, rating_b: float) -> float:
        """
        Calculate expected score using ELO formula.
        expected = 1 / (1 + 10^((opponent_rating - rating)/400))
        """
        return 1.0 / (1.0 + math.pow(10.0, (rating_b - rating_a) / 400.0))
    
    @staticmethod
    def calculate_new_rating(
        current_rating: float,
        expected_score: float,
        actual_score: float,
        confidence_weight: float,
        volatility: float
    ) -> float:
        """
        Calculate new rating.
        new_rating = rating + K * (actual - expected) * confidence_weight
        K = 40 if volatility > 0.2 else 20
        """
        # Determine K factor based on volatility
        if volatility > RankingEngineService.VOLATILITY_THRESHOLD:
            k_factor = RankingEngineService.K_FACTOR_HIGH
        else:
            k_factor = RankingEngineService.K_FACTOR_LOW
        
        # Calculate rating change
        rating_change = k_factor * (actual_score - expected_score) * confidence_weight
        
        # New rating
        new_rating = current_rating + rating_change
        
        # Ensure rating doesn't go below 0
        return max(0.0, new_rating)
    
    @staticmethod
    def assign_tier(rating: float) -> RankingTier:
        """
        Assign tier based on rating.
        S: >= 2400
        A: >= 2000
        B: >= 1600
        C: < 1600
        """
        if rating >= RankingEngineService.TIER_S_THRESHOLD:
            return RankingTier.S
        elif rating >= RankingEngineService.TIER_A_THRESHOLD:
            return RankingTier.A
        elif rating >= RankingEngineService.TIER_B_THRESHOLD:
            return RankingTier.B
        else:
            return RankingTier.C
    
    @staticmethod
    def calculate_volatility(
        current_volatility: float,
        expected_score: float,
        actual_score: float
    ) -> float:
        """
        Update volatility based on prediction accuracy.
        Higher prediction error = higher volatility.
        """
        prediction_error = abs(actual_score - expected_score)
        
        # Simple volatility update: blend current with recent error
        new_volatility = (current_volatility * 0.7) + (prediction_error * 0.3)
        
        # Clamp between 0 and 1
        return max(0.0, min(1.0, new_volatility))
    
    @staticmethod
    async def recompute_rankings(
        db: AsyncSession,
        entity_type: EntityType,
        season: str = "2026"
    ) -> Dict[str, Any]:
        """
        Recompute all rankings for an entity type.
        Processes matches chronologically and updates ratings.
        
        CONCURRENCY SAFETY: Uses global asyncio.Lock to prevent
        multiple simultaneous recomputes. Only one recompute
        can run at a time per process.
        """
        # Acquire global lock to prevent concurrent recomputes
        if _recompute_lock.locked():
            return {
                "error": "Recompute already in progress",
                "status": "skipped",
                "reason": "concurrent_request"
            }
        
        async with _recompute_lock:
            return await RankingEngineService._do_recompute_rankings(
                db, entity_type, season
            )
    
    @staticmethod
    async def _do_recompute_rankings(
        db: AsyncSession,
        entity_type: EntityType,
        season: str = "2026"
    ) -> Dict[str, Any]:
        # Get all entities of this type with stats
        if entity_type == EntityType.SPEAKER:
            stats_result = await db.execute(
                select(SpeakerPerformanceStats)
                .where(SpeakerPerformanceStats.total_matches > 0)
            )
            entities = stats_result.scalars().all()
            entity_ids = [e.user_id for e in entities]
        elif entity_type == EntityType.TEAM:
            stats_result = await db.execute(
                select(TeamPerformanceStats)
                .where(TeamPerformanceStats.total_matches > 0)
            )
            entities = stats_result.scalars().all()
            entity_ids = [e.team_id for e in entities]
        else:
            return {"error": "Unsupported entity type"}
        
        # Get or create ranking records for all entities
        rankings_map = {}
        for entity_id in entity_ids:
            # Lock record for update
            result = await db.execute(
                select(NationalRankings)
                .where(
                    and_(
                        NationalRankings.entity_type == entity_type,
                        NationalRankings.entity_id == entity_id,
                        NationalRankings.season == season
                    )
                )
                .with_for_update()
            )
            ranking = result.scalar_one_or_none()
            
            if not ranking:
                ranking = NationalRankings(
                    id=str(uuid.uuid4()),
                    entity_type=entity_type,
                    entity_id=entity_id,
                    season=season,
                    rating_score=RankingEngineService.DEFAULT_RATING,
                    elo_rating=RankingEngineService.DEFAULT_RATING,
                    volatility=RankingEngineService.DEFAULT_VOLATILITY,
                    confidence_score=0.0,
                    tier=RankingTier.C,
                    rank_position=0,
                    previous_rank=0,
                    rank_movement=0
                )
                db.add(ranking)
            
            rankings_map[entity_id] = ranking
        
        # Get all FROZEN matches with results
        # Order by completion time for chronological processing
        matches_query = select(
            TournamentMatch,
            MatchScoreLock,
            AIMatchEvaluation
        ).select_from(TournamentMatch).join(
            MatchScoreLock,
            TournamentMatch.id == MatchScoreLock.match_id
        ).outerjoin(
            AIMatchEvaluation,
            and_(
                AIMatchEvaluation.match_id == TournamentMatch.id,
                AIMatchEvaluation.mode == "official",
                AIMatchEvaluation.evaluation_status == "completed"
            )
        ).where(
            TournamentMatch.status == MatchStatus.FROZEN
        ).order_by(
            TournamentMatch.completed_at.asc()
        )
        
        result = await db.execute(matches_query)
        matches_data = result.all()
        
        # Process each match and update ratings
        for match, score_lock, ai_eval in matches_data:
            # Skip if no scores
            if not score_lock.petitioner_total or not score_lock.respondent_total:
                continue
            
            pet_score = float(score_lock.petitioner_total)
            resp_score = float(score_lock.respondent_total)
            
            # PHASE 17 INTEGRATION: Check for appeal override
            effective_winner = None
            if feature_flags.FEATURE_APPEAL_OVERRIDE_RANKING:
                from backend.services.phase17_appeal_service import AppealService
                effective_winner = await AppealService.get_effective_winner(db, match.id)
            
            # Get AI confidence if available
            if ai_eval and ai_eval.confidence_score:
                confidence = ai_eval.confidence_score
            else:
                confidence = 0.5  # Default confidence
            
            # Determine actual scores (1 for win, 0.5 for tie, 0 for loss)
            # Use effective winner from appeal if available
            if effective_winner:
                if effective_winner == "petitioner":
                    pet_actual = 1.0
                    resp_actual = 0.0
                elif effective_winner == "respondent":
                    pet_actual = 0.0
                    resp_actual = 1.0
                else:
                    # Fallback to score-based determination
                    if pet_score > resp_score:
                        pet_actual = 1.0
                        resp_actual = 0.0
                    elif pet_score < resp_score:
                        pet_actual = 0.0
                        resp_actual = 1.0
                    else:
                        pet_actual = 0.5
                        resp_actual = 0.5
            else:
                # No override, use original scores
                if pet_score > resp_score:
                    pet_actual = 1.0
                    resp_actual = 0.0
                elif pet_score < resp_score:
                    pet_actual = 0.0
                    resp_actual = 1.0
                else:
                    pet_actual = 0.5
                    resp_actual = 0.5
            
            # Update petitioner rating if tracked
            if entity_type == EntityType.SPEAKER and match.petitioner_id in rankings_map:
                pet_ranking = rankings_map[match.petitioner_id]
                
                # Get opponent rating
                if match.respondent_id in rankings_map:
                    resp_rating = rankings_map[match.respondent_id].elo_rating
                else:
                    resp_rating = RankingEngineService.DEFAULT_RATING
                
                # Calculate expected and new rating
                expected = RankingEngineService.calculate_expected_score(
                    pet_ranking.elo_rating, resp_rating
                )
                new_rating = RankingEngineService.calculate_new_rating(
                    pet_ranking.elo_rating,
                    expected,
                    pet_actual,
                    confidence,
                    pet_ranking.volatility
                )
                
                # Update volatility
                new_volatility = RankingEngineService.calculate_volatility(
                    pet_ranking.volatility,
                    expected,
                    pet_actual
                )
                
                # Update record
                pet_ranking.elo_rating = new_rating
                pet_ranking.volatility = new_volatility
                pet_ranking.confidence_score = confidence
            
            # Update respondent rating if tracked
            if entity_type == EntityType.SPEAKER and match.respondent_id in rankings_map:
                resp_ranking = rankings_map[match.respondent_id]
                
                # Get opponent rating
                if match.petitioner_id in rankings_map:
                    pet_rating = rankings_map[match.petitioner_id].elo_rating
                else:
                    pet_rating = RankingEngineService.DEFAULT_RATING
                
                # Calculate expected and new rating
                expected = RankingEngineService.calculate_expected_score(
                    resp_ranking.elo_rating, pet_rating
                )
                new_rating = RankingEngineService.calculate_new_rating(
                    resp_ranking.elo_rating,
                    expected,
                    resp_actual,
                    confidence,
                    resp_ranking.volatility
                )
                
                # Update volatility
                new_volatility = RankingEngineService.calculate_volatility(
                    resp_ranking.volatility,
                    expected,
                    resp_actual
                )
                
                # Update record
                resp_ranking.elo_rating = new_rating
                resp_ranking.volatility = new_volatility
                resp_ranking.confidence_score = confidence
        
        # Sync rating_score with elo_rating
        for ranking in rankings_map.values():
            ranking.rating_score = ranking.elo_rating
            ranking.tier = RankingEngineService.assign_tier(ranking.rating_score)
        
        # Calculate rank positions
        # Deterministic ordering: rating DESC, confidence DESC, entity_id ASC
        sorted_rankings = sorted(
            rankings_map.values(),
            key=lambda r: (-r.rating_score, -r.confidence_score, r.entity_id)
        )
        
        # Assign ranks
        for i, ranking in enumerate(sorted_rankings, start=1):
            ranking.previous_rank = ranking.rank_position
            ranking.rank_position = i
            ranking.rank_movement = ranking.previous_rank - ranking.rank_position
            ranking.last_calculated = datetime.utcnow()
        
        await db.commit()
        
        return {
            "entity_type": entity_type.value,
            "season": season,
            "total_ranked": len(rankings_map),
            "matches_processed": len(matches_data),
            "top_rating": sorted_rankings[0].rating_score if sorted_rankings else 0,
            "avg_rating": sum(r.rating_score for r in sorted_rankings) / len(sorted_rankings) if sorted_rankings else 0
        }
    
    @staticmethod
    async def get_rankings(
        db: AsyncSession,
        entity_type: EntityType,
        season: str = "2026",
        tier: Optional[RankingTier] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get rankings for an entity type.
        Deterministic ordering guaranteed.
        """
        query = select(NationalRankings).where(
            and_(
                NationalRankings.entity_type == entity_type,
                NationalRankings.season == season
            )
        )
        
        if tier:
            query = query.where(NationalRankings.tier == tier)
        
        # Deterministic ordering
        query = query.order_by(
            desc(NationalRankings.rating_score),
            desc(NationalRankings.confidence_score),
            asc(NationalRankings.entity_id)
        ).limit(limit).offset(offset)
        
        result = await db.execute(query)
        rankings = result.scalars().all()
        
        return [r.to_dict() for r in rankings]
    
    @staticmethod
    async def get_entity_ranking(
        db: AsyncSession,
        entity_type: EntityType,
        entity_id: str,
        season: str = "2026"
    ) -> Optional[Dict[str, Any]]:
        """Get ranking for a specific entity."""
        result = await db.execute(
            select(NationalRankings).where(
                and_(
                    NationalRankings.entity_type == entity_type,
                    NationalRankings.entity_id == entity_id,
                    NationalRankings.season == season
                )
            )
        )
        ranking = result.scalar_one_or_none()
        
        if ranking:
            return ranking.to_dict()
        return None
    
    @staticmethod
    async def get_tier_distribution(
        db: AsyncSession,
        entity_type: EntityType,
        season: str = "2026"
    ) -> Dict[str, int]:
        """Get distribution of entities across tiers."""
        result = await db.execute(
            select(
                NationalRankings.tier,
                func.count(NationalRankings.id).label("count")
            ).where(
                and_(
                    NationalRankings.entity_type == entity_type,
                    NationalRankings.season == season
                )
            ).group_by(NationalRankings.tier)
        )
        
        distribution = {}
        for tier, count in result.all():
            distribution[tier.value] = count
        
        # Ensure all tiers are present
        for tier in RankingTier:
            if tier.value not in distribution:
                distribution[tier.value] = 0
        
        return distribution
    
    @staticmethod
    async def batch_update_all_rankings(
        db: AsyncSession,
        season: str = "2026"
    ) -> Dict[str, Any]:
        """
        Update rankings for all entity types.
        Returns summary of updates.
        """
        results = {}
        
        for entity_type in [EntityType.SPEAKER, EntityType.TEAM]:
            result = await RankingEngineService.recompute_rankings(
                db=db,
                entity_type=entity_type,
                season=season
            )
            results[entity_type.value] = result
        
        return results
