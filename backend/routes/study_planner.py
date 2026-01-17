"""
backend/routes/study_planner.py
Phase 6.3: Study Planner API Routes

Provides endpoints for auto-generated personalized study plans.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List

from backend.database import get_db
from backend.orm.user import User
from backend.routes.auth import get_current_user
from backend.services.study_planner_service import (
    generate_daily_plan,
    generate_weekly_plan,
    save_plan_to_db,
    get_next_study_item,
    PlanHorizon,
    ActivityType,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/study-planner", tags=["study-planner"])


class PlanItemResponse(BaseModel):
    subject_id: int
    subject_name: str
    module_id: Optional[int]
    module_name: Optional[str]
    topic_tag: Optional[str]
    activity_type: str
    content_id: Optional[int]
    content_title: str
    estimated_time_minutes: int
    priority_level: str
    why: str
    focus: str
    success_criteria: str
    mastery_percent: Optional[float]
    days_since_practice: Optional[int]


class DayPlanResponse(BaseModel):
    day_label: str
    date: Optional[str]
    items: List[PlanItemResponse]
    total_time_minutes: int
    focus_subjects: List[str]


class StudyPlanResponse(BaseModel):
    user_id: int
    plan_type: str
    generated_at: str
    days: List[DayPlanResponse]
    summary: Dict[str, Any]
    recommendations: List[str]
    plan_id: Optional[int] = None


class NextItemResponse(BaseModel):
    subject: str
    topic: Optional[str]
    activity: str
    content_title: str
    estimated_time_minutes: int
    priority: str
    why: str
    focus: str
    success_criteria: str
    content_id: Optional[int]
    module_id: Optional[int]


@router.get("/daily", response_model=StudyPlanResponse)
async def get_daily_plan(
    target_minutes: int = Query(default=120, ge=30, le=480),
    save: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Generate a daily study plan.
    
    Returns the most important items to study today based on:
    - Topic mastery levels
    - Time since last practice
    - Priority scores
    - Diagnostic patterns
    
    Parameters:
    - target_minutes: Total study time target (default 120)
    - save: If true, saves the plan to database
    """
    try:
        plan = await generate_daily_plan(
            user_id=current_user.id,
            db=db,
            target_minutes=target_minutes
        )
        
        plan_id = None
        if save:
            plan_id = await save_plan_to_db(current_user.id, plan, db)
        
        response = plan.to_dict()
        response["plan_id"] = plan_id
        
        return StudyPlanResponse(**response)
        
    except Exception as e:
        logger.error(f"Daily plan generation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate daily plan"
        )


@router.get("/weekly", response_model=StudyPlanResponse)
async def get_weekly_plan(
    days: int = Query(default=7, ge=1, le=14),
    daily_minutes: int = Query(default=120, ge=30, le=480),
    save: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Generate a weekly study plan.
    
    Distributes topics across multiple days with proper balance:
    - 40% weak topics
    - 40% medium topics
    - 20% revision
    
    Parameters:
    - days: Number of days in plan (default 7)
    - daily_minutes: Daily study time target (default 120)
    - save: If true, saves the plan to database
    """
    try:
        plan = await generate_weekly_plan(
            user_id=current_user.id,
            db=db,
            days=days,
            daily_minutes=daily_minutes
        )
        
        plan_id = None
        if save:
            plan_id = await save_plan_to_db(current_user.id, plan, db)
        
        response = plan.to_dict()
        response["plan_id"] = plan_id
        
        return StudyPlanResponse(**response)
        
    except Exception as e:
        logger.error(f"Weekly plan generation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate weekly plan"
        )


@router.get("/next", response_model=NextItemResponse)
async def get_next_item(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get the single most important item to study right now.
    
    Quick endpoint for "What should I study next?"
    
    Returns one item with:
    - WHY this item was selected
    - WHAT to focus on
    - WHAT success looks like
    """
    try:
        item = await get_next_study_item(
            user_id=current_user.id,
            db=db
        )
        
        if not item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No study items available. Start exploring subjects first."
            )
        
        return NextItemResponse(**item)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Next item fetch failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get next study item"
        )


@router.get("/summary")
async def get_plan_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get a quick summary of what the student should focus on.
    
    Lighter than full plan generation - good for dashboard widgets.
    """
    try:
        plan = await generate_daily_plan(
            user_id=current_user.id,
            db=db,
            target_minutes=60
        )
        
        if not plan.days or not plan.days[0].items:
            return {
                "has_plan": False,
                "message": "No study plan available. Start learning to get personalized recommendations.",
                "focus_areas": [],
                "recommendations": plan.recommendations,
            }
        
        top_items = plan.days[0].items[:3]
        
        return {
            "has_plan": True,
            "focus_areas": [
                {
                    "subject": item.subject_name,
                    "topic": item.topic_tag,
                    "priority": item.priority_level,
                    "activity": item.activity_type.value,
                    "why": item.why,
                }
                for item in top_items
            ],
            "total_time_suggested": plan.summary.get("total_time_minutes", 0),
            "weak_topics_count": plan.summary.get("weak_topics_covered", 0),
            "recommendations": plan.recommendations,
        }
        
    except Exception as e:
        logger.error(f"Plan summary failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get plan summary"
        )


@router.get("/activity-types")
async def get_activity_types():
    """
    Get all available activity types with descriptions.
    """
    return {
        "activity_types": [
            {
                "type": ActivityType.LEARN.value,
                "description": "Study theoretical content and concepts",
                "icon": "book",
            },
            {
                "type": ActivityType.CASE.value,
                "description": "Study case law, ratio decidendi, and applications",
                "icon": "gavel",
            },
            {
                "type": ActivityType.PRACTICE.value,
                "description": "Attempt practice questions (MCQ, essay, etc.)",
                "icon": "edit",
            },
            {
                "type": ActivityType.REVISION.value,
                "description": "Quick review of previously mastered topics",
                "icon": "refresh",
            },
        ],
        "plan_horizons": [
            {
                "type": PlanHorizon.DAILY.value,
                "description": "Single day focused study plan",
            },
            {
                "type": PlanHorizon.WEEKLY.value,
                "description": "7-day balanced study plan",
            },
        ],
    }


@router.post("/regenerate")
async def regenerate_plan(
    plan_type: str = Query(default="daily"),
    target_minutes: int = Query(default=120, ge=30, le=480),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Force regenerate a study plan.
    
    Use after:
    - New practice attempt submitted
    - Mastery changed significantly
    - Student wants fresh recommendations
    """
    try:
        if plan_type == "weekly":
            plan = await generate_weekly_plan(
                user_id=current_user.id,
                db=db,
                days=7,
                daily_minutes=target_minutes
            )
        else:
            plan = await generate_daily_plan(
                user_id=current_user.id,
                db=db,
                target_minutes=target_minutes
            )
        
        plan_id = await save_plan_to_db(current_user.id, plan, db)
        
        response = plan.to_dict()
        response["plan_id"] = plan_id
        response["regenerated"] = True
        
        return response
        
    except Exception as e:
        logger.error(f"Plan regeneration failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to regenerate plan"
        )
