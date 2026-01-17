"""
backend/routes/benchmark.py
Phase 8.1 & 8.2: Peer Cohort Benchmarking API

Phase 8.1: Anonymous cohort aggregation
Phase 8.2: Percentile comparison and performance bands

Privacy guarantees:
- NO user identifiers in output
- NO exact ranks (never "Rank 23 of 140")
- NO peer identities exposed
- All comparisons are relative percentiles only
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any, Optional

from fastapi import Query

from backend.database import get_db
from backend.orm.user import User
from backend.routes.auth import get_current_user
from backend.services.cohort_aggregation_service import (
    get_cohort_aggregation,
    get_empty_cohort_response,
    get_cohort_definition,
    ACTIVITY_WINDOW_DAYS,
    DISTRIBUTION_WEAK_THRESHOLD,
    DISTRIBUTION_STRONG_THRESHOLD,
)
from backend.services.benchmark_percentile_service import (
    get_benchmark_comparison,
    get_subject_percentile_detail,
    MIN_COHORT_SIZE,
    MIN_ATTEMPTS_FOR_BENCHMARK,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/benchmark", tags=["benchmark"])


@router.get("/cohort")
async def get_cohort_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get cohort aggregation for the current user.
    
    Cohort Definition:
    - Same course (BA LLB / BBA LLB / LLB)
    - Same semester
    - Active in last 90 days (at least 1 practice attempt)
    
    Returns:
    - cohort: Course, semester, student counts
    - subjects: Per-subject aggregated stats (avg, median, distribution)
    - global_stats: Cohort-wide practice statistics
    
    Privacy:
    - NO user identifiers in output
    - All data is aggregated
    - Deterministic (same input → same output)
    
    Works even if:
    - Cohort size < 10 students
    - User has no progress yet
    - No subjects in curriculum
    """
    try:
        result = await get_cohort_aggregation(current_user.id, db)
        return result
        
    except Exception as e:
        logger.error(f"Cohort aggregation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to aggregate cohort data"
        )


@router.get("/cohort/definition")
async def get_user_cohort_definition(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get the cohort definition parameters for current user.
    
    Shows what defines this user's cohort:
    - course_id and name
    - semester number
    
    Useful for understanding which peer group the user belongs to.
    """
    try:
        result = await get_cohort_definition(current_user.id, db)
        
        if "error" in result:
            return {
                "success": False,
                "error": result["error"],
                "cohort_defined": False
            }
        
        return {
            "success": True,
            "cohort_defined": True,
            "course_id": result["course_id"],
            "course_name": result["course_name"],
            "course_code": result["course_code"],
            "semester": result["semester"],
            "activity_window_days": ACTIVITY_WINDOW_DAYS
        }
        
    except Exception as e:
        logger.error(f"Cohort definition error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get cohort definition"
        )


@router.get("/cohort/config")
async def get_cohort_config() -> Dict[str, Any]:
    """
    Get cohort aggregation configuration.
    
    Returns the rules used for cohort definition and aggregation:
    - Activity window (90 days)
    - Distribution thresholds
    - What defines a cohort
    
    For transparency and documentation.
    """
    return {
        "cohort_rules": {
            "defined_by": [
                "course_id (BA LLB / BBA LLB / LLB)",
                "current_semester (exact match)",
                "activity_window (at least 1 attempt in last N days)"
            ],
            "not_used": [
                "college name",
                "user role",
                "year of admission",
                "random sampling"
            ]
        },
        "activity_window_days": ACTIVITY_WINDOW_DAYS,
        "distribution_thresholds": {
            "weak": f"< {DISTRIBUTION_WEAK_THRESHOLD}%",
            "average": f"{DISTRIBUTION_WEAK_THRESHOLD}% - {DISTRIBUTION_STRONG_THRESHOLD}%",
            "strong": f">= {DISTRIBUTION_STRONG_THRESHOLD}%"
        },
        "aggregation_metrics": {
            "per_subject": [
                "students_with_progress",
                "avg_mastery",
                "median_mastery (P50)",
                "distribution (weak/average/strong counts)"
            ],
            "global": [
                "avg_attempts_per_student",
                "avg_answers_per_student",
                "avg_time_per_attempt"
            ]
        },
        "data_sources": [
            "users (course_id, current_semester)",
            "practice_attempts (activity detection)",
            "subject_progress (mastery/completion)",
            "course_curriculum (subject mapping)"
        ],
        "guarantees": [
            "Deterministic (same input → same output)",
            "No randomness",
            "No user identifiers in output",
            "Works with any cohort size including < 10"
        ]
    }


@router.get("/compare")
async def get_benchmark_compare(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get benchmark comparison for the current user (Phase 8.2).
    
    Computes:
    - Overall percentile (weighted avg of subject percentiles)
    - Per-subject percentile, band, and label
    - Weakest and strongest subject identification
    
    Percentile Calculation:
    - Uses PERCENT_RANK: (count below your score) / (total - 1) × 100
    - Cohort must have >= 10 students for valid percentile
    - Student must have >= 3 attempts to be eligible
    
    Performance Bands:
    - Bottom 25%: percentile < 25
    - Middle 50%: 25 <= percentile < 75
    - Top 25%: percentile >= 75
    
    Privacy:
    - NO exact ranks (never "Rank 23 of 140")
    - NO peer identities
    - Only relative percentile position
    
    Deterministic: Same mastery → Same percentile
    """
    try:
        result = await get_benchmark_comparison(current_user.id, db)
        return result
        
    except Exception as e:
        logger.error(f"Benchmark comparison error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to compute benchmark comparison"
        )


@router.get("/compare/subject/{subject_id}")
async def get_subject_benchmark(
    subject_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get detailed benchmark for a specific subject.
    
    Returns:
    - Student's mastery vs cohort average
    - Percentile within cohort
    - Performance band
    - Human-readable label
    - Explanation of calculation
    
    Useful for drill-down views.
    """
    try:
        result = await get_subject_percentile_detail(current_user.id, subject_id, db)
        return result
        
    except Exception as e:
        logger.error(f"Subject benchmark error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get subject benchmark"
        )


@router.get("/compare/config")
async def get_compare_config() -> Dict[str, Any]:
    """
    Get percentile calculation configuration.
    
    Documents how benchmarks are calculated for transparency.
    """
    return {
        "percentile_calculation": {
            "formula": "PERCENT_RANK = (count below your score) / (total students - 1) × 100",
            "min_cohort_size": MIN_COHORT_SIZE,
            "min_attempts_required": MIN_ATTEMPTS_FOR_BENCHMARK,
            "rounding": "Nearest whole number",
            "deterministic": True
        },
        "performance_bands": {
            "Bottom 25%": "percentile < 25",
            "Middle 50%": "25 <= percentile < 75",
            "Top 25%": "percentile >= 75"
        },
        "relative_labels": {
            "Strong relative to peers": "Top 25%",
            "Above average": "Above cohort mean",
            "At average": "Within ±5% of cohort mean",
            "Below average": "Below cohort mean",
            "Needs improvement relative to peers": "Bottom 25%"
        },
        "edge_cases": {
            "small_cohort": f"If cohort < {MIN_COHORT_SIZE}, percentile marked as insufficient_data",
            "new_student": f"Benchmark available after {MIN_ATTEMPTS_FOR_BENCHMARK} attempts",
            "no_mastery": "Subject excluded if student has no progress"
        },
        "privacy_guarantees": [
            "No exact ranks (never 'Rank 23 of 140')",
            "No peer identities exposed",
            "No leaderboard functionality",
            "All comparisons are relative percentiles only"
        ]
    }
