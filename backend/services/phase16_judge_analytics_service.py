"""
Phase 16 — Judge Analytics Service.

Behavioral analytics for judges based on scoring patterns.
Deterministic calculations - no LLM calls.
"""
import uuid
from decimal import Decimal
from typing import List, Dict, Any, Optional
from datetime import datetime
from statistics import mean, stdev

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.orm.phase16_analytics import JudgeBehaviorProfile
from backend.orm.phase14_round_engine import (
    TournamentMatch, MatchStatus, MatchScoreLock
)
from backend.orm.phase15_ai_evaluation import AIMatchEvaluation


class JudgeAnalyticsService:
    """
    Service for computing judge behavior profiles.
    Analyzes scoring patterns, bias, and AI alignment.
    """
    
    @staticmethod
    async def recompute_judge_profile(
        db: AsyncSession,
        judge_user_id: str,
        force: bool = False
    ) -> Dict[str, Any]:
        """
        Recompute judge behavior profile from all scored matches.
        Uses FOR UPDATE locking for concurrency safety.
        """
        # Verify user is actually a judge (deferred import)
        from backend.orm.user import User, UserRole
        user_result = await db.execute(
            select(User).where(
                and_(
                    User.id == judge_user_id,
                    User.role.in_([UserRole.JUDGE, UserRole.ADMIN, UserRole.SUPER_ADMIN])
                )
            )
        )
        user = user_result.scalar_one_or_none()
        
        if not user:
            return {"error": "User is not a judge"}
        
        # Get or create profile with locking
        result = await db.execute(
            select(JudgeBehaviorProfile)
            .where(JudgeBehaviorProfile.judge_user_id == judge_user_id)
            .with_for_update()
        )
        profile = result.scalar_one_or_none()
        
        if not profile:
            profile = JudgeBehaviorProfile(
                id=str(uuid.uuid4()),
                judge_user_id=judge_user_id
            )
            db.add(profile)
        
        # Get all matches scored by this judge that are FROZEN
        # Note: This assumes we can link judges to matches through score_locks
        # In a real implementation, we'd need a judge_match_assignment table
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
                # This would be replaced with actual judge assignment logic
                MatchScoreLock.is_locked == True
            )
        )
        
        result = await db.execute(query)
        matches_data = result.all()
        
        if not matches_data:
            # No matches found
            profile.total_matches_scored = 0
            profile.avg_score_given = Decimal("0.00")
            profile.score_variance = Decimal("0.000")
            profile.ai_deviation_index = Decimal("0.000")
            profile.confidence_alignment_score = Decimal("0.000")
            profile.bias_petitioner_ratio = Decimal("0.000")
            profile.bias_respondent_ratio = Decimal("0.000")
            profile.strictness_index = Decimal("0.000")
            profile.last_updated = datetime.utcnow()
            await db.commit()
            return profile.to_dict()
        
        # Aggregate metrics
        total_scored = len(matches_data)
        all_scores = []
        ai_deviations = []
        petitioner_scores = []
        respondent_scores = []
        confidences = []
        
        for match, score_lock, ai_eval in matches_data:
            # Collect all scores given
            if score_lock.petitioner_total:
                pet_score = float(score_lock.petitioner_total)
                all_scores.append(pet_score)
                petitioner_scores.append(pet_score)
            
            if score_lock.respondent_total:
                resp_score = float(score_lock.respondent_total)
                all_scores.append(resp_score)
                respondent_scores.append(resp_score)
            
            # Calculate AI deviation
            if ai_eval and ai_eval.petitioner_score_json:
                if score_lock.petitioner_total:
                    pet_human = float(score_lock.petitioner_total)
                    pet_ai = ai_eval.petitioner_score_json.get("total", 0)
                    ai_deviations.append(abs(pet_human - pet_ai))
                
                if score_lock.respondent_total:
                    resp_human = float(score_lock.respondent_total)
                    resp_ai = ai_eval.respondent_score_json.get("total", 0)
                    ai_deviations.append(abs(resp_human - resp_ai))
                
                if ai_eval.confidence_score:
                    confidences.append(ai_eval.confidence_score)
        
        # Calculate average score given
        if all_scores:
            avg_given = Decimal(str(mean(all_scores)))
        else:
            avg_given = Decimal("0.00")
        
        # Calculate score variance
        if len(all_scores) > 1:
            try:
                variance = Decimal(str(stdev(all_scores)))
            except:
                variance = Decimal("0.000")
        else:
            variance = Decimal("0.000")
        
        # Calculate AI deviation index
        if ai_deviations:
            avg_deviation = Decimal(str(mean(ai_deviations)))
            # Normalize to 0-1 scale (assuming max deviation of 100)
            ai_dev_index = (avg_deviation / Decimal("100")).quantize(Decimal("0.001"))
        else:
            ai_dev_index = Decimal("0.000")
        
        # Calculate bias ratios
        if petitioner_scores and respondent_scores:
            avg_petitioner = mean(petitioner_scores)
            avg_respondent = mean(respondent_scores)
            
            # Bias ratio: how much higher one side scores than the other
            total_avg = (avg_petitioner + avg_respondent) / 2
            if total_avg > 0:
                bias_pet = Decimal(str(avg_petitioner / total_avg / 2))
                bias_resp = Decimal(str(avg_respondent / total_avg / 2))
            else:
                bias_pet = Decimal("0.500")
                bias_resp = Decimal("0.500")
        else:
            bias_pet = Decimal("0.000")
            bias_resp = Decimal("0.000")
        
        # Calculate confidence alignment
        # How often judge agrees with high-confidence AI evaluations
        if confidences:
            avg_confidence = Decimal(str(mean(confidences)))
        else:
            avg_confidence = Decimal("0.000")
        
        # Calculate strictness index
        # Difference between this judge's average and global average
        # This would need a global average query in production
        # For now, assuming global average of 70
        global_avg = Decimal("70.00")
        strictness = (avg_given - global_avg).quantize(Decimal("0.001"))
        
        # Update profile
        profile.total_matches_scored = total_scored
        profile.avg_score_given = avg_given.quantize(Decimal("0.01"))
        profile.score_variance = variance.quantize(Decimal("0.001"))
        profile.ai_deviation_index = ai_dev_index
        profile.confidence_alignment_score = avg_confidence.quantize(Decimal("0.001"))
        profile.bias_petitioner_ratio = bias_pet.quantize(Decimal("0.001"))
        profile.bias_respondent_ratio = bias_resp.quantize(Decimal("0.001"))
        profile.strictness_index = strictness.quantize(Decimal("0.001"))
        profile.last_updated = datetime.utcnow()
        
        await db.commit()
        return profile.to_dict()
    
    @staticmethod
    async def get_judge_profile(
        db: AsyncSession,
        judge_user_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get judge profile by user ID."""
        result = await db.execute(
            select(JudgeBehaviorProfile)
            .where(JudgeBehaviorProfile.judge_user_id == judge_user_id)
        )
        profile = result.scalar_one_or_none()
        
        if profile:
            return profile.to_dict()
        return None
    
    @staticmethod
    async def get_all_judge_profiles(
        db: AsyncSession,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get all judge profiles."""
        result = await db.execute(
            select(JudgeBehaviorProfile)
            .order_by(JudgeBehaviorProfile.total_matches_scored.desc())
            .limit(limit)
            .offset(offset)
        )
        profiles = result.scalars().all()
        return [p.to_dict() for p in profiles]
    
    @staticmethod
    async def get_judge_bias_report(
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Generate aggregate bias report for all judges.
        Identifies systematic bias patterns.
        """
        result = await db.execute(
            select(JudgeBehaviorProfile)
            .where(JudgeBehaviorProfile.total_matches_scored > 0)
        )
        profiles = result.scalars().all()
        
        if not profiles:
            return {
                "total_judges": 0,
                "avg_strictness": 0,
                "biased_judges": [],
                "high_deviation_judges": []
            }
        
        # Calculate aggregate metrics
        strictness_values = [float(p.strictness_index) for p in profiles]
        avg_strictness = mean(strictness_values)
        
        # Identify biased judges (bias ratio > 0.6 either direction)
        biased = []
        for p in profiles:
            if float(p.bias_petitioner_ratio) > 0.6 or float(p.bias_respondent_ratio) > 0.6:
                biased.append({
                    "judge_id": p.judge_user_id,
                    "petitioner_bias": float(p.bias_petitioner_ratio),
                    "respondent_bias": float(p.bias_respondent_ratio)
                })
        
        # Identify high deviation judges
        high_deviation = []
        for p in profiles:
            if float(p.ai_deviation_index) > 0.3:  # >30% deviation from AI
                high_deviation.append({
                    "judge_id": p.judge_user_id,
                    "deviation_index": float(p.ai_deviation_index),
                    "matches_scored": p.total_matches_scored
                })
        
        return {
            "total_judges": len(profiles),
            "avg_strictness": round(avg_strictness, 3),
            "biased_judges_count": len(biased),
            "biased_judges": biased,
            "high_deviation_count": len(high_deviation),
            "high_deviation_judges": high_deviation
        }
    
    @staticmethod
    async def batch_recompute_all_judges(
        db: AsyncSession,
        batch_size: int = 50
    ) -> Dict[str, int]:
        """
        Recompute all judge profiles.
        Processes in batches for memory efficiency.
        """
        # Get all judges (deferred import)
        from backend.orm.user import User, UserRole
        result = await db.execute(
            select(User.id).where(
                User.role.in_([UserRole.JUDGE, UserRole.ADMIN, UserRole.SUPER_ADMIN])
            ).order_by(User.id)
        )
        judge_ids = [row[0] for row in result.all()]
        
        processed = 0
        errors = 0
        
        for i in range(0, len(judge_ids), batch_size):
            batch = judge_ids[i:i + batch_size]
            
            for judge_id in batch:
                try:
                    await JudgeAnalyticsService.recompute_judge_profile(
                        db=db,
                        judge_user_id=judge_id,
                        force=True
                    )
                    processed += 1
                except Exception as e:
                    errors += 1
                    print(f"Error recomputing judge {judge_id}: {e}")
            
            await db.commit()
        
        return {
            "processed": processed,
            "errors": errors,
            "total_judges": len(judge_ids)
        }
