"""
backend/routes/diagnostics.py
Phase 6.2: Diagnostic Intelligence API Routes

Provides endpoints for mistake pattern detection and diagnostic insights.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional, Dict, Any, List

from backend.database import get_db
from backend.orm.user import User
from backend.routes.auth import get_current_user
from backend.services.mistake_pattern_service import (
    run_diagnostic_analysis,
    get_quick_diagnosis,
    get_patterns_for_topic,
    PatternType,
    Severity,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])


class PatternResponse(BaseModel):
    pattern_type: str
    severity: str
    evidence: List[Dict[str, Any]]
    explanation: str
    recommended_fix: List[str]
    topic_tags: List[str]
    frequency: int
    first_detected: Optional[str]
    last_detected: Optional[str]


class DiagnosticReportResponse(BaseModel):
    user_id: int
    generated_at: str
    total_attempts_analyzed: int
    patterns: List[PatternResponse]
    summary: Dict[str, Any]
    topic_breakdown: Dict[str, Dict[str, Any]]
    recommendations: List[str]


class QuickDiagnosisResponse(BaseModel):
    user_id: int
    generated_at: str
    critical_patterns: int
    weak_topics: List[str]
    top_recommendation: Optional[str]
    average_score: Optional[float]
    pattern_types: List[str]


@router.get("/full", response_model=DiagnosticReportResponse)
async def get_full_diagnostic_report(
    limit: int = Query(default=100, ge=10, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get full diagnostic report with all detected patterns.
    
    Analyzes practice attempts and evaluations to identify:
    - Conceptual weaknesses
    - Structure errors
    - Application deficiencies
    - Time management issues
    - Improvement failures
    - Case integration gaps
    
    Returns detailed patterns with evidence, severity, and recommendations.
    """
    try:
        report = await run_diagnostic_analysis(
            user_id=current_user.id,
            db=db,
            limit=limit
        )
        
        return DiagnosticReportResponse(
            user_id=report.user_id,
            generated_at=report.generated_at,
            total_attempts_analyzed=report.total_attempts_analyzed,
            patterns=[
                PatternResponse(
                    pattern_type=p.pattern_type.value,
                    severity=p.severity.value,
                    evidence=p.evidence,
                    explanation=p.explanation,
                    recommended_fix=p.recommended_fix,
                    topic_tags=p.topic_tags,
                    frequency=p.frequency,
                    first_detected=p.first_detected,
                    last_detected=p.last_detected,
                )
                for p in report.patterns
            ],
            summary=report.summary,
            topic_breakdown=report.topic_breakdown,
            recommendations=report.recommendations,
        )
        
    except Exception as e:
        logger.error(f"Diagnostic analysis failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate diagnostic report"
        )


@router.get("/quick", response_model=QuickDiagnosisResponse)
async def get_quick_diagnostic(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get quick diagnostic summary for dashboard display.
    
    Returns:
    - Number of critical patterns
    - Weak topics (up to 3)
    - Top recommendation
    - Average score
    - Pattern types detected
    """
    try:
        result = await get_quick_diagnosis(
            user_id=current_user.id,
            db=db
        )
        
        return QuickDiagnosisResponse(**result)
        
    except Exception as e:
        logger.error(f"Quick diagnosis failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate quick diagnosis"
        )


@router.get("/topic/{topic_tag}")
async def get_topic_diagnostic(
    topic_tag: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get diagnostic patterns specific to a topic.
    
    Used by AI Tutor to provide context-aware responses.
    """
    try:
        patterns = await get_patterns_for_topic(
            user_id=current_user.id,
            topic_tag=topic_tag,
            db=db
        )
        
        return {
            "topic_tag": topic_tag,
            "patterns_count": len(patterns),
            "patterns": [p.to_dict() for p in patterns],
            "has_issues": len(patterns) > 0,
            "severity_level": max(
                (p.severity.value for p in patterns),
                default="none"
            ) if patterns else "none",
        }
        
    except Exception as e:
        logger.error(f"Topic diagnostic failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get topic diagnostic"
        )


@router.get("/patterns/types")
async def get_pattern_types():
    """
    Get all available pattern types with descriptions.
    """
    return {
        "pattern_types": [
            {
                "type": PatternType.CONCEPTUAL_WEAKNESS.value,
                "description": "Repeated low scores in the same topic, indicating fundamental misunderstanding",
            },
            {
                "type": PatternType.STRUCTURE_ERROR.value,
                "description": "Missing introduction, conclusion, or issue framing in answers",
            },
            {
                "type": PatternType.APPLICATION_DEFICIENCY.value,
                "description": "Theory present but not applied to facts",
            },
            {
                "type": PatternType.TIME_MANAGEMENT_ISSUE.value,
                "description": "Very short answers or rushed submissions",
            },
            {
                "type": PatternType.IMPROVEMENT_FAILURE.value,
                "description": "Reattempts without meaningful score improvement",
            },
            {
                "type": PatternType.CASE_INTEGRATION_GAP.value,
                "description": "Missing case citations in essay/analysis answers",
            },
        ],
        "severity_levels": [
            {"level": Severity.LOW.value, "description": "Minor issue, easy to address"},
            {"level": Severity.MEDIUM.value, "description": "Notable pattern, needs attention"},
            {"level": Severity.HIGH.value, "description": "Significant issue affecting performance"},
            {"level": Severity.CRITICAL.value, "description": "Severe recurring pattern, immediate action needed"},
        ],
    }


@router.get("/summary")
async def get_diagnostic_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get diagnostic summary with topic breakdown.
    
    Lighter than full report - excludes detailed evidence.
    Used for study planner integration.
    """
    try:
        report = await run_diagnostic_analysis(
            user_id=current_user.id,
            db=db,
            limit=50
        )
        
        return {
            "user_id": report.user_id,
            "generated_at": report.generated_at,
            "summary": report.summary,
            "topic_breakdown": report.topic_breakdown,
            "recommendations": report.recommendations,
            "pattern_summary": [
                {
                    "type": p.pattern_type.value,
                    "severity": p.severity.value,
                    "frequency": p.frequency,
                }
                for p in report.patterns
            ],
        }
        
    except Exception as e:
        logger.error(f"Diagnostic summary failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get diagnostic summary"
        )
