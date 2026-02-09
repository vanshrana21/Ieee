"""
backend/routes/faculty.py
Phase 7: Faculty Oversight & Academic Monitoring Routes

Faculty can monitor student progress without editing, scoring, or influencing submissions.
All faculty access is read-only + advisory notes only.
"""
import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, func

from backend.database import get_db
from backend.rbac import get_current_user
from backend.orm.user import User, UserRole
from backend.orm.moot_project import MootProject, MootIssue, IRACBlock
from backend.orm.oral_round import OralRound, OralResponse, RoundTranscript
from backend.orm.team import Team, TeamMember, TeamRole
from backend.orm.team_activity import TeamActivityLog, ActionType
from backend.orm.faculty_note import FacultyNote
from backend.services.progress_calculator import (
    calculate_project_progress,
    get_institution_wide_metrics
)
from backend.services.activity_logger import log_faculty_view, log_faculty_note_added

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/faculty", tags=["Faculty"])


# ================= PERMISSION DECORATOR =================

async def require_faculty(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 7: Enforce faculty-only access.
    Faculty must have UserRole.FACULTY.
    """
    if current_user.role not in [UserRole.FACULTY, UserRole.ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(
            status_code=403,
            detail="Access denied. Faculty, Admin, or Super Admin role required."
        )
    return current_user


async def check_institution_access(
    faculty_user: User,
    institution_id: int
):
    """
    Phase 7: Enforce institution isolation.
    Faculty can only access data within their own institution.
    """
    if faculty_user.role == UserRole.SUPER_ADMIN:
        return True  # Super admin can access all
    
    if faculty_user.institution_id != institution_id:
        raise HTTPException(
            status_code=403,
            detail="Access denied. Cannot access data from other institutions."
        )
    return True


# ================= SCHEMAS =================

class FacultyNoteCreate(BaseModel):
    """Schema for creating a faculty note"""
    note_text: str = Field(..., min_length=1, max_length=5000, description="Advisory note content")


class FacultyNoteUpdate(BaseModel):
    """Schema for updating a faculty note"""
    note_text: str = Field(..., min_length=1, max_length=5000, description="Updated note content")


# ================= FACULTY DASHBOARD =================

@router.get("/dashboard", status_code=200)
async def get_faculty_dashboard(
    current_user: User = Depends(require_faculty),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 7: Faculty dashboard - read-only overview of institution.
    
    Returns:
    - Institution-wide metrics
    - List of all teams with active projects
    - Recent activity highlights
    """
    # Enforce institution access
    await check_institution_access(current_user, current_user.institution_id)
    
    # Get institution-wide metrics
    metrics = await get_institution_wide_metrics(db, current_user.institution_id)
    
    # Get all teams in institution with active projects
    teams_result = await db.execute(
        select(Team).where(
            and_(
                Team.institution_id == current_user.institution_id,
                Team.is_active == True
            )
        )
    )
    teams = teams_result.scalars().all()
    
    # Get team summaries
    team_summaries = []
    for team in teams:
        # Count projects per team
        projects_result = await db.execute(
            select(func.count(MootProject.id)).where(
                and_(
                    MootProject.team_id == team.id,
                    MootProject.is_active == True
                )
            )
        )
        project_count = projects_result.scalar() or 0
        
        # Get team member count
        members_result = await db.execute(
            select(func.count(TeamMember.id)).where(
                and_(
                    TeamMember.team_id == team.id,
                    TeamMember.status == "active"
                )
            )
        )
        member_count = members_result.scalar() or 0
        
        team_summaries.append({
            "id": team.id,
            "name": team.name,
            "side": team.side.value if team.side else None,
            "status": team.status.value if team.status else None,
            "project_count": project_count,
            "member_count": member_count,
            "created_at": team.created_at.isoformat() if team.created_at else None,
        })
    
    # Get recent faculty activity (for this faculty member)
    recent_activity_result = await db.execute(
        select(TeamActivityLog).where(
            and_(
                TeamActivityLog.actor_id == current_user.id,
                TeamActivityLog.action_type.in_([
                    ActionType.FACULTY_VIEW,
                    ActionType.FACULTY_NOTE_ADDED
                ])
            )
        ).order_by(desc(TeamActivityLog.timestamp)).limit(10)
    )
    recent_activity = [log.to_dict() for log in recent_activity_result.scalars().all()]
    
    return {
        "success": True,
        "faculty": {
            "id": current_user.id,
            "full_name": current_user.full_name if hasattr(current_user, 'full_name') else None,
            "email": current_user.email if hasattr(current_user, 'email') else None,
            "institution_id": current_user.institution_id,
        },
        "metrics": metrics,
        "teams": team_summaries,
        "recent_activity": recent_activity,
    }


# ================= PROJECT MONITORING =================

@router.get("/projects", status_code=200)
async def list_all_projects(
    team_id: Optional[int] = Query(None, description="Filter by team ID"),
    status: Optional[str] = Query(None, description="Filter by status: draft, submitted, locked"),
    current_user: User = Depends(require_faculty),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 7: List all moot projects for faculty monitoring.
    Faculty can view all projects within their institution.
    """
    # Enforce institution access
    await check_institution_access(current_user, current_user.institution_id)
    
    # Build query
    query = select(MootProject).where(
        and_(
            MootProject.institution_id == current_user.institution_id,
            MootProject.is_active == True
        )
    )
    
    # Apply team filter if provided
    if team_id:
        query = query.where(MootProject.team_id == team_id)
    
    # Apply status filter
    if status == "locked":
        query = query.where(MootProject.is_locked == True)
    elif status == "draft":
        query = query.where(MootProject.is_locked == False)
    
    query = query.order_by(desc(MootProject.created_at))
    
    result = await db.execute(query)
    projects = result.scalars().all()
    
    # Calculate progress for each project
    project_summaries = []
    for project in projects:
        progress = await calculate_project_progress(db, project, current_user.id)
        project_summaries.append(progress.to_dict())
    
    return {
        "success": True,
        "projects": project_summaries,
        "count": len(project_summaries),
        "filters": {
            "team_id": team_id,
            "status": status,
        }
    }


@router.get("/projects/{project_id}", status_code=200)
async def view_project_details(
    project_id: int,
    current_user: User = Depends(require_faculty),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 7: View detailed project information (read-only).
    
    Faculty can see:
    - Project details
    - Progress metrics
    - Issues list
    - IRAC summary
    - Oral rounds summary
    - Activity log
    - Faculty notes
    """
    # Get project
    project_result = await db.execute(
        select(MootProject).where(
            and_(
                MootProject.id == project_id,
                MootProject.is_active == True
            )
        )
    )
    project = project_result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Enforce institution access
    await check_institution_access(current_user, project.institution_id)
    
    # Log faculty view
    await log_faculty_view(db, project, current_user)
    
    # Calculate progress metrics
    progress = await calculate_project_progress(db, project, current_user.id)
    
    # Get issues
    issues_result = await db.execute(
        select(MootIssue).where(MootIssue.project_id == project_id)
    )
    issues = [issue.to_dict() for issue in issues_result.scalars().all()]
    
    # Get IRAC summary (no content, just presence)
    irac_result = await db.execute(
        select(IRACBlock).where(
            and_(
                IRACBlock.project_id == project_id,
                IRACBlock.is_active == True
            )
        )
    )
    irac_blocks = irac_result.scalars().all()
    irac_summary = {}
    for block in irac_blocks:
        key = f"issue_{block.issue_id}"
        if key not in irac_summary:
            irac_summary[key] = []
        irac_summary[key].append(block.block_type)
    
    # Get oral rounds
    rounds_result = await db.execute(
        select(OralRound).where(OralRound.project_id == project_id)
    )
    rounds = rounds_result.scalars().all()
    oral_summary = []
    for round in rounds:
        round_dict = round.to_dict()
        
        # Count responses
        responses_result = await db.execute(
            select(func.count(OralResponse.id)).where(
                OralResponse.round_id == round.id
            )
        )
        round_dict["response_count"] = responses_result.scalar() or 0
        
        # Check for transcript
        transcript_result = await db.execute(
            select(RoundTranscript).where(
                RoundTranscript.round_id == round.id
            )
        )
        round_dict["has_transcript"] = transcript_result.scalar_one_or_none() is not None
        
        oral_summary.append(round_dict)
    
    # Get activity log (last 20 entries)
    activity_result = await db.execute(
        select(TeamActivityLog).where(
            TeamActivityLog.project_id == project_id
        ).order_by(desc(TeamActivityLog.timestamp)).limit(20)
    )
    activity_logs = [log.to_dict(include_actor=True) for log in activity_result.scalars().all()]
    
    # Get faculty notes for this project
    notes_result = await db.execute(
        select(FacultyNote).where(
            and_(
                FacultyNote.project_id == project_id,
                FacultyNote.faculty_id == current_user.id
            )
        ).order_by(desc(FacultyNote.created_at))
    )
    faculty_notes = [note.to_dict(include_faculty=True) for note in notes_result.scalars().all()]
    
    return {
        "success": True,
        "project": {
            "id": project.id,
            "title": project.title,
            "team_id": project.team_id,
            "institution_id": project.institution_id,
            "created_by": project.created_by,
            "created_at": project.created_at.isoformat() if project.created_at else None,
            "is_locked": project.is_locked,
            "deadline": project.deadline.isoformat() if hasattr(project, 'deadline') and project.deadline else None,
        },
        "progress": progress.to_dict(),
        "issues": issues,
        "irac_summary": irac_summary,
        "oral_rounds": oral_summary,
        "activity_logs": activity_logs,
        "faculty_notes": faculty_notes,
    }


# ================= FACULTY NOTES (ADVISORY ONLY) =================

@router.post("/projects/{project_id}/notes", status_code=201)
async def add_faculty_note(
    project_id: int,
    data: FacultyNoteCreate,
    current_user: User = Depends(require_faculty),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 7: Add a faculty advisory note to a project.
    
    Notes are:
    - Private to the faculty member
    - Advisory only (do not affect student work)
    - Clearly labeled as "Faculty Guidance (Non-Evaluative)"
    """
    # Get project
    project_result = await db.execute(
        select(MootProject).where(
            and_(
                MootProject.id == project_id,
                MootProject.is_active == True
            )
        )
    )
    project = project_result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Enforce institution access
    await check_institution_access(current_user, project.institution_id)
    
    # Create note
    note = FacultyNote(
        institution_id=project.institution_id,
        faculty_id=current_user.id,
        project_id=project_id,
        note_text=data.note_text,
        is_private=1
    )
    
    db.add(note)
    await db.commit()
    await db.refresh(note)
    
    # Log faculty note added
    await log_faculty_note_added(db, project, current_user, note.id)
    
    logger.info(f"Faculty note added: {note.id} by faculty {current_user.id} for project {project_id}")
    
    return {
        "success": True,
        "note": note.to_dict(include_faculty=True),
        "message": "Faculty note added successfully. This note is advisory and does not affect student work."
    }


@router.get("/projects/{project_id}/notes", status_code=200)
async def list_faculty_notes(
    project_id: int,
    current_user: User = Depends(require_faculty),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 7: List all faculty notes for a project.
    Faculty can only see their own notes.
    """
    # Verify project exists and is accessible
    project_result = await db.execute(
        select(MootProject).where(
            and_(
                MootProject.id == project_id,
                MootProject.is_active == True
            )
        )
    )
    project = project_result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Enforce institution access
    await check_institution_access(current_user, project.institution_id)
    
    # Get notes for this faculty member only
    notes_result = await db.execute(
        select(FacultyNote).where(
            and_(
                FacultyNote.project_id == project_id,
                FacultyNote.faculty_id == current_user.id
            )
        ).order_by(desc(FacultyNote.created_at))
    )
    notes = [note.to_dict(include_faculty=True) for note in notes_result.scalars().all()]
    
    return {
        "success": True,
        "notes": notes,
        "count": len(notes),
        "disclaimer": "These notes are Faculty Guidance (Non-Evaluative) and do not affect student submissions."
    }


@router.patch("/notes/{note_id}", status_code=200)
async def update_faculty_note(
    note_id: int,
    data: FacultyNoteUpdate,
    current_user: User = Depends(require_faculty),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 7: Update a faculty note.
    Faculty can only edit their own notes.
    """
    # Get note
    note_result = await db.execute(
        select(FacultyNote).where(FacultyNote.id == note_id)
    )
    note = note_result.scalar_one_or_none()
    
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    
    # Verify ownership
    if note.faculty_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only edit your own notes")
    
    # Enforce institution access
    await check_institution_access(current_user, note.institution_id)
    
    # Update note
    note.note_text = data.note_text
    note.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(note)
    
    return {
        "success": True,
        "note": note.to_dict(include_faculty=True),
        "message": "Faculty note updated successfully."
    }


@router.delete("/notes/{note_id}", status_code=200)
async def delete_faculty_note(
    note_id: int,
    current_user: User = Depends(require_faculty),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 7: Delete a faculty note.
    Faculty can only delete their own notes.
    """
    # Get note
    note_result = await db.execute(
        select(FacultyNote).where(FacultyNote.id == note_id)
    )
    note = note_result.scalar_one_or_none()
    
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    
    # Verify ownership
    if note.faculty_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only delete your own notes")
    
    # Enforce institution access
    await check_institution_access(current_user, note.institution_id)
    
    await db.delete(note)
    await db.commit()
    
    return {
        "success": True,
        "message": "Faculty note deleted successfully."
    }


# ================= IRAC VIEWING (READ-ONLY) =================

@router.get("/projects/{project_id}/irac", status_code=200)
async def view_project_irac(
    project_id: int,
    issue_id: Optional[int] = Query(None, description="Filter by issue ID"),
    current_user: User = Depends(require_faculty),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 7: View IRAC content for a project (read-only).
    Faculty can read but NEVER edit IRAC content.
    """
    # Verify project access
    project_result = await db.execute(
        select(MootProject).where(
            and_(
                MootProject.id == project_id,
                MootProject.is_active == True
            )
        )
    )
    project = project_result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Enforce institution access
    await check_institution_access(current_user, project.institution_id)
    
    # Log faculty view
    await log_faculty_view(db, project, current_user)
    
    # Build query
    query = select(IRACBlock).where(
        and_(
            IRACBlock.project_id == project_id,
            IRACBlock.is_active == True
        )
    )
    
    if issue_id:
        query = query.where(IRACBlock.issue_id == issue_id)
    
    query = query.order_by(IRACBlock.issue_id, IRACBlock.block_type)
    
    result = await db.execute(query)
    blocks = result.scalars().all()
    
    # Group by issue
    irac_data = {}
    for block in blocks:
        key = f"issue_{block.issue_id}"
        if key not in irac_data:
            irac_data[key] = {
                "issue_id": block.issue_id,
                "blocks": []
            }
        irac_data[key]["blocks"].append({
            "block_type": block.block_type,
            "content": block.content,  # Faculty can read content
            "version": block.version,
            "created_at": block.created_at.isoformat() if block.created_at else None,
        })
    
    return {
        "success": True,
        "project_id": project_id,
        "irac_data": list(irac_data.values()),
        "disclaimer": "This content is view-only. Faculty cannot edit student work.",
        "viewed_by": "faculty",
    }


# ================= ORAL ROUND TRANSCRIPTS (READ-ONLY) =================

@router.get("/projects/{project_id}/oral-rounds/{round_id}/transcript", status_code=200)
async def view_oral_transcript(
    project_id: int,
    round_id: int,
    current_user: User = Depends(require_faculty),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 7: View oral round transcript (read-only).
    Faculty can view transcripts for mentoring purposes.
    """
    # Verify project access
    project_result = await db.execute(
        select(MootProject).where(
            and_(
                MootProject.id == project_id,
                MootProject.is_active == True
            )
        )
    )
    project = project_result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Enforce institution access
    await check_institution_access(current_user, project.institution_id)
    
    # Get round
    round_result = await db.execute(
        select(OralRound).where(
            and_(
                OralRound.id == round_id,
                OralRound.project_id == project_id
            )
        )
    )
    round = round_result.scalar_one_or_none()
    
    if not round:
        raise HTTPException(status_code=404, detail="Oral round not found")
    
    # Get transcript
    transcript_result = await db.execute(
        select(RoundTranscript).where(
            RoundTranscript.round_id == round_id
        )
    )
    transcript = transcript_result.scalar_one_or_none()
    
    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found. May not be generated yet.")
    
    # Log faculty view
    await log_faculty_view(db, project, current_user)
    
    return {
        "success": True,
        "round_id": round_id,
        "round_stage": round.stage.value if round.stage else None,
        "transcript": transcript.to_dict(),
        "disclaimer": "This content is view-only. Faculty cannot edit or evaluate oral submissions.",
    }


# ================= ACTIVITY LOG VIEWING =================

@router.get("/projects/{project_id}/activity", status_code=200)
async def view_project_activity(
    project_id: int,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_faculty),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 7: View complete activity log for a project.
    Faculty can monitor all team actions for accountability.
    """
    # Verify project access
    project_result = await db.execute(
        select(MootProject).where(
            and_(
                MootProject.id == project_id,
                MootProject.is_active == True
            )
        )
    )
    project = project_result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Enforce institution access
    await check_institution_access(current_user, project.institution_id)
    
    # Get activity logs
    result = await db.execute(
        select(TeamActivityLog).where(
            TeamActivityLog.project_id == project_id
        ).order_by(desc(TeamActivityLog.timestamp))
        .offset(offset)
        .limit(limit)
    )
    logs = [log.to_dict(include_actor=True) for log in result.scalars().all()]
    
    # Get total count
    count_result = await db.execute(
        select(func.count(TeamActivityLog.id)).where(
            TeamActivityLog.project_id == project_id
        )
    )
    total_count = count_result.scalar() or 0
    
    return {
        "success": True,
        "project_id": project_id,
        "activity_logs": logs,
        "pagination": {
            "limit": limit,
            "offset": offset,
            "total": total_count,
            "has_more": (offset + limit) < total_count
        }
    }
