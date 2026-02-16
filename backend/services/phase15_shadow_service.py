"""
Phase 15 — Shadow Scoring Service

Provides lightweight provisional scoring for LIVE matches.
Uses heuristics first, optionally micro LLM.
Never modifies official scores.
Auto-deletes on match freeze.
"""
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select as sa_select, delete as sa_delete
from fastapi import HTTPException, status

from backend.config.feature_flags import feature_flags
from backend.orm.phase14_round_engine import (
    TournamentMatch, MatchSpeakerTurn, MatchStatus, TurnStatus
)
from backend.orm.phase15_ai_evaluation import AIShadowScore
from backend.services.phase15_model_router import ModelRouterService, EvaluationMode


class ShadowScoringService:
    """
    Provides provisional shadow scoring during LIVE matches.
    Uses heuristics for cost efficiency.
    """

    HEURISTIC_VERSION = "1.0"

    @staticmethod
    async def evaluate_match_shadow(
        db: AsyncSession,
        match_id: uuid.UUID,
        use_llm: bool = False
    ) -> Dict[str, Any]:
        """
        Generate shadow evaluation for a LIVE match.

        Args:
            db: Database session
            match_id: Match UUID
            use_llm: Whether to use LLM (more expensive) or heuristics

        Returns:
            Dictionary with provisional scores

        Raises:
            HTTPException: If feature disabled or match not LIVE
        """
        # Verify feature flag
        if not feature_flags.FEATURE_AI_JUDGE_SHADOW:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="AI shadow scoring feature is disabled"
            )

        # Fetch match
        match_result = await db.execute(
            sa_select(TournamentMatch).where(TournamentMatch.id == match_id)
        )
        match = match_result.scalar_one_or_none()

        if not match:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Match {match_id} not found"
            )

        # Shadow scoring only for LIVE matches
        if match.status != MatchStatus.LIVE.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Shadow scoring only for LIVE matches. Status: {match.status}"
            )

        # Fetch turns
        turns_result = await db.execute(
            sa_select(MatchSpeakerTurn)
            .where(MatchSpeakerTurn.match_id == match_id)
            .order_by(MatchSpeakerTurn.turn_order)
        )
        turns = turns_result.scalars().all()

        # Generate heuristic scores
        scores = ShadowScoringService._calculate_heuristic_scores(turns)

        # Store shadow scores
        shadow_scores = []
        for turn in turns:
            role = turn.speaker_role
            if role in scores:
                score_data = scores[role]

                shadow_score = AIShadowScore(
                    match_id=match_id,
                    turn_id=turn.id,
                    provisional_score=score_data["total"],
                    confidence=score_data["confidence"],
                    legal_knowledge=score_data.get("legal_knowledge"),
                    application_of_law=score_data.get("application_of_law"),
                    structure_clarity=score_data.get("structure_clarity"),
                    etiquette=score_data.get("etiquette"),
                    heuristic_version=ShadowScoringService.HEURISTIC_VERSION,
                    used_llm="heuristic" if not use_llm else None,
                    expires_at=datetime.utcnow() + timedelta(hours=1)  # Auto-expire
                )
                db.add(shadow_score)
                shadow_scores.append(shadow_score)

        await db.flush()

        # Aggregate team scores
        petitioner_score = sum(
            s.provisional_score for s in shadow_scores
            if s.provisional_score and ShadowScoringService._is_petitioner_role(str(s.turn_id), turns)
        )
        respondent_score = sum(
            s.provisional_score for s in shadow_scores
            if s.provisional_score and not ShadowScoringService._is_petitioner_role(str(s.turn_id), turns)
        )

        return {
            "match_id": str(match_id),
            "mode": "shadow",
            "heuristic_version": ShadowScoringService.HEURISTIC_VERSION,
            "used_llm": use_llm,
            "provisional_winner": (
                "PETITIONER" if petitioner_score > respondent_score
                else "RESPONDENT" if respondent_score > petitioner_score
                else "TIE"
            ),
            "petitioner_provisional_score": round(petitioner_score, 2),
            "respondent_provisional_score": round(respondent_score, 2),
            "turn_scores": [s.to_dict() for s in shadow_scores],
            "generated_at": datetime.utcnow().isoformat(),
        }

    @staticmethod
    def _calculate_heuristic_scores(
        turns: List[MatchSpeakerTurn]
    ) -> Dict[str, Dict[str, float]]:
        """
        Calculate heuristic-based scores from turn data.
        """
        scores = {}

        for turn in turns:
            role = turn.speaker_role
            if not role:
                continue

            # Base score from time usage
            allocated = turn.allocated_seconds or 600
            actual = turn.actual_seconds or 0
            time_ratio = min(actual / allocated, 1.0) if allocated > 0 else 0

            # Status bonus
            status_bonus = 0
            if turn.status == TurnStatus.COMPLETED.value:
                status_bonus = 10
            elif turn.status == TurnStatus.ACTIVE.value:
                status_bonus = 5

            # Calculate component scores (simplified heuristics)
            legal_knowledge = min(15 + (time_ratio * 3), 18)
            application_of_law = min(14 + (time_ratio * 4), 18)
            structure_clarity = min(12 + (time_ratio * 5), 16)
            etiquette = min(6 + (time_ratio * 2), 8)
            rebuttal_strength = 0
            objection_handling = 0

            # Add rebuttal bonus for rebuttal turns
            if "rebuttal" in role:
                rebuttal_strength = min(12 + (time_ratio * 6), 18)

            # Total score
            total = (
                legal_knowledge + application_of_law + structure_clarity +
                etiquette + rebuttal_strength + objection_handling +
                status_bonus
            )

            # Confidence based on data quality
            confidence = 0.5 + (time_ratio * 0.3) + (0.2 if turn.status == TurnStatus.COMPLETED.value else 0)

            scores[role] = {
                "legal_knowledge": round(legal_knowledge, 1),
                "application_of_law": round(application_of_law, 1),
                "structure_clarity": round(structure_clarity, 1),
                "etiquette": round(etiquette, 1),
                "rebuttal_strength": round(rebuttal_strength, 1),
                "objection_handling": round(objection_handling, 1),
                "total": round(total, 1),
                "confidence": round(min(confidence, 1.0), 2),
            }

        return scores

    @staticmethod
    def _is_petitioner_role(turn_id: str, turns: List[MatchSpeakerTurn]) -> bool:
        """Check if turn belongs to petitioner team."""
        for turn in turns:
            if str(turn.id) == turn_id:
                return turn.speaker_role in ["p1", "p2", "rebuttal_p"]
        return False

    @staticmethod
    async def get_shadow_scores(
        db: AsyncSession,
        match_id: uuid.UUID
    ) -> List[Dict[str, Any]]:
        """
        Get all shadow scores for a match.
        """
        if not feature_flags.FEATURE_AI_JUDGE_SHADOW:
            return []

        result = await db.execute(
            sa_select(AIShadowScore)
            .where(AIShadowScore.match_id == match_id)
            .order_by(AIShadowScore.created_at.desc())
        )
        scores = result.scalars().all()

        return [s.to_dict() for s in scores]

    @staticmethod
    async def delete_shadow_scores(
        db: AsyncSession,
        match_id: uuid.UUID
    ) -> int:
        """
        Delete all shadow scores for a match.
        Called automatically when match is frozen.

        Returns:
            Number of deleted records
        """
        result = await db.execute(
            sa_delete(AIShadowScore)
            .where(AIShadowScore.match_id == match_id)
        )
        return result.rowcount or 0

    @staticmethod
    async def cleanup_expired_scores(db: AsyncSession) -> int:
        """
        Delete all expired shadow scores system-wide.
        Should be run periodically (e.g., hourly).

        Returns:
            Number of deleted records
        """
        result = await db.execute(
            sa_delete(AIShadowScore)
            .where(AIShadowScore.expires_at < datetime.utcnow())
        )
        return result.rowcount or 0


# Singleton instance
shadow_service = ShadowScoringService()
