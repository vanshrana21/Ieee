"""
Phase 16 — Trend Engine Service.

Computes performance trends, streaks, and momentum metrics.
All deterministic mathematical operations.
"""
import uuid
from decimal import Decimal
from typing import List, Dict, Any, Optional
from datetime import datetime
from statistics import mean, stdev

from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.orm.phase16_analytics import (
    PerformanceTrends, EntityType, StreakType,
    SpeakerPerformanceStats, TeamPerformanceStats
)
from backend.orm.phase14_round_engine import (
    TournamentMatch, MatchStatus, MatchScoreLock
)


class TrendEngineService:
    """
    Service for computing performance trends and momentum metrics.
    Tracks moving averages, streaks, and volatility.
    """
    
    @staticmethod
    async def compute_trends(
        db: AsyncSession,
        entity_type: EntityType,
        entity_id: str,
        force: bool = False
    ) -> Dict[str, Any]:
        """
        Compute trends for an entity (speaker or team).
        Uses FOR UPDATE locking for concurrency safety.
        """
        # Get or create trend record with locking
        result = await db.execute(
            select(PerformanceTrends)
            .where(
                and_(
                    PerformanceTrends.entity_type == entity_type,
                    PerformanceTrends.entity_id == entity_id
                )
            )
            .with_for_update()
        )
        trends = result.scalar_one_or_none()
        
        if not trends:
            trends = PerformanceTrends(
                id=str(uuid.uuid4()),
                entity_type=entity_type,
                entity_id=entity_id
            )
            db.add(trends)
        
        # Get match history for this entity
        if entity_type == EntityType.SPEAKER:
            # Get matches where entity was petitioner or respondent
            query = select(
                TournamentMatch,
                MatchScoreLock
            ).select_from(TournamentMatch).join(
                MatchScoreLock,
                TournamentMatch.id == MatchScoreLock.match_id
            ).where(
                and_(
                    TournamentMatch.status == MatchStatus.FROZEN,
                    or_(
                        TournamentMatch.petitioner_id == entity_id,
                        TournamentMatch.respondent_id == entity_id
                    )
                )
            ).order_by(TournamentMatch.completed_at.asc())
        elif entity_type == EntityType.TEAM:
            # For teams, we'd need to query team membership
            # Simplified: query matches with team_id (placeholder)
            query = select(
                TournamentMatch,
                MatchScoreLock
            ).select_from(TournamentMatch).join(
                MatchScoreLock,
                TournamentMatch.id == MatchScoreLock.match_id
            ).where(
                TournamentMatch.status == MatchStatus.FROZEN
            ).order_by(TournamentMatch.completed_at.asc())
        else:
            return {"error": "Unsupported entity type"}
        
        result = await db.execute(query)
        matches_data = result.all()
        
        if not matches_data:
            # No matches found
            trends.last_5_avg = Decimal("0.00")
            trends.last_10_avg = Decimal("0.00")
            trends.improvement_velocity = Decimal("0.000")
            trends.volatility_index = Decimal("0.000")
            trends.streak_type = StreakType.NONE
            trends.streak_count = 0
            trends.momentum_score = Decimal("0.000")
            trends.risk_index = Decimal("0.000")
            trends.last_updated = datetime.utcnow()
            await db.commit()
            return trends.to_dict()
        
        # Extract scores and results
        scores = []
        results = []  # 'W' for win, 'L' for loss, 'D' for draw
        
        for match, score_lock in matches_data:
            if entity_type == EntityType.SPEAKER:
                is_petitioner = (match.petitioner_id == entity_id)
                
                if is_petitioner and score_lock.petitioner_total:
                    score = float(score_lock.petitioner_total)
                    opponent_score = float(score_lock.respondent_total) if score_lock.respondent_total else 0
                elif not is_petitioner and score_lock.respondent_total:
                    score = float(score_lock.respondent_total)
                    opponent_score = float(score_lock.petitioner_total) if score_lock.petitioner_total else 0
                else:
                    continue
                
                scores.append(score)
                
                # Determine result
                if score > opponent_score:
                    results.append('W')
                elif score < opponent_score:
                    results.append('L')
                else:
                    results.append('D')
        
        # Calculate moving averages
        if len(scores) >= 5:
            last_5_avg = Decimal(str(mean(scores[-5:])))
        else:
            last_5_avg = Decimal(str(mean(scores))) if scores else Decimal("0.00")
        
        if len(scores) >= 10:
            last_10_avg = Decimal(str(mean(scores[-10:])))
        else:
            last_10_avg = Decimal(str(mean(scores))) if scores else Decimal("0.00")
        
        # Calculate improvement velocity
        # Slope of performance over time (last 5 vs previous 5)
        if len(scores) >= 10:
            first_5 = mean(scores[-10:-5])
            last_5 = mean(scores[-5:])
            velocity = Decimal(str((last_5 - first_5) / 100))
        elif len(scores) >= 2:
            # Simple difference between first and last
            velocity = Decimal(str((scores[-1] - scores[0]) / (len(scores) * 100)))
        else:
            velocity = Decimal("0.000")
        
        # Calculate volatility
        if len(scores) > 1:
            try:
                vol = stdev(scores)
                volatility = Decimal(str(vol / 100))  # Normalize
            except:
                volatility = Decimal("0.000")
        else:
            volatility = Decimal("0.000")
        
        # Detect streak
        streak_type, streak_count = TrendEngineService._detect_streak(results)
        
        # Calculate momentum
        # momentum = improvement_velocity / volatility (safe divide)
        if volatility > 0:
            momentum = (velocity / volatility).quantize(Decimal("0.001"))
        else:
            # If no volatility, momentum equals velocity
            momentum = velocity.quantize(Decimal("0.001"))
        
        # Calculate risk index
        # Higher volatility + negative velocity = higher risk
        risk_components = []
        if volatility > 0:
            risk_components.append(float(volatility))
        if velocity < 0:
            risk_components.append(abs(float(velocity)))
        
        if risk_components:
            risk = Decimal(str(mean(risk_components))).quantize(Decimal("0.001"))
        else:
            risk = Decimal("0.000")
        
        # Update trends
        trends.last_5_avg = last_5_avg.quantize(Decimal("0.01"))
        trends.last_10_avg = last_10_avg.quantize(Decimal("0.01"))
        trends.improvement_velocity = velocity.quantize(Decimal("0.001"))
        trends.volatility_index = volatility.quantize(Decimal("0.001"))
        trends.streak_type = streak_type
        trends.streak_count = streak_count
        trends.momentum_score = momentum
        trends.risk_index = risk
        trends.last_updated = datetime.utcnow()
        
        await db.commit()
        return trends.to_dict()
    
    @staticmethod
    def _detect_streak(results: List[str]) -> tuple:
        """
        Detect current streak from results.
        Returns (streak_type, streak_count).
        """
        if not results:
            return StreakType.NONE, 0
        
        # Start from the end and count consecutive same results
        last_result = results[-1]
        streak_count = 1
        
        for i in range(len(results) - 2, -1, -1):
            if results[i] == last_result:
                streak_count += 1
            else:
                break
        
        # Map result to streak type
        if last_result == 'W':
            return StreakType.WIN, streak_count
        elif last_result == 'L':
            return StreakType.LOSS, streak_count
        else:
            return StreakType.NONE, 0
    
    @staticmethod
    async def get_trends(
        db: AsyncSession,
        entity_type: EntityType,
        entity_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get trends for an entity."""
        result = await db.execute(
            select(PerformanceTrends)
            .where(
                and_(
                    PerformanceTrends.entity_type == entity_type,
                    PerformanceTrends.entity_id == entity_id
                )
            )
        )
        trends = result.scalar_one_or_none()
        
        if trends:
            return trends.to_dict()
        return None
    
    @staticmethod
    async def batch_compute_all_trends(
        db: AsyncSession,
        entity_type: EntityType,
        batch_size: int = 100
    ) -> Dict[str, int]:
        """
        Compute trends for all entities of a type.
        Processes in batches.
        """
        # Get all entity IDs with stats
        if entity_type == EntityType.SPEAKER:
            result = await db.execute(
                select(SpeakerPerformanceStats.user_id)
                .where(SpeakerPerformanceStats.total_matches > 0)
                .order_by(SpeakerPerformanceStats.user_id)
            )
        elif entity_type == EntityType.TEAM:
            result = await db.execute(
                select(TeamPerformanceStats.team_id)
                .where(TeamPerformanceStats.total_matches > 0)
                .order_by(TeamPerformanceStats.team_id)
            )
        else:
            return {"processed": 0, "errors": 0}
        
        entity_ids = [row[0] for row in result.all()]
        
        processed = 0
        errors = 0
        
        for i in range(0, len(entity_ids), batch_size):
            batch = entity_ids[i:i + batch_size]
            
            for entity_id in batch:
                try:
                    await TrendEngineService.compute_trends(
                        db=db,
                        entity_type=entity_type,
                        entity_id=entity_id
                    )
                    processed += 1
                except Exception as e:
                    errors += 1
                    print(f"Error computing trends for {entity_id}: {e}")
            
            await db.commit()
        
        return {
            "processed": processed,
            "errors": errors,
            "total_entities": len(entity_ids)
        }
    
    @staticmethod
    async def get_trending_entities(
        db: AsyncSession,
        entity_type: EntityType,
        min_momentum: float = 0.5,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get entities with positive momentum.
        """
        result = await db.execute(
            select(PerformanceTrends)
            .where(
                and_(
                    PerformanceTrends.entity_type == entity_type,
                    PerformanceTrends.momentum_score >= min_momentum
                )
            )
            .order_by(desc(PerformanceTrends.momentum_score))
            .limit(limit)
        )
        trends = result.scalars().all()
        return [t.to_dict() for t in trends]
    
    @staticmethod
    async def get_hot_streaks(
        db: AsyncSession,
        entity_type: EntityType,
        min_streak: int = 3,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get entities on winning streaks.
        """
        result = await db.execute(
            select(PerformanceTrends)
            .where(
                and_(
                    PerformanceTrends.entity_type == entity_type,
                    PerformanceTrends.streak_type == StreakType.WIN,
                    PerformanceTrends.streak_count >= min_streak
                )
            )
            .order_by(desc(PerformanceTrends.streak_count))
            .limit(limit)
        )
        trends = result.scalars().all()
        return [t.to_dict() for t in trends]
    
    @staticmethod
    async def get_risky_entities(
        db: AsyncSession,
        entity_type: EntityType,
        min_risk: float = 0.5,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get entities with high risk (volatile + declining).
        """
        result = await db.execute(
            select(PerformanceTrends)
            .where(
                and_(
                    PerformanceTrends.entity_type == entity_type,
                    PerformanceTrends.risk_index >= min_risk
                )
            )
            .order_by(desc(PerformanceTrends.risk_index))
            .limit(limit)
        )
        trends = result.scalars().all()
        return [t.to_dict() for t in trends]
