"""
backend/services/benchmark_percentile_service.py
Phase 8.2: Benchmark Metrics & Percentile Engine

SYSTEM PURPOSE:
Compute percentile position, performance band, and relative standing
for each student compared to their cohort (defined in Phase 8.1).

METRICS COMPUTED:
=================
Per subject:
- percentile: Based on subject mastery vs cohort (PERCENT_RANK)
- band: Bottom 25% / Middle 50% / Top 25%
- label: Below average / At average / Above average

Global:
- overall_percentile: Weighted average of subject percentiles
- weakest_subject: Lowest percentile subject
- strongest_subject: Highest percentile subject

PERCENTILE RULES:
================
- Use PERCENT_RANK logic: (count of values < x) / (total count - 1)
- If cohort < 10 → mark as "insufficient_data"
- Round to nearest whole number
- Deterministic only (no randomness)
- Same mastery → same percentile

CONSTRAINTS:
============
❌ No exact ranks (never "Rank 23 of 140")
❌ No peer identities
❌ No AI calls
✅ Explainable math only
✅ Transparent calculations
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from backend.orm.user import User
from backend.orm.subject import Subject
from backend.orm.subject_progress import SubjectProgress
from backend.orm.practice_attempt import PracticeAttempt
from backend.services.cohort_aggregation_service import (
    get_cohort_definition,
    get_active_cohort_members,
    get_cohort_subjects,
    ACTIVITY_WINDOW_DAYS,
)
from backend.services.benchmark_normalization_service import (
    apply_benchmark_normalization,
)

logger = logging.getLogger(__name__)

MIN_COHORT_SIZE = 10
MIN_ATTEMPTS_FOR_BENCHMARK = 3


def calculate_percent_rank(value: float, all_values: List[float]) -> Optional[int]:
    """
    Calculate PERCENT_RANK for a value within a list.
    
    Formula: (count of values < x) / (total count - 1) * 100
    
    Returns:
    - Percentile as integer (0-100)
    - None if insufficient data
    
    This is deterministic: same value + same list = same result.
    """
    if len(all_values) < MIN_COHORT_SIZE:
        return None
    
    if len(all_values) == 1:
        return 50
    
    count_below = sum(1 for v in all_values if v < value)
    
    percent_rank = (count_below / (len(all_values) - 1)) * 100
    
    return round(percent_rank)


def get_performance_band(percentile: Optional[int]) -> str:
    """
    Determine performance band from percentile.
    
    Bands:
    - Bottom 25%: percentile < 25
    - Middle 50%: 25 <= percentile < 75
    - Top 25%: percentile >= 75
    """
    if percentile is None:
        return "insufficient_data"
    
    if percentile < 25:
        return "Bottom 25%"
    elif percentile < 75:
        return "Middle 50%"
    else:
        return "Top 25%"


def get_relative_label(percentile: Optional[int], student_mastery: float, cohort_avg: Optional[float]) -> str:
    """
    Generate human-readable label for relative standing.
    
    Labels:
    - "Below average" if mastery < cohort_avg
    - "At average" if within ±5% of cohort_avg
    - "Above average" if mastery > cohort_avg
    - "Strong relative to peers" if Top 25%
    - "Needs improvement" if Bottom 25%
    """
    if percentile is None:
        return "Benchmark available after more peer data"
    
    if cohort_avg is None:
        return "No cohort data"
    
    if percentile >= 75:
        return "Strong relative to peers"
    elif percentile < 25:
        return "Needs improvement relative to peers"
    elif abs(student_mastery - cohort_avg) <= 5:
        return "At average"
    elif student_mastery > cohort_avg:
        return "Above average"
    else:
        return "Below average"


async def get_student_mastery(
    user_id: int,
    subject_id: int,
    db: AsyncSession
) -> Optional[float]:
    """
    Get student's mastery for a subject.
    
    Uses subject_progress.completion_percentage.
    Returns None if no progress data.
    """
    progress_stmt = select(SubjectProgress.completion_percentage).where(
        and_(
            SubjectProgress.user_id == user_id,
            SubjectProgress.subject_id == subject_id
        )
    )
    
    result = await db.execute(progress_stmt)
    row = result.fetchone()
    
    if row and row[0] is not None:
        return float(row[0])
    return None


async def get_cohort_mastery_values(
    subject_id: int,
    cohort_user_ids: List[int],
    db: AsyncSession
) -> List[float]:
    """
    Get all mastery values for a subject within the cohort.
    
    Returns list of non-null completion_percentage values.
    Used for percentile calculation.
    """
    if not cohort_user_ids:
        return []
    
    progress_stmt = select(SubjectProgress.completion_percentage).where(
        and_(
            SubjectProgress.subject_id == subject_id,
            SubjectProgress.user_id.in_(cohort_user_ids),
            SubjectProgress.completion_percentage.isnot(None)
        )
    )
    
    result = await db.execute(progress_stmt)
    return [float(row[0]) for row in result.fetchall() if row[0] is not None]


async def get_student_attempt_count(
    user_id: int,
    db: AsyncSession
) -> int:
    """
    Get total practice attempts for a student.
    
    Used to check if student has enough data for benchmarking.
    """
    from sqlalchemy import func
    
    count_stmt = select(func.count(PracticeAttempt.id)).where(
        PracticeAttempt.user_id == user_id
    )
    
    result = await db.execute(count_stmt)
    return result.scalar() or 0


async def compute_subject_benchmark(
    user_id: int,
    subject_id: int,
    subject_title: str,
    cohort_user_ids: List[int],
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Compute benchmark metrics for a single subject.
    
    Returns:
    {
        "subject_id": 1,
        "title": "Constitutional Law",
        "student_mastery": 64.2,
        "cohort_avg": 58.2,
        "cohort_median": 61.0,
        "percentile": 71,
        "band": "Top 25%",
        "label": "Strong relative to peers",
        "cohort_size": 142
    }
    """
    student_mastery = await get_student_mastery(user_id, subject_id, db)
    cohort_values = await get_cohort_mastery_values(subject_id, cohort_user_ids, db)
    
    if not cohort_values:
        return {
            "subject_id": subject_id,
            "title": subject_title,
            "student_mastery": student_mastery,
            "cohort_avg": None,
            "cohort_median": None,
            "percentile": None,
            "band": "insufficient_data",
            "label": "No cohort data available",
            "cohort_size": 0
        }
    
    import statistics
    cohort_avg = statistics.mean(cohort_values)
    cohort_median = statistics.median(cohort_values)
    
    if student_mastery is None:
        return {
            "subject_id": subject_id,
            "title": subject_title,
            "student_mastery": None,
            "cohort_avg": round(cohort_avg, 2),
            "cohort_median": round(cohort_median, 2),
            "percentile": None,
            "band": "no_student_data",
            "label": "Complete practice to see benchmark",
            "cohort_size": len(cohort_values)
        }
    
    percentile = calculate_percent_rank(student_mastery, cohort_values)
    band = get_performance_band(percentile)
    label = get_relative_label(percentile, student_mastery, cohort_avg)
    
    return {
        "subject_id": subject_id,
        "title": subject_title,
        "student_mastery": round(student_mastery, 2),
        "cohort_avg": round(cohort_avg, 2),
        "cohort_median": round(cohort_median, 2),
        "percentile": percentile,
        "band": band,
        "label": label,
        "cohort_size": len(cohort_values)
    }


def compute_overall_benchmark(subject_benchmarks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Compute overall benchmark from subject benchmarks.
    
    Overall percentile = weighted average of subject percentiles
    (weighted by cohort_size to give more weight to subjects with more data)
    
    Returns:
    {
        "percentile": 62,
        "band": "Middle 50%",
        "label": "Above average",
        "weakest_subject": {...},
        "strongest_subject": {...},
        "subjects_benchmarked": 5
    }
    """
    valid_benchmarks = [
        b for b in subject_benchmarks 
        if b["percentile"] is not None and b["cohort_size"] > 0
    ]
    
    if not valid_benchmarks:
        return {
            "percentile": None,
            "band": "insufficient_data",
            "label": "Complete more practice to see overall benchmark",
            "weakest_subject": None,
            "strongest_subject": None,
            "subjects_benchmarked": 0
        }
    
    total_weight = sum(b["cohort_size"] for b in valid_benchmarks)
    weighted_sum = sum(b["percentile"] * b["cohort_size"] for b in valid_benchmarks)
    
    overall_percentile = round(weighted_sum / total_weight) if total_weight > 0 else None
    
    sorted_by_percentile = sorted(valid_benchmarks, key=lambda x: x["percentile"])
    weakest = sorted_by_percentile[0]
    strongest = sorted_by_percentile[-1]
    
    overall_band = get_performance_band(overall_percentile)
    
    if overall_percentile is None:
        overall_label = "Insufficient data"
    elif overall_percentile >= 75:
        overall_label = "Performing above most peers"
    elif overall_percentile < 25:
        overall_label = "Room for improvement"
    elif overall_percentile >= 50:
        overall_label = "Above average"
    else:
        overall_label = "Below average"
    
    return {
        "percentile": overall_percentile,
        "band": overall_band,
        "label": overall_label,
        "weakest_subject": {
            "subject_id": weakest["subject_id"],
            "title": weakest["title"],
            "percentile": weakest["percentile"]
        },
        "strongest_subject": {
            "subject_id": strongest["subject_id"],
            "title": strongest["title"],
            "percentile": strongest["percentile"]
        },
        "subjects_benchmarked": len(valid_benchmarks)
    }


async def get_benchmark_comparison(
    user_id: int,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Get complete benchmark comparison for a student.
    
    Main entry point for Phase 8.2.
    
    Returns:
    {
        "success": true,
        "overall": {
            "percentile": 62,
            "band": "Middle 50%",
            "label": "Above average"
        },
        "subjects": [
            {
                "subject_id": 1,
                "title": "Constitutional Law",
                "student_mastery": 64.2,
                "cohort_avg": 58.2,
                "percentile": 71,
                "band": "Top 25%",
                "label": "Strong relative to peers"
            }
        ],
        "cohort": {...},
        "eligibility": {...}
    }
    """
    cohort_def = await get_cohort_definition(user_id, db)
    
    if "error" in cohort_def:
        return {
            "success": False,
            "error": cohort_def["error"],
            "overall": None,
            "subjects": [],
            "cohort": None,
            "eligibility": {"eligible": False, "reason": cohort_def["error"]}
        }
    
    course_id = cohort_def["course_id"]
    semester = cohort_def["semester"]
    
    attempt_count = await get_student_attempt_count(user_id, db)
    
    if attempt_count < MIN_ATTEMPTS_FOR_BENCHMARK:
        return {
            "success": True,
            "overall": {
                "percentile": None,
                "band": "insufficient_data",
                "label": f"Benchmark available after {MIN_ATTEMPTS_FOR_BENCHMARK} attempts"
            },
            "subjects": [],
            "cohort": {
                "course": cohort_def["course_name"],
                "semester": semester
            },
            "eligibility": {
                "eligible": False,
                "reason": f"Need {MIN_ATTEMPTS_FOR_BENCHMARK - attempt_count} more attempts",
                "attempts_completed": attempt_count,
                "attempts_required": MIN_ATTEMPTS_FOR_BENCHMARK
            }
        }
    
    cohort_user_ids = await get_active_cohort_members(course_id, semester, db)
    
    subjects = await get_cohort_subjects(course_id, semester, db)
    
    subject_benchmarks = []
    cohort_mastery_by_subject = {}
    
    for subject in subjects:
        subject_id = subject["subject_id"]
        cohort_values = await get_cohort_mastery_values(subject_id, cohort_user_ids, db)
        cohort_mastery_by_subject[subject_id] = cohort_values
        
        benchmark = await compute_subject_benchmark(
            user_id,
            subject_id,
            subject["title"],
            cohort_user_ids,
            db
        )
        subject_benchmarks.append(benchmark)
    
    overall = compute_overall_benchmark(subject_benchmarks)
    
    cohort_size = len(cohort_user_ids)
    small_cohort = cohort_size < MIN_COHORT_SIZE
    
    result = {
        "success": True,
        "overall": overall,
        "subjects": subject_benchmarks,
        "cohort": {
            "course": cohort_def["course_name"],
            "course_code": cohort_def["course_code"],
            "semester": semester,
            "active_students": cohort_size,
            "small_cohort_warning": small_cohort,
            "activity_window_days": ACTIVITY_WINDOW_DAYS
        },
        "eligibility": {
            "eligible": True,
            "attempts_completed": attempt_count,
            "min_cohort_size": MIN_COHORT_SIZE
        },
        "calculated_at": datetime.utcnow().isoformat()
    }
    
    result = apply_benchmark_normalization(
        result,
        attempt_count,
        cohort_mastery_by_subject
    )
    
    logger.info(
        f"Benchmark comparison for user={user_id}: "
        f"overall_percentile={overall['percentile']}, "
        f"normalized_percentile={overall.get('normalized', {}).get('percentile')}, "
        f"subjects_benchmarked={overall['subjects_benchmarked']}, "
        f"cohort_size={cohort_size}"
    )
    
    return result


async def get_subject_percentile_detail(
    user_id: int,
    subject_id: int,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Get detailed percentile breakdown for a single subject.
    
    Useful for drill-down views.
    """
    cohort_def = await get_cohort_definition(user_id, db)
    
    if "error" in cohort_def:
        return {"success": False, "error": cohort_def["error"]}
    
    cohort_user_ids = await get_active_cohort_members(
        cohort_def["course_id"], 
        cohort_def["semester"], 
        db
    )
    
    subject_stmt = select(Subject).where(Subject.id == subject_id)
    subject_result = await db.execute(subject_stmt)
    subject = subject_result.scalar_one_or_none()
    
    if not subject:
        return {"success": False, "error": "Subject not found"}
    
    benchmark = await compute_subject_benchmark(
        user_id,
        subject_id,
        subject.title,
        cohort_user_ids,
        db
    )
    
    return {
        "success": True,
        "benchmark": benchmark,
        "explanation": {
            "formula": "PERCENT_RANK = (count below your score) / (total students - 1) × 100",
            "your_mastery": benchmark["student_mastery"],
            "cohort_average": benchmark["cohort_avg"],
            "cohort_size": benchmark["cohort_size"],
            "interpretation": f"You performed better than {benchmark['percentile']}% of your peers" if benchmark["percentile"] else "Insufficient data"
        }
    }
