"""
backend/routes/submissions.py
Phase 5C: Formal submissions with file upload and deadline management
"""
import os
import hashlib
import logging
from typing import List, Optional
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc

from backend.database import get_db
from backend.orm.submission import Submission, SubmissionType, SubmissionStatus, SubmissionDeadline, SubmissionLog
from backend.orm.competition import Competition
from backend.orm.team import Team
from backend.orm.user import User, UserRole
from backend.rbac import get_current_user, require_role
from backend.errors import ErrorCode

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/submissions", tags=["Submissions"])

# Configuration
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads"))
ALLOWED_EXTENSIONS = {'.pdf', '.docx', '.doc'}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

# Ensure upload directory exists
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ================= SCHEMAS =================

class DeadlineCreate(BaseModel):
    """Schema for creating submission deadline"""
    submission_type: SubmissionType
    draft_deadline: datetime
    final_deadline: datetime
    grace_period_minutes: int = Field(default=0, ge=0)
    timezone: str = "UTC"
    notes: Optional[str] = None


class DeadlineUpdate(BaseModel):
    """Schema for updating deadline"""
    draft_deadline: Optional[datetime] = None
    final_deadline: Optional[datetime] = None
    grace_period_minutes: Optional[int] = None
    notes: Optional[str] = None


class SubmissionResponse(BaseModel):
    """Submission response schema"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    submission_type: str
    status: str
    file_name: str
    file_size: int
    word_count: Optional[int]
    draft_started_at: str
    last_edited_at: str
    submitted_at: Optional[str]
    locked_at: Optional[str]
    is_late: bool
    minutes_late: int
    student_notes: Optional[str]


# ================= HELPER FUNCTIONS =================

def get_file_extension(filename: str) -> str:
    """Get lowercase file extension"""
    return Path(filename).suffix.lower()

def is_allowed_file(filename: str) -> bool:
    """Check if file extension is allowed"""
    return get_file_extension(filename) in ALLOWED_EXTENSIONS

def calculate_file_hash(file_path: Path) -> str:
    """Calculate SHA-256 hash of file for integrity"""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def format_file_size(size_bytes: int) -> str:
    """Format file size for display"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


async def check_deadline_status(
    competition_id: int,
    submission_type: SubmissionType,
    db: AsyncSession
) -> dict:
    """
    Check current deadline status for a submission type.
    Returns dict with is_locked, is_closed, minutes_remaining, etc.
    """
    result = await db.execute(
        select(SubmissionDeadline).where(
            and_(
                SubmissionDeadline.competition_id == competition_id,
                SubmissionDeadline.submission_type == submission_type
            )
        )
    )
    deadline = result.scalar_one_or_none()
    
    if not deadline:
        return {
            "has_deadline": False,
            "is_draft_locked": False,
            "is_final_closed": False,
            "minutes_until_draft_lock": None,
            "minutes_until_final_close": None
        }
    
    now = datetime.utcnow()
    
    # Check draft lock
    is_draft_locked = now >= deadline.draft_deadline
    is_final_closed = now >= deadline.final_deadline
    
    # Calculate remaining time
    minutes_until_draft_lock = max(0, (deadline.draft_deadline - now).total_seconds() // 60) if not is_draft_locked else 0
    minutes_until_final_close = max(0, (deadline.final_deadline - now).total_seconds() // 60) if not is_final_closed else 0
    
    # Check if in grace period
    in_grace_period = False
    if is_draft_locked and not is_final_closed and deadline.grace_period_minutes > 0:
        grace_end = deadline.draft_deadline + timedelta(minutes=deadline.grace_period_minutes)
        in_grace_period = now < grace_end
    
    return {
        "has_deadline": True,
        "deadline_id": deadline.id,
        "draft_deadline": deadline.draft_deadline.isoformat(),
        "final_deadline": deadline.final_deadline.isoformat(),
        "grace_period_minutes": deadline.grace_period_minutes,
        "is_draft_locked": is_draft_locked,
        "is_final_closed": is_final_closed,
        "in_grace_period": in_grace_period,
        "minutes_until_draft_lock": int(minutes_until_draft_lock),
        "minutes_until_final_close": int(minutes_until_final_close),
        "timezone": deadline.timezone
    }


async def auto_lock_submissions(competition_id: int, db: AsyncSession):
    """
    Auto-lock submissions that have passed their draft deadline.
    Called periodically or on submission endpoints.
    """
    now = datetime.utcnow()
    
    # Find all deadlines that have passed draft deadline
    deadlines_result = await db.execute(
        select(SubmissionDeadline).where(
            and_(
                SubmissionDeadline.competition_id == competition_id,
                SubmissionDeadline.draft_deadline <= now
            )
        )
    )
    deadlines = deadlines_result.scalars().all()
    
    for deadline in deadlines:
        # Find submissions of this type that are still draft
        submissions_result = await db.execute(
            select(Submission).where(
                and_(
                    Submission.competition_id == competition_id,
                    Submission.submission_type == deadline.submission_type,
                    Submission.status == SubmissionStatus.DRAFT,
                    Submission.locked_at.is_(None)  # Not already locked
                )
            )
        )
        submissions = submissions_result.scalars().all()
        
        for submission in submissions:
            # Check if in grace period
            grace_end = deadline.draft_deadline + timedelta(minutes=deadline.grace_period_minutes)
            now = datetime.utcnow()
            
            if now > grace_end:
                # Past grace period - lock it
                submission.status = SubmissionStatus.LOCKED
                submission.locked_at = now
                
                # Create log entry
                log = SubmissionLog(
                    submission_id=submission.id,
                    action="auto_lock",
                    performed_by=0,  # System
                    details=f"Auto-locked after draft deadline: {deadline.draft_deadline}"
                )
                db.add(log)
                
                logger.info(f"Submission {submission.id} auto-locked")
    
    await db.commit()


# ================= DEADLINE MANAGEMENT =================

@router.post("/deadlines", status_code=201)
async def create_deadline(
    competition_id: int = Query(...),
    data: DeadlineCreate = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create submission deadline for a competition.
    Admin+ only.
    """
    # Check permissions
    if current_user.role not in [UserRole.teacher, UserRole.teacher, UserRole.teacher]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    # Verify competition exists and user has access
    comp_result = await db.execute(
        select(Competition).where(Competition.id == competition_id)
    )
    competition = comp_result.scalar_one_or_none()
    
    if not competition:
        raise HTTPException(status_code=404, detail="Competition not found")
    
    if current_user.role != UserRole.teacher and current_user.institution_id != competition.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Check if deadline already exists for this type
    existing = await db.execute(
        select(SubmissionDeadline).where(
            and_(
                SubmissionDeadline.competition_id == competition_id,
                SubmissionDeadline.submission_type == data.submission_type
            )
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Deadline already exists for {data.submission_type.value}")
    
    # Create deadline
    deadline = SubmissionDeadline(
        institution_id=competition.institution_id,
        competition_id=competition_id,
        submission_type=data.submission_type,
        draft_deadline=data.draft_deadline,
        final_deadline=data.final_deadline,
        grace_period_minutes=data.grace_period_minutes,
        timezone=data.timezone,
        notes=data.notes,
        created_by=current_user.id
    )
    
    db.add(deadline)
    await db.commit()
    await db.refresh(deadline)
    
    logger.info(f"Deadline created for competition {competition_id}, type {data.submission_type.value}")
    
    return {
        "success": True,
        "deadline": deadline.to_dict()
    }


@router.get("/deadlines", status_code=200)
async def list_deadlines(
    competition_id: int = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List all submission deadlines for a competition.
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
    
    result = await db.execute(
        select(SubmissionDeadline).where(
            SubmissionDeadline.competition_id == competition_id
        )
    )
    deadlines = result.scalars().all()
    
    return {
        "success": True,
        "competition_id": competition_id,
        "deadlines": [d.to_dict() for d in deadlines]
    }


# ================= FILE UPLOAD =================

@router.post("/upload", status_code=201)
async def upload_submission(
    competition_id: int = Form(...),
    team_id: int = Form(...),
    submission_type: str = Form(...),
    file: UploadFile = File(...),
    student_notes: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload or replace submission file.
    Handles draft storage and final submission logic.
    """
    # Validate file
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    
    if not is_allowed_file(file.filename):
        raise HTTPException(status_code=400, detail=f"File type not allowed. Use: {', '.join(ALLOWED_EXTENSIONS)}")
    
    # Verify team membership
    team_result = await db.execute(
        select(Team).where(
            and_(
                Team.id == team_id,
                Team.competition_id == competition_id
            )
        )
    )
    team = team_result.scalar_one_or_none()
    
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    
    # Check if user is team member
    if current_user.role == UserRole.student and current_user.id not in [m.id for m in team.members]:
        raise HTTPException(status_code=403, detail="You are not a member of this team")
    
    # Check deadline status
    deadline_status = await check_deadline_status(competition_id, SubmissionType(submission_type), db)
    
    # If final deadline passed, reject upload
    if deadline_status["is_final_closed"]:
        raise HTTPException(
            status_code=403,
            detail="Submission window has closed. Contact admin for late submission."
        )
    
    # Check for existing submission
    existing_result = await db.execute(
        select(Submission).where(
            and_(
                Submission.competition_id == competition_id,
                Submission.team_id == team_id,
                Submission.submission_type == SubmissionType(submission_type)
            )
        )
    )
    existing = existing_result.scalar_one_or_none()
    
    # Read file content
    content = await file.read()
    
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail=f"File too large. Max size: {format_file_size(MAX_FILE_SIZE)}")
    
    # Generate unique filename
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_filename = f"{competition_id}_{team_id}_{submission_type}_{timestamp}_{file.filename}"
    file_path = UPLOAD_DIR / safe_filename
    
    # Save file
    with open(file_path, "wb") as f:
        f.write(content)
    
    # Calculate hash
    file_hash = calculate_file_hash(file_path)
    
    # Create or update submission
    if existing:
        # Update existing
        old_file_path = Path(existing.file_path)
        
        existing.file_name = file.filename
        existing.file_path = str(file_path)
        existing.file_size = len(content)
        existing.file_hash = file_hash
        existing.mime_type = file.content_type
        existing.last_edited_at = datetime.utcnow()
        existing.student_notes = student_notes or existing.student_notes
        
        # Delete old file
        if old_file_path.exists() and old_file_path != file_path:
            old_file_path.unlink()
        
        action = "replace"
    else:
        # Create new
        existing = Submission(
            institution_id=team.institution_id,
            competition_id=competition_id,
            team_id=team_id,
            submission_type=SubmissionType(submission_type),
            status=SubmissionStatus.DRAFT,
            file_name=file.filename,
            file_path=str(file_path),
            file_size=len(content),
            file_hash=file_hash,
            mime_type=file.content_type,
            draft_started_at=datetime.utcnow(),
            last_edited_at=datetime.utcnow(),
            student_notes=student_notes
        )
        db.add(existing)
        action = "upload"
    
    await db.commit()
    await db.refresh(existing)
    
    # Create log entry
    log = SubmissionLog(
        submission_id=existing.id,
        action=action,
        performed_by=current_user.id,
        details=f"File: {file.filename}, Size: {len(content)} bytes"
    )
    db.add(log)
    await db.commit()
    
    logger.info(f"Submission {action}: {existing.id} by user {current_user.id}")
    
    return {
        "success": True,
        "submission": existing.to_dict(),
        "deadline_status": deadline_status,
        "message": f"File uploaded successfully. Deadline: {deadline_status['minutes_until_draft_lock']} minutes until lock."
    }


# ================= SUBMISSION FINALIZATION =================

@router.post("/{submission_id}/submit", status_code=200)
async def finalize_submission(
    submission_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Mark submission as final.
    After this, file can only be changed if admin unlocks.
    """
    result = await db.execute(
        select(Submission).where(Submission.id == submission_id)
    )
    submission = result.scalar_one_or_none()
    
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    
    # Verify access
    if current_user.role == UserRole.student:
        team_result = await db.execute(
            select(Team).where(Team.id == submission.team_id)
        )
        team = team_result.scalar_one_or_none()
        if not team or current_user.id not in [m.id for m in team.members]:
            raise HTTPException(status_code=403, detail="Access denied")
    
    # Check deadline
    deadline_status = await check_deadline_status(
        submission.competition_id,
        submission.submission_type,
        db
    )
    
    if deadline_status["is_final_closed"]:
        raise HTTPException(status_code=403, detail="Submission window has closed")
    
    # Check if locked
    if submission.status == SubmissionStatus.LOCKED:
        raise HTTPException(status_code=403, detail="Submission is locked. Contact admin to unlock.")
    
    # Calculate if late
    is_late = deadline_status["is_draft_locked"]
    minutes_late = 0
    
    if is_late and deadline_status.get("draft_deadline"):
        draft_deadline = datetime.fromisoformat(deadline_status["draft_deadline"])
        now = datetime.utcnow()
        minutes_late = int((now - draft_deadline).total_seconds() // 60)
    
    # Update submission
    submission.status = SubmissionStatus.SUBMITTED
    submission.submitted_at = datetime.utcnow()
    submission.is_late = is_late
    submission.minutes_late = minutes_late if is_late else 0
    
    # Create log
    log = SubmissionLog(
        submission_id=submission.id,
        action="submit",
        performed_by=current_user.id,
        details=f"Final submission. Late: {is_late}, Minutes late: {minutes_late}"
    )
    db.add(log)
    
    await db.commit()
    
    return {
        "success": True,
        "submission": submission.to_dict(),
        "is_late": is_late,
        "message": "Submission finalized successfully." + (" Note: Submitted after draft deadline." if is_late else "")
    }


# ================= ADMIN UNLOCK =================

@router.post("/{submission_id}/unlock", status_code=200)
async def unlock_submission(
    submission_id: int,
    reason: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Admin/Judge unlocks a submission for late editing.
    Phase 5C: Judges can override lock for legitimate late submissions.
    """
    # Check permissions
    if current_user.role not in [UserRole.teacher, UserRole.teacher, UserRole.teacher]:
        raise HTTPException(status_code=403, detail="Only Admin/Faculty can unlock submissions")
    
    result = await db.execute(
        select(Submission).where(Submission.id == submission_id)
    )
    submission = result.scalar_one_or_none()
    
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    
    # Verify institution access
    if current_user.role != UserRole.teacher and current_user.institution_id != submission.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Unlock
    old_status = submission.status
    submission.status = SubmissionStatus.DRAFT
    submission.unlocked_by = current_user.id
    submission.unlocked_at = datetime.utcnow()
    submission.unlock_reason = reason
    
    # Create log
    log = SubmissionLog(
        submission_id=submission.id,
        action="unlock",
        performed_by=current_user.id,
        details=f"Unlocked from {old_status}. Reason: {reason}"
    )
    db.add(log)
    
    await db.commit()
    
    logger.info(f"Submission {submission_id} unlocked by {current_user.id}. Reason: {reason}")
    
    return {
        "success": True,
        "message": "Submission unlocked successfully",
        "submission": submission.to_dict()
    }


# ================= LIST SUBMISSIONS =================

@router.get("", status_code=200)
async def list_submissions(
    competition_id: int = Query(...),
    team_id: Optional[int] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List submissions for a competition.
    Students see their own team's submissions.
    Admins/Judges see all submissions.
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
    query = select(Submission).where(Submission.competition_id == competition_id)
    
    # Students only see their own team's submissions
    if current_user.role == UserRole.student:
        # Find teams this user is a member of
        team_result = await db.execute(
            select(Team).where(
                and_(
                    Team.competition_id == competition_id,
                    Team.members.any(id=current_user.id)
                )
            )
        )
        user_teams = team_result.scalars().all()
        user_team_ids = [t.id for t in user_teams]
        
        if not user_team_ids:
            return {"success": True, "submissions": []}
        
        query = query.where(Submission.team_id.in_(user_team_ids))
    elif team_id:
        query = query.where(Submission.team_id == team_id)
    
    result = await db.execute(query.order_by(desc(Submission.created_at)))
    submissions = result.scalars().all()
    
    # Auto-lock any submissions that need it
    await auto_lock_submissions(competition_id, db)
    
    return {
        "success": True,
        "submissions": [s.to_dict() for s in submissions]
    }
