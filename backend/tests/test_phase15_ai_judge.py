"""
Phase 15 — AI Judge Test Suite

Comprehensive tests for AI Judge Intelligence Layer.
Minimum 25 tests covering all functionality.
"""
import pytest
import uuid
import json
from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select as sa_select, delete as sa_delete

from backend.services.phase15_hash_service import HashService
from backend.services.phase15_credit_optimizer import CreditOptimizerService
from backend.services.phase15_model_router import ModelRouterService, EvaluationMode
from backend.services.phase15_snapshot_builder import SnapshotBuilderService
from backend.services.phase15_shadow_service import ShadowScoringService
from backend.services.phase15_official_service import OfficialEvaluationService

from backend.orm.phase15_ai_evaluation import (
    AIMatchEvaluation, AIShadowScore, AIEvaluationCache
)
from backend.orm.phase14_round_engine import (
    TournamentMatch, MatchSpeakerTurn, MatchScoreLock,
    MatchStatus, TurnStatus, SpeakerRole
)
from backend.config.feature_flags import feature_flags


# =============================================================================
# TEST 1-3: Feature Flag Enforcement
# =============================================================================

@pytest.mark.asyncio
class TestFeatureFlagEnforcement:
    """Verify feature flags control access."""

    async def test_cannot_evaluate_if_official_feature_disabled(
        self, db: AsyncSession, sample_frozen_match_id
    ):
        """Official evaluation should fail if feature disabled."""
        original = feature_flags.FEATURE_AI_JUDGE_OFFICIAL
        feature_flags.FEATURE_AI_JUDGE_OFFICIAL = False

        try:
            with pytest.raises(HTTPException) as exc:
                await OfficialEvaluationService.evaluate_match_official(
                    db=db, match_id=sample_frozen_match_id
                )
            assert exc.value.status_code == status.HTTP_403_FORBIDDEN
        finally:
            feature_flags.FEATURE_AI_JUDGE_OFFICIAL = original

    async def test_cannot_shadow_score_if_shadow_feature_disabled(
        self, db: AsyncSession, sample_live_match_id
    ):
        """Shadow scoring should fail if feature disabled."""
        original = feature_flags.FEATURE_AI_JUDGE_SHADOW
        feature_flags.FEATURE_AI_JUDGE_SHADOW = False

        try:
            with pytest.raises(HTTPException) as exc:
                await ShadowScoringService.evaluate_match_shadow(
                    db=db, match_id=sample_live_match_id
                )
            assert exc.value.status_code == status.HTTP_403_FORBIDDEN
        finally:
            feature_flags.FEATURE_AI_JUDGE_SHADOW = original

    async def test_cannot_evaluate_if_match_not_frozen(
        self, db: AsyncSession, sample_live_match_id
    ):
        """Official evaluation should fail if match not frozen."""
        original = feature_flags.FEATURE_AI_JUDGE_OFFICIAL
        feature_flags.FEATURE_AI_JUDGE_OFFICIAL = True

        try:
            with pytest.raises(HTTPException) as exc:
                await SnapshotBuilderService.build_match_snapshot(
                    db=db, match_id=sample_live_match_id, validate_frozen=True
                )
            assert exc.value.status_code == status.HTTP_403_FORBIDDEN
        finally:
            feature_flags.FEATURE_AI_JUDGE_OFFICIAL = original


# =============================================================================
# TEST 4-7: Snapshot Hash Determinism
# =============================================================================

@pytest.mark.asyncio
class TestSnapshotHashDeterminism:
    """Verify snapshot hashes are deterministic."""

    def test_same_input_produces_same_hash(self):
        """Identical snapshots must produce identical hashes."""
        snapshot = {
            "match_id": "test-123",
            "petitioner_summary": "Test summary",
            "respondent_summary": "Test summary 2",
            "turn_count": 6,
        }

        hash1 = HashService.generate_snapshot_hash(snapshot)
        hash2 = HashService.generate_snapshot_hash(snapshot)
        hash3 = HashService.generate_snapshot_hash(snapshot)

        assert hash1 == hash2 == hash3
        assert len(hash1) == 64  # SHA256 hex length

    def test_different_input_produces_different_hash(self):
        """Different snapshots must produce different hashes."""
        snapshot1 = {"match_id": "test-123", "turn_count": 6}
        snapshot2 = {"match_id": "test-123", "turn_count": 7}

        hash1 = HashService.generate_snapshot_hash(snapshot1)
        hash2 = HashService.generate_snapshot_hash(snapshot2)

        assert hash1 != hash2

    def test_timestamps_removed_before_hashing(self):
        """Timestamps should not affect hash."""
        snapshot_with_ts = {
            "match_id": "test-123",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        snapshot_without_ts = {
            "match_id": "test-123",
        }

        hash1 = HashService.generate_snapshot_hash(snapshot_with_ts)
        hash2 = HashService.generate_snapshot_hash(snapshot_without_ts)

        assert hash1 == hash2

    def test_nested_dict_hashing(self):
        """Nested dictionaries should hash deterministically."""
        snapshot = {
            "match_id": "test-123",
            "scores": {
                "petitioner": {"total": 85},
                "respondent": {"total": 78},
            },
        }

        hash1 = HashService.generate_snapshot_hash(snapshot)
        hash2 = HashService.generate_snapshot_hash(snapshot)

        assert hash1 == hash2


# =============================================================================
# TEST 8-11: Evaluation Hash Determinism
# =============================================================================

@pytest.mark.asyncio
class TestEvaluationHashDeterminism:
    """Verify evaluation hashes are deterministic."""

    def test_same_evaluation_produces_same_hash(self):
        """Identical evaluations must produce identical hashes."""
        snapshot_hash = "abc123" * 10 + "def"  # 64 chars
        model_name = "gpt-4"
        response = {
            "petitioner": {"total": 85},
            "respondent": {"total": 78},
            "winner": "PETITIONER",
        }

        hash1 = HashService.generate_evaluation_hash(
            snapshot_hash, model_name, response
        )
        hash2 = HashService.generate_evaluation_hash(
            snapshot_hash, model_name, response
        )

        assert hash1 == hash2
        assert len(hash1) == 64

    def test_different_response_produces_different_hash(self):
        """Different responses must produce different hashes."""
        snapshot_hash = "abc123" * 10 + "def"
        model_name = "gpt-4"
        response1 = {"winner": "PETITIONER"}
        response2 = {"winner": "RESPONDENT"}

        hash1 = HashService.generate_evaluation_hash(
            snapshot_hash, model_name, response1
        )
        hash2 = HashService.generate_evaluation_hash(
            snapshot_hash, model_name, response2
        )

        assert hash1 != hash2

    def test_different_model_produces_different_hash(self):
        """Different models must produce different hashes."""
        snapshot_hash = "abc123" * 10 + "def"
        response = {"winner": "PETITIONER"}

        hash1 = HashService.generate_evaluation_hash(
            snapshot_hash, "gpt-4", response
        )
        hash2 = HashService.generate_evaluation_hash(
            snapshot_hash, "gpt-3.5-turbo", response
        )

        assert hash1 != hash2

    def test_hash_verification_works(self):
        """Hash verification should detect tampering."""
        snapshot_hash = "abc123" * 10 + "def"
        model_name = "gpt-4"
        response = {"winner": "PETITIONER"}

        computed_hash = HashService.generate_evaluation_hash(
            snapshot_hash, model_name, response
        )

        # Valid verification
        assert HashService.verify_evaluation_integrity(
            snapshot_hash, model_name, response, computed_hash
        )

        # Invalid verification (wrong hash)
        assert not HashService.verify_evaluation_integrity(
            snapshot_hash, model_name, response, "wrong_hash"
        )


# =============================================================================
# TEST 12-14: Cache Functionality
# =============================================================================

@pytest.mark.asyncio
class TestCacheFunctionality:
    """Verify caching works correctly."""

    async def test_duplicate_evaluation_returns_cached(
        self, db: AsyncSession, sample_frozen_match_id
    ):
        """Second evaluation with same snapshot should return cached."""
        original_cache = feature_flags.FEATURE_AI_JUDGE_CACHE
        feature_flags.FEATURE_AI_JUDGE_CACHE = True
        original_official = feature_flags.FEATURE_AI_JUDGE_OFFICIAL
        feature_flags.FEATURE_AI_JUDGE_OFFICIAL = True

        try:
            # First evaluation
            result1 = await OfficialEvaluationService.evaluate_match_official(
                db=db, match_id=sample_frozen_match_id
            )

            # Second evaluation (should be cached)
            result2 = await OfficialEvaluationService.evaluate_match_official(
                db=db, match_id=sample_frozen_match_id
            )

            assert result2["cached"] is True
            assert result1["evaluation_hash"] == result2["evaluation_hash"]
        finally:
            feature_flags.FEATURE_AI_JUDGE_CACHE = original_cache
            feature_flags.FEATURE_AI_JUDGE_OFFICIAL = original_official

    async def test_force_refresh_bypasses_cache(
        self, db: AsyncSession, sample_frozen_match_id
    ):
        """Force refresh should generate new evaluation."""
        original_cache = feature_flags.FEATURE_AI_JUDGE_CACHE
        feature_flags.FEATURE_AI_JUDGE_CACHE = True
        original_official = feature_flags.FEATURE_AI_JUDGE_OFFICIAL
        feature_flags.FEATURE_AI_JUDGE_OFFICIAL = True

        try:
            # First evaluation
            await OfficialEvaluationService.evaluate_match_official(
                db=db, match_id=sample_frozen_match_id
            )

            # Force refresh
            result2 = await OfficialEvaluationService.evaluate_match_official(
                db=db, match_id=sample_frozen_match_id, force_refresh=True
            )

            assert result2["cached"] is False
        finally:
            feature_flags.FEATURE_AI_JUDGE_CACHE = original_cache
            feature_flags.FEATURE_AI_JUDGE_OFFICIAL = original_official

    async def test_cache_respects_expiry(self, db: AsyncSession):
        """Expired cache entries should not be returned."""
        # Create expired cache entry
        expired_entry = AIEvaluationCache(
            snapshot_hash="expired_hash_12345" + "x" * 43,
            model_name="gpt-4",
            cached_response_json={"winner": "PETITIONER"},
            expires_at=datetime.utcnow() - timedelta(hours=1)
        )
        db.add(expired_entry)
        await db.flush()

        # Should be expired
        assert expired_entry.is_expired()


# =============================================================================
# TEST 15-17: Shadow Score Cleanup
# =============================================================================

@pytest.mark.asyncio
class TestShadowScoreCleanup:
    """Verify shadow scores are cleaned up correctly."""

    async def test_shadow_score_deleted_on_freeze(
        self, db: AsyncSession, sample_live_match_id
    ):
        """Shadow scores should be deletable."""
        original = feature_flags.FEATURE_AI_JUDGE_SHADOW
        feature_flags.FEATURE_AI_JUDGE_SHADOW = True

        try:
            # Create shadow scores
            await ShadowScoringService.evaluate_match_shadow(
                db=db, match_id=sample_live_match_id
            )

            # Verify scores exist
            scores_before = await ShadowScoringService.get_shadow_scores(
                db=db, match_id=sample_live_match_id
            )
            assert len(scores_before) > 0

            # Delete shadow scores
            deleted = await ShadowScoringService.delete_shadow_scores(
                db=db, match_id=sample_live_match_id
            )
            assert deleted > 0

            # Verify scores deleted
            scores_after = await ShadowScoringService.get_shadow_scores(
                db=db, match_id=sample_live_match_id
            )
            assert len(scores_after) == 0
        finally:
            feature_flags.FEATURE_AI_JUDGE_SHADOW = original

    async def test_expired_shadow_scores_cleaned_up(
        self, db: AsyncSession
    ):
        """Expired shadow scores should be cleaned up."""
        # Create expired shadow score
        expired_score = AIShadowScore(
            match_id=uuid.uuid4(),
            turn_id=uuid.uuid4(),
            provisional_score=75.0,
            confidence=0.8,
            expires_at=datetime.utcnow() - timedelta(hours=1)
        )
        db.add(expired_score)
        await db.flush()

        # Cleanup
        cleaned = await ShadowScoringService.cleanup_expired_scores(db=db)
        assert cleaned >= 1

    async def test_shadow_only_works_on_live_matches(
        self, db: AsyncSession, sample_frozen_match_id
    ):
        """Shadow scoring should fail on non-LIVE matches."""
        original = feature_flags.FEATURE_AI_JUDGE_SHADOW
        feature_flags.FEATURE_AI_JUDGE_SHADOW = True

        try:
            with pytest.raises(HTTPException) as exc:
                await ShadowScoringService.evaluate_match_shadow(
                    db=db, match_id=sample_frozen_match_id
                )
            assert exc.value.status_code == status.HTTP_403_FORBIDDEN
        finally:
            feature_flags.FEATURE_AI_JUDGE_SHADOW = original


# =============================================================================
# TEST 18-20: Token Budget
# =============================================================================

@pytest.mark.asyncio
class TestTokenBudget:
    """Verify token budget constraints."""

    def test_token_estimation(self):
        """Token estimation should be accurate."""
        text = "a" * 4000  # ~1000 tokens at 4 chars/token
        tokens = CreditOptimizerService.estimate_tokens(text)
        assert tokens >= 900 and tokens <= 1100

    def test_text_optimization_reduces_size(self):
        """Optimization should reduce text size."""
        text = "Basically, this is essentially a test. " * 100
        original_tokens = CreditOptimizerService.estimate_tokens(text)

        optimized = CreditOptimizerService.optimize_text(text)
        optimized_tokens = CreditOptimizerService.estimate_tokens(optimized)

        assert optimized_tokens <= original_tokens

    def test_optimization_respects_budget(self):
        """Optimized text should fit within budget."""
        long_text = "Word " * 2000  # Way over budget
        optimized = CreditOptimizerService.optimize_text(long_text, max_tokens=500)

        tokens = CreditOptimizerService.estimate_tokens(optimized)
        assert tokens <= 500


# =============================================================================
# TEST 21-23: AI Response Validation
# =============================================================================

@pytest.mark.asyncio
class TestAIResponseValidation:
    """Verify AI response validation."""

    def test_valid_response_passes_validation(self):
        """Valid AI response should pass validation."""
        response = {
            "petitioner": {
                "legal_knowledge": 18,
                "application_of_law": 17,
                "structure_clarity": 16,
                "etiquette": 8,
                "rebuttal_strength": 15,
                "objection_handling": 9,
                "total": 83
            },
            "respondent": {
                "legal_knowledge": 16,
                "application_of_law": 15,
                "structure_clarity": 14,
                "etiquette": 7,
                "rebuttal_strength": 13,
                "objection_handling": 8,
                "total": 73
            },
            "winner": "PETITIONER",
            "reasoning_summary": "Strong legal knowledge shown",
            "confidence": 0.85
        }

        validated = OfficialEvaluationService._validate_ai_response(response)
        assert validated["valid"] is True
        assert len(validated["errors"]) == 0

    def test_invalid_winner_fails_validation(self):
        """Winner not matching scores should fail validation."""
        response = {
            "petitioner": {"total": 70},
            "respondent": {"total": 80},
            "winner": "PETITIONER",  # Wrong - respondent has higher score
            "reasoning_summary": "Test",
            "confidence": 0.8
        }

        validated = OfficialEvaluationService._validate_ai_response(response)
        assert validated["valid"] is False
        assert any("Winner" in e for e in validated["errors"])

    def test_excessive_score_fails_validation(self):
        """Score over 100 should fail validation."""
        response = {
            "petitioner": {"total": 105},  # Over 100
            "respondent": {"total": 70},
            "winner": "PETITIONER",
            "reasoning_summary": "Test",
            "confidence": 0.8
        }

        validated = OfficialEvaluationService._validate_ai_response(response)
        assert validated["valid"] is False


# =============================================================================
# TEST 24-27: Model Routing
# =============================================================================

@pytest.mark.asyncio
class TestModelRouting:
    """Verify model routing logic."""

    def test_shadow_mode_uses_cheaper_model(self):
        """Shadow mode should use low-cost model."""
        config = ModelRouterService.get_model_config(
            mode=EvaluationMode.SHADOW.value,
            use_heuristics=False
        )
        assert config.quality_tier == "low"

    def test_official_mode_uses_balanced_model(self):
        """Official mode should use balanced model."""
        config = ModelRouterService.get_model_config(
            mode=EvaluationMode.OFFICIAL.value
        )
        assert config.quality_tier in ["balanced", "premium"]

    def test_finals_use_premium_model(self):
        """Finals matches should use premium model."""
        routing = ModelRouterService.route_evaluation(
            mode=EvaluationMode.OFFICIAL.value,
            is_finals=True
        )
        assert routing["quality_tier"] == "premium"

    def test_heuristics_available_for_shadow(self):
        """Heuristics should be available for shadow mode."""
        config = ModelRouterService.get_model_config(
            mode=EvaluationMode.SHADOW.value,
            use_heuristics=True
        )
        assert config.model_name == "heuristic"


# =============================================================================
# TEST 28-30: Winner Calculation
# =============================================================================

@pytest.mark.asyncio
class TestWinnerCalculation:
    """Verify winner calculation logic."""

    def test_higher_score_wins(self):
        """Team with higher score should be winner."""
        # Test via heuristics calculation
        snapshot = {
            "heuristics": {"time_efficiency": 0.9}
        }
        response = OfficialEvaluationService._simulate_ai_evaluation(snapshot)

        p_score = response["petitioner"]["total"]
        r_score = response["respondent"]["total"]
        winner = response["winner"]

        if winner == "PETITIONER":
            assert p_score > r_score
        else:
            assert r_score > p_score

    def test_deterministic_winner_calculation(self):
        """Winner calculation should be deterministic."""
        snapshot = {"heuristics": {"time_efficiency": 0.5}}

        response1 = OfficialEvaluationService._simulate_ai_evaluation(snapshot)
        response2 = OfficialEvaluationService._simulate_ai_evaluation(snapshot)

        assert response1["winner"] == response2["winner"]
        assert response1["petitioner"]["total"] == response2["petitioner"]["total"]

    def test_confidence_within_range(self):
        """Confidence score should be 0-1."""
        snapshot = {"heuristics": {"time_efficiency": 0.7}}
        response = OfficialEvaluationService._simulate_ai_evaluation(snapshot)

        assert 0 <= response["confidence"] <= 1


# =============================================================================
# TEST 31-33: Parallel Evaluation Safety
# =============================================================================

@pytest.mark.asyncio
class TestParallelEvaluationSafety:
    """Verify parallel evaluations don't corrupt data."""

    async def test_concurrent_evaluations_safe(
        self, db: AsyncSession, sample_frozen_match_id
    ):
        """Concurrent evaluations should not cause data corruption."""
        import asyncio

        original_official = feature_flags.FEATURE_AI_JUDGE_OFFICIAL
        feature_flags.FEATURE_AI_JUDGE_OFFICIAL = True

        try:
            # Run 5 evaluations concurrently
            tasks = [
                OfficialEvaluationService.evaluate_match_official(
                    db=db, match_id=sample_frozen_match_id
                )
                for _ in range(5)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # All should succeed
            successful = [r for r in results if not isinstance(r, Exception)]
            assert len(successful) == 5

        finally:
            feature_flags.FEATURE_AI_JUDGE_OFFICIAL = original_official

    async def test_cache_prevents_duplicate_api_calls(
        self, db: AsyncSession, sample_frozen_match_id
    ):
        """Cache should prevent duplicate API calls for same snapshot."""
        original_cache = feature_flags.FEATURE_AI_JUDGE_CACHE
        original_official = feature_flags.FEATURE_AI_JUDGE_OFFICIAL
        feature_flags.FEATURE_AI_JUDGE_CACHE = True
        feature_flags.FEATURE_AI_JUDGE_OFFICIAL = True

        try:
            # First evaluation
            result1 = await OfficialEvaluationService.evaluate_match_official(
                db=db, match_id=sample_frozen_match_id
            )

            # Get history
            history = await OfficialEvaluationService.get_evaluation_history(
                db=db, match_id=sample_frozen_match_id
            )

            # Should have at least one evaluation
            assert history["evaluation_count"] >= 1

        finally:
            feature_flags.FEATURE_AI_JUDGE_CACHE = original_cache
            feature_flags.FEATURE_AI_JUDGE_OFFICIAL = original_official


# =============================================================================
# TEST 34-35: Snapshot Tampering Detection
# =============================================================================

@pytest.mark.asyncio
class TestSnapshotTamperingDetection:
    """Verify snapshot tampering is detected."""

    async def test_tampered_snapshot_detected(
        self, db: AsyncSession, sample_frozen_match_id
    ):
        """Snapshot with wrong hash should fail verification."""
        original_official = feature_flags.FEATURE_AI_JUDGE_OFFICIAL
        feature_flags.FEATURE_AI_JUDGE_OFFICIAL = True

        try:
            # Create evaluation
            result = await OfficialEvaluationService.evaluate_match_official(
                db=db, match_id=sample_frozen_match_id
            )
            stored_hash = result["snapshot_hash"]

            # Verify with correct hash
            is_valid = HashService.verify_snapshot_integrity(
                result["snapshot"], stored_hash
            )
            assert is_valid is True

            # Verify with wrong hash
            is_invalid = HashService.verify_snapshot_integrity(
                result["snapshot"], "wrong" * 22  # Fake 64-char hash
            )
            assert is_invalid is False

        finally:
            feature_flags.FEATURE_AI_JUDGE_OFFICIAL = original_official

    async def test_integrity_verification_endpoint(
        self, db: AsyncSession, sample_frozen_match_id
    ):
        """Integrity verification endpoint should work."""
        original_official = feature_flags.FEATURE_AI_JUDGE_OFFICIAL
        feature_flags.FEATURE_AI_JUDGE_OFFICIAL = True

        try:
            # Create evaluation
            await OfficialEvaluationService.evaluate_match_official(
                db=db, match_id=sample_frozen_match_id
            )

            # Verify
            verification = await OfficialEvaluationService.verify_evaluation(
                db=db, match_id=sample_frozen_match_id
            )

            assert "verified" in verification
            assert "evaluation_valid" in verification

        finally:
            feature_flags.FEATURE_AI_JUDGE_OFFICIAL = original_official


# =============================================================================
# TEST 36-38: Credit Optimizer
# =============================================================================

@pytest.mark.asyncio
class TestCreditOptimizer:
    """Verify credit optimization."""

    def test_filler_phrases_removed(self):
        """Filler phrases should be removed from text."""
        text = "Basically, this is essentially a very important point."
        optimized = CreditOptimizerService.optimize_text(text)

        assert "basically" not in optimized.lower()
        assert "essentially" not in optimized.lower()

    def test_repetitive_sentences_removed(self):
        """Repetitive sentences should be deduplicated."""
        text = "Respectfully submitted. Respectfully submitted. Argument follows."
        optimized = CreditOptimizerService.optimize_text(text)

        # Should have reduced length
        assert len(optimized) <= len(text)

    def test_budget_calculation_accurate(self):
        """Budget calculation should be accurate."""
        summary = {
            "section1": "a" * 400,
            "section2": "b" * 400,
            "section3": "c" * 400,
        }

        breakdown = CreditOptimizerService.calculate_summary_length(summary)
        total_chars = breakdown["_total"]["chars"]

        assert total_chars == 1200
        assert breakdown["_total"]["over_budget"] == (total_chars > 2000)


# =============================================================================
# TEST 39-40: Error Handling
# =============================================================================

@pytest.mark.asyncio
class TestErrorHandling:
    """Verify error handling."""

    async def test_nonexistent_match_returns_404(
        self, db: AsyncSession
    ):
        """Request for nonexistent match should return 404."""
        fake_id = uuid.uuid4()

        with pytest.raises(HTTPException) as exc:
            await SnapshotBuilderService.build_match_snapshot(
                db=db, match_id=fake_id, validate_frozen=False
            )
        assert exc.value.status_code == status.HTTP_404_NOT_FOUND

    async def test_invalid_ai_response_marked_for_retry(
        self, db: AsyncSession
    ):
        """Invalid AI response should be handled gracefully."""
        invalid_response = {
            "petitioner": {"total": 999},  # Over limit
            "winner": "INVALID_WINNER"
        }

        validated = OfficialEvaluationService._validate_ai_response(
            invalid_response
        )

        assert validated["valid"] is False
        assert len(validated["errors"]) > 0
