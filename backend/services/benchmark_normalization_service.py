"""
backend/services/benchmark_normalization_service.py
Phase 8.4: Fairness & Difficulty Normalization

SYSTEM PURPOSE:
Ensure benchmarking is fair across subjects and exams by accounting for:
- Question difficulty
- Subject scoring bias
- Attempt volume imbalance

This phase ADJUSTS interpretation, NOT raw scores.

PROBLEM SOLVED:
- Criminal Law questions are harder → lower mastery across cohort
- Environmental Law easier → inflated mastery
- Without normalization, students are misjudged

NORMALIZATION RULES:
==================
1. Subject Difficulty Index
   difficulty_index = 1 - (avg_mastery / 100)
   Higher index → harder subject

2. Normalized Percentile Adjustment
   adjusted_percentile = raw_percentile + (difficulty_index × 10)
   Capped between 5% and 95%
   Rounded to nearest integer

3. Confidence Threshold
   If total_attempts < 5 OR cohort_size < 10:
     benchmark_confidence = "low"

CONSTRAINTS:
============
❌ No AI calls
❌ No manual overrides
❌ No hardcoded difficulty values
✅ All derived from live cohort data
✅ Deterministic & auditable
"""

import logging
import statistics
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

MIN_ATTEMPTS_FOR_HIGH_CONFIDENCE = 5
MIN_COHORT_FOR_HIGH_CONFIDENCE = 10
DIFFICULTY_ADJUSTMENT_FACTOR = 10
MIN_PERCENTILE_CAP = 5
MAX_PERCENTILE_CAP = 95

SAFE_EXPLANATIONS = {
    "harder_subject": "This subject is generally considered more challenging.",
    "adjusted_fairness": "Your standing is adjusted to ensure fairness.",
    "normalization_applied": "Difficulty normalization applied.",
    "low_confidence": "Benchmark accuracy improves with more practice."
}


@dataclass
class DifficultyMetrics:
    subject_id: int
    title: str
    cohort_avg: float
    cohort_variance: float
    difficulty_index: float
    is_harder_than_average: bool


@dataclass
class NormalizationResult:
    raw_percentile: Optional[int]
    normalized_percentile: Optional[int]
    confidence: str
    adjustment_applied: float
    note: str


def calculate_difficulty_index(cohort_avg: float) -> float:
    """
    Calculate subject difficulty index from cohort average.
    
    Formula: difficulty_index = 1 - (avg_mastery / 100)
    
    Range: 0.0 (very easy, 100% avg) to 1.0 (very hard, 0% avg)
    
    Higher index → harder subject
    
    This is deterministic: same cohort_avg → same difficulty_index.
    """
    if cohort_avg is None or cohort_avg < 0:
        return 0.5
    
    clamped_avg = max(0, min(100, cohort_avg))
    return round(1 - (clamped_avg / 100), 4)


def calculate_cohort_variance(mastery_values: List[float]) -> float:
    """
    Calculate variance in cohort mastery values.
    
    Higher variance indicates inconsistent difficulty perception.
    Used for confidence assessment.
    """
    if len(mastery_values) < 2:
        return 0.0
    
    try:
        return round(statistics.variance(mastery_values), 4)
    except statistics.StatisticsError:
        return 0.0


def calculate_normalized_percentile(
    raw_percentile: Optional[int],
    difficulty_index: float
) -> Optional[int]:
    """
    Apply difficulty normalization to raw percentile.
    
    Formula: adjusted_percentile = raw_percentile + (difficulty_index × 10)
    
    Constraints:
    - Capped between 5% and 95%
    - Rounded to nearest integer
    
    This rewards students in harder subjects and slightly adjusts
    those in easier subjects, ensuring fairness.
    """
    if raw_percentile is None:
        return None
    
    adjustment = difficulty_index * DIFFICULTY_ADJUSTMENT_FACTOR
    
    adjusted = raw_percentile + adjustment
    
    capped = max(MIN_PERCENTILE_CAP, min(MAX_PERCENTILE_CAP, adjusted))
    
    return round(capped)


def determine_confidence(
    student_attempts: int,
    cohort_size: int,
    cohort_variance: float
) -> str:
    """
    Determine benchmark confidence level.
    
    Confidence is "high" only if:
    - Student has >= 5 attempts
    - Cohort has >= 10 members
    
    Otherwise "low" - UI should show disclaimer.
    """
    if student_attempts < MIN_ATTEMPTS_FOR_HIGH_CONFIDENCE:
        return "low"
    
    if cohort_size < MIN_COHORT_FOR_HIGH_CONFIDENCE:
        return "low"
    
    if cohort_variance > 2000:
        return "medium"
    
    return "high"


def get_normalization_note(
    confidence: str,
    difficulty_index: float,
    adjustment_applied: float
) -> str:
    """
    Generate student-safe explanation note.
    
    Only uses approved safe messages.
    No math formulas or internal weights shown.
    """
    if confidence == "low":
        return SAFE_EXPLANATIONS["low_confidence"]
    
    if difficulty_index > 0.5:
        return SAFE_EXPLANATIONS["harder_subject"]
    
    if abs(adjustment_applied) > 1:
        return SAFE_EXPLANATIONS["normalization_applied"]
    
    return SAFE_EXPLANATIONS["adjusted_fairness"]


def compute_subject_difficulty_metrics(
    subject_id: int,
    title: str,
    cohort_avg: Optional[float],
    cohort_values: List[float]
) -> DifficultyMetrics:
    """
    Compute difficulty metrics for a single subject.
    
    Returns DifficultyMetrics containing:
    - difficulty_index
    - cohort_variance
    - is_harder_than_average flag
    """
    if cohort_avg is None:
        return DifficultyMetrics(
            subject_id=subject_id,
            title=title,
            cohort_avg=0.0,
            cohort_variance=0.0,
            difficulty_index=0.5,
            is_harder_than_average=False
        )
    
    difficulty_index = calculate_difficulty_index(cohort_avg)
    variance = calculate_cohort_variance(cohort_values)
    
    return DifficultyMetrics(
        subject_id=subject_id,
        title=title,
        cohort_avg=cohort_avg,
        cohort_variance=variance,
        difficulty_index=difficulty_index,
        is_harder_than_average=difficulty_index > 0.5
    )


def normalize_subject_benchmark(
    subject_benchmark: Dict[str, Any],
    student_attempts: int,
    cohort_values: List[float]
) -> Dict[str, Any]:
    """
    Apply normalization to a subject benchmark.
    
    Extends the benchmark dict with 'normalized' field.
    
    Returns benchmark with added:
    {
        "normalized": {
            "percentile": 68,
            "confidence": "high",
            "adjustment": 3.2,
            "note": "Difficulty normalization applied."
        },
        "difficulty": {
            "index": 0.32,
            "is_harder": false
        }
    }
    """
    cohort_avg = subject_benchmark.get("cohort_avg")
    raw_percentile = subject_benchmark.get("percentile")
    cohort_size = subject_benchmark.get("cohort_size", 0)
    
    difficulty_metrics = compute_subject_difficulty_metrics(
        subject_benchmark.get("subject_id"),
        subject_benchmark.get("title", ""),
        cohort_avg,
        cohort_values
    )
    
    normalized_percentile = calculate_normalized_percentile(
        raw_percentile,
        difficulty_metrics.difficulty_index
    )
    
    adjustment = 0.0
    if raw_percentile is not None and normalized_percentile is not None:
        adjustment = round(normalized_percentile - raw_percentile, 2)
    
    confidence = determine_confidence(
        student_attempts,
        cohort_size,
        difficulty_metrics.cohort_variance
    )
    
    note = get_normalization_note(
        confidence,
        difficulty_metrics.difficulty_index,
        adjustment
    )
    
    subject_benchmark["normalized"] = {
        "percentile": normalized_percentile,
        "confidence": confidence,
        "adjustment": adjustment,
        "note": note
    }
    
    subject_benchmark["difficulty"] = {
        "index": round(difficulty_metrics.difficulty_index, 2),
        "is_harder": difficulty_metrics.is_harder_than_average
    }
    
    return subject_benchmark


def normalize_overall_benchmark(
    overall: Dict[str, Any],
    subject_benchmarks: List[Dict[str, Any]],
    student_attempts: int,
    cohort_size: int
) -> Dict[str, Any]:
    """
    Apply normalization to overall benchmark.
    
    Computes weighted average of normalized subject percentiles.
    """
    raw_percentile = overall.get("percentile")
    
    valid_normalized = [
        s["normalized"]["percentile"]
        for s in subject_benchmarks
        if s.get("normalized") and s["normalized"].get("percentile") is not None
    ]
    
    if valid_normalized:
        weights = [
            s.get("cohort_size", 1) 
            for s in subject_benchmarks
            if s.get("normalized") and s["normalized"].get("percentile") is not None
        ]
        total_weight = sum(weights)
        if total_weight > 0:
            weighted_sum = sum(p * w for p, w in zip(valid_normalized, weights))
            normalized_percentile = round(weighted_sum / total_weight)
            normalized_percentile = max(MIN_PERCENTILE_CAP, min(MAX_PERCENTILE_CAP, normalized_percentile))
        else:
            normalized_percentile = None
    else:
        normalized_percentile = None
    
    avg_variance = 0.0
    variances = [
        s["difficulty"].get("variance", 0) 
        for s in subject_benchmarks 
        if s.get("difficulty")
    ]
    if variances:
        avg_variance = sum(variances) / len(variances)
    
    confidence = determine_confidence(student_attempts, cohort_size, avg_variance)
    
    adjustment = 0.0
    if raw_percentile is not None and normalized_percentile is not None:
        adjustment = round(normalized_percentile - raw_percentile, 2)
    
    note = get_normalization_note(confidence, 0.5, adjustment)
    
    overall["normalized"] = {
        "percentile": normalized_percentile,
        "confidence": confidence,
        "adjustment": adjustment,
        "note": note
    }
    
    return overall


def apply_benchmark_normalization(
    benchmark_result: Dict[str, Any],
    student_attempts: int,
    cohort_mastery_by_subject: Dict[int, List[float]]
) -> Dict[str, Any]:
    """
    Main entry point: Apply normalization to complete benchmark result.
    
    This is called after Phase 8.2 computes raw benchmarks.
    
    Modifies benchmark_result in-place, adding 'normalized' fields
    to both overall and each subject benchmark.
    
    Args:
        benchmark_result: Full benchmark response from Phase 8.2
        student_attempts: Total attempts by the student
        cohort_mastery_by_subject: Dict mapping subject_id to list of cohort mastery values
    
    Returns:
        Modified benchmark_result with normalization data
    """
    if not benchmark_result.get("success"):
        return benchmark_result
    
    subjects = benchmark_result.get("subjects", [])
    
    for subject in subjects:
        subject_id = subject.get("subject_id")
        cohort_values = cohort_mastery_by_subject.get(subject_id, [])
        normalize_subject_benchmark(subject, student_attempts, cohort_values)
    
    overall = benchmark_result.get("overall")
    cohort_size = benchmark_result.get("cohort", {}).get("active_students", 0)
    
    if overall:
        normalize_overall_benchmark(overall, subjects, student_attempts, cohort_size)
    
    benchmark_result["normalization_applied"] = True
    benchmark_result["normalization_config"] = {
        "adjustment_factor": DIFFICULTY_ADJUSTMENT_FACTOR,
        "min_cap": MIN_PERCENTILE_CAP,
        "max_cap": MAX_PERCENTILE_CAP,
        "min_attempts_for_high_confidence": MIN_ATTEMPTS_FOR_HIGH_CONFIDENCE,
        "min_cohort_for_high_confidence": MIN_COHORT_FOR_HIGH_CONFIDENCE
    }
    
    logger.info(
        f"Applied benchmark normalization: "
        f"subjects={len(subjects)}, "
        f"student_attempts={student_attempts}, "
        f"overall_confidence={overall.get('normalized', {}).get('confidence') if overall else 'N/A'}"
    )
    
    return benchmark_result
