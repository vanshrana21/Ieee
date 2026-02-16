"""
backend/routes/scoring.py
Phase 5D: Judge scoring routes with publish control and conflict resolution
"""
import logging
from typing import List, Optional
from datetime import datetime
from statistics import variance, stdev

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, func
from sqlalchemy.orm import selectinload

from backend.database import get_db
from backend.orm.scoring import JudgeScore, EvaluationStatus, ScoreConflict, ScoreConflictStatus, ScoreAuditLog
from backend.orm.team import Team
from backend.orm.competition import Competition
from backend.orm.submission_slot import SubmissionSlot
from backend.orm.user import User, UserRole
from backend.rbac import get_current_user
from backend.errors import ErrorCode

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/scoring", tags=["Scoring"])


# ================= SCHEMAS =================

class ScoreCreate(BaseModel):
    """Schema for creating a new judge score"""
    team_id: int
    submission_id: Optional[int] = None
    slot_id: Optional[int] = None
    
    # Scores (0-10 scale)
    issue_framing_score: float = Field(..., ge=0, le=10)
    legal_reasoning_score: float = Field(..., ge=0, le=10)
    use_of_authority_score: float = Field(..., ge=0, le=10)
    structure_clarity_score: float = Field(..., ge=0, le=10)
    oral_advocacy_score: Optional[float] = Field(None, ge=0, le=10)
    responsiveness_score: Optional[float] = Field(None, ge=0, le=10)
    
    # Notes
    issue_framing_notes: Optional[str] = None
    legal_reasoning_notes: Optional[str] = None
    use_of_authority_notes: Optional[str] = None
    structure_clarity_notes: Optional[str] = None
    oral_advocacy_notes: Optional[str] = None
    responsiveness_notes: Optional[str] = None
    overall_assessment: Optional[str] = None
    strengths: Optional[str] = None  # JSON array as string
    improvements: Optional[str] = None  # JSON array as string


class ScoreUpdate(BaseModel):
    """Schema for updating a score (only when in DRAFT)"""
    issue_framing_score: Optional[float] = Field(None, ge=0, le=10)
    legal_reasoning_score: Optional[float] = Field(None, ge=0, le=10)
    use_of_authority_score: Optional[float] = Field(None, ge=0, le=10)
    structure_clarity_score: Optional[float] = Field(None, ge=0, le=10)
    oral_advocacy_score: Optional[float] = Field(None, ge=0, le=10)
    responsiveness_score: Optional[float] = Field(None, ge=0, le=10)
    
    # Notes
    issue_framing_notes: Optional[str] = None
    legal_reasoning_notes: Optional[str] = None
    use_of_authority_notes: Optional[str] = None
    structure_clarity_notes: Optional[str] = None
    oral_advocacy_notes: Optional[str] = None
    responsiveness_notes: Optional[str] = None
    overall_assessment: Optional[str] = None
    strengths: Optional[str] = None
    improvements: Optional[str] = None


class ConflictResolveRequest(BaseModel):
    """Schema for resolving a conflict"""
    resolution_notes: str
    override_score_id: Optional[int] = None  # Which judge's score to use as final
    status: str = "resolved"  # resolved or overridden


# ================= HELPER FUNCTIONS =================

async def log_score_action(
    judge_score_id: int,
    action: str,
    performed_by: int,
    field_changed: Optional[str] = None,
    old_value: Optional[str] = None,
    new_value: Optional[str] = None,
    notes: Optional[str] = None,
    db: AsyncSession = None
):
    """Log a scoring action to audit trail"""
    log = ScoreAuditLog(
        judge_score_id=judge_score_id,
        action=action,
        performed_by=performed_by,
        field_changed=field_changed,
        old_value=old_value,
        new_value=new_value,
        notes=notes
    )
    db.add(log)
    await db.commit()


async def detect_score_conflicts(
    competition_id: int,
    team_id: int,
    criterion: str,
    variance_threshold: float = 4.0,  # Flag if variance > 4 (2 point avg diff)
    db: AsyncSession = None
) -> Optional[ScoreConflict]:
    """
    Phase 5D: Detect if judges have significantly different scores.
    Returns conflict object if detected, None otherwise.
    """
    # Get all final scores for this team
    result = await db.execute(
        select(JudgeScore).where(
            and_(
                JudgeScore.competition_id == competition_id,
                JudgeScore.team_id == team_id,
                JudgeScore.is_final == True,
                JudgeScore.conflict_status != ScoreConflictStatus.OVERRIDDEN
            )
        )
    )
    scores = result.scalars().all()
    
    if len(scores) < 2:
        return None  # Need at least 2 judges to have conflict
    
    # Extract scores for each criterion
    criterion_scores = {}
    criteria = [
        "issue_framing_score", "legal_reasoning_score", "use_of_authority_score",
        "structure_clarity_score", "oral_advocacy_score", "responsiveness_score"
    ]
    
    for crit in criteria:
        values = [getattr(s, crit) for s in scores if getattr(s, crit) is not None]
        if len(values) >= 2:
            criterion_scores[crit] = values
    
    # Find highest variance criterion
    max_variance = 0
    conflict_criterion = None
    conflict_scores = []
    
    for crit, values in criterion_scores.items():
        if len(values) >= 2:
            var = variance(values) if len(values) > 1 else 0
            if var > max_variance:
                max_variance = var
                conflict_criterion = crit
                conflict_scores = values
    
    # If variance exceeds threshold, create conflict
    if max_variance >= variance_threshold:
        max_diff = max(conflict_scores) - min(conflict_scores)
        
        conflict = ScoreConflict(
            institution_id=scores[0].institution_id,
            competition_id=competition_id,
            team_id=team_id,
            judge_score_ids=[s.id for s in scores],
            criterion_in_conflict=conflict_criterion,
            score_variance=max_variance,
            max_difference=max_diff,
            status="pending",
            detected_by=0  # System
        )
        
        db.add(conflict)
        await db.commit()
        await db.refresh(conflict)
        
        # Update all involved scores to mark conflict
        for score in scores:
            score.conflict_status = ScoreConflictStatus.PENDING
            await log_score_action(score.id, "dispute", 0, notes=f"Auto-detected conflict: variance={max_variance:.2f}", db=db)
        
        await db.commit()
        
        logger.info(f"Score conflict detected: competition={competition_id}, team={team_id}, variance={max_variance:.2f}")
        return conflict
    
    return None


# ================= SCORING CRUD =================

@router.post("", status_code=201)
async def create_score(
    competition_id: int = Query(...),
    data: ScoreCreate = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new judge score evaluation.
    Judges can create scores for teams they are assigned to evaluate.
    """
    # Check permissions
    if current_user.role not in [UserRole.teacher, UserRole.teacher, UserRole.teacher, UserRole.teacher]:
        raise HTTPException(status_code=403, detail="Only judges can create scores")
    
    # Verify competition access
    comp_result = await db.execute(
        select(Competition).where(Competition.id == competition_id)
    )
    competition = comp_result.scalar_one_or_none()
    
    if not competition:
        raise HTTPException(status_code=404, detail="Competition not found")
    
    if current_user.role != UserRole.teacher and current_user.institution_id != competition.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Check if judge already has a score for this team/submission/slot
    existing_query = select(JudgeScore).where(
        and_(
            JudgeScore.competition_id == competition_id,
            JudgeScore.judge_id == current_user.id,
            JudgeScore.team_id == data.team_id
        )
    )
    
    if data.submission_id:
        existing_query = existing_query.where(JudgeScore.submission_id == data.submission_id)
    if data.slot_id:
        existing_query = existing_query.where(JudgeScore.slot_id == data.slot_id)
    
    existing_result = await db.execute(existing_query)
    existing = existing_result.scalar_one_or_none()
    
    if existing:
        raise HTTPException(status_code=400, detail="You already have a score for this team. Use PATCH to update.")
    
    # Create score
    score = JudgeScore(
        institution_id=competition.institution_id,
        competition_id=competition_id,
        team_id=data.team_id,
        submission_id=data.submission_id,
        slot_id=data.slot_id,
        judge_id=current_user.id,
        status=EvaluationStatus.DRAFT,
        conflict_status=ScoreConflictStatus.NONE,
        
        # Scores
        issue_framing_score=data.issue_framing_score,
        legal_reasoning_score=data.legal_reasoning_score,
        use_of_authority_score=data.use_of_authority_score,
        structure_clarity_score=data.structure_clarity_score,
        oral_advocacy_score=data.oral_advocacy_score,
        responsiveness_score=data.responsiveness_score,
        
        # Notes
        issue_framing_notes=data.issue_framing_notes,
        legal_reasoning_notes=data.legal_reasoning_notes,
        use_of_authority_notes=data.use_of_authority_notes,
        structure_clarity_notes=data.structure_clarity_notes,
        oral_advocacy_notes=data.oral_advocacy_notes,
        responsiveness_notes=data.responsiveness_notes,
        overall_assessment=data.overall_assessment,
        strengths=data.strengths,
        improvements=data.improvements,
        
        is_published=False,
        is_final=False
    )
    
    # Calculate total
    score.calculate_total()
    
    db.add(score)
    await db.commit()
    await db.refresh(score)
    
    # Log creation
    await log_score_action(score.id, "create", current_user.id, db=db)
    
    logger.info(f"Score created: {score.id} by judge {current_user.id}")
    
    return {
        "success": True,
        "score": score.to_dict()
    }


@router.get("", status_code=200)
async def list_scores(
    competition_id: int = Query(...),
    team_id: Optional[int] = Query(None),
    judge_id: Optional[int] = Query(None),
    include_unpublished: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List judge scores.
    Phase 5D: Students only see published scores. Judges see their own. Admins see all.
    """
    # Verify competition access
    comp_result = await db.execute(
        select(Competition).where(Competition.id == competition_id)
    )
    competition = comp_result.scalar_one_or_none()
    
    if not competition:
        raise HTTPException(status_code=404, detail="Competition not found")
    
    if current_user.role != UserRole.teacher and current_user.institution_id != competition.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Build query
    query = select(JudgeScore).where(JudgeScore.competition_id == competition_id)
    
    # Filters
    if team_id:
        query = query.where(JudgeScore.team_id == team_id)
    if judge_id:
        query = query.where(JudgeScore.judge_id == judge_id)
    
    # Publication filter (Phase 5D: Critical for privacy)
    if current_user.role == UserRole.student:
        # Students only see published scores
        query = query.where(JudgeScore.is_published == True)
    elif current_user.role in [UserRole.teacher]:
        # Judges see their own scores (published or not) + published scores from others
        if not include_unpublished:
            query = query.where(
                or_(
                    JudgeScore.judge_id == current_user.id,
                    JudgeScore.is_published == True
                )
            )
    # Admins/Faculty can see all if include_unpublished=true
    elif not include_unpublished:
        query = query.where(JudgeScore.is_published == True)
    
    query = query.order_by(desc(JudgeScore.created_at))
    
    result = await db.execute(query)
    scores = result.scalars().all()
    
    return {
        "success": True,
        "competition_id": competition_id,
        "scores": [s.to_dict(include_notes=(current_user.role != UserRole.student)) for s in scores],
        "count": len(scores)
    }


@router.get("/{score_id}", status_code=200)
async def get_score(
    score_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific judge score.
    Phase 5D: Students can only see published scores.
    """
    result = await db.execute(
        select(JudgeScore).where(JudgeScore.id == score_id)
    )
    score = result.scalar_one_or_none()
    
    if not score:
        raise HTTPException(status_code=404, detail="Score not found")
    
    # Check access
    if current_user.role != UserRole.teacher and current_user.institution_id != score.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Students can only see published scores
    if current_user.role == UserRole.student and not score.is_published:
        raise HTTPException(status_code=404, detail="Score not found")  # Don't reveal existence
    
    # Judges can see their own unpublished scores
    if current_user.role == UserRole.teacher and score.judge_id != current_user.id and not score.is_published:
        raise HTTPException(status_code=404, detail="Score not found")
    
    return {
        "success": True,
        "score": score.to_dict(include_notes=(current_user.role != UserRole.student))
    }


@router.patch("/{score_id}", status_code=200)
async def update_score(
    score_id: int,
    data: ScoreUpdate = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update a judge score.
    Phase 5D: Can only update if in DRAFT status (not finalized).
    """
    result = await db.execute(
        select(JudgeScore).where(JudgeScore.id == score_id)
    )
    score = result.scalar_one_or_none()
    
    if not score:
        raise HTTPException(status_code=404, detail="Score not found")
    
    # Check ownership
    if score.judge_id != current_user.id and current_user.role not in [UserRole.teacher, UserRole.teacher]:
        raise HTTPException(status_code=403, detail="You can only update your own scores")
    
    # Check if already finalized
    if score.is_final and current_user.role not in [UserRole.teacher, UserRole.teacher]:
        raise HTTPException(status_code=400, detail="Score is finalized. Contact admin to unlock.")
    
    # Update fields
    updates = []
    score_fields = [
        "issue_framing_score", "legal_reasoning_score", "use_of_authority_score",
        "structure_clarity_score", "oral_advocacy_score", "responsiveness_score"
    ]
    note_fields = [
        "issue_framing_notes", "legal_reasoning_notes", "use_of_authority_notes",
        "structure_clarity_notes", "oral_advocacy_notes", "responsiveness_notes"
    ]
    
    for field in score_fields:
        value = getattr(data, field)
        if value is not None:
            old_val = getattr(score, field)
            setattr(score, field, value)
            updates.append((field, str(old_val), str(value)))
    
    for field in note_fields:
        value = getattr(data, field)
        if value is not None:
            old_val = getattr(score, field)
            setattr(score, field, value)
            updates.append((field, old_val, value))
    
    if data.overall_assessment is not None:
        updates.append(("overall_assessment", score.overall_assessment, data.overall_assessment))
        score.overall_assessment = data.overall_assessment
    
    if data.strengths is not None:
        updates.append(("strengths", score.strengths, data.strengths))
        score.strengths = data.strengths
    
    if data.improvements is not None:
        updates.append(("improvements", score.improvements, data.improvements))
        score.improvements = data.improvements
    
    # Recalculate total
    score.calculate_total()
    score.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(score)
    
    # Log updates
    for field, old, new in updates:
        await log_score_action(score.id, "update", current_user.id, field, old, new, db=db)
    
    return {
        "success": True,
        "score": score.to_dict()
    }


# ================= FINALIZATION =================

@router.post("/{score_id}/finalize", status_code=200)
async def finalize_score(
    score_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Finalize a judge score.
    After finalization, score can only be edited by admin.
    """
    result = await db.execute(
        select(JudgeScore).where(JudgeScore.id == score_id)
    )
    score = result.scalar_one_or_none()
    
    if not score:
        raise HTTPException(status_code=404, detail="Score not found")
    
    # Check ownership
    if score.judge_id != current_user.id and current_user.role not in [UserRole.teacher, UserRole.teacher]:
        raise HTTPException(status_code=403, detail="You can only finalize your own scores")
    
    # Check if already finalized
    if score.is_final:
        raise HTTPException(status_code=400, detail="Score is already finalized")
    
    # Finalize
    score.is_final = True
    score.finalized_at = datetime.utcnow()
    score.status = EvaluationStatus.SUBMITTED
    
    await db.commit()
    
    # Log
    await log_score_action(score.id, "finalize", current_user.id, db=db)
    
    # Check for conflicts with other judges
    conflict = await detect_score_conflicts(
        score.competition_id,
        score.team_id,
        "issue_framing_score",  # Primary criterion
        db=db
    )
    
    logger.info(f"Score finalized: {score_id} by judge {current_user.id}")
    
    return {
        "success": True,
        "score": score.to_dict(),
        "conflict_detected": conflict is not None,
        "conflict_id": conflict.id if conflict else None
    }


# ================= PUBLISH/UNPUBLISH =================

@router.post("/{score_id}/publish", status_code=200)
async def publish_score(
    score_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Publish a judge score to make it visible to students.
    Phase 5D: Only Admin/Faculty can publish.
    """
    # Check permissions
    if current_user.role not in [UserRole.teacher, UserRole.teacher, UserRole.teacher]:
        raise HTTPException(status_code=403, detail="Only Faculty/Admin can publish scores")
    
    result = await db.execute(
        select(JudgeScore).where(JudgeScore.id == score_id)
    )
    score = result.scalar_one_or_none()
    
    if not score:
        raise HTTPException(status_code=404, detail="Score not found")
    
    # Verify institution
    if current_user.role != UserRole.teacher and current_user.institution_id != score.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Check if already published
    if score.is_published:
        raise HTTPException(status_code=400, detail="Score is already published")
    
    # Check if finalized
    if not score.is_final:
        raise HTTPException(status_code=400, detail="Score must be finalized before publishing")
    
    # Publish
    score.is_published = True
    score.published_at = datetime.utcnow()
    score.published_by = current_user.id
    score.status = EvaluationStatus.PUBLISHED
    
    await db.commit()
    
    # Log
    await log_score_action(score.id, "publish", current_user.id, db=db)
    
    logger.info(f"Score published: {score_id} by {current_user.id}")
    
    return {
        "success": True,
        "message": "Score published successfully",
        "score": score.to_dict()
    }


@router.post("/{score_id}/unpublish", status_code=200)
async def unpublish_score(
    score_id: int,
    reason: str = Query(..., description="Reason for unpublishing"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Unpublish a score to hide it from students.
    Phase 5D: Only Admin can unpublish.
    """
    # Check permissions
    if current_user.role not in [UserRole.teacher, UserRole.teacher]:
        raise HTTPException(status_code=403, detail="Only Admin can unpublish scores")
    
    result = await db.execute(
        select(JudgeScore).where(JudgeScore.id == score_id)
    )
    score = result.scalar_one_or_none()
    
    if not score:
        raise HTTPException(status_code=404, detail="Score not found")
    
    # Verify institution
    if current_user.role != UserRole.teacher and current_user.institution_id != score.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Check if published
    if not score.is_published:
        raise HTTPException(status_code=400, detail="Score is not published")
    
    # Unpublish
    score.is_published = False
    score.published_at = None
    score.published_by = None
    score.status = EvaluationStatus.SUBMITTED  # Back to submitted
    
    await db.commit()
    
    # Log
    await log_score_action(score.id, "unpublish", current_user.id, notes=reason, db=db)
    
    logger.info(f"Score unpublished: {score_id} by {current_user.id}, reason: {reason}")
    
    return {
        "success": True,
        "message": "Score unpublished successfully",
        "score": score.to_dict()
    }


# ================= CONFLICT RESOLUTION =================

@router.get("/conflicts", status_code=200)
async def list_conflicts(
    competition_id: int = Query(...),
    status: Optional[str] = Query(None, description="Filter by status: pending, under_review, resolved, overridden"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List score conflicts for conflict resolution.
    Phase 5D: Admin/Faculty can view and resolve conflicts.
    """
    # Check permissions
    if current_user.role not in [UserRole.teacher, UserRole.teacher, UserRole.teacher]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    # Verify competition access
    comp_result = await db.execute(
        select(Competition).where(Competition.id == competition_id)
    )
    competition = comp_result.scalar_one_or_none()
    
    if not competition:
        raise HTTPException(status_code=404, detail="Competition not found")
    
    if current_user.role != UserRole.teacher and current_user.institution_id != competition.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Build query
    query = select(ScoreConflict).where(ScoreConflict.competition_id == competition_id)
    
    if status:
        query = query.where(ScoreConflict.status == status)
    
    query = query.order_by(desc(ScoreConflict.detected_at))
    
    result = await db.execute(query)
    conflicts = result.scalars().all()
    
    return {
        "success": True,
        "competition_id": competition_id,
        "conflicts": [c.to_dict() for c in conflicts],
        "count": len(conflicts)
    }


@router.post("/conflicts/{conflict_id}/resolve", status_code=200)
async def resolve_conflict(
    conflict_id: int,
    data: ConflictResolveRequest = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Resolve a score conflict.
    Phase 5D: Admin can resolve conflicts by selecting which score to use or providing override.
    """
    # Check permissions
    if current_user.role not in [UserRole.teacher, UserRole.teacher]:
        raise HTTPException(status_code=403, detail="Only Admin can resolve conflicts")
    
    result = await db.execute(
        select(ScoreConflict).where(ScoreConflict.id == conflict_id)
    )
    conflict = result.scalar_one_or_none()
    
    if not conflict:
        raise HTTPException(status_code=404, detail="Conflict not found")
    
    # Verify institution
    if current_user.role != UserRole.teacher and current_user.institution_id != conflict.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Update conflict
    conflict.status = data.status
    conflict.resolution_notes = data.resolution_notes
    conflict.resolved_by = current_user.id
    conflict.resolved_at = datetime.utcnow()
    conflict.override_score_id = data.override_score_id
    
    # Update involved scores
    for score_id in conflict.judge_score_ids:
        score_result = await db.execute(
            select(JudgeScore).where(JudgeScore.id == score_id)
        )
        score = score_result.scalar_one_or_none()
        if score:
            if data.status == "resolved":
                score.conflict_status = ScoreConflictStatus.RESOLVED
            elif data.status == "overridden":
                score.conflict_status = ScoreConflictStatus.OVERRIDDEN
                # Mark the selected score as authoritative
                if data.override_score_id == score_id:
                    score.is_published = True  # Auto-publish override
    
    await db.commit()
    await db.refresh(conflict)
    
    logger.info(f"Conflict resolved: {conflict_id} by admin {current_user.id}")
    
    return {
        "success": True,
        "message": "Conflict resolved successfully",
        "conflict": conflict.to_dict()
    }
