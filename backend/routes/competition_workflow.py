"""
backend/routes/competition_workflow.py
Phase 5D: Competition workflow, deadlines, and submission locking
"""
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from backend.database import get_db
from backend.orm.competition import Competition, CompetitionStatus
from backend.orm.moot_project import MootProject, ProjectStatus, LockReason
from backend.orm.submission_audit import SubmissionAuditLog
from backend.orm.user import User, UserRole
from backend.rbac import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/competitions", tags=["Competition Workflow"])


# ================= SCHEMAS =================

class SubmitProjectRequest(BaseModel):
    """Student submits their project"""
    project_id: int


class LockProjectRequest(BaseModel):
    """Admin locks a project"""
    reason: str = Field(..., min_length=1, description="Reason for locking")


class UnlockProjectRequest(BaseModel):
    """Admin unlocks a project"""
    reason: str = Field(..., min_length=1, description="Reason for unlocking")


class ExtendDeadlineRequest(BaseModel):
    """Admin extends deadline"""
    new_deadline: datetime
    reason: str = Field(..., min_length=1)


class StatusChangeRequest(BaseModel):
    """Admin changes competition status"""
    new_status: str = Field(..., pattern="^(draft|registration|active|submission_closed|evaluation|closed|cancelled)$")
    reason: str = Field(..., min_length=1)


# ================= HELPERS =================

async def log_submission_action(
    db: AsyncSession,
    institution_id: int,
    competition_id: int,
    project_id: int,
    user_id: int,
    user_role: str,
    action: str,
    reason: str = None,
    competition_status: str = None,
    deadline: datetime = None
):
    """Log submission action to audit trail"""
    log = SubmissionAuditLog(
        institution_id=institution_id,
        competition_id=competition_id,
        project_id=project_id,
        user_id=user_id,
        user_role=user_role,
        action=action,
        reason=reason,
        competition_status=competition_status,
        deadline_at_action=deadline
    )
    db.add(log)
    await db.commit()


def is_editing_allowed(project: MootProject, competition: Competition) -> bool:
    """
    Phase 5D: Check if editing is allowed for this project.
    Returns True if editing is permitted, False otherwise.
    """
    # If project is explicitly locked
    if project.is_locked:
        return False
    
    # If project is submitted
    if project.is_submitted:
        return False
    
    # If competition is in locked state
    if competition.status in [CompetitionStatus.SUBMISSION_CLOSED, CompetitionStatus.EVALUATION, CompetitionStatus.CLOSED]:
        return False
    
    return True


# ================= PROJECT SUBMISSION =================

@router.post("/{competition_id}/submit", status_code=200)
async def submit_project(
    competition_id: int,
    data: SubmitProjectRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 5D: Student explicitly submits their project.
    This locks the project from further edits.
    """
    # Get competition
    comp_result = await db.execute(
        select(Competition).where(Competition.id == competition_id)
    )
    competition = comp_result.scalar_one_or_none()
    
    if not competition:
        raise HTTPException(status_code=404, detail="Competition not found")
    
    # Check institution
    if current_user.role != UserRole.teacher and current_user.institution_id != competition.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get project
    proj_result = await db.execute(
        select(MootProject).where(
            and_(
                MootProject.id == data.project_id,
                MootProject.competition_id == competition_id
            )
        )
    )
    project = proj_result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Verify ownership
    if current_user.role == UserRole.student and project.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="You can only submit your own projects")
    
    # Check if already submitted
    if project.is_submitted:
        raise HTTPException(status_code=400, detail="Project is already submitted")
    
    # Check deadline
    if competition.memorial_submission_deadline and datetime.utcnow() > competition.memorial_submission_deadline:
        raise HTTPException(
            status_code=403,
            detail="Submission deadline has passed. Contact admin for assistance."
        )
    
    # Check competition status
    if competition.status not in [CompetitionStatus.ACTIVE, CompetitionStatus.REGISTRATION]:
        raise HTTPException(
            status_code=403,
            detail=f"Submissions are not allowed in {competition.status.value} status"
        )
    
    # Submit the project
    project.is_submitted = True
    project.submitted_at = datetime.utcnow()
    project.status = ProjectStatus.SUBMITTED
    project.is_locked = True
    project.locked_reason = LockReason.SUBMISSION
    project.locked_at = datetime.utcnow()
    
    await db.commit()
    
    # Log the submission
    await log_submission_action(
        db=db,
        institution_id=competition.institution_id,
        competition_id=competition_id,
        project_id=project.id,
        user_id=current_user.id,
        user_role=current_user.role.value,
        action="submit",
        reason="Student submitted project",
        competition_status=competition.status.value,
        deadline=competition.memorial_submission_deadline
    )
    
    logger.info(f"Project {project.id} submitted by user {current_user.id}")
    
    return {
        "success": True,
        "message": "Project submitted successfully. No further edits allowed.",
        "submitted_at": project.submitted_at.isoformat(),
        "project": project.to_dict()
    }


# ================= ADMIN LOCK/UNLOCK =================

@router.post("/{competition_id}/projects/{project_id}/lock", status_code=200)
async def lock_project(
    competition_id: int,
    project_id: int,
    data: LockProjectRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 5D: Admin manually locks a project.
    Requires reason and is logged.
    """
    # Check permissions
    if current_user.role not in [UserRole.teacher, UserRole.teacher]:
        raise HTTPException(status_code=403, detail="Only admins can lock projects")
    
    # Get competition
    comp_result = await db.execute(
        select(Competition).where(Competition.id == competition_id)
    )
    competition = comp_result.scalar_one_or_none()
    
    if not competition:
        raise HTTPException(status_code=404, detail="Competition not found")
    
    if current_user.role != UserRole.teacher and current_user.institution_id != competition.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get project
    proj_result = await db.execute(
        select(MootProject).where(
            and_(
                MootProject.id == project_id,
                MootProject.competition_id == competition_id
            )
        )
    )
    project = proj_result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Check if already locked
    if project.is_locked and project.locked_reason != LockReason.NOT_LOCKED:
        raise HTTPException(status_code=400, detail="Project is already locked")
    
    # Lock the project
    project.is_locked = True
    project.locked_reason = LockReason.ADMIN_LOCK
    project.locked_at = datetime.utcnow()
    project.locked_by = current_user.id
    
    await db.commit()
    
    # Log the lock
    await log_submission_action(
        db=db,
        institution_id=competition.institution_id,
        competition_id=competition_id,
        project_id=project_id,
        user_id=current_user.id,
        user_role=current_user.role.value,
        action="lock",
        reason=data.reason,
        competition_status=competition.status.value
    )
    
    logger.info(f"Project {project_id} locked by admin {current_user.id}: {data.reason}")
    
    return {
        "success": True,
        "message": "Project locked successfully",
        "reason": data.reason,
        "locked_at": project.locked_at.isoformat(),
        "project": project.to_dict()
    }


@router.post("/{competition_id}/projects/{project_id}/unlock", status_code=200)
async def unlock_project(
    competition_id: int,
    project_id: int,
    data: UnlockProjectRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 5D: Admin unlocks a project for editing.
    Requires reason and is logged.
    """
    # Check permissions
    if current_user.role not in [UserRole.teacher, UserRole.teacher]:
        raise HTTPException(status_code=403, detail="Only admins can unlock projects")
    
    # Get competition
    comp_result = await db.execute(
        select(Competition).where(Competition.id == competition_id)
    )
    competition = comp_result.scalar_one_or_none()
    
    if not competition:
        raise HTTPException(status_code=404, detail="Competition not found")
    
    if current_user.role != UserRole.teacher and current_user.institution_id != competition.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get project
    proj_result = await db.execute(
        select(MootProject).where(
            and_(
                MootProject.id == project_id,
                MootProject.competition_id == competition_id
            )
        )
    )
    project = proj_result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Check if locked
    if not project.is_locked:
        raise HTTPException(status_code=400, detail="Project is not locked")
    
    # Unlock the project
    project.is_locked = False
    project.locked_reason = LockReason.NOT_LOCKED
    project.locked_at = None
    project.locked_by = current_user.id  # Track who unlocked
    
    # If it was a submission lock, we also clear is_submitted
    # This allows students to edit and resubmit
    if project.is_submitted:
        project.is_submitted = False
        project.submitted_at = None
        project.status = ProjectStatus.ACTIVE
    
    await db.commit()
    
    # Log the unlock
    await log_submission_action(
        db=db,
        institution_id=competition.institution_id,
        competition_id=competition_id,
        project_id=project_id,
        user_id=current_user.id,
        user_role=current_user.role.value,
        action="unlock",
        reason=data.reason,
        competition_status=competition.status.value
    )
    
    logger.info(f"Project {project_id} unlocked by admin {current_user.id}: {data.reason}")
    
    return {
        "success": True,
        "message": "Project unlocked successfully. Student can now edit.",
        "reason": data.reason,
        "unlocked_at": datetime.utcnow().isoformat(),
        "project": project.to_dict()
    }


# ================= DEADLINE MANAGEMENT =================

@router.post("/{competition_id}/extend-deadline", status_code=200)
async def extend_deadline(
    competition_id: int,
    deadline_type: str = Query(..., pattern="^(registration|memorial|oral_start|oral_end)$"),
    data: ExtendDeadlineRequest = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 5D: Admin extends a deadline.
    Requires reason and is logged.
    """
    # Check permissions
    if current_user.role not in [UserRole.teacher, UserRole.teacher]:
        raise HTTPException(status_code=403, detail="Only admins can extend deadlines")
    
    # Get competition
    comp_result = await db.execute(
        select(Competition).where(Competition.id == competition_id)
    )
    competition = comp_result.scalar_one_or_none()
    
    if not competition:
        raise HTTPException(status_code=404, detail="Competition not found")
    
    if current_user.role != UserRole.teacher and current_user.institution_id != competition.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get old deadline for logging
    old_deadline = None
    if deadline_type == "registration":
        old_deadline = competition.registration_deadline
        competition.registration_deadline = data.new_deadline
    elif deadline_type == "memorial":
        old_deadline = competition.memorial_submission_deadline
        competition.memorial_submission_deadline = data.new_deadline
    elif deadline_type == "oral_start":
        old_deadline = competition.oral_round_start
        competition.oral_round_start = data.new_deadline
    elif deadline_type == "oral_end":
        old_deadline = competition.oral_round_end
        competition.oral_round_end = data.new_deadline
    
    await db.commit()
    
    # Log the extension
    await log_submission_action(
        db=db,
        institution_id=competition.institution_id,
        competition_id=competition_id,
        project_id=0,  # No specific project
        user_id=current_user.id,
        user_role=current_user.role.value,
        action="extend_deadline",
        reason=f"Extended {deadline_type} deadline from {old_deadline} to {data.new_deadline}. Reason: {data.reason}",
        competition_status=competition.status.value,
        deadline=data.new_deadline
    )
    
    logger.info(f"Deadline {deadline_type} extended for competition {competition_id} by admin {current_user.id}")
    
    return {
        "success": True,
        "message": f"{deadline_type} deadline extended successfully",
        "new_deadline": data.new_deadline.isoformat(),
        "reason": data.reason
    }


# ================= STATUS MANAGEMENT =================

@router.post("/{competition_id}/status", status_code=200)
async def change_competition_status(
    competition_id: int,
    data: StatusChangeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 5D: Admin changes competition status.
    When moving to submission_closed/evaluation, all projects are locked.
    """
    # Check permissions
    if current_user.role not in [UserRole.teacher, UserRole.teacher]:
        raise HTTPException(status_code=403, detail="Only admins can change competition status")
    
    # Get competition
    comp_result = await db.execute(
        select(Competition).where(Competition.id == competition_id)
    )
    competition = comp_result.scalar_one_or_none()
    
    if not competition:
        raise HTTPException(status_code=404, detail="Competition not found")
    
    if current_user.role != UserRole.teacher and current_user.institution_id != competition.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    old_status = competition.status
    new_status = CompetitionStatus(data.new_status)
    
    # Update status
    competition.status = new_status
    await db.commit()
    
    # If moving to submission_closed or evaluation, lock all unsubmitted projects
    if new_status in [CompetitionStatus.SUBMISSION_CLOSED, CompetitionStatus.EVALUATION]:
        proj_result = await db.execute(
            select(MootProject).where(
                and_(
                    MootProject.competition_id == competition_id,
                    MootProject.is_submitted == False,
                    MootProject.is_active == True
                )
            )
        )
        projects = proj_result.scalars().all()
        
        for project in projects:
            project.is_locked = True
            project.locked_reason = LockReason.EVALUATION if new_status == CompetitionStatus.EVALUATION else LockReason.DEADLINE
            project.locked_at = datetime.utcnow()
            project.status = ProjectStatus.LOCKED
        
        await db.commit()
        logger.info(f"Locked {len(projects)} projects due to status change to {new_status.value}")
    
    # Log the status change
    await log_submission_action(
        db=db,
        institution_id=competition.institution_id,
        competition_id=competition_id,
        project_id=0,
        user_id=current_user.id,
        user_role=current_user.role.value,
        action="status_change",
        reason=f"Changed status from {old_status.value} to {new_status.value}. {data.reason}",
        competition_status=new_status.value
    )
    
    logger.info(f"Competition {competition_id} status changed from {old_status.value} to {new_status.value}")
    
    return {
        "success": True,
        "message": f"Competition status changed to {new_status.value}",
        "old_status": old_status.value,
        "new_status": new_status.value,
        "reason": data.reason
    }


# ================= AUDIT LOGS =================

@router.get("/{competition_id}/audit-logs", status_code=200)
async def get_audit_logs(
    competition_id: int,
    project_id: Optional[int] = Query(None),
    action: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 5D: Get audit logs for a competition.
    Admins see all, students see only their own project logs.
    """
    # Get competition
    comp_result = await db.execute(
        select(Competition).where(Competition.id == competition_id)
    )
    competition = comp_result.scalar_one_or_none()
    
    if not competition:
        raise HTTPException(status_code=404, detail="Competition not found")
    
    if current_user.role != UserRole.teacher and current_user.institution_id != competition.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Build query
    query = select(SubmissionAuditLog).where(
        SubmissionAuditLog.competition_id == competition_id
    )
    
    # Students only see logs for their own projects
    if current_user.role == UserRole.student:
        # Get student's projects in this competition
        proj_result = await db.execute(
            select(MootProject.id).where(
                and_(
                    MootProject.competition_id == competition_id,
                    MootProject.created_by == current_user.id
                )
            )
        )
        student_project_ids = [row[0] for row in proj_result.all()]
        query = query.where(SubmissionAuditLog.project_id.in_(student_project_ids))
    
    if project_id:
        query = query.where(SubmissionAuditLog.project_id == project_id)
    
    if action:
        query = query.where(SubmissionAuditLog.action == action)
    
    query = query.order_by(SubmissionAuditLog.created_at.desc())
    
    result = await db.execute(query)
    logs = result.scalars().all()
    
    return {
        "success": True,
        "logs": [log.to_dict() for log in logs],
        "count": len(logs)
    }
