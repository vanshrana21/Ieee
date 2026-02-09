"""
backend/routes/judge.py
Phase 9: Judge Routes - Judging, Evaluation & Competition Scoring

Routes for judges to:
- View assignments
- Evaluate projects (blind)
- Submit and finalize evaluations

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
from backend.orm.judge_evaluation import (
    JudgeAssignment, EvaluationRubric, JudgeEvaluation, 
    EvaluationAuditLog, EvaluationAction
)
from backend.orm.team_activity import TeamActivityLog, ActionType, TargetType
from backend.services.judge_evaluation import JudgeEvaluationService, EvaluationError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/judge", tags=["Judge"])


# ================= PERMISSION DECORATORS =================

async def require_judge(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 9: Enforce judge-only access.
    Only JUDGE, ADMIN, or SUPER_ADMIN can access judge endpoints.
    Faculty is explicitly blocked from judging.
    """
    if current_user.role not in [UserRole.JUDGE, UserRole.ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(
            status_code=403,
            detail="Access denied. Judge role required. Faculty cannot judge."
        )
    return current_user


# ================= SCHEMAS =================

class EvaluationScore(BaseModel):
    """Score for a single criterion"""
    criterion_key: str
    score: int = Field(..., ge=0, description="Score must be non-negative")


class EvaluationCreate(BaseModel):
    """Create/update evaluation (draft mode)"""
    assignment_id: int
    rubric_id: int
    scores: List[EvaluationScore]
    remarks: Optional[str] = None


class EvaluationFinalize(BaseModel):
    """Finalize evaluation - LOCK FOREVER"""
    confirm: bool = Field(..., description="Must confirm finalization")


# ================= JUDGE ASSIGNMENTS =================

@router.get("/assignments", status_code=200)
async def get_judge_assignments(
    competition_id: Optional[int] = Query(None),
    current_user: User = Depends(require_judge),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 9: Get all assignments for current judge.
    
    Returns assignments with evaluation status.
    """
    # Build query
    query = select(JudgeAssignment).where(
        and_(
            JudgeAssignment.judge_id == current_user.id,
            JudgeAssignment.institution_id == current_user.institution_id,
            JudgeAssignment.is_active == True
        )
    )
    
    if competition_id:
        query = query.where(JudgeAssignment.competition_id == competition_id)
    
    query = query.order_by(desc(JudgeAssignment.assigned_at))
    
    result = await db.execute(query)
    assignments = result.scalars().all()
    
    # Enrich with evaluation status
    assignments_data = []
    for assignment in assignments:
        # Check if evaluation exists
        eval_result = await db.execute(
            select(JudgeEvaluation).where(
                JudgeEvaluation.assignment_id == assignment.id
            )
        )
        evaluation = eval_result.scalar_one_or_none()
        
        assignments_data.append({
            **assignment.to_dict(),
            "evaluation_status": "finalized" if (evaluation and evaluation.is_final) else 
                              ("draft" if evaluation else "pending"),
            "evaluation_id": evaluation.id if evaluation else None,
            "has_evaluation": evaluation is not None
        })
    
    return {
        "success": True,
        "assignments": assignments_data,
        "count": len(assignments_data)
    }


# ================= BLIND PROJECT VIEW =================

@router.get("/projects/{project_id}", status_code=200)
async def get_blind_project(
    project_id: int,
    assignment_id: int = Query(..., description="Assignment ID for verification"),
    current_user: User = Depends(require_judge),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 9: Get blind project view for evaluation.
    
    Strips all student-identifying information.
    Verifies judge is actually assigned to this project.
    """
    # Verify assignment exists and belongs to judge
    result = await db.execute(
        select(JudgeAssignment).where(
            and_(
                JudgeAssignment.id == assignment_id,
                JudgeAssignment.judge_id == current_user.id,
                JudgeAssignment.project_id == project_id,
                JudgeAssignment.institution_id == current_user.institution_id,
                JudgeAssignment.is_active == True
            )
        )
    )
    assignment = result.scalar_one_or_none()
    
    if not assignment:
        raise HTTPException(
            status_code=403,
            detail="Access denied. You are not assigned to evaluate this project."
        )
    
    # Get blind view
    try:
        blind_view = await JudgeEvaluationService.get_blind_project_view(db, assignment)
        
        # Log view action
        await JudgeEvaluationService.log_evaluation_action(
            db=db,
            institution_id=current_user.institution_id,
            judge_id=current_user.id,
            evaluation_id=0,  # No evaluation yet
            action=EvaluationAction.VIEWED,
            context={"project_id": project_id, "blind": assignment.is_blind}
        )
        
        return {
            "success": True,
            "project": blind_view,
            "assignment": assignment.to_dict(),
            "is_blind": assignment.is_blind,
            "warning": "Student identities are hidden. Evaluate on merit only." if assignment.is_blind else None
        }
        
    except EvaluationError as e:
        raise HTTPException(status_code=400, detail=e.message)


# ================= EVALUATIONS =================

@router.get("/evaluations", status_code=200)
async def get_my_evaluations(
    status: Optional[str] = Query(None, description="Filter: draft, final, or all"),
    current_user: User = Depends(require_judge),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 9: Get current judge's evaluations.
    """
    query = select(JudgeEvaluation).where(
        and_(
            JudgeEvaluation.judge_id == current_user.id,
            JudgeEvaluation.institution_id == current_user.institution_id
        )
    )
    
    if status == "draft":
        query = query.where(JudgeEvaluation.is_draft == True)
    elif status == "final":
        query = query.where(JudgeEvaluation.is_final == True)
    
    query = query.order_by(desc(JudgeEvaluation.created_at))
    
    result = await db.execute(query)
    evaluations = result.scalars().all()
    
    return {
        "success": True,
        "evaluations": [e.to_dict(include_scores=True) for e in evaluations],
        "count": len(evaluations)
    }


@router.post("/evaluations", status_code=201)
async def create_evaluation(
    data: EvaluationCreate,
    request: Request,
    current_user: User = Depends(require_judge),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 9: Create or update evaluation (draft mode).
    
    Saves evaluation as draft. Can be edited until finalized.
    """
    # Verify assignment
    result = await db.execute(
        select(JudgeAssignment).where(
            and_(
                JudgeAssignment.id == data.assignment_id,
                JudgeAssignment.judge_id == current_user.id,
                JudgeAssignment.institution_id == current_user.institution_id,
                JudgeAssignment.is_active == True
            )
        )
    )
    assignment = result.scalar_one_or_none()
    
    if not assignment:
        raise HTTPException(
            status_code=403,
            detail="Invalid assignment or you are not assigned to this project."
        )
    
    # Get rubric
    result = await db.execute(
        select(EvaluationRubric).where(
            and_(
                EvaluationRubric.id == data.rubric_id,
                EvaluationRubric.institution_id == current_user.institution_id,
                EvaluationRubric.is_active == True
            )
        )
    )
    rubric = result.scalar_one_or_none()
    
    if not rubric:
        raise HTTPException(status_code=404, detail="Rubric not found")
    
    # Validate scores
    scores_dict = {s.criterion_key: s.score for s in data.scores}
    is_valid, error_msg = await JudgeEvaluationService.validate_scores(
        scores_dict, rubric.criteria
    )
    
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)
    
    # Calculate total
    total_score = await JudgeEvaluationService.calculate_total_score(
        scores_dict, rubric.criteria
    )
    
    # Check if evaluation already exists for this assignment
    result = await db.execute(
        select(JudgeEvaluation).where(
            JudgeEvaluation.assignment_id == assignment.id
        )
    )
    existing = result.scalar_one_or_none()
    
    if existing:
        # Check if can edit
        can_edit, reason = await JudgeEvaluationService.can_judge_edit_evaluation(
            existing, current_user.id
        )
        if not can_edit:
            raise HTTPException(status_code=403, detail=reason)
        
        # Update existing
        existing.scores = scores_dict
        existing.total_score = total_score
        existing.remarks = data.remarks
        existing.updated_at = datetime.utcnow()
        
        await db.commit()
        await db.refresh(existing)
        
        evaluation = existing
        action = EvaluationAction.UPDATED
    else:
        # Create new
        evaluation = JudgeEvaluation(
            institution_id=current_user.institution_id,
            judge_id=current_user.id,
            assignment_id=assignment.id,
            project_id=assignment.project_id,
            round_id=assignment.round_id,
            rubric_id=rubric.id,
            scores=scores_dict,
            total_score=total_score,
            remarks=data.remarks,
            is_draft=True,
            is_final=False
        )
        
        db.add(evaluation)
        await db.commit()
        await db.refresh(evaluation)
        
        action = EvaluationAction.CREATED
    
    # Log action
    await JudgeEvaluationService.log_evaluation_action(
        db=db,
        institution_id=current_user.institution_id,
        judge_id=current_user.id,
        evaluation_id=evaluation.id,
        action=action,
        ip_address=request.client.host if request.client else None,
        context={"total_score": total_score, "is_draft": True}
    )
    
    return {
        "success": True,
        "evaluation": evaluation.to_dict(include_scores=True),
        "message": "Evaluation saved as draft"
    }


@router.post("/evaluations/{evaluation_id}/finalize", status_code=200)
async def finalize_evaluation(
    evaluation_id: int,
    data: EvaluationFinalize,
    request: Request,
    current_user: User = Depends(require_judge),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 9: Finalize evaluation - LOCK FOREVER.
    
    Once finalized, evaluation CANNOT be edited.
    """
    if not data.confirm:
        raise HTTPException(
            status_code=400,
            detail="Must confirm finalization by setting confirm=true"
        )
    
    # Get evaluation
    result = await db.execute(
        select(JudgeEvaluation).where(
            and_(
                JudgeEvaluation.id == evaluation_id,
                JudgeEvaluation.judge_id == current_user.id,
                JudgeEvaluation.institution_id == current_user.institution_id
            )
        )
    )
    evaluation = result.scalar_one_or_none()
    
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    
    # Check if already finalized
    if evaluation.is_final:
        raise HTTPException(
            status_code=400,
            detail="Evaluation is already finalized"
        )
    
    # Verify rubric exists and validate scores one more time
    result = await db.execute(
        select(EvaluationRubric).where(EvaluationRubric.id == evaluation.rubric_id)
    )
    rubric = result.scalar_one_or_none()
    
    if not rubric:
        raise HTTPException(status_code=404, detail="Rubric not found")
    
    if evaluation.scores:
        is_valid, error_msg = await JudgeEvaluationService.validate_scores(
            evaluation.scores, rubric.criteria
        )
        if not is_valid:
            raise HTTPException(status_code=400, detail=f"Invalid scores: {error_msg}")
        
        # Recalculate total
        evaluation.total_score = await JudgeEvaluationService.calculate_total_score(
            evaluation.scores, rubric.criteria
        )
    
    # FINALIZE - LOCK FOREVER
    evaluation.is_draft = False
    evaluation.is_final = True
    evaluation.finalized_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(evaluation)
    
    # Log finalization
    await JudgeEvaluationService.log_evaluation_action(
        db=db,
        institution_id=current_user.institution_id,
        judge_id=current_user.id,
        evaluation_id=evaluation.id,
        action=EvaluationAction.FINALIZED,
        ip_address=request.client.host if request.client else None,
        context={
            "total_score": evaluation.total_score,
            "finalized_at": evaluation.finalized_at.isoformat()
        }
    )
    
    return {
        "success": True,
        "evaluation": evaluation.to_dict(include_scores=True),
        "message": "Evaluation finalized - LOCKED FOREVER",
        "warning": "This evaluation can no longer be edited"
    }


@router.get("/rubrics", status_code=200)
async def get_available_rubrics(
    competition_id: Optional[int] = Query(None),
    current_user: User = Depends(require_judge),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 9: Get available rubrics for judge to use.
    """
    query = select(EvaluationRubric).where(
        and_(
            EvaluationRubric.institution_id == current_user.institution_id,
            EvaluationRubric.is_active == True
        )
    )
    
    if competition_id:
        query = query.where(
            and_(
                EvaluationRubric.competition_id == competition_id,
                EvaluationRubric.competition_id.is_(None)  # Or generic rubrics
            )
        )
    
    result = await db.execute(query)
    rubrics = result.scalars().all()
    
    return {
        "success": True,
        "rubrics": [r.to_dict() for r in rubrics]
    }


@router.get("/evaluations/{evaluation_id}", status_code=200)
async def get_evaluation_detail(
    evaluation_id: int,
    current_user: User = Depends(require_judge),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 9: Get detailed view of own evaluation.
    """
    result = await db.execute(
        select(JudgeEvaluation).where(
            and_(
                JudgeEvaluation.id == evaluation_id,
                JudgeEvaluation.judge_id == current_user.id,
                JudgeEvaluation.institution_id == current_user.institution_id
            )
        )
    )
    evaluation = result.scalar_one_or_none()
    
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    
    # Get audit trail
    result = await db.execute(
        select(EvaluationAuditLog).where(
            EvaluationAuditLog.evaluation_id == evaluation_id
        ).order_by(desc(EvaluationAuditLog.timestamp))
    )
    audit_logs = result.scalars().all()
    
    return {
        "success": True,
        "evaluation": evaluation.to_dict(include_scores=True),
        "audit_trail": [log.to_dict() for log in audit_logs]
    }
