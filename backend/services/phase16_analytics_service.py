"""
Phase 16 — Performance Analytics Service.

Pure deterministic aggregation on top of Phase 14/15.
All writes use FOR UPDATE locking.
No LLM calls. 100% mathematical operations.
"""
import uuid
from decimal import Decimal
from typing import List, Dict, Any, Optional
from datetime import datetime
from statistics import mean, stdev
import math

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.orm.phase14_round_engine import (
    TournamentMatch, MatchStatus, MatchScoreLock
)
from backend.orm.phase15_ai_evaluation import AIMatchEvaluation
from backend.orm.phase16_analytics import (
    SpeakerPerformanceStats, TeamPerformanceStats, EntityType
)


class AnalyticsAggregatorService:
    """
    Service for computing performance analytics.
    All operations are deterministic and idempotent.
    """
    
    @staticmethod
    async def recompute_speaker(
        db: AsyncSession,
        user_id: str,
        force: bool = False
    ) -> Dict[str, Any]:
        """
        Recompute speaker performance stats from FROZEN + evaluated matches.
        Uses FOR UPDATE locking for concurrency safety.
        """
        # Get or create stats record with locking
        result = await db.execute(
            select(SpeakerPerformanceStats)
            .where(SpeakerPerformanceStats.user_id == user_id)
            .with_for_update()
        )
        stats = result.scalar_one_or_none()
        
        if not stats:
            stats = SpeakerPerformanceStats(
                id=str(uuid.uuid4()),
                user_id=user_id
            )
            db.add(stats)
        
        # Fetch all FROZEN matches with AI evaluations for this user
        # Query joins through match_speaker_turns to find user's matches
        query = select(
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
            and_(
                TournamentMatch.status == MatchStatus.FROZEN,
                or_(
                    TournamentMatch.petitioner_id == user_id,
                    TournamentMatch.respondent_id == user_id
                )
            )
        )
        
        result = await db.execute(query)
        matches_data = result.all()
        
        if not matches_data:
            # No matches found, reset to defaults
            stats.total_matches = 0
            stats.wins = 0
            stats.losses = 0
            stats.avg_score = Decimal("0.00")
            stats.avg_ai_score = Decimal("0.00")
            stats.confidence_weighted_score = Decimal("0.000")
            stats.peak_score = Decimal("0.00")
            stats.lowest_score = Decimal("0.00")
            stats.consistency_index = Decimal("0.000")
            stats.improvement_trend = Decimal("0.000")
            stats.last_updated = datetime.utcnow()
            await db.commit()
            return stats.to_dict()
        
        # Aggregate metrics
        total_matches = len(matches_data)
        wins = 0
        losses = 0
        scores = []
        ai_scores = []
        confidences = []
        
        for match, score_lock, ai_eval in matches_data:
            # Determine if user was petitioner or respondent
            is_petitioner = (match.petitioner_id == user_id)
            
            # Get user's score from official scoring
            if is_petitioner and score_lock.petitioner_total:
                user_score = float(score_lock.petitioner_total)
            elif not is_petitioner and score_lock.respondent_total:
                user_score = float(score_lock.respondent_total)
            else:
                continue
            
            scores.append(user_score)
            
            # Check for win/loss
            if score_lock.petitioner_total and score_lock.respondent_total:
                pet_score = float(score_lock.petitioner_total)
                resp_score = float(score_lock.respondent_total)
                
                if is_petitioner:
                    if pet_score > resp_score:
                        wins += 1
                    elif pet_score < resp_score:
                        losses += 1
                else:
                    if resp_score > pet_score:
                        wins += 1
                    elif resp_score < pet_score:
                        losses += 1
            
            # Get AI scores if available
            if ai_eval and ai_eval.petitioner_score_json:
                pet_ai = ai_eval.petitioner_score_json.get("total", 0)
                resp_ai = ai_eval.respondent_score_json.get("total", 0)
                ai_confidence = ai_eval.confidence_score or 0.5
                
                if is_petitioner:
                    ai_scores.append(pet_ai)
                else:
                    ai_scores.append(resp_ai)
                
                confidences.append(ai_confidence)
        
        # Compute aggregates
        if scores:
            avg_score = Decimal(str(mean(scores)))
            peak_score = Decimal(str(max(scores)))
            lowest_score = Decimal(str(min(scores)))
            
            # Consistency index = 1 / (std_dev + 1) to avoid div by zero
            if len(scores) > 1:
                try:
                    std_dev = stdev(scores)
                    consistency = Decimal(str(1 / (std_dev + 1)))
                except:
                    consistency = Decimal("1.000")
            else:
                consistency = Decimal("1.000")
        else:
            avg_score = Decimal("0.00")
            peak_score = Decimal("0.00")
            lowest_score = Decimal("0.00")
            consistency = Decimal("0.000")
        
        # AI scores and confidence weighting
        if ai_scores:
            avg_ai_score = Decimal(str(mean(ai_scores)))
            
            if confidences and sum(confidences) > 0:
                weighted_sum = sum(s * c for s, c in zip(ai_scores, confidences))
                conf_weighted = Decimal(str(weighted_sum / sum(confidences) / 100))
            else:
                conf_weighted = Decimal("0.000")
        else:
            avg_ai_score = Decimal("0.00")
            conf_weighted = Decimal("0.000")
        
        # Improvement trend (slope of last 5 vs first 5)
        if len(scores) >= 10:
            first_5 = mean(scores[:5])
            last_5 = mean(scores[-5:])
            trend = Decimal(str((last_5 - first_5) / 100))  # Normalized to 0-1
        else:
            trend = Decimal("0.000")
        
        # Update stats
        stats.total_matches = total_matches
        stats.wins = wins
        stats.losses = losses
        stats.avg_score = avg_score.quantize(Decimal("0.01"))
        stats.avg_ai_score = avg_ai_score.quantize(Decimal("0.01"))
        stats.confidence_weighted_score = conf_weighted.quantize(Decimal("0.001"))
        stats.consistency_index = consistency.quantize(Decimal("0.001"))
        stats.peak_score = peak_score.quantize(Decimal("0.01"))
        stats.lowest_score = lowest_score.quantize(Decimal("0.01"))
        stats.improvement_trend = trend.quantize(Decimal("0.001"))
        stats.last_updated = datetime.utcnow()
        
        await db.commit()
        return stats.to_dict()
    
    @staticmethod
    async def recompute_team(
        db: AsyncSession,
        team_id: str,
        force: bool = False
    ) -> Dict[str, Any]:
        """
        Recompute team performance stats.
        Computes synergy index, comeback index, freeze integrity.
        """
        # Get or create stats record with locking
        result = await db.execute(
            select(TeamPerformanceStats)
            .where(TeamPerformanceStats.team_id == team_id)
            .with_for_update()
        )
        stats = result.scalar_one_or_none()
        
        if not stats:
            stats = TeamPerformanceStats(
                id=str(uuid.uuid4()),
                team_id=team_id
            )
            db.add(stats)
        
        # Get team members (deferred import to avoid circular imports)
        from backend.orm.national_network import TournamentTeam
        team_result = await db.execute(
            select(TournamentTeam)
            .where(TournamentTeam.id == team_id)
        )
        team = team_result.scalar_one_or_none()
        
        if not team:
            return stats.to_dict()
        
        # Get members (this is a simplified version - actual implementation
        # would need to query team membership table)
        member_ids = []  # Would be populated from team_members table
        
        # Fetch matches where team members participated
        query = select(
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
        )
        
        result = await db.execute(query)
        matches_data = result.all()
        
        if not matches_data:
            stats.total_matches = 0
            stats.wins = 0
            stats.losses = 0
            stats.avg_score = Decimal("0.00")
            stats.avg_ai_score = Decimal("0.00")
            stats.team_synergy_index = Decimal("0.000")
            stats.comeback_index = Decimal("0.000")
            stats.freeze_integrity_score = Decimal("0.000")
            stats.last_updated = datetime.utcnow()
            await db.commit()
            return stats.to_dict()
        
        # Aggregate team metrics
        total_matches = len(matches_data)
        wins = 0
        losses = 0
        team_scores = []
        ai_confidences = []
        speaker_variances = []
        comeback_scores = []
        
        for match, score_lock, ai_eval in matches_data:
            # Team score (average of petitioner and respondent if both present)
            if score_lock.petitioner_total and score_lock.respondent_total:
                match_score = (
                    float(score_lock.petitioner_total) + 
                    float(score_lock.respondent_total)
                ) / 2
                team_scores.append(match_score)
                
                # Win/loss based on which side had higher score
                if float(score_lock.petitioner_total) > float(score_lock.respondent_total):
                    wins += 1
                elif float(score_lock.petitioner_total) < float(score_lock.respondent_total):
                    losses += 1
            
            # AI confidence for freeze integrity
            if ai_eval and ai_eval.confidence_score:
                ai_confidences.append(ai_eval.confidence_score)
        
        # Compute averages
        if team_scores:
            avg_score = Decimal(str(mean(team_scores)))
        else:
            avg_score = Decimal("0.00")
        
        # Freeze integrity = average AI confidence
        if ai_confidences:
            freeze_integrity = Decimal(str(mean(ai_confidences)))
        else:
            freeze_integrity = Decimal("0.000")
        
        # Team synergy (inverse of score variance between speakers)
        # Lower variance = higher synergy
        if len(team_scores) > 1:
            try:
                score_variance = stdev(team_scores)
                synergy = Decimal(str(1 / (score_variance + 1)))
            except:
                synergy = Decimal("0.500")
        else:
            synergy = Decimal("0.500")
        
        # Comeback index (placeholder - would need turn-level data)
        comeback = Decimal("0.000")
        
        # Update stats
        stats.total_matches = total_matches
        stats.wins = wins
        stats.losses = losses
        stats.avg_score = avg_score.quantize(Decimal("0.01"))
        stats.avg_ai_score = Decimal("0.00")  # Placeholder
        stats.team_synergy_index = synergy.quantize(Decimal("0.001"))
        stats.comeback_index = comeback.quantize(Decimal("0.001"))
        stats.freeze_integrity_score = freeze_integrity.quantize(Decimal("0.001"))
        stats.rank_points = Decimal("0.00")  # Updated by ranking engine
        stats.national_rank = 0
        stats.institution_rank = 0
        stats.last_updated = datetime.utcnow()
        
        await db.commit()
        return stats.to_dict()
    
    @staticmethod
    async def batch_recompute_all(
        db: AsyncSession,
        batch_size: int = 100
    ) -> Dict[str, int]:
        """
        Batch recompute all speakers and teams.
        Processes deterministically ordered by UUID.
        Commits per batch.
        """
        processed = {
            "speakers": 0,
            "teams": 0,
            "errors": 0
        }
        
        # Get all speaker IDs (users who have participated in matches)
        speaker_query = select(
            TournamentMatch.petitioner_id
        ).where(
            TournamentMatch.status == MatchStatus.FROZEN
        ).union(
            select(TournamentMatch.respondent_id).where(
                TournamentMatch.status == MatchStatus.FROZEN
            )
        ).order_by(TournamentMatch.petitioner_id)
        
        result = await db.execute(speaker_query)
        speaker_ids = [row[0] for row in result.all()]
        speaker_ids = list(set(speaker_ids))  # Deduplicate
        speaker_ids.sort()  # Deterministic ordering
        
        # Process speakers in batches
        for i in range(0, len(speaker_ids), batch_size):
            batch = speaker_ids[i:i + batch_size]
            
            for user_id in batch:
                try:
                    await AnalyticsAggregatorService.recompute_speaker(
                        db=db,
                        user_id=user_id,
                        force=True
                    )
                    processed["speakers"] += 1
                except Exception as e:
                    processed["errors"] += 1
                    # Log error but continue
                    print(f"Error recomputing speaker {user_id}: {e}")
            
            # Commit per batch
            await db.commit()
        
        # Get all team IDs (deferred import)
        from backend.orm.national_network import TournamentTeam
        team_query = select(TournamentTeam.id).order_by(TournamentTeam.id)
        result = await db.execute(team_query)
        team_ids = [row[0] for row in result.all()]
        
        # Process teams in batches
        for i in range(0, len(team_ids), batch_size):
            batch = team_ids[i:i + batch_size]
            
            for team_id in batch:
                try:
                    await AnalyticsAggregatorService.recompute_team(
                        db=db,
                        team_id=team_id,
                        force=True
                    )
                    processed["teams"] += 1
                except Exception as e:
                    processed["errors"] += 1
                    print(f"Error recomputing team {team_id}: {e}")
            
            await db.commit()
        
        return processed
    
    @staticmethod
    async def get_speaker_stats(
        db: AsyncSession,
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get speaker stats by user ID."""
        result = await db.execute(
            select(SpeakerPerformanceStats)
            .where(SpeakerPerformanceStats.user_id == user_id)
        )
        stats = result.scalar_one_or_none()
        
        if stats:
            return stats.to_dict()
        return None
    
    @staticmethod
    async def get_team_stats(
        db: AsyncSession,
        team_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get team stats by team ID."""
        result = await db.execute(
            select(TeamPerformanceStats)
            .where(TeamPerformanceStats.team_id == team_id)
        )
        stats = result.scalar_one_or_none()
        
        if stats:
            return stats.to_dict()
        return None
    
    @staticmethod
    async def get_leaderboard(
        db: AsyncSession,
        entity_type: EntityType,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get leaderboard for speakers or teams.
        Deterministic ordering by avg_score DESC, wins DESC, entity_id ASC.
        """
        if entity_type == EntityType.SPEAKER:
            result = await db.execute(
                select(SpeakerPerformanceStats)
                .order_by(
                    SpeakerPerformanceStats.avg_score.desc(),
                    SpeakerPerformanceStats.wins.desc(),
                    SpeakerPerformanceStats.user_id
                )
                .limit(limit)
            )
            return [s.to_dict() for s in result.scalars().all()]
        
        elif entity_type == EntityType.TEAM:
            result = await db.execute(
                select(TeamPerformanceStats)
                .order_by(
                    TeamPerformanceStats.avg_score.desc(),
                    TeamPerformanceStats.wins.desc(),
                    TeamPerformanceStats.team_id
                )
                .limit(limit)
            )
            return [s.to_dict() for s in result.scalars().all()]
        
        return []
