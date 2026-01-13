"""
backend/routes/recommendations.py
API Routes for Learning Recommendations

PHASE 8: Intelligent Learning Engine - Recommendations API
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.orm.user import User
from backend.routes.auth import get_current_user
from backend.services.recommendations import RecommendationEngine
from backend.schemas.ai_tutor import (
    RecommendationsResponse,
    NextActionResponse
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recommendations", tags=["Recommendations"])


# ========== RECOMMENDATION ENDPOINTS ==========

@router.get("/all", response_model=RecommendationsResponse)
async def get_all_recommendations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all learning recommendations for user.
    
    PHASE 8 ENDPOINT - Rule-Based Recommendations
    
    Returns recommendations grouped by priority:
    - Urgent: Critical gaps, low accuracy
    - Important: Incomplete modules, needs practice
    - Suggested: Revision, next steps
    
    All recommendations are deterministic (no ML).
    
    Response:
        {
            "success": true,
            "message": "Recommendations generated",
            "data": {
                "urgent": [
                    {
                        "priority": "urgent",
                        "type": "practice_weak_areas",
                        "subject_id": 5,
                        "subject_name": "Contract Law",
                        "reason": "Despite 75% completion, accuracy is only 45%",
                        "action": "Focus on practice questions in weak topics"
                    }
                ],
                "important": [
                    {
                        "priority": "important",
                        "type": "study",
                        "subject_id": 7,
                        "subject_name": "Criminal Law",
                        "reason": "Only 30% complete",
                        "action": "Complete remaining learning modules"
                    }
                ],
                "suggested": [
                    {
                        "priority": "suggested",
                        "type": "revise",
                        "subject_id": 3,
                        "subject_name": "Legal Methods",
                        "reason": "Last activity 8 days ago",
                        "action": "Quick revision to maintain retention"
                    }
                ]
            }
        }
    """
    logger.info(f"[RECOMMENDATIONS] Request from {current_user.email}")
    
    try:
        recommendations = await RecommendationEngine.get_recommendations(
            current_user, db
        )
        
        total_count = sum(len(recs) for recs in recommendations.values())
        logger.info(
            f"[RECOMMENDATIONS] Generated {total_count} recommendations: "
            f"{len(recommendations['urgent'])} urgent, "
            f"{len(recommendations['important'])} important, "
            f"{len(recommendations['suggested'])} suggested"
        )
        
        return {
            "success": True,
            "message": "Recommendations generated successfully",
            "data": recommendations
        }
    
    except Exception as e:
        logger.error(f"[RECOMMENDATIONS] Error generating: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate recommendations"
        )


@router.get("/next-action", response_model=NextActionResponse)
async def get_next_action(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get single most important next action.
    
    PHASE 8 ENDPOINT - Next Action Recommendation
    
    Returns the highest priority recommendation:
    1. First urgent action (if any)
    2. First important action (if no urgent)
    3. First suggested action (if no important)
    4. None (if no recommendations)
    
    Use case: "What should I study next?" button
    
    Response:
        {
            "success": true,
            "message": "Next action determined",
            "data": {
                "priority": "urgent",
                "type": "practice",
                "subject_id": 5,
                "subject_name": "Contract Law",
                "reason": "Low accuracy (45%) indicates gaps in understanding",
                "action": "Complete practice questions to identify weak areas"
            }
        }
    
    Or if no recommendations:
        {
            "success": true,
            "message": "No recommendations available",
            "data": null
        }
    """
    logger.info(f"[RECOMMENDATIONS] Next action request from {current_user.email}")
    
    try:
        next_action = await RecommendationEngine.get_next_action(current_user, db)
        
        if next_action:
            logger.info(
                f"[RECOMMENDATIONS] Next action: {next_action['type']} "
                f"for subject {next_action['subject_id']} "
                f"(priority: {next_action['priority']})"
            )
            message = "Next action determined"
        else:
            logger.info("[RECOMMENDATIONS] No recommendations available")
            message = "No recommendations available. Great progress!"
        
        return {
            "success": True,
            "message": message,
            "data": next_action
        }
    
    except Exception as e:
        logger.error(f"[RECOMMENDATIONS] Error determining next action: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to determine next action"
        )


@router.get("/subject/{subject_id}", response_model=RecommendationsResponse)
async def get_subject_recommendations(
    subject_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get recommendations for a specific subject.
    
    PHASE 8 ENDPOINT - Subject-Specific Recommendations
    
    Returns only recommendations related to the specified subject.
    
    Args:
        subject_id: Subject ID to get recommendations for
    
    Response:
        {
            "success": true,
            "message": "Subject recommendations generated",
            "data": {
                "urgent": [...],
                "important": [...],
                "suggested": [...]
            }
        }
    """
    logger.info(
        f"[RECOMMENDATIONS] Subject {subject_id} recommendations "
        f"from {current_user.email}"
    )
    
    try:
        # Get all recommendations
        all_recommendations = await RecommendationEngine.get_recommendations(
            current_user, db
        )
        
        # Filter for this subject
        subject_recs = {
            "urgent": [
                r for r in all_recommendations["urgent"]
                if r["subject_id"] == subject_id
            ],
            "important": [
                r for r in all_recommendations["important"]
                if r["subject_id"] == subject_id
            ],
            "suggested": [
                r for r in all_recommendations["suggested"]
                if r["subject_id"] == subject_id
            ]
        }
        
        total_count = sum(len(recs) for recs in subject_recs.values())
        logger.info(
            f"[RECOMMENDATIONS] Subject {subject_id}: {total_count} recommendations"
        )
        
        return {
            "success": True,
            "message": f"Recommendations for subject {subject_id} generated",
            "data": subject_recs
        }
    
    except Exception as e:
        logger.error(
            f"[RECOMMENDATIONS] Error for subject {subject_id}: {e}",
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate recommendations for subject {subject_id}"
        )