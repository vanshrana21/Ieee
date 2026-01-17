"""
backend/routes/exam_readiness.py
Phase 7.4: Exam Readiness Index (ERI) API Routes

Provides endpoints for:
- Getting ERI score
- Diagnostic reports
- Trend data
- Subject comparisons
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List

from backend.database import get_db
from backend.orm.user import User
from backend.routes.auth import get_current_user
from backend.services.exam_readiness_service import (
    calculate_eri,
    generate_diagnostics,
    get_eri_trend,
    compare_readiness_by_subject,
    ERI_BANDS,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/exams", tags=["exam-readiness"])


@router.get("/readiness")
async def get_exam_readiness(
    subject_id: Optional[int] = Query(default=None, description="Filter by subject"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get Exam Readiness Index (ERI) for the current user.
    
    ERI Formula:
    ERI = (Knowledge × 0.35) + (Application × 0.30) + (Strategy × 0.20) + (Consistency × 0.15)
    
    Returns:
    - eri_score: 0-100
    - band: Exam Ready / Almost Ready / Needs Revision / High Risk
    - components: Detailed breakdown of each component
    - impact_analysis: How each component contributes to final score
    
    All calculations are deterministic and explainable.
    """
    try:
        result = await calculate_eri(current_user.id, db, subject_id)
        return result
        
    except Exception as e:
        logger.error(f"ERI calculation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to calculate readiness index"
        )


@router.get("/readiness/diagnostics")
async def get_readiness_diagnostics(
    subject_id: Optional[int] = Query(default=None, description="Filter by subject"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get comprehensive diagnostic report.
    
    Includes:
    - ERI score and components
    - Strength summary
    - Weak topic list
    - Time management issues
    - Marks leakage analysis
    - Priority fixes (Top 5 actionable recommendations)
    
    Every recommendation is backed by data and is actionable.
    """
    try:
        result = await generate_diagnostics(current_user.id, db, subject_id)
        return result
        
    except Exception as e:
        logger.error(f"Diagnostics error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate diagnostics"
        )


@router.get("/readiness/trend")
async def get_readiness_trend(
    days: int = Query(default=30, ge=7, le=90, description="Lookback days"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get ERI trend data for visualization.
    
    Returns exam results over time to show:
    - Improving trend
    - Stable performance
    - Declining trend
    
    Useful for dashboard charts and progress tracking.
    """
    try:
        result = await get_eri_trend(current_user.id, db, days)
        return {
            "trend_data": result,
            "period_days": days,
            "data_points": len(result)
        }
        
    except Exception as e:
        logger.error(f"Trend error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get trend data"
        )


@router.get("/readiness/compare")
async def compare_subject_readiness(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Compare ERI across all subjects.
    
    Returns list of subjects with their ERI scores, sorted by readiness.
    Helps identify which subjects need more attention.
    """
    try:
        result = await compare_readiness_by_subject(current_user.id, db)
        return {
            "comparisons": result,
            "subject_count": len(result)
        }
        
    except Exception as e:
        logger.error(f"Compare error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to compare subjects"
        )


@router.get("/readiness/bands")
async def get_eri_bands():
    """
    Get ERI band definitions.
    
    Returns:
    - Band names and score ranges
    - Colors for UI
    - Messages for each band
    """
    return {
        "bands": [
            {
                "band": band["band"],
                "min_score": band["min"],
                "max_score": band["max"],
                "color": band["color"],
                "message": band["message"]
            }
            for band in ERI_BANDS
        ]
    }


@router.get("/readiness/formula")
async def get_eri_formula():
    """
    Get ERI formula explanation.
    
    Returns complete documentation of how ERI is calculated,
    including all component weights and sub-formulas.
    
    For transparency and trust in the system.
    """
    return {
        "formula": "ERI = (Knowledge × 0.35) + (Application × 0.30) + (Strategy × 0.20) + (Consistency × 0.15)",
        "components": [
            {
                "name": "Knowledge Readiness",
                "weight": 0.35,
                "formula": "Knowledge = (Subject Mastery × 0.60) + (Topic Coverage × 0.40)",
                "data_sources": ["topic_mastery", "subject_progress"],
                "description": "Measures understanding of legal concepts and topic coverage"
            },
            {
                "name": "Application Readiness",
                "weight": 0.30,
                "formula": "Application = (Case Analysis × 0.50) + (Essay Quality × 0.50)",
                "data_sources": ["exam_answer_evaluations", "practice_evaluations"],
                "description": "Measures ability to apply law to facts in exam answers"
            },
            {
                "name": "Strategy Readiness",
                "weight": 0.20,
                "formula": "Strategy = (Time Management × 0.50) + (Completion Rate × 0.30) + (Distribution × 0.20)",
                "data_sources": ["exam_sessions", "exam_answers"],
                "description": "Measures exam-taking skills and time management"
            },
            {
                "name": "Consistency & Confidence",
                "weight": 0.15,
                "formula": "Consistency = (Frequency × 0.40) + (Stability × 0.35) + (Trend × 0.25)",
                "data_sources": ["practice_attempts", "exam_session_evaluations"],
                "description": "Measures practice regularity and performance stability"
            }
        ],
        "bands": [
            {"range": "80-100", "band": "Exam Ready", "description": "Well prepared for the exam"},
            {"range": "60-79", "band": "Almost Ready", "description": "Good progress, focus on weak areas"},
            {"range": "40-59", "band": "Needs Revision", "description": "Increase practice intensity"},
            {"range": "0-39", "band": "High Risk", "description": "Significant preparation needed"}
        ],
        "principles": [
            "All calculations are deterministic - same inputs always produce same outputs",
            "No ML black boxes - every score is explainable",
            "Uses only existing database tables",
            "Every component is traceable to specific data sources"
        ]
    }


@router.get("/readiness/summary")
async def get_readiness_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get a quick ERI summary for dashboard display.
    
    Lightweight endpoint returning just the essentials:
    - ERI score and band
    - Top recommendation
    - Trend direction
    """
    try:
        eri_data = await calculate_eri(current_user.id, db)
        
        top_recommendation = None
        consistency = eri_data["components"]["consistency"]
        knowledge = eri_data["components"]["knowledge"]
        
        if knowledge["weak_topics"]:
            top_recommendation = f"Focus on {knowledge['weak_topics'][0]['topic']}"
        elif consistency["trend_direction"] == "declining":
            top_recommendation = "Review recent weak areas"
        elif consistency["study_streak"] < 3:
            top_recommendation = "Maintain daily practice"
        else:
            top_recommendation = "Continue your great progress!"
        
        return {
            "eri_score": eri_data["eri_score"],
            "band": eri_data["band"],
            "band_color": eri_data["band_color"],
            "trend_direction": consistency["trend_direction"],
            "study_streak": consistency["study_streak"],
            "top_recommendation": top_recommendation,
            "calculated_at": eri_data["calculated_at"]
        }
        
    except Exception as e:
        logger.error(f"Summary error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get readiness summary"
        )
