"""
backend/routes/moot_evaluations.py
Phase 5C: Moot project evaluation API routes
Drafts editable, finalized evaluations locked forever
"""
import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc

from backend.database import get_db
from backend.orm.moot_evaluation import MootEvaluation
from backend.orm.moot_project import MootProject
from backend.orm.user import User, UserRole
from backend.rbac import get_current_user

# Phase 6C: Activity logging
from backend.services.activity_logger import (
    log_evaluation_draft_created,
    log_evaluation_finalized
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/moot-evaluations", tags=["Moot Evaluations"])


# ================= SCHEMAS =================

class EvaluationCreate(BaseModel):
    """Schema for creating an evaluation"""
    project_id: int
    issue_framing_score: Optional[float] = Field(None, ge=0, le=10)
    legal_reasoning_score: Optional[float] = Field(None, ge=0, le=10)
    use_of_authority_score: Optional[float] = Field(None, ge=0, le=10)
    structure_clarity_score: Optional[float] = Field(None, ge=0, le=10)
    oral_advocacy_score: Optional[float] = Field(None, ge=0, le=10)
    responsiveness_score: Optional[float] = Field(None, ge=0, le=10)
    category_comments: Optional[str] = None  # JSON string
    overall_comments: Optional[str] = None
    strengths: Optional[str] = None  # JSON string
    improvements: Optional[str] = None  # JSON string


class EvaluationUpdate(BaseModel):
    """Schema for updating an evaluation (draft only)"""
    issue_framing_score: Optional[float] = Field(None, ge=0, le=10)
    legal_reasoning_score: Optional[float] = Field(None, ge=0, le=10)
    use_of_authority_score: Optional[float] = Field(None, ge=0, le=10)
    structure_clarity_score: Optional[float] = Field(None, ge=0, le=10)
    oral_advocacy_score: Optional[float] = Field(None, ge=0, le=10)
    responsiveness_score: Optional[float] = Field(None, ge=0, le=10)
    category_comments: Optional[str] = None
    overall_comments: Optional[str] = None
    strengths: Optional[str] = None
    improvements: Optional[str] = None


# ================= EVALUATION CRUD =================

@router.post("", status_code=201)
async def create_evaluation(
    data: EvaluationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 5C: Create a new evaluation (as draft).
    Only judges/faculty can create evaluations.
    """
    # Check permissions
    if current_user.role not in [UserRole.JUDGE, UserRole.FACULTY, UserRole.ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(status_code=403, detail="Only judges can create evaluations")
    
    # Verify project access
    project_result = await db.execute(
        select(MootProject).where(
            and_(
                MootProject.id == data.project_id,
                MootProject.is_active == True
            )
        )
    )
    project = project_result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if current_user.role != UserRole.SUPER_ADMIN and current_user.institution_id != project.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Check if evaluation already exists
    existing_result = await db.execute(
        select(MootEvaluation).where(
            and_(
                MootEvaluation.project_id == data.project_id,
                MootEvaluation.judge_id == current_user.id
            )
        )
    )
    existing = existing_result.scalar_one_or_none()
    
    if existing:
        raise HTTPException(status_code=400, detail="You already have an evaluation for this project. Use PATCH to update.")
    
    # Create evaluation
    evaluation = MootEvaluation(
        institution_id=project.institution_id,
        project_id=data.project_id,
        judge_id=current_user.id,
        issue_framing_score=data.issue_framing_score,
        legal_reasoning_score=data.legal_reasoning_score,
        use_of_authority_score=data.use_of_authority_score,
        structure_clarity_score=data.structure_clarity_score,
        oral_advocacy_score=data.oral_advocacy_score,
        responsiveness_score=data.responsiveness_score,
        category_comments=data.category_comments,
        overall_comments=data.overall_comments,
        strengths=data.strengths,
        improvements=data.improvements,
        is_draft=True,
        is_locked=False
    )
    
    # Calculate total
    evaluation.calculate_total()
    
    db.add(evaluation)
    await db.commit()
    await db.refresh(evaluation)
    
    # Phase 6C: Log evaluation draft creation
    await log_evaluation_draft_created(
        db=db,
        project=project,
        actor=current_user,
        evaluation_id=evaluation.id
    )
    
    logger.info(f"Evaluation created: {evaluation.id} for project {data.project_id}")
    
    return {
        "success": True,
        "evaluation": evaluation.to_dict()
    }


@router.get("", status_code=200)
async def list_evaluations(
    project_id: int = Query(...),
    include_details: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 5C: List evaluations for a project.
    Judges see their own. Students see all finalized.
    """
    # Verify project access
    project_result = await db.execute(
        select(MootProject).where(MootProject.id == project_id)
    )
    project = project_result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if current_user.role != UserRole.SUPER_ADMIN and current_user.institution_id != project.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Build query
    query = select(MootEvaluation).where(MootEvaluation.project_id == project_id)
    
    # Students only see finalized evaluations
    if current_user.role == UserRole.STUDENT:
        query = query.where(MootEvaluation.is_draft == False)
        # Students only see their own project's evaluations
        if project.created_by != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
    
    # Judges see their own + all finalized
    if current_user.role == UserRole.JUDGE:
        query = query.where(
            or_(
                MootEvaluation.judge_id == current_user.id,
                MootEvaluation.is_draft == False
            )
        )
    
    query = query.order_by(desc(MootEvaluation.created_at))
    
    result = await db.execute(query)
    evaluations = result.scalars().all()
    
    return {
        "success": True,
        "evaluations": [e.to_dict(include_details=include_details) for e in evaluations],
        "count": len(evaluations)
    }


@router.get("/{evaluation_id}", status_code=200)
async def get_evaluation(
    evaluation_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 5C: Get evaluation details.
    """
    result = await db.execute(
        select(MootEvaluation).where(MootEvaluation.id == evaluation_id)
    )
    evaluation = result.scalar_one_or_none()
    
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    
    # Verify project access
    project_result = await db.execute(
        select(MootProject).where(MootProject.id == evaluation.project_id)
    )
    project = project_result.scalar_one_or_none()
    
    if current_user.role != UserRole.SUPER_ADMIN and current_user.institution_id != project.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Access control
    if current_user.role == UserRole.STUDENT:
        # Students only see finalized evaluations for their own projects
        if evaluation.is_draft:
            raise HTTPException(status_code=404, detail="Evaluation not found")
        if project.created_by != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
    
    if current_user.role == UserRole.JUDGE:
        # Judges can see their own drafts, but not other judges' drafts
        if evaluation.is_draft and evaluation.judge_id != current_user.id:
            raise HTTPException(status_code=404, detail="Evaluation not found")
    
    return {
        "success": True,
        "evaluation": evaluation.to_dict()
    }


@router.patch("/{evaluation_id}", status_code=200)
async def update_evaluation(
    evaluation_id: int,
    data: EvaluationUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 5C: Update an evaluation.
    Only drafts can be edited. Finalized evaluations are immutable.
    """
    result = await db.execute(
        select(MootEvaluation).where(MootEvaluation.id == evaluation_id)
    )
    evaluation = result.scalar_one_or_none()
    
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    
    # Check ownership
    if evaluation.judge_id != current_user.id and current_user.role not in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(status_code=403, detail="You can only update your own evaluations")
    
    # Check if locked
    if evaluation.is_locked:
        raise HTTPException(status_code=400, detail="Evaluation is finalized and locked. No edits allowed.")
    
    # Update fields
    if data.issue_framing_score is not None:
        evaluation.issue_framing_score = data.issue_framing_score
    if data.legal_reasoning_score is not None:
        evaluation.legal_reasoning_score = data.legal_reasoning_score
    if data.use_of_authority_score is not None:
        evaluation.use_of_authority_score = data.use_of_authority_score
    if data.structure_clarity_score is not None:
        evaluation.structure_clarity_score = data.structure_clarity_score
    if data.oral_advocacy_score is not None:
        evaluation.oral_advocacy_score = data.oral_advocacy_score
    if data.responsiveness_score is not None:
        evaluation.responsiveness_score = data.responsiveness_score
    if data.category_comments is not None:
        evaluation.category_comments = data.category_comments
    if data.overall_comments is not None:
        evaluation.overall_comments = data.overall_comments
    if data.strengths is not None:
        evaluation.strengths = data.strengths
    if data.improvements is not None:
        evaluation.improvements = data.improvements
    
    # Recalculate total
    evaluation.calculate_total()
    evaluation.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(evaluation)
    
    return {
        "success": True,
        "evaluation": evaluation.to_dict()
    }


@router.post("/{evaluation_id}/finalize", status_code=200)
async def finalize_evaluation(
    evaluation_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 5C: Finalize an evaluation.
    Once finalized, it becomes immutable and visible to students.
    """
    result = await db.execute(
        select(MootEvaluation).where(MootEvaluation.id == evaluation_id)
    )
    evaluation = result.scalar_one_or_none()
    
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    
    # Check ownership
    if evaluation.judge_id != current_user.id and current_user.role not in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(status_code=403, detail="You can only finalize your own evaluations")
    
    # Check if already finalized
    if not evaluation.is_draft:
        raise HTTPException(status_code=400, detail="Evaluation is already finalized")
    
    # Finalize
    evaluation.is_draft = False
    evaluation.finalized_at = datetime.utcnow()
    evaluation.is_locked = True
    
    await db.commit()
    await db.refresh(evaluation)
    
    # Phase 6C: Log evaluation finalization
    await log_evaluation_finalized(
        db=db,
        project=project,
        actor=current_user,
        evaluation_id=evaluation.id,
        total_score=evaluation.total_score
    )
    
    logger.info(f"Evaluation finalized: {evaluation_id}")
    
    return {
        "success": True,
        "message": "Evaluation finalized successfully. It is now visible to students and cannot be edited.",
        "evaluation": evaluation.to_dict()
    }


@router.delete("/{evaluation_id}", status_code=200)
async def delete_evaluation(
    evaluation_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 5C: Delete an evaluation (only drafts).
    Finalized evaluations cannot be deleted.
    """
    result = await db.execute(
        select(MootEvaluation).where(MootEvaluation.id == evaluation_id)
    )
    evaluation = result.scalar_one_or_none()
    
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    
    # Check ownership or admin
    if evaluation.judge_id != current_user.id and current_user.role not in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(status_code=403, detail="You can only delete your own evaluations")
    
    # Check if finalized
    if not evaluation.is_draft:
        raise HTTPException(status_code=400, detail="Cannot delete a finalized evaluation")
    
    await db.delete(evaluation)
    await db.commit()
    
    logger.info(f"Evaluation deleted: {evaluation_id}")
    
    return {
        "success": True,
        "message": "Evaluation deleted successfully"
    }
