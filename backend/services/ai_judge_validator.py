"""
JSON Schema Validator for AI Judge Engine — Phase 4

Strict validation of LLM output against expected schema.
Implements validation steps from Phase 4 spec:
1. Validate parse → JSON
2. Validate required keys present and types match
3. Validate numeric ranges
4. Validate weights align with rubric weights
5. Compute final score server-side
"""
import json
import logging
from typing import Dict, Any, List, Tuple, Optional
from decimal import Decimal

from pydantic import ValidationError

from backend.schemas.ai_judge import LLMExpectedResponse

logger = logging.getLogger(__name__)


class ValidationResult:
    """Result of LLM output validation."""
    def __init__(
        self,
        is_valid: bool,
        parsed_data: Optional[Dict[str, Any]] = None,
        errors: List[str] = None,
        computed_score: Optional[Decimal] = None,
        score_breakdown: Optional[Dict[str, float]] = None
    ):
        self.is_valid = is_valid
        self.parsed_data = parsed_data
        self.errors = errors or []
        self.computed_score = computed_score
        self.score_breakdown = score_breakdown
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "errors": self.errors,
            "computed_score": float(self.computed_score) if self.computed_score else None,
            "score_breakdown": self.score_breakdown
        }


def validate_llm_json(raw_response: str, rubric_definition: Dict[str, Any]) -> ValidationResult:
    """
    Validate LLM raw response against strict schema.
    
    Steps:
    1. Parse JSON
    2. Validate against pydantic schema
    3. Validate numeric ranges
    4. Validate weights match rubric
    5. Compute final score server-side
    
    Args:
        raw_response: Raw text from LLM
        rubric_definition: Rubric JSON with criteria and weights
        
    Returns:
        ValidationResult with parsed data or errors
    """
    # Step 1: Parse JSON
    try:
        parsed = json.loads(raw_response)
    except json.JSONDecodeError as e:
        logger.warning(f"JSON parse failed: {e}")
        return ValidationResult(
            is_valid=False,
            errors=[f"Invalid JSON: {str(e)}"]
        )
    
    # Step 2: Validate against pydantic schema
    try:
        validated = LLMExpectedResponse(**parsed)
        parsed_data = validated.model_dump()
    except ValidationError as e:
        logger.warning(f"Schema validation failed: {e}")
        errors = []
        for err in e.errors():
            loc = ".".join(str(l) for l in err.get("loc", []))
            msg = err.get("msg", "Unknown error")
            errors.append(f"{loc}: {msg}")
        return ValidationResult(is_valid=False, errors=errors)
    
    # Step 3: Validate scores against rubric criteria
    rubric_criteria = rubric_definition.get("criteria", [])
    rubric_criteria_map = {c["id"]: c for c in rubric_criteria}
    
    validation_errors = []
    scores = parsed_data.get("scores", {})
    
    # Check all rubric criteria have scores
    for criterion in rubric_criteria:
        cid = criterion["id"]
        if cid not in scores:
            validation_errors.append(f"Missing score for criterion: {cid}")
            continue
        
        score = scores[cid]
        scale = criterion.get("scale", [0, 100])
        
        # Validate score is within scale
        if not isinstance(score, (int, float)):
            validation_errors.append(f"Score for {cid} must be numeric, got {type(score)}")
        elif score < scale[0] or score > scale[1]:
            validation_errors.append(f"Score for {cid} ({score}) outside range {scale}")
    
    # Check no extra scores not in rubric
    for score_key in scores:
        if score_key not in rubric_criteria_map:
            validation_errors.append(f"Unknown criterion in scores: {score_key}")
    
    # Step 4: Validate weights (or use rubric weights)
    rubric_weights = {c["id"]: c["weight"] for c in rubric_criteria}
    returned_weights = parsed_data.get("weights", {})
    
    # Log if weights don't match but don't fail - we use server-side weights
    if returned_weights:
        for cid, expected_weight in rubric_weights.items():
            returned_weight = returned_weights.get(cid)
            if returned_weight is not None:
                if abs(returned_weight - expected_weight) > 0.01:
                    logger.warning(
                        f"Weight mismatch for {cid}: expected {expected_weight}, got {returned_weight}. "
                        "Using server-side weights."
                    )
    
    # Step 5: Compute final score server-side
    if validation_errors:
        return ValidationResult(is_valid=False, errors=validation_errors, parsed_data=parsed_data)
    
    computed_score, score_breakdown = compute_final_score(scores, rubric_weights)
    
    return ValidationResult(
        is_valid=True,
        parsed_data=parsed_data,
        computed_score=computed_score,
        score_breakdown=score_breakdown,
        errors=[]
    )


def compute_final_score(
    scores: Dict[str, float], 
    weights: Dict[str, float]
) -> Tuple[Decimal, Dict[str, float]]:
    """
    Compute weighted final score.
    
    Server-side computation - never trust LLM's calculated total.
    
    Args:
        scores: Dict of criterion_id -> score
        weights: Dict of criterion_id -> weight (sum should be 1.0)
        
    Returns:
        Tuple of (final_score, breakdown_dict)
    """
    total = Decimal("0")
    breakdown = {}
    
    for criterion_id, score in scores.items():
        weight = Decimal(str(weights.get(criterion_id, 0)))
        weighted_score = Decimal(str(score)) * weight
        total += weighted_score
        breakdown[criterion_id] = float(weighted_score)
    
    # Round to 2 decimal places
    final_score = total.quantize(Decimal("0.01"))
    
    return final_score, breakdown


def validate_rubric_definition(definition: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate a rubric definition before saving.
    
    Args:
        definition: Rubric definition JSON
        
    Returns:
        Tuple of (is_valid, error_messages)
    """
    errors = []
    
    # Check required fields
    required = ["name", "version", "criteria", "instructions_for_llm"]
    for field in required:
        if field not in definition:
            errors.append(f"Missing required field: {field}")
    
    if errors:
        return False, errors
    
    # Validate criteria
    criteria = definition.get("criteria", [])
    if not criteria:
        errors.append("Rubric must have at least one criterion")
    
    total_weight = 0.0
    criterion_ids = set()
    
    for i, criterion in enumerate(criteria):
        # Check required criterion fields
        if "id" not in criterion:
            errors.append(f"Criterion {i}: missing 'id'")
        elif criterion["id"] in criterion_ids:
            errors.append(f"Duplicate criterion id: {criterion['id']}")
        else:
            criterion_ids.add(criterion["id"])
        
        if "label" not in criterion:
            errors.append(f"Criterion {i}: missing 'label'")
        
        if "weight" not in criterion:
            errors.append(f"Criterion {criterion.get('id', i)}: missing 'weight'")
        else:
            weight = float(criterion["weight"])
            if weight < 0 or weight > 1:
                errors.append(f"Criterion {criterion.get('id', i)}: weight must be 0-1")
            total_weight += weight
        
        if "type" not in criterion:
            errors.append(f"Criterion {criterion.get('id', i)}: missing 'type'")
        
        # Validate scale if numeric
        if criterion.get("type") == "numeric":
            scale = criterion.get("scale", [0, 100])
            if len(scale) != 2 or scale[0] >= scale[1]:
                errors.append(f"Criterion {criterion.get('id', i)}: invalid scale {scale}")
    
    # Check weights sum to approximately 1.0
    if abs(total_weight - 1.0) > 0.01:
        errors.append(f"Weights must sum to 1.0, got {total_weight}")
    
    return len(errors) == 0, errors


def extract_criteria_summary(definition: Dict[str, Any]) -> str:
    """
    Extract a short summary of rubric criteria for indexing.
    
    Args:
        definition: Rubric definition
        
    Returns:
        String summary like "substance(0.4), structure(0.2), ..."
    """
    criteria = definition.get("criteria", [])
    parts = [f"{c['id']}({c['weight']})" for c in criteria]
    return ", ".join(parts) if parts else ""


def format_validation_errors(errors: List[str]) -> str:
    """Format validation errors for display."""
    if not errors:
        return "No errors"
    return "; ".join(errors)
