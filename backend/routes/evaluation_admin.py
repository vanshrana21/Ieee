"""
backend/routes/evaluation_admin.py
Phase 9: Admin Routes for Evaluation Management

Admin endpoints for:
- Creating/managing rubrics
- Assigning judges to projects/teams
- Viewing all evaluations
- Publishing results

Zero AI involvement. Full audit trail.
"""
import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc

from backend.database import get_db
from backend.rbac import get_current_user
from backend.orm.user import User, UserRole
from backend.orm.moot_project import MootProject
from backend.orm.team import Team
from backend.orm.competition import Competition
from backend.orm.judge_evaluation import (
    JudgeAssignment, EvaluationRubric, JudgeEvaluation, 
    EvaluationAuditLog, EvaluationAction
)
from backend.orm.team_activity import TeamActivityLog, ActionType, TargetType
from backend.services.judge_evaluation import JudgeEvaluationService
from backend.services.activity_logger import log_team_activity

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/evaluation-admin", tags=["Evaluation Admin"])


# ================= PERMISSION DECORATORS =================

async def require_admin_or_super(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 9: Only Admin and Super Admin can manage evaluations.
    Faculty explicitly blocked.
    """
    if current_user.role not in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(
            status_code=403,
            detail="Access denied. Admin or Super Admin role required. Faculty cannot manage evaluations."
        )
    return current_user


# ================= SCHEMAS =================

class RubricCreate(BaseModel):
    """Create new rubric"""
    title: str = Field(..., min_length=3, max_length=255)
    description: Optional[str] = None
    criteria: List[dict] = Field(..., description="List of criteria with key, label, max, description")
    competition_id: Optional[int] = None
    is_default: bool = False


class JudgeAssignmentCreate(BaseModel):
    """Assign judge to project/team/round"""
    judge_id: int
    competition_id: int
    team_id: Optional[int] = None
    project_id: Optional[int] = None
    round_id: Optional[int] = None
    is_blind: bool = True


class ResultsPublish(BaseModel):
    """Publish competition results"""
    confirm: bool = Field(..., description="Must confirm publication")
    publish_to_students: bool = True


# ================= RUBRIC MANAGEMENT =================

@router.post("/rubrics", status_code=201)
async def create_rubric(
    data: RubricCreate,
    request: Request,
    current_user: User = Depends(require_admin_or_super),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 9: Create new evaluation rubric.
    """
    # Validate criteria
    if not data.criteria:
        raise HTTPException(status_code=400, detail="At least one criterion required")
    
    # Calculate total score
    total = sum(c.get("max", 0) for c in data.criteria)
    
    if total <= 0:
        raise HTTPException(status_code=400, detail="Total score must be greater than 0")
    
    # Validate competition exists and belongs to institution
    if data.competition_id:
        result = await db.execute(
            select(Competition).where(
                and_(
                    Competition.id == data.competition_id,
                    Competition.institution_id == current_user.institution_id
                )
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Competition not found")
    
    # Create rubric
    rubric = EvaluationRubric(
        institution_id=current_user.institution_id,
        competition_id=data.competition_id,
        title=data.title,
        description=data.description,
        criteria=data.criteria,
        total_score=total,
        is_active=True,
        is_default=data.is_default,
        created_by=current_user.id
    )
    
    db.add(rubric)
    await db.commit()
    await db.refresh(rubric)
    
    return {
        "success": True,
        "rubric": rubric.to_dict(),
        "message": "Rubric created successfully"
    }


@router.get("/rubrics", status_code=200)
async def list_rubrics(
    competition_id: Optional[int] = Query(None),
    current_user: User = Depends(require_admin_or_super),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 9: List all rubrics for institution.
    """
    query = select(EvaluationRubric).where(
        EvaluationRubric.institution_id == current_user.institution_id
    )
    
    if competition_id:
        query = query.where(
            and_(
                EvaluationRubric.competition_id == competition_id,
                EvaluationRubric.competition_id.is_(None)
            )
        )
    
    query = query.order_by(desc(EvaluationRubric.created_at))
    
    result = await db.execute(query)
    rubrics = result.scalars().all()
    
    return {
        "success": True,
        "rubrics": [r.to_dict() for r in rubrics],
        "count": len(rubrics)
    }


@router.get("/rubrics/{rubric_id}", status_code=200)
async def get_rubric(
    rubric_id: int,
    current_user: User = Depends(require_admin_or_super),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 9: Get rubric details.
    """
    result = await db.execute(
        select(EvaluationRubric).where(
            and_(
                EvaluationRubric.id == rubric_id,
                EvaluationRubric.institution_id == current_user.institution_id
            )
        )
    )
    rubric = result.scalar_one_or_none()
    
    if not rubric:
        raise HTTPException(status_code=404, detail="Rubric not found")
    
    return {
        "success": True,
        "rubric": rubric.to_dict()
    }


# ================= JUDGE ASSIGNMENT =================

@router.post("/assign-judge", status_code=201)
async def assign_judge(
    data: JudgeAssignmentCreate,
    request: Request,
    current_user: User = Depends(require_admin_or_super),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 9: Assign judge to project/team/round.
    """
    # Validate at least one target is provided
    if not any([data.team_id, data.project_id, data.round_id]):
        raise HTTPException(
            status_code=400,
            detail="Must provide at least one of: team_id, project_id, round_id"
        )
    
    # Validate judge exists and has JUDGE role
    result = await db.execute(
        select(User).where(
            and_(
                User.id == data.judge_id,
                User.institution_id == current_user.institution_id,
                User.role == UserRole.JUDGE
            )
        )
    )
    judge = result.scalar_one_or_none()
    
    if not judge:
        raise HTTPException(
            status_code=404,
            detail="Judge not found or user does not have JUDGE role"
        )
    
    # Validate competition exists
    result = await db.execute(
        select(Competition).where(
            and_(
                Competition.id == data.competition_id,
                Competition.institution_id == current_user.institution_id
            )
        )
    )
    competition = result.scalar_one_or_none()
    
    if not competition:
        raise HTTPException(status_code=404, detail="Competition not found")
    
    # Validate project/team/round exists
    if data.project_id:
        result = await db.execute(
            select(MootProject).where(
                and_(
                    MootProject.id == data.project_id,
                    MootProject.institution_id == current_user.institution_id
                )
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Project not found")
    
    if data.team_id:
        result = await db.execute(
            select(Team).where(
                and_(
                    Team.id == data.team_id,
                    Team.institution_id == current_user.institution_id
                )
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Team not found")
    
    # Check for duplicate assignment (same judge, same target in same competition)
    duplicate_check = await db.execute(
        select(JudgeAssignment).where(
            and_(
                JudgeAssignment.judge_id == data.judge_id,
                JudgeAssignment.competition_id == data.competition_id,
                JudgeAssignment.is_active == True,
                JudgeAssignment.project_id == data.project_id if data.project_id else True,
                JudgeAssignment.team_id == data.team_id if data.team_id else True,
                JudgeAssignment.round_id == data.round_id if data.round_id else True
            )
        )
    )
    
    if duplicate_check.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="Judge is already assigned to this target"
        )
    
    # Create assignment
    assignment = JudgeAssignment(
        institution_id=current_user.institution_id,
        competition_id=data.competition_id,
        judge_id=data.judge_id,
        team_id=data.team_id,
        project_id=data.project_id,
        round_id=data.round_id,
        is_blind=data.is_blind,
        assigned_by=current_user.id
    )
    
    db.add(assignment)
    await db.commit()
    await db.refresh(assignment)
    
    # Log to team activity
    target_name = f"Judge to {data.project_id or data.team_id or data.round_id}"
    await log_team_activity(
        db=db,
        institution_id=current_user.institution_id,
        team_id=data.team_id if data.team_id else 0,  # May be 0 for project-only
        actor=current_user,
        action_type=ActionType.JUDGE_ASSIGNED,
        target_type=TargetType.TEAM if data.team_id else TargetType.PROJECT,
        target_id=data.team_id or data.project_id,
        target_name=target_name,
        ip_address=request.client.host if request.client else None
    )
    
    return {
        "success": True,
        "assignment": assignment.to_dict(),
        "message": f"Judge assigned successfully (Blind: {data.is_blind})"
    }


@router.get("/assignments", status_code=200)
async def list_assignments(
    competition_id: Optional[int] = Query(None),
    judge_id: Optional[int] = Query(None),
    current_user: User = Depends(require_admin_or_super),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 9: List all judge assignments.
    """
    query = select(JudgeAssignment).where(
        JudgeAssignment.institution_id == current_user.institution_id
    )
    
    if competition_id:
        query = query.where(JudgeAssignment.competition_id == competition_id)
    
    if judge_id:
        query = query.where(JudgeAssignment.judge_id == judge_id)
    
    query = query.order_by(desc(JudgeAssignment.assigned_at))
    
    result = await db.execute(query)
    assignments = result.scalars().all()
    
    # Enrich with judge info
    assignments_data = []
    for assignment in assignments:
        # Get judge
        judge_result = await db.execute(
            select(User).where(User.id == assignment.judge_id)
        )
        judge = judge_result.scalar_one_or_none()
        
        # Get evaluation status
        eval_result = await db.execute(
            select(JudgeEvaluation).where(
                JudgeEvaluation.assignment_id == assignment.id
            )
        )
        evaluation = eval_result.scalar_one_or_none()
        
        assignments_data.append({
            **assignment.to_dict(),
            "judge": {
                "id": judge.id if judge else None,
                "full_name": judge.full_name if judge else None,
                "email": judge.email if judge else None
            } if judge else None,
            "evaluation_status": "finalized" if (evaluation and evaluation.is_final) else 
                              ("draft" if evaluation else "pending")
        })
    
    return {
        "success": True,
        "assignments": assignments_data,
        "count": len(assignments_data)
    }


# ================= EVALUATION VIEWING =================

@router.get("/evaluations", status_code=200)
async def list_all_evaluations(
    competition_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None, description="draft, final, or all"),
    current_user: User = Depends(require_admin_or_super),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 9: View all evaluations for institution.
    Admin can see all evaluations but NOT edit them.
    """
    query = select(JudgeEvaluation).where(
        JudgeEvaluation.institution_id == current_user.institution_id
    )
    
    if competition_id:
        # Filter by competition through assignment
        query = query.where(
            JudgeEvaluation.assignment_id.in_(
                select(JudgeAssignment.id).where(
                    JudgeAssignment.competition_id == competition_id
                )
            )
        )
    
    if status == "draft":
        query = query.where(JudgeEvaluation.is_draft == True)
    elif status == "final":
        query = query.where(JudgeEvaluation.is_final == True)
    
    query = query.order_by(desc(JudgeEvaluation.created_at))
    
    result = await db.execute(query)
    evaluations = result.scalars().all()
    
    # Enrich with judge and project info
    evaluations_data = []
    for evaluation in evaluations:
        # Get judge
        judge_result = await db.execute(
            select(User).where(User.id == evaluation.judge_id)
        )
        judge = judge_result.scalar_one_or_none()
        
        # Get project
        project_result = await db.execute(
            select(MootProject).where(MootProject.id == evaluation.project_id)
        ) if evaluation.project_id else None
        project = project_result.scalar_one_or_none() if project_result else None
        
        evaluations_data.append({
            **evaluation.to_dict(include_scores=True),
            "judge": {
                "id": judge.id if judge else None,
                "full_name": judge.full_name if judge else None
            } if judge else None,
            "project": {
                "id": project.id if project else None,
                "title": project.project_title if project else None
            } if project else None
        })
    
    return {
        "success": True,
        "evaluations": evaluations_data,
        "count": len(evaluations_data),
        "admin_notice": "Admins can view but CANNOT edit judge evaluations"
    }


# ================= RESULTS =================

@router.get("/competitions/{competition_id}/results", status_code=200)
async def get_competition_results(
    competition_id: int,
    current_user: User = Depends(require_admin_or_super),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 9: Get aggregated competition results.
    
    Calculates final scores by averaging judge scores.
    NO AI involvement - pure mathematical aggregation.
    """
    # Verify competition exists
    result = await db.execute(
        select(Competition).where(
            and_(
                Competition.id == competition_id,
                Competition.institution_id == current_user.institution_id
            )
        )
    )
    competition = result.scalar_one_or_none()
    
    if not competition:
        raise HTTPException(status_code=404, detail="Competition not found")
    
    # Get aggregated results
    results = await JudgeEvaluationService.aggregate_competition_results(
        db, competition_id, current_user.institution_id
    )
    
    # Enrich with project/team info
    enriched_results = []
    for result in results:
        project_result = await db.execute(
            select(MootProject).where(MootProject.id == result["project_id"])
        )
        project = project_result.scalar_one_or_none()
        
        if project:
            enriched_results.append({
                **result,
                "project": {
                    "id": project.id,
                    "title": project.project_title,
                    "side": project.side,
                    "team_id": project.team_id
                }
            })
    
    return {
        "success": True,
        "competition_id": competition_id,
        "competition_name": competition.name if hasattr(competition, 'name') else None,
        "results": enriched_results,
        "total_projects": len(enriched_results),
        "calculation_method": "Average of finalized judge scores (NO AI)",
        "tie_breaker": "Manual review if scores are identical"
    }


@router.post("/competitions/{competition_id}/publish-results", status_code=200)
async def publish_results(
    competition_id: int,
    data: ResultsPublish,
    request: Request,
    current_user: User = Depends(require_admin_or_super),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 9: Publish competition results.
    
    Makes results visible to students if publish_to_students=True.
    """
    if not data.confirm:
        raise HTTPException(
            status_code=400,
            detail="Must confirm publication by setting confirm=true"
        )
    
    # Verify competition exists
    result = await db.execute(
        select(Competition).where(
            and_(
                Competition.id == competition_id,
                Competition.institution_id == current_user.institution_id
            )
        )
    )
    competition = result.scalar_one_or_none()
    
    if not competition:
        raise HTTPException(status_code=404, detail="Competition not found")
    
    # Log publication
    await log_team_activity(
        db=db,
        institution_id=current_user.institution_id,
        team_id=0,  # Institution-level action
        actor=current_user,
        action_type=ActionType.RESULTS_PUBLISHED,
        target_type=TargetType.PROJECT,  # Using project as target type
        target_id=competition_id,
        target_name=f"Results for {competition.name if hasattr(competition, 'name') else 'Competition'}",
        context={"publish_to_students": data.publish_to_students},
        ip_address=request.client.host if request.client else None
    )
    
    return {
        "success": True,
        "message": f"Results published{' to students' if data.publish_to_students else ' (admin only)'}",
        "competition_id": competition_id,
        "published_by": current_user.id,
        "published_at": datetime.utcnow().isoformat()
    }
