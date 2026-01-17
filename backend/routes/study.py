"""
backend/routes/study.py
Phase 2.3: Personalized Study Intelligence API

ENDPOINTS:
- GET /api/study/recommendations - Get personalized recommendations
- GET /api/study/focus - Get today's focus topics
- GET /api/study/plan - Get or generate weekly study plan
- POST /api/study/plan/generate - Generate new study plan

ALL LOGIC IS RULE-BASED - NO AI/LLM CALLS
"""

import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from backend.database import get_db
from backend.orm.user import User
from backend.orm.study_plan import StudyPlan
from backend.orm.study_plan_item import StudyPlanItem
from backend.routes.auth import get_current_user
from backend.services.study_priority_engine import (
    get_study_recommendations,
    get_todays_focus,
    generate_weekly_study_plan,
    compute_topic_priority
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/study", tags=["study"])


@router.get("/recommendations")
async def get_recommendations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get personalized study recommendations.
    
    PHASE 2.3 ENDPOINT - Study Recommendations
    
    Returns:
    - next_topic: Highest priority topic to study now
    - needs_revision: Topics needing revision
    - mastered: Topics that can be skipped
    - focus_subjects: Subjects needing attention
    
    ALL RECOMMENDATIONS ARE RULE-BASED WITH EXPLANATIONS.
    
    Example Response:
    {
        "success": true,
        "data": {
            "next_topic": {
                "topic_tag": "ipc-section-300",
                "priority": "High",
                "mastery_percent": 35.5,
                "explanation": "IPC Section 300 marked High priority: 36% mastery (needs improvement), last practiced 12 days ago.",
                "recommended_actions": ["Review foundational concepts", "Practice 5+ questions"]
            },
            "needs_revision": [...],
            "mastered": [...],
            "focus_subjects": [...]
        }
    }
    """
    logger.info(f"[STUDY] Recommendations request: user={current_user.email}")
    
    try:
        recommendations = await get_study_recommendations(current_user.id, db)
        
        return {
            "success": True,
            "message": recommendations.get("message"),
            "data": recommendations
        }
    
    except Exception as e:
        logger.error(f"Error fetching recommendations: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch study recommendations"
        )


@router.get("/focus")
async def get_focus(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get today's focus topics.
    
    PHASE 2.3 ENDPOINT - Today's Focus
    
    Returns top 3 priority topics with:
    - Why this topic (explanation)
    - What to do (actions)
    - Why now (urgency reason)
    
    Example Response:
    {
        "success": true,
        "data": {
            "has_focus": true,
            "topics": [
                {
                    "rank": 1,
                    "topic_tag": "article-21",
                    "priority": "High",
                    "mastery_percent": 28.5,
                    "explanation": "Article 21 marked High priority: 29% mastery (needs improvement), no practice in 15 days.",
                    "actions": ["Review foundational concepts", "Practice 5+ questions"],
                    "why_now": "This is your highest priority topic based on mastery and practice history."
                }
            ],
            "total_weak_topics": 5,
            "total_mastered_topics": 2
        }
    }
    """
    logger.info(f"[STUDY] Focus request: user={current_user.email}")
    
    try:
        focus = await get_todays_focus(current_user.id, db)
        
        return {
            "success": True,
            "message": focus.get("message"),
            "data": focus
        }
    
    except Exception as e:
        logger.error(f"Error fetching focus: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch today's focus"
        )


@router.get("/plan")
async def get_study_plan(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get current active study plan.
    
    PHASE 2.3 ENDPOINT - Weekly Study Plan
    
    Returns the user's active study plan with all items.
    If no plan exists, returns instruction to generate one.
    
    Example Response:
    {
        "success": true,
        "data": {
            "has_plan": true,
            "plan": {
                "id": 1,
                "duration_weeks": 1,
                "summary": "Focus on 3 high-priority topics and 5 moderate topics over 1 week(s).",
                "items": [
                    {
                        "week": 1,
                        "day": 1,
                        "topic_tag": "article-21",
                        "priority": "High",
                        "estimated_hours": 2,
                        "rationale": "Article 21 marked High priority...",
                        "actions": [...]
                    }
                ]
            }
        }
    }
    """
    logger.info(f"[STUDY] Plan request: user={current_user.email}")
    
    try:
        plan_stmt = select(StudyPlan).where(
            and_(
                StudyPlan.user_id == current_user.id,
                StudyPlan.is_active == True
            )
        ).order_by(StudyPlan.created_at.desc())
        
        plan_result = await db.execute(plan_stmt)
        plan = plan_result.scalar_one_or_none()
        
        if not plan:
            return {
                "success": True,
                "message": "No active study plan. Generate one using POST /api/study/plan/generate",
                "data": {
                    "has_plan": False,
                    "plan": None
                }
            }
        
        items_stmt = select(StudyPlanItem).where(
            StudyPlanItem.plan_id == plan.id
        ).order_by(StudyPlanItem.week_number, StudyPlanItem.id)
        
        items_result = await db.execute(items_stmt)
        items = items_result.scalars().all()
        
        return {
            "success": True,
            "message": None,
            "data": {
                "has_plan": True,
                "plan": {
                    "id": plan.id,
                    "duration_weeks": plan.duration_weeks,
                    "summary": plan.summary,
                    "is_active": plan.is_active,
                    "created_at": plan.created_at.isoformat() if plan.created_at else None,
                    "items": [item.to_dict() for item in items]
                }
            }
        }
    
    except Exception as e:
        logger.error(f"Error fetching study plan: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch study plan"
        )


@router.post("/plan/generate")
async def generate_plan(
    weeks: int = Query(default=1, ge=1, le=4, description="Number of weeks (1-4)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Generate a new weekly study plan.
    
    PHASE 2.3 ENDPOINT - Plan Generator
    
    Rules:
    - Max 2 subjects per day
    - Mix weak + moderate topics
    - Avoid overload (max 4 hours/day)
    - Prioritize by score
    - Deactivates any existing active plans
    
    Args:
        weeks: Number of weeks to plan (1-4)
    
    Returns:
        Generated plan with daily breakdown
    """
    logger.info(f"[STUDY] Generate plan: user={current_user.email}, weeks={weeks}")
    
    try:
        result = await generate_weekly_study_plan(current_user.id, db, weeks)
        
        if not result["success"]:
            return {
                "success": False,
                "message": result["message"],
                "data": None
            }
        
        return {
            "success": True,
            "message": "Study plan generated successfully",
            "data": result["plan"]
        }
    
    except Exception as e:
        logger.error(f"Error generating study plan: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate study plan"
        )


@router.get("/priority/{subject_id}")
async def get_topic_priorities(
    subject_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get priority scores for all topics in a subject.
    
    PHASE 2.3 ENDPOINT - Topic Priorities
    
    Returns detailed priority breakdown for each topic including:
    - Priority score and label
    - Component scores (mastery deficit, staleness, importance, urgency)
    - Explanation of priority
    - Recommended actions
    
    Useful for understanding WHY topics have their priorities.
    """
    logger.info(f"[STUDY] Topic priorities: user={current_user.email}, subject={subject_id}")
    
    try:
        user_semester = current_user.current_semester if current_user.current_semester else 1
        
        priorities = await compute_topic_priority(
            current_user.id,
            subject_id,
            db,
            user_semester
        )
        
        return {
            "success": True,
            "message": None,
            "data": {
                "subject_id": subject_id,
                "total_topics": len(priorities),
                "high_priority_count": sum(1 for p in priorities if p["priority"] == "High"),
                "medium_priority_count": sum(1 for p in priorities if p["priority"] == "Medium"),
                "low_priority_count": sum(1 for p in priorities if p["priority"] == "Low"),
                "topics": priorities
            }
        }
    
    except Exception as e:
        logger.error(f"Error fetching topic priorities: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch topic priorities"
        )
