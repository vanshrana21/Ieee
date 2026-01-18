"""
backend/routes/analytics.py
Learning Analytics API Endpoints

PHASE 2.2: Mastery & Analytics Engine

All endpoints:
- JWT protected
- Read-only (no mutations except mastery recalculation)
- Database-driven calculations
- Return standardized JSON
- No AI/LLM calls
"""
import logging
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from backend.database import get_db
from backend.orm.user import User
from backend.orm.subject import Subject
from backend.orm.topic_mastery import TopicMastery
from backend.orm.subject_progress import SubjectProgress
from backend.routes.auth import get_current_user
from backend.services.learning_analytics_service import (
    get_learning_analytics_service,
    LearningAnalyticsService,
    StrengthLevel,
    RevisionPriority
)
from backend.services.mastery_calculator import (
    compute_topic_mastery,
    compute_subject_mastery,
    get_weak_topics,
    get_strong_topics,
    calculate_study_streak,
    recalculate_all_mastery_for_user,
    get_topic_mastery_detail,
    get_strength_label
)
from backend.empty_states import (
    wrap_with_empty_state,
    safe_percentage,
    safe_average,
    safe_int,
    get_first_time_user_guidance,
    get_partial_progress_guidance
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


@router.get("/topic/{topic_id}", response_model=AnalyticsAPIResponse)
async def get_topic_analytics(
    topic_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get mastery analytics for a specific topic.
    
    PHASE 2.2 ENDPOINT - Topic Mastery
    
    Args:
        topic_id: Topic tag (e.g., "article-21", "contract-formation")
    
    Returns:
        {
            "success": true,
            "data": {
                "topic_tag": "article-21",
                "mastery_percent": 65.5,
                "strength_label": "Average",
                "attempt_count": 12,
                "last_practiced": "2026-01-17T10:30:00Z",
                "difficulty_level": "medium"
            }
        }
    """
    logger.info(f"[ANALYTICS] Topic analytics: user={current_user.email}, topic={topic_id}")
    
    try:
        topic_data = await get_topic_mastery_detail(current_user.id, topic_id, db)
        
        if not topic_data:
            return {
                "success": True,
                "message": "No data for this topic yet",
                "data": {
                    "topic_tag": topic_id,
                    "mastery_percent": 0.0,
                    "strength_label": "Weak",
                    "attempt_count": 0,
                    "last_practiced": None,
                    "difficulty_level": "easy"
                }
            }
        
        return {
            "success": True,
            "message": "Topic analytics retrieved successfully",
            "data": topic_data
        }
    
    except Exception as e:
        logger.error(f"Error fetching topic analytics: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch topic analytics"
        )


@router.get("/subject/{subject_id}", response_model=AnalyticsAPIResponse)
async def get_subject_analytics(
    subject_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get mastery analytics for a specific subject.
    
    PHASE 2.2 ENDPOINT - Subject Mastery
    
    Triggers mastery recalculation for accuracy.
    
    Args:
        subject_id: Subject ID
    
    Returns:
        {
            "success": true,
            "data": {
                "subject_id": 1,
                "subject_title": "Constitutional Law",
                "mastery_percent": 72.5,
                "strength_label": "Strong",
                "completed_topics": 5,
                "total_topics": 8,
                "topic_breakdown": [...]
            }
        }
    """
    logger.info(f"[ANALYTICS] Subject analytics: user={current_user.email}, subject={subject_id}")
    
    try:
        subject_stmt = select(Subject).where(Subject.id == subject_id)
        subject_result = await db.execute(subject_stmt)
        subject = subject_result.scalar_one_or_none()
        
        if not subject:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subject not found"
            )
        
        mastery_data = await compute_subject_mastery(current_user.id, subject_id, db)
        
        mastery_data["subject_title"] = subject.title
        
        return {
            "success": True,
            "message": "Subject analytics retrieved successfully",
            "data": mastery_data
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching subject analytics: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch subject analytics"
        )


@router.get("/dashboard", response_model=AnalyticsAPIResponse)
async def get_dashboard_analytics(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get complete dashboard analytics.
    
    PHASE 2.2 ENDPOINT - Dashboard Analytics
    
    Returns:
        {
            "success": true,
            "data": {
                "overall_mastery_percent": 58.2,
                "weakest_topics": [...],
                "strongest_topics": [...],
                "subjects_by_mastery": [...],
                "study_streak": 5
            }
        }
    """
    logger.info(f"[ANALYTICS] Dashboard analytics: user={current_user.email}")
    
    try:
        recalc_result = await recalculate_all_mastery_for_user(current_user.id, db)
        
        all_topics_stmt = select(TopicMastery).where(
            TopicMastery.user_id == current_user.id
        ).order_by(TopicMastery.mastery_score.asc())
        
        all_topics_result = await db.execute(all_topics_stmt)
        all_topics = all_topics_result.scalars().all()
        
        overall_mastery = 0.0
        if all_topics:
            total_weighted = sum(t.mastery_score * t.attempt_count for t in all_topics)
            total_weight = sum(t.attempt_count for t in all_topics)
            overall_mastery = round(safe_percentage(total_weighted, total_weight), 2)
        
        weakest_topics = [
            {
                "topic_tag": t.topic_tag,
                "subject_id": t.subject_id,
                "mastery_percent": round(t.mastery_score * 100, 2),
                "strength_label": get_strength_label(t.mastery_score * 100)
            }
            for t in all_topics[:3]
        ]
        
        strongest_topics = [
            {
                "topic_tag": t.topic_tag,
                "subject_id": t.subject_id,
                "mastery_percent": round(t.mastery_score * 100, 2),
                "strength_label": get_strength_label(t.mastery_score * 100)
            }
            for t in sorted(all_topics, key=lambda x: x.mastery_score, reverse=True)[:3]
        ]
        
        subjects_stmt = (
            select(SubjectProgress)
            .options(joinedload(SubjectProgress.subject))
            .where(SubjectProgress.user_id == current_user.id)
            .order_by(SubjectProgress.completion_percentage.desc())
        )
        subjects_result = await db.execute(subjects_stmt)
        subjects_progress = subjects_result.scalars().all()
        
        subjects_by_mastery = [
            {
                "subject_id": sp.subject_id,
                "subject_title": sp.subject.title if sp.subject else "Unknown",
                "mastery_percent": round(sp.completion_percentage or 0, 2),
                "strength_label": get_strength_label(sp.completion_percentage or 0),
                "completed_topics": safe_int(sp.completed_items),
                "total_topics": safe_int(sp.total_items)
            }
            for sp in subjects_progress
        ]
        
        study_streak = await calculate_study_streak(current_user.id, db)
        
        has_data = len(all_topics) > 0
        has_sufficient_data = len(all_topics) >= 5
        
        response_data = {
            "has_data": has_data,
            "data_quality": "full" if has_sufficient_data else ("partial" if has_data else "empty"),
            "overall_mastery_percent": overall_mastery,
            "overall_strength_label": get_strength_label(overall_mastery),
            "weakest_topics": weakest_topics,
            "strongest_topics": strongest_topics,
            "subjects_by_mastery": subjects_by_mastery,
            "study_streak": study_streak,
            "subjects_recalculated": recalc_result["subjects_recalculated"]
        }
        
        if not has_data:
            response_data["empty_state"] = {
                "reason": "No analytics data yet",
                "guidance": "Complete practice questions to see your analytics.",
                "action_label": "Start Practice",
                "action_href": "practice-content.html"
            }
        elif not has_sufficient_data:
            response_data["insufficient_data_warning"] = {
                "message": f"Limited data available ({len(all_topics)}/5 minimum for accurate insights)",
                "guidance": "Complete more practice questions for better analytics accuracy."
            }
        
        return {
            "success": True,
            "message": "Dashboard analytics retrieved successfully",
            "data": response_data
        }
    
    except Exception as e:
        logger.error(f"Error fetching dashboard analytics: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch dashboard analytics"
        )