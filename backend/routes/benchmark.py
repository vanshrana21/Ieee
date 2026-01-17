"""
backend/routes/benchmark.py
Phase 8.1: Peer Cohort Benchmarking API

Provides anonymous cohort aggregation for benchmarking.
NO user identifiers in output.
NO ranks or percentiles yet (Phase 8.1 is aggregation only).
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any

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
