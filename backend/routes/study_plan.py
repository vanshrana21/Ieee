"""
backend/routes/study_plan.py
Phase 9C: Study plan generation and retrieval
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from backend.database import get_db
from backend.orm.user import User
from backend.orm.study_plan import StudyPlan
from backend.orm.study_plan_item import StudyPlanItem
from backend.routes.auth import get_current_user
from backend.schemas.study_plan_schemas import (
    GeneratePlanRequest,
    GeneratePlanResponse,
    GetActivePlanResponse,
    WeeklyPlan,
    WeeklyTopicItem
)
from backend.services.study_plan_builder import build_study_plan

router = APIRouter(prefix="/api/study-plan", tags=["study-plan"])
logger = logging.getLogger(__name__)


@router.post("/generate", response_model=GeneratePlanResponse)
async def generate_study_plan(
    request: GeneratePlanRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Generate a personalized study plan using deterministic logic.
    
    Phase 9C: Pure algorithmic planning - NO AI calls.
    
    Process:
    1. Deactivate old plans (only one active per user)
    2. Analyze topic mastery scores
    3. Detect tutor confusion patterns
    4. Prioritize topics (weakest first)
    5. Distribute across weeks
    6. Store plan and items
    
    Security:
    - JWT authentication required
    - One active plan per user
    
    Args:
        request: Plan parameters
    
    Returns:
        Generated study plan with weekly breakdown
    
    Raises:
        400: Invalid request or no study data
        401: Not authenticated
    """
    
    logger.info(f"Generating study plan: user={current_user.email}, weeks={request.duration_weeks}")
    
    # Validate enrollment
    if not current_user.course_id or not current_user.current_semester:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incomplete enrollment. Please complete course setup."
        )
    
    # 1. Deactivate old plans
    old_plans_stmt = select(StudyPlan).where(
        and_(
            StudyPlan.user_id == current_user.id,
            StudyPlan.is_active == True
        )
    )
    old_plans_result = await db.execute(old_plans_stmt)
    old_plans = old_plans_result.scalars().all()
    
    for old_plan in old_plans:
        old_plan.deactivate()
        logger.info(f"Deactivated old plan: {old_plan.id}")
    
    # 2. Build study plan (deterministic logic)
    try:
        plan_data = await build_study_plan(
            user=current_user,
            duration_weeks=request.duration_weeks,
            focus_subject_ids=request.focus_subject_ids,
            db=db
        )
    except Exception as e:
        logger.error(f"Plan building failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to build study plan. Please try again."
        )
    
    # 3. Create StudyPlan record
    study_plan = StudyPlan(
        user_id=current_user.id,
        duration_weeks=request.duration_weeks,
        summary=plan_data["summary"],
        is_active=True
    )
    
    db.add(study_plan)
    await db.flush()
    await db.refresh(study_plan)
    
    logger.info(f"Created study plan: id={study_plan.id}")
    
    # 4. Create StudyPlanItem records
    for week in plan_data["weeks"]:
        for topic in week["topics"]:
            item = StudyPlanItem(
                plan_id=study_plan.id,
                week_number=week["week_number"],
                subject_id=topic["subject_id"],
                topic_tag=topic["topic_tag"],
                recommended_actions=topic["recommended_actions"],
                estimated_hours=topic["estimated_hours"],
                priority=topic["priority"],
                rationale=topic["rationale"]
            )
            db.add(item)
    
    await db.commit()
    
    logger.info(f"Study plan created: {len(plan_data['weeks'])} weeks, {plan_data['total_topics']} topics")
    
    # 5. Build response
    weeks_response = []
    for week in plan_data["weeks"]:
        topics_response = [
            WeeklyTopicItem(
                subject_name=t["subject_name"],
                subject_code=t["subject_code"],
                topic_tag=t["topic_tag"],
                priority=t["priority"],
                estimated_hours=t["estimated_hours"],
                recommended_actions=t["recommended_actions"],
                rationale=t["rationale"],
                mastery_score=t.get("mastery_score")
            )
            for t in week["topics"]
        ]
        
        weeks_response.append(WeeklyPlan(
            week_number=week["week_number"],
            total_hours=week["total_hours"],
            topics=topics_response
        ))
    
    return GeneratePlanResponse(
        plan_id=study_plan.id,
        summary=study_plan.summary,
        duration_weeks=study_plan.duration_weeks,
        weeks=weeks_response,
        created_at=study_plan.created_at.isoformat()
    )


@router.get("/active", response_model=GetActivePlanResponse)
async def get_active_plan(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get user's currently active study plan.
    
    Returns:
        Active plan with full details, or null if no active plan
    """
    
    logger.info(f"Fetching active plan: user={current_user.email}")
    
    # Get active plan
    plan_stmt = select(StudyPlan).where(
        and_(
            StudyPlan.user_id == current_user.id,
            StudyPlan.is_active == True
        )
    )
    
    plan_result = await db.execute(plan_stmt)
    plan = plan_result.scalar_one_or_none()
    
    if not plan:
        return GetActivePlanResponse(
            has_active_plan=False,
            plan=None
        )
    
    # Get plan items
    items_stmt = select(StudyPlanItem).where(
        StudyPlanItem.plan_id == plan.id
    ).order_by(
        StudyPlanItem.week_number.asc()
    )
    
    items_result = await db.execute(items_stmt)
    items = items_result.scalars().all()
    
    # Get subject info for each item
    from backend.orm.subject import Subject
    
    subject_cache = {}
    
    # Organize by week
    weeks_dict = {}
    for item in items:
        if item.week_number not in weeks_dict:
            weeks_dict[item.week_number] = {
                "week_number": item.week_number,
                "total_hours": 0,
                "topics": []
            }
        
        # Get subject info
        if item.subject_id not in subject_cache:
            subject_stmt = select(Subject).where(Subject.id == item.subject_id)
            subject_result = await db.execute(subject_stmt)
            subject = subject_result.scalar_one_or_none()
            if subject:
                subject_cache[item.subject_id] = subject
        
        subject = subject_cache.get(item.subject_id)
        
        if subject:
            topic = WeeklyTopicItem(
                subject_name=subject.title,
                subject_code=subject.code,
                topic_tag=item.topic_tag,
                priority=item.priority,
                estimated_hours=item.estimated_hours,
                recommended_actions=item.recommended_actions or [],
                rationale=item.rationale
            )
            
            weeks_dict[item.week_number]["topics"].append(topic)
            weeks_dict[item.week_number]["total_hours"] += item.estimated_hours
    
    # Build weeks list
    weeks_response = [
        WeeklyPlan(**week_data)
        for week_data in sorted(weeks_dict.values(), key=lambda x: x["week_number"])
    ]
    
    plan_response = GeneratePlanResponse(
        plan_id=plan.id,
        summary=plan.summary,
        duration_weeks=plan.duration_weeks,
        weeks=weeks_response,
        created_at=plan.created_at.isoformat()
    )
    
    return GetActivePlanResponse(
        has_active_plan=True,
        plan=plan_response
    )
