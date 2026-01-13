"""
backend/routes/analytics.py
Learning Analytics API Endpoints

PHASE 10: Read-only intelligence endpoints

All endpoints:
- JWT protected
- Read-only (no mutations)
- Call analytics service
- Return standardized JSON
- No AI/LLM calls
"""
import logging
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.orm.user import User
from backend.routes.auth import get_current_user
from backend.services.learning_analytics_service import (
    get_learning_analytics_service,
    LearningAnalyticsService,
    StrengthLevel,
    RevisionPriority
)
from backend.schemas.analytics import (
    AnalyticsAPIResponse,
    LearningSnapshotResponse,
    SubjectStrengthMapResponse,
    SubjectStrengthItem,
    PracticeAccuracyResponse,
    RevisionRecommendationsResponse,
    RevisionItem,
    StudyConsistencyResponse,
    ComprehensiveAnalyticsResponse
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["Learning Analytics"])


# ================= DEPENDENCY =================

async def get_analytics_service(
    db: AsyncSession = Depends(get_db)
) -> LearningAnalyticsService:
    """Dependency to inject analytics service"""
    return get_learning_analytics_service(db)


# ================= API ENDPOINTS =================

@router.get("/overview", response_model=AnalyticsAPIResponse)
async def get_analytics_overview(
    current_user: User = Depends(get_current_user),
    analytics: LearningAnalyticsService = Depends(get_analytics_service)
):
    """
    Get high-level learning analytics overview.
    
    PHASE 10 ENDPOINT - Learning Intelligence
    
    Provides:
    - Overall completion percentage
    - Overall accuracy
    - Study consistency level
    - Subject strength summary
    - Revision needs count
    
    Returns comprehensive snapshot of learning progress.
    
    SECURITY:
    - JWT authentication required
    - User can only see their own data
    
    RESPONSE:
        {
            "success": true,
            "message": "Analytics retrieved successfully",
            "data": {
                "total_subjects": 8,
                "overall_completion": 37.5,
                "overall_accuracy": 76.0,
                "study_consistency": "good",
                "weak_subjects_count": 2,
                "strong_subjects_count": 3,
                "needs_revision_count": 2,
                "last_activity": "2026-01-12T14:30:00Z"
            }
        }
    """
    logger.info(f"[ANALYTICS] Overview requested: user={current_user.email}")
    
    try:
        # Get learning snapshot from service
        snapshot = await analytics.get_user_learning_snapshot(current_user.id)
        
        # Also get consistency metrics for detail
        consistency = await analytics.get_study_consistency_metrics(current_user.id)
        
        # Combine into response
        data = {
            **snapshot,
            "consistency_details": consistency
        }
        
        logger.info(
            f"[ANALYTICS] Overview generated: user={current_user.email}, "
            f"completion={snapshot['overall_completion']}%"
        )
        
        return {
            "success": True,
            "message": "Analytics overview retrieved successfully",
            "data": data
        }
    
    except Exception as e:
        logger.error(f"Error generating analytics overview: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate analytics overview"
        )


@router.get("/subjects", response_model=AnalyticsAPIResponse)
async def get_subject_strength_analysis(
    current_user: User = Depends(get_current_user),
    analytics: LearningAnalyticsService = Depends(get_analytics_service)
):
    """
    Get subject-by-subject strength analysis.
    
    PHASE 10 ENDPOINT - Subject Intelligence
    
    Classifies each subject:
    - WEAK: < 50% accuracy
    - AVERAGE: 50-75% accuracy
    - STRONG: > 75% accuracy
    - UNSTARTED: No attempts yet
    
    Sorted by strength (weak subjects first).
    
    SECURITY:
    - JWT authentication required
    - User can only see their own data
    
    RESPONSE:
        {
            "success": true,
            "message": "Subject analysis retrieved successfully",
            "data": {
                "subjects": [...],
                "weak_subjects": [...],
                "strong_subjects": [...],
                "total_subjects": 8
            }
        }
    """
    logger.info(f"[ANALYTICS] Subject analysis requested: user={current_user.email}")
    
    try:
        # Get strength map from service
        strength_map = await analytics.get_subject_strength_map(current_user.id)
        
        # Separate by strength level
        weak_subjects = [
            s for s in strength_map
            if s["strength"] == StrengthLevel.WEAK.value
        ]
        
        strong_subjects = [
            s for s in strength_map
            if s["strength"] == StrengthLevel.STRONG.value
        ]
        
        data = {
            "subjects": strength_map,
            "weak_subjects": weak_subjects,
            "strong_subjects": strong_subjects,
            "total_subjects": len(strength_map)
        }
        
        logger.info(
            f"[ANALYTICS] Subject analysis complete: user={current_user.email}, "
            f"total={len(strength_map)}, weak={len(weak_subjects)}, strong={len(strong_subjects)}"
        )
        
        return {
            "success": True,
            "message": "Subject strength analysis retrieved successfully",
            "data": data
        }
    
    except Exception as e:
        logger.error(f"Error analyzing subjects: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to analyze subject strengths"
        )


@router.get("/practice", response_model=AnalyticsAPIResponse)
async def get_practice_accuracy_analysis(
    current_user: User = Depends(get_current_user),
    analytics: LearningAnalyticsService = Depends(get_analytics_service)
):
    """
    Get detailed practice accuracy analysis.
    
    PHASE 10 ENDPOINT - Practice Intelligence
    
    Provides:
    - Overall accuracy percentage
    - Accuracy by difficulty level
    - Recent accuracy (last 7 days)
    - Accuracy trend (improving/declining/stable)
    
    SECURITY:
    - JWT authentication required
    - User can only see their own data
    
    RESPONSE:
        {
            "success": true,
            "message": "Practice analysis retrieved successfully",
            "data": {
                "overall_accuracy": 76.0,
                "total_attempts": 50,
                "correct_attempts": 38,
                "by_difficulty": {
                    "easy": 90.0,
                    "medium": 75.0,
                    "hard": 60.0
                },
                "recent_accuracy": 82.0,
                "trend": "improving"
            }
        }
    """
    logger.info(f"[ANALYTICS] Practice analysis requested: user={current_user.email}")
    
    try:
        # Get practice accuracy from service
        accuracy_data = await analytics.get_practice_accuracy(current_user.id)
        
        logger.info(
            f"[ANALYTICS] Practice analysis complete: user={current_user.email}, "
            f"accuracy={accuracy_data.get('overall_accuracy')}%, "
            f"trend={accuracy_data.get('trend')}"
        )
        
        return {
            "success": True,
            "message": "Practice accuracy analysis retrieved successfully",
            "data": accuracy_data
        }
    
    except Exception as e:
        logger.error(f"Error analyzing practice accuracy: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to analyze practice accuracy"
        )


@router.get("/recommendations", response_model=AnalyticsAPIResponse)
async def get_revision_recommendations(
    current_user: User = Depends(get_current_user),
    analytics: LearningAnalyticsService = Depends(get_analytics_service)
):
    """
    Get prioritized revision recommendations.
    
    PHASE 10 ENDPOINT - Revision Intelligence
    
    Priority Rules:
    - HIGH: Weak accuracy (< 50%) AND low completion (< 60%)
    - MEDIUM: Average accuracy OR incomplete
    - LOW: Strong accuracy (> 75%) AND complete
    - NONE: Perfect performance
    
    Detects conceptual gaps (high time + low accuracy).
    
    Sorted by priority (high first).
    
    SECURITY:
    - JWT authentication required
    - User can only see their own data
    
    RESPONSE:
        {
            "success": true,
            "message": "Revision recommendations retrieved successfully",
            "data": {
                "recommendations": [...],
                "high_priority": [...],
                "medium_priority": [...],
                "low_priority": [...],
                "total_recommendations": 8
            }
        }
    """
    logger.info(f"[ANALYTICS] Recommendations requested: user={current_user.email}")
    
    try:
        # Get recommendations from service
        recommendations = await analytics.get_revision_recommendations(current_user.id)
        
        # Separate by priority
        high_priority = [
            r for r in recommendations
            if r["priority"] == RevisionPriority.HIGH.value
        ]
        
        medium_priority = [
            r for r in recommendations
            if r["priority"] == RevisionPriority.MEDIUM.value
        ]
        
        low_priority = [
            r for r in recommendations
            if r["priority"] == RevisionPriority.LOW.value
        ]
        
        data = {
            "recommendations": recommendations,
            "high_priority": high_priority,
            "medium_priority": medium_priority,
            "low_priority": low_priority,
            "total_recommendations": len(recommendations)
        }
        
        logger.info(
            f"[ANALYTICS] Recommendations generated: user={current_user.email}, "
            f"high={len(high_priority)}, medium={len(medium_priority)}, low={len(low_priority)}"
        )
        
        return {
            "success": True,
            "message": "Revision recommendations retrieved successfully",
            "data": data
        }
    
    except Exception as e:
        logger.error(f"Error generating recommendations: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate revision recommendations"
        )


@router.get("/consistency", response_model=AnalyticsAPIResponse)
async def get_study_consistency(
    current_user: User = Depends(get_current_user),
    analytics: LearningAnalyticsService = Depends(get_analytics_service)
):
    """
    Get study consistency and pattern analysis.
    
    PHASE 10 ENDPOINT - Consistency Intelligence
    
    Provides:
    - Consistency level (excellent/good/irregular/inactive)
    - Days active in last 30 days
    - Current learning streak
    - Average session time
    - Total time spent
    
    SECURITY:
    - JWT authentication required
    - User can only see their own data
    
    RESPONSE:
        {
            "success": true,
            "message": "Study consistency retrieved successfully",
            "data": {
                "consistency_level": "good",
                "days_active_last_30": 15,
                "current_streak": 3,
                "average_session_time_minutes": 12.5,
                "total_time_spent_hours": 18.5,
                "last_activity_date": "2026-01-12T14:30:00Z"
            }
        }
    """
    logger.info(f"[ANALYTICS] Consistency requested: user={current_user.email}")
    
    try:
        # Get consistency metrics from service
        consistency_data = await analytics.get_study_consistency_metrics(current_user.id)
        
        logger.info(
            f"[ANALYTICS] Consistency calculated: user={current_user.email}, "
            f"level={consistency_data['consistency_level']}, "
            f"streak={consistency_data['current_streak']}"
        )
        
        return {
            "success": True,
            "message": "Study consistency metrics retrieved successfully",
            "data": consistency_data
        }
    
    except Exception as e:
        logger.error(f"Error calculating consistency: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to calculate study consistency"
        )


@router.get("/comprehensive", response_model=AnalyticsAPIResponse)
async def get_comprehensive_analytics(
    current_user: User = Depends(get_current_user),
    analytics: LearningAnalyticsService = Depends(get_analytics_service)
):
    """
    Get comprehensive analytics package (all data in one call).
    
    PHASE 10 ENDPOINT - Complete Intelligence Package
    
    Combines all analytics into single response:
    - Overview snapshot
    - Study consistency
    - Top 5 weak subjects
    - Top 5 revision priorities
    
    Optimized for dashboard display.
    
    SECURITY:
    - JWT authentication required
    - User can only see their own data
    
    RESPONSE:
        {
            "success": true,
            "message": "Comprehensive analytics retrieved successfully",
            "data": {
                "snapshot": {...},
                "consistency": {...},
                "top_weak_subjects": [...],
                "top_recommendations": [...]
            }
        }
    """
    logger.info(f"[ANALYTICS] Comprehensive analytics requested: user={current_user.email}")
    
    try:
        # Get all analytics data
        snapshot = await analytics.get_user_learning_snapshot(current_user.id)
        consistency = await analytics.get_study_consistency_metrics(current_user.id)
        strength_map = await analytics.get_subject_strength_map(current_user.id)
        recommendations = await analytics.get_revision_recommendations(current_user.id)
        
        # Extract top items
        weak_subjects = [
            s for s in strength_map
            if s["strength"] == StrengthLevel.WEAK.value
        ][:5]
        
        top_recommendations = recommendations[:5]
        
        data = {
            "snapshot": snapshot,
            "consistency": consistency,
            "top_weak_subjects": weak_subjects,
            "top_recommendations": top_recommendations
        }
        
        logger.info(
            f"[ANALYTICS] Comprehensive analytics generated: user={current_user.email}"
        )
        
        return {
            "success": True,
            "message": "Comprehensive analytics retrieved successfully",
            "data": data
        }
    
    except Exception as e:
        logger.error(f"Error generating comprehensive analytics: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate comprehensive analytics"
        )