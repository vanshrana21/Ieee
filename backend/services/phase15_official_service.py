"""
Phase 15 — Official Evaluation Service

Provides official AI evaluations for FROZEN matches only.
Uses caching, hash verification, and deterministic routing.
"""
import uuid
import json
from typing import Dict, Any, Optional
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select as sa_select
from fastapi import HTTPException, status

from backend.config.feature_flags import feature_flags
from backend.orm.phase14_round_engine import TournamentMatch, MatchStatus
from backend.orm.phase15_ai_evaluation import (
    AIMatchEvaluation, AIEvaluationCache
)
from backend.services.phase15_snapshot_builder import SnapshotBuilderService
from backend.services.phase15_hash_service import HashService
from backend.services.phase15_model_router import ModelRouterService, EvaluationMode
from backend.services.phase15_credit_optimizer import CreditOptimizerService


class OfficialEvaluationService:
    """
    Provides official AI evaluations for frozen matches.
    All evaluations are cached and hash-verified.
    """

    @staticmethod
    async def evaluate_match_official(
        db: AsyncSession,
        match_id: uuid.UUID,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        Generate official AI evaluation for a FROZEN match.

        Args:
            db: Database session
            match_id: Match UUID
            force_refresh: Whether to force new evaluation (ignore cache)

        Returns:
            Dictionary with evaluation results

        Raises:
            HTTPException: If feature disabled, match not frozen, etc.
        """
        # Step 1: Verify feature flag
        if not feature_flags.FEATURE_AI_JUDGE_OFFICIAL:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="AI official evaluation feature is disabled"
            )

        # Step 2: Build snapshot (validates match is frozen)
        snapshot_result = await SnapshotBuilderService.build_match_snapshot(
            db=db,
            match_id=match_id,
            validate_frozen=True
        )

        snapshot = snapshot_result["snapshot"]
        snapshot_hash = snapshot_result["snapshot_hash"]

        # Step 3: Check cache (if not forcing refresh)
        if not force_refresh and feature_flags.FEATURE_AI_JUDGE_CACHE:
            cached = await OfficialEvaluationService._get_cached_evaluation(
                db=db,
                snapshot_hash=snapshot_hash
            )
            if cached:
                # Update hit count
                cached.hit_count += 1
                await db.flush()

                return {
                    "match_id": str(match_id),
                    "snapshot_hash": snapshot_hash,
                    "evaluation_hash": cached.evaluation_hash if hasattr(cached, 'evaluation_hash') else None,
                    "model_name": cached.model_name,
                    "mode": "official",
                    "cached": True,
                    "hit_count": cached.hit_count,
                    "petitioner_score": cached.cached_response_json.get("petitioner"),
                    "respondent_score": cached.cached_response_json.get("respondent"),
                    "winner": cached.winner,
                    "reasoning_summary": cached.cached_response_json.get("reasoning_summary"),
                    "confidence_score": cached.confidence_score,
                    "token_usage": None,  # Cached result has no token usage
                }

        # Step 4: Route model
        routing = ModelRouterService.route_evaluation(
            mode=EvaluationMode.OFFICIAL.value,
            is_finals=False  # Could be determined from context
        )
        model_name = routing["model_name"]

        # Step 5: Generate AI evaluation (simulated for now)
        # In production, this would call actual LLM API
        ai_response = OfficialEvaluationService._simulate_ai_evaluation(snapshot)

        # Step 6: Validate response
        validated = OfficialEvaluationService._validate_ai_response(ai_response)
        if not validated["valid"]:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"AI response validation failed: {validated['errors']}"
            )

        # Step 7: Compute evaluation hash
        evaluation_hash = HashService.generate_evaluation_hash(
            snapshot_hash=snapshot_hash,
            model_name=model_name,
            response_data=ai_response
        )

        # Step 8: Store evaluation
        evaluation = AIMatchEvaluation(
            match_id=match_id,
            snapshot_hash=snapshot_hash,
            evaluation_hash=evaluation_hash,
            model_name=model_name,
            mode=EvaluationMode.OFFICIAL.value,
            petitioner_score_json=ai_response.get("petitioner"),
            respondent_score_json=ai_response.get("respondent"),
            winner=ai_response.get("winner"),
            reasoning_summary=ai_response.get("reasoning_summary"),
            confidence_score=ai_response.get("confidence"),
            evaluation_status="completed",
            token_usage=routing.get("max_tokens", 500),
        )
        db.add(evaluation)

        # Step 9: Cache result
        if feature_flags.FEATURE_AI_JUDGE_CACHE:
            cache_entry = AIEvaluationCache(
                snapshot_hash=snapshot_hash,
                model_name=model_name,
                cached_response_json=ai_response,
                winner=ai_response.get("winner"),
                confidence_score=ai_response.get("confidence"),
                hit_count=1,
                expires_at=datetime.utcnow() + routing.get("cache_duration", 86400)  # 24 hours
            )
            db.add(cache_entry)

        await db.flush()

        return {
            "match_id": str(match_id),
            "snapshot_hash": snapshot_hash,
            "evaluation_hash": evaluation_hash,
            "model_name": model_name,
            "mode": "official",
            "cached": False,
            "petitioner_score": ai_response.get("petitioner"),
            "respondent_score": ai_response.get("respondent"),
            "winner": ai_response.get("winner"),
            "reasoning_summary": ai_response.get("reasoning_summary"),
            "confidence_score": ai_response.get("confidence"),
            "token_usage": routing.get("max_tokens", 500),
            "created_at": datetime.utcnow().isoformat(),
        }

    @staticmethod
    async def verify_evaluation(
        db: AsyncSession,
        match_id: uuid.UUID,
        evaluation_id: Optional[uuid.UUID] = None
    ) -> Dict[str, Any]:
        """
        Verify integrity of an AI evaluation.

        Args:
            db: Database session
            match_id: Match UUID
            evaluation_id: Specific evaluation to verify (optional)

        Returns:
            Verification result
        """
        # Build current snapshot
        snapshot_result = await SnapshotBuilderService.build_match_snapshot(
            db=db,
            match_id=match_id,
            validate_frozen=False
        )
        current_hash = snapshot_result["snapshot_hash"]

        # Get evaluation
        if evaluation_id:
            result = await db.execute(
                sa_select(AIMatchEvaluation)
                .where(AIMatchEvaluation.id == evaluation_id)
            )
            evaluation = result.scalar_one_or_none()
        else:
            # Get latest evaluation
            result = await db.execute(
                sa_select(AIMatchEvaluation)
                .where(AIMatchEvaluation.match_id == match_id)
                .order_by(AIMatchEvaluation.created_at.desc())
                .limit(1)
            )
            evaluation = result.scalar_one_or_none()

        if not evaluation:
            return {
                "match_id": str(match_id),
                "verified": False,
                "error": "No evaluation found",
            }

        # Verify snapshot hash matches
        snapshot_valid = HashService.compare_hashes(
            current_hash,
            evaluation.snapshot_hash
        )

        # Reconstruct response data
        response_data = {
            "petitioner": evaluation.petitioner_score_json,
            "respondent": evaluation.respondent_score_json,
            "winner": evaluation.winner,
            "reasoning_summary": evaluation.reasoning_summary,
            "confidence": evaluation.confidence_score,
        }

        # Verify evaluation hash
        computed_hash = HashService.generate_evaluation_hash(
            snapshot_hash=evaluation.snapshot_hash,
            model_name=evaluation.model_name,
            response_data=response_data
        )
        evaluation_valid = HashService.compare_hashes(
            computed_hash,
            evaluation.evaluation_hash
        )

        return {
            "match_id": str(match_id),
            "evaluation_id": str(evaluation.id),
            "snapshot_valid": snapshot_valid,
            "evaluation_valid": evaluation_valid,
            "verified": snapshot_valid and evaluation_valid,
            "snapshot_hash_stored": evaluation.snapshot_hash,
            "snapshot_hash_current": current_hash,
            "evaluation_hash_stored": evaluation.evaluation_hash,
            "evaluation_hash_computed": computed_hash,
            "match_frozen": snapshot_result["is_frozen"],
        }

    @staticmethod
    async def get_evaluation_history(
        db: AsyncSession,
        match_id: uuid.UUID
    ) -> Dict[str, Any]:
        """
        Get evaluation history for a match.
        """
        result = await db.execute(
            sa_select(AIMatchEvaluation)
            .where(AIMatchEvaluation.match_id == match_id)
            .order_by(AIMatchEvaluation.created_at.desc())
        )
        evaluations = result.scalars().all()

        return {
            "match_id": str(match_id),
            "evaluation_count": len(evaluations),
            "evaluations": [e.to_dict() for e in evaluations],
        }

    @staticmethod
    async def _get_cached_evaluation(
        db: AsyncSession,
        snapshot_hash: str
    ) -> Optional[AIEvaluationCache]:
        """Get cached evaluation by snapshot hash."""
        result = await db.execute(
            sa_select(AIEvaluationCache)
            .where(AIEvaluationCache.snapshot_hash == snapshot_hash)
            .where(
                (AIEvaluationCache.expires_at > datetime.utcnow()) |
                (AIEvaluationCache.expires_at.is_(None))
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _simulate_ai_evaluation(snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """
        Simulate AI evaluation for development/testing.
        In production, this calls actual LLM API.
        """
        # Simple heuristic-based simulation
        heuristics = snapshot.get("heuristics", {})
        time_efficiency = heuristics.get("time_efficiency", 0.5)

        # Generate deterministic scores based on heuristics
        p_base = 65 + (time_efficiency * 15)
        r_base = 60 + (time_efficiency * 10)

        return {
            "petitioner": {
                "legal_knowledge": int(p_base * 0.2),
                "application_of_law": int(p_base * 0.2),
                "structure_clarity": int(p_base * 0.2),
                "etiquette": int(p_base * 0.1),
                "rebuttal_strength": int(p_base * 0.2),
                "objection_handling": int(p_base * 0.1),
                "total": int(p_base)
            },
            "respondent": {
                "legal_knowledge": int(r_base * 0.2),
                "application_of_law": int(r_base * 0.2),
                "structure_clarity": int(r_base * 0.2),
                "etiquette": int(r_base * 0.1),
                "rebuttal_strength": int(r_base * 0.2),
                "objection_handling": int(r_base * 0.1),
                "total": int(r_base)
            },
            "winner": "PETITIONER" if p_base > r_base else "RESPONDENT",
            "reasoning_summary": f"Based on time efficiency of {time_efficiency:.2f}, petitioner showed stronger overall performance.",
            "confidence": 0.75 + (time_efficiency * 0.2),
        }

    @staticmethod
    def _validate_ai_response(response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate AI response structure and values.
        """
        errors = []

        # Check required fields
        required = ["petitioner", "respondent", "winner", "reasoning_summary", "confidence"]
        for field in required:
            if field not in response:
                errors.append(f"Missing required field: {field}")

        # Validate petitioner scores
        p = response.get("petitioner", {})
        p_total = p.get("total", 0)
        p_sum = sum([
            p.get("legal_knowledge", 0),
            p.get("application_of_law", 0),
            p.get("structure_clarity", 0),
            p.get("etiquette", 0),
            p.get("rebuttal_strength", 0),
            p.get("objection_handling", 0),
        ])

        if p_total > 100:
            errors.append(f"Petitioner total score {p_total} exceeds 100")

        # Validate respondent scores
        r = response.get("respondent", {})
        r_total = r.get("total", 0)

        if r_total > 100:
            errors.append(f"Respondent total score {r_total} exceeds 100")

        # Validate winner matches scores
        winner = response.get("winner")
        if winner == "PETITIONER" and p_total <= r_total:
            errors.append("Winner is PETITIONER but score is not higher")
        if winner == "RESPONDENT" and r_total <= p_total:
            errors.append("Winner is RESPONDENT but score is not higher")

        # Validate confidence
        confidence = response.get("confidence", 0)
        if not 0 <= confidence <= 1:
            errors.append(f"Confidence {confidence} not in range [0,1]")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
        }


# Singleton instance
official_service = OfficialEvaluationService()
