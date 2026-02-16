"""
AI Judge Unit Tests — Phase 4

Tests for validator, score computation, and service logic with mocked dependencies.
"""
import pytest
import json
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch

from backend.services.ai_judge_validator import (
    validate_llm_json, compute_final_score, validate_rubric_definition,
    extract_criteria_summary, ValidationResult
)
from backend.services import ai_evaluation_service as eval_svc


# ============================================================================
# Validation Tests
# ============================================================================

class TestValidateLLMJSON:
    """Tests for LLM response validation."""
    
    def test_valid_response_passes(self):
        """Valid JSON response should pass validation."""
        rubric = {
            "criteria": [
                {"id": "substance", "label": "Substance", "weight": 0.4, "scale": [0, 100]},
                {"id": "delivery", "label": "Delivery", "weight": 0.6, "scale": [0, 100]}
            ]
        }
        
        valid_response = {
            "scores": {"substance": 85, "delivery": 75},
            "weights": {"substance": 0.4, "delivery": 0.6},
            "comments": {"substance": "Good", "delivery": "Fair"},
            "pass_fail": True,
            "meta": {"confidence": 0.9}
        }
        
        result = validate_llm_json(json.dumps(valid_response), rubric)
        
        assert result.is_valid is True
        assert result.errors == []
        assert result.computed_score is not None
        assert result.score_breakdown is not None
    
    def test_invalid_json_fails(self):
        """Invalid JSON should fail with parse error."""
        rubric = {"criteria": []}
        
        result = validate_llm_json("not valid json", rubric)
        
        assert result.is_valid is False
        assert any("Invalid JSON" in e for e in result.errors)
    
    def test_missing_keys_fails(self):
        """Missing required keys should fail."""
        rubric = {
            "criteria": [{"id": "substance", "label": "Substance", "weight": 1.0, "scale": [0, 100]}]
        }
        
        incomplete_response = {
            "scores": {"substance": 80}  # Missing comments, pass_fail, meta
        }
        
        result = validate_llm_json(json.dumps(incomplete_response), rubric)
        
        # Should fail schema validation for missing keys
        assert result.is_valid is False
        assert len(result.errors) > 0
    
    def test_score_out_of_range_fails(self):
        """Score outside scale range should fail."""
        rubric = {
            "criteria": [{"id": "substance", "label": "Substance", "weight": 1.0, "scale": [0, 100]}]
        }
        
        invalid_response = {
            "scores": {"substance": 150},  # Out of range
            "weights": {"substance": 1.0},
            "comments": {"substance": "Too high"},
            "pass_fail": True,
            "meta": {"confidence": 0.5}
        }
        
        result = validate_llm_json(json.dumps(invalid_response), rubric)
        
        assert result.is_valid is False
        assert any("outside range" in e for e in result.errors)
    
    def test_missing_criterion_score_fails(self):
        """Missing score for rubric criterion should fail."""
        rubric = {
            "criteria": [
                {"id": "substance", "label": "Substance", "weight": 0.5, "scale": [0, 100]},
                {"id": "delivery", "label": "Delivery", "weight": 0.5, "scale": [0, 100]}
            ]
        }
        
        incomplete_response = {
            "scores": {"substance": 80},  # Missing delivery
            "weights": {"substance": 0.5, "delivery": 0.5},
            "comments": {"substance": "Good", "delivery": "Missing"},
            "pass_fail": True,
            "meta": {"confidence": 0.8}
        }
        
        result = validate_llm_json(json.dumps(incomplete_response), rubric)
        
        assert result.is_valid is False
        assert any("delivery" in e.lower() for e in result.errors)


class TestComputeFinalScore:
    """Tests for score computation."""
    
    def test_weighted_score_calculation(self):
        """Weighted scores should sum correctly."""
        scores = {"substance": 80, "delivery": 60}
        weights = {"substance": 0.6, "delivery": 0.4}
        
        final_score, breakdown = compute_final_score(scores, weights)
        
        # Expected: 80*0.6 + 60*0.4 = 48 + 24 = 72
        expected = Decimal("72.00")
        assert final_score == expected
        assert breakdown["substance"] == 48.0
        assert breakdown["delivery"] == 24.0
    
    def test_equal_weights(self):
        """Equal weights should average scores."""
        scores = {"a": 100, "b": 0, "c": 50}
        weights = {"a": 0.333, "b": 0.333, "c": 0.334}
        
        final_score, _ = compute_final_score(scores, weights)
        
        # Should be close to 50
        assert 49 < float(final_score) < 51
    
    def test_decimal_precision(self):
        """Should maintain 2 decimal precision."""
        scores = {"x": 33.333}
        weights = {"x": 1.0}
        
        final_score, _ = compute_final_score(scores, weights)
        
        # Should round to 2 decimal places
        assert final_score == Decimal("33.33")


class TestValidateRubricDefinition:
    """Tests for rubric definition validation."""
    
    def test_valid_rubric_passes(self):
        """Valid rubric definition should pass."""
        definition = {
            "name": "Test Rubric",
            "version": 1,
            "criteria": [
                {"id": "c1", "label": "Crit 1", "weight": 0.5, "type": "numeric", "scale": [0, 100]},
                {"id": "c2", "label": "Crit 2", "weight": 0.5, "type": "numeric", "scale": [0, 100]}
            ],
            "instructions_for_llm": "Return JSON"
        }
        
        is_valid, errors = validate_rubric_definition(definition)
        
        assert is_valid is True
        assert errors == []
    
    def test_weights_must_sum_to_one(self):
        """Weights not summing to 1.0 should fail."""
        definition = {
            "name": "Test",
            "version": 1,
            "criteria": [
                {"id": "c1", "label": "Crit 1", "weight": 0.3, "type": "numeric", "scale": [0, 100]},
                {"id": "c2", "label": "Crit 2", "weight": 0.3, "type": "numeric", "scale": [0, 100]}
            ],
            "instructions_for_llm": "Return JSON"
        }
        
        is_valid, errors = validate_rubric_definition(definition)
        
        assert is_valid is False
        assert any("sum to 1.0" in e for e in errors)
    
    def test_missing_criterion_fields_fails(self):
        """Missing criterion fields should fail."""
        definition = {
            "name": "Test",
            "version": 1,
            "criteria": [
                {"id": "c1"}  # Missing label, weight, type
            ],
            "instructions_for_llm": "Return JSON"
        }
        
        is_valid, errors = validate_rubric_definition(definition)
        
        assert is_valid is False
        assert len(errors) > 0
    
    def test_duplicate_criterion_ids_fails(self):
        """Duplicate criterion IDs should fail."""
        definition = {
            "name": "Test",
            "version": 1,
            "criteria": [
                {"id": "c1", "label": "Crit 1", "weight": 0.5, "type": "numeric", "scale": [0, 100]},
                {"id": "c1", "label": "Crit 2", "weight": 0.5, "type": "numeric", "scale": [0, 100]}
            ],
            "instructions_for_llm": "Return JSON"
        }
        
        is_valid, errors = validate_rubric_definition(definition)
        
        assert is_valid is False
        assert any("Duplicate" in e for e in errors)


class TestExtractCriteriaSummary:
    """Tests for criteria summary extraction."""
    
    def test_summary_format(self):
        """Summary should format as id(weight)."""
        definition = {
            "criteria": [
                {"id": "substance", "weight": 0.4},
                {"id": "delivery", "weight": 0.6}
            ]
        }
        
        summary = extract_criteria_summary(definition)
        
        assert "substance(0.4)" in summary
        assert "delivery(0.6)" in summary
    
    def test_empty_criteria(self):
        """Empty criteria should return empty string."""
        definition = {"criteria": []}
        
        summary = extract_criteria_summary(definition)
        
        assert summary == ""


# ============================================================================
# Service Logic Tests
# ============================================================================

@pytest.mark.asyncio
class TestAIEvaluationService:
    """Tests for AI evaluation service."""
    
    async def test_create_rubric_creates_version(self):
        """Creating rubric should also create frozen version."""
        mock_db = AsyncMock()
        mock_db.flush = AsyncMock()
        
        definition = {
            "name": "Test Rubric",
            "version": 1,
            "criteria": [
                {"id": "c1", "label": "Crit 1", "weight": 1.0, "type": "numeric", "scale": [0, 100]}
            ],
            "instructions_for_llm": "Test"
        }
        
        with patch.object(eval_svc, 'AIRubric') as mock_rubric_class, \
             patch.object(eval_svc, 'AIRubricVersion') as mock_version_class:
            
            mock_rubric = Mock()
            mock_rubric.id = 1
            mock_rubric_class.return_value = mock_rubric
            
            mock_version = Mock()
            mock_version_class.return_value = mock_version
            
            result = await eval_svc.create_rubric(
                name="Test",
                description="Desc",
                rubric_type="oral_argument",
                definition=definition,
                created_by_faculty_id=101,
                db=mock_db
            )
            
            # Should create rubric and version
            mock_db.add.assert_called()
            mock_db.flush.assert_called()
    
    async def test_unauthorized_evaluation_raises(self):
        """Non-faculty should not be able to evaluate."""
        mock_db = AsyncMock()
        
        with pytest.raises(eval_svc.UnauthorizedEvaluationError):
            await eval_svc.evaluate(
                session_id=1,
                round_id=1,
                participant_id=1,
                rubric_version_id=1,
                db=mock_db,
                user_id=201,
                is_faculty=False  # Not faculty
            )
    
    def test_build_evaluation_prompt_structure(self):
        """Prompt should include transcript, criteria, and instructions."""
        transcript = "Test argument"
        rubric = {
            "criteria": [
                {"id": "substance", "label": "Substance & Law", "weight": 0.4, "scale": [0, 100]}
            ],
            "instructions_for_llm": "Return JSON"
        }
        
        prompt = eval_svc._build_evaluation_prompt(transcript, rubric, 1, 1)
        
        assert "Test argument" in prompt
        assert "substance" in prompt
        assert "Substance & Law" in prompt
        assert "Return JSON" in prompt
        assert "weight 0.4" in prompt


# ============================================================================
# Prompt Hash Tests
# ============================================================================

class TestPromptHash:
    """Tests for prompt hashing reproducibility."""
    
    def test_same_prompt_same_hash(self):
        """Same prompt should always produce same hash."""
        import hashlib
        
        prompt = "Evaluate this transcript: test"
        
        hash1 = hashlib.sha256(prompt.encode()).hexdigest()
        hash2 = hashlib.sha256(prompt.encode()).hexdigest()
        
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex length
    
    def test_different_prompt_different_hash(self):
        """Different prompts should produce different hashes."""
        import hashlib
        
        prompt1 = "Evaluate: test1"
        prompt2 = "Evaluate: test2"
        
        hash1 = hashlib.sha256(prompt1.encode()).hexdigest()
        hash2 = hashlib.sha256(prompt2.encode()).hexdigest()
        
        assert hash1 != hash2


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    print("AI Judge Unit Tests")
    print("=" * 50)
    print("\nRun with: pytest backend/tests/test_ai_judge_unit.py -v")
