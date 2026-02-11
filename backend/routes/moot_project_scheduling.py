"""
Moot Project Scheduling API Routes

Endpoints for scheduling oral rounds from moot projects.
Connects project workflow to courtroom experience.
"""
from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from pydantic import BaseModel
from typing import Optional

from backend.database import get_db


router = APIRouter(
    prefix="/api/moot-projects",
    tags=["moot-project-scheduling"]
)


class ScheduleRoundRequest(BaseModel):
    """Request body for scheduling an oral round."""
    scheduled_time: str  # ISO format datetime
    duration_minutes: int = 45


class RoundResponse(BaseModel):
    """Response model for created round."""
    round_id: int
    scheduled_start: str
    scheduled_end: str
    status: str
    petitioner_team: str
    respondent_team: str
    duration_minutes: int


def get_current_user():
    """
    Get current authenticated user from token.
    Placeholder - replace with actual auth dependency.
    """
    return {
        "id": 1,
        "role": "team_captain",
        "team_id": 1,
        "is_captain": True
    }


def require_team_captain_or_admin(user: dict):
    """Validate user is team captain or admin."""
    is_captain = user.get("is_captain", False)
    is_admin = user.get("role") in ["admin", "super_admin"]
    
    if not (is_captain or is_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only team captains or admins can schedule rounds"
        )


@router.post("/{project_id}/schedule-round", response_model=RoundResponse)
async def schedule_round(
    project_id: int,
    request: ScheduleRoundRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Schedule an oral round for a moot project.
    
    Args:
        project_id: ID of the moot project
        request: Schedule details (time, duration)
        db: Database session
        current_user: Authenticated team captain or admin
    
    Returns:
        Created round object with round_id
    """
    # Permission check
    require_team_captain_or_admin(current_user)
    
    # Parse scheduled time
    try:
        scheduled_start = datetime.fromisoformat(request.scheduled_time.replace('Z', '+00:00'))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid datetime format. Use ISO format (YYYY-MM-DDTHH:MM:SSZ)"
        )
    
    # Validate scheduled time is in the future
    if scheduled_start < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Scheduled time must be in the future"
        )
    
    # Calculate end time
    scheduled_end = scheduled_start + timedelta(minutes=request.duration_minutes)
    
    # TODO: Fetch project from database
    # For now, use mock data
    project = {
        "id": project_id,
        "petitioner_team_id": 1,
        "respondent_team_id": 2,
        "petitioner_team_name": "Team Puttaswamy",
        "respondent_team_name": "Team Maneka",
        "competition_id": 1
    }
    
    # TODO: Check if memorial has been submitted
    # For now, skip this check
    
    # Create oral round record
    # TODO: Use actual OralRound ORM model in production
    round_data = {
        "id": 42,  # Would be auto-generated
        "competition_id": project["competition_id"],
        "round_number": 1,
        "petitioner_team_id": project["petitioner_team_id"],
        "respondent_team_id": project["respondent_team_id"],
        "scheduled_start": scheduled_start,
        "scheduled_end": scheduled_end,
        "actual_start": None,
        "actual_end": None,
        "status": "scheduled",
        "transcript_id": None,
        "created_by": current_user["id"],
        "created_at": datetime.utcnow(),
        "moot_project_id": project_id
    }
    
    # TODO: Save to database
    # db.add(oral_round)
    # db.commit()
    # db.refresh(oral_round)
    
    return RoundResponse(
        round_id=round_data["id"],
        scheduled_start=scheduled_start.isoformat(),
        scheduled_end=scheduled_end.isoformat(),
        status="scheduled",
        petitioner_team=project["petitioner_team_name"],
        respondent_team=project["respondent_team_name"],
        duration_minutes=request.duration_minutes
    )


@router.get("/{project_id}/state")
async def get_project_state(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get current state of moot project workflow.
    
    Returns:
        Current progression state including:
        - has_legal_issues: bool
        - memorial_submitted: bool
        - memorial_status: string
        - round_scheduled: bool
        - round_id: int or null
        - scheduled_time: string or null
        - round_status: string
        - participants_joined: int
    """
    # TODO: Fetch actual project state from database
    # For now, return mock state based on project_id
    
    # Mock logic: project_id 1 = fully complete, others = varying states
    if project_id == 1:
        return {
            "project_id": project_id,
            "has_legal_issues": True,
            "memorial_submitted": True,
            "memorial_status": "completed",
            "round_scheduled": True,
            "round_id": 42,
            "scheduled_time": "2026-02-12T14:00:00Z",
            "round_status": "scheduled",
            "participants_joined": 3,
            "petitioner_team": "Team Puttaswamy",
            "respondent_team": "Team Maneka",
            "case_title": "Privacy v. State"
        }
    elif project_id == 2:
        return {
            "project_id": project_id,
            "has_legal_issues": True,
            "memorial_submitted": True,
            "memorial_status": "completed",
            "round_scheduled": False,
            "round_id": None,
            "scheduled_time": None,
            "round_status": "none",
            "participants_joined": 0,
            "petitioner_team": "Team Alpha",
            "respondent_team": "Team Beta",
            "case_title": "Constitutional Challenge"
        }
    elif project_id == 3:
        return {
            "project_id": project_id,
            "has_legal_issues": True,
            "memorial_submitted": False,
            "memorial_status": "none",
            "round_scheduled": False,
            "round_id": None,
            "scheduled_time": None,
            "round_status": "none",
            "participants_joined": 0,
            "petitioner_team": "Team Gamma",
            "respondent_team": "Team Delta",
            "case_title": "Civil Rights Case"
        }
    else:
        return {
            "project_id": project_id,
            "has_legal_issues": False,
            "memorial_submitted": False,
            "memorial_status": "none",
            "round_scheduled": False,
            "round_id": None,
            "scheduled_time": None,
            "round_status": "none",
            "participants_joined": 0,
            "petitioner_team": None,
            "respondent_team": None,
            "case_title": None
        }


@router.get("/{project_id}/memorial/status")
async def get_memorial_status(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get memorial submission status for a project.
    
    Returns:
        Memorial status and processing progress
    """
    # TODO: Fetch from database
    # For now, return mock status
    
    return {
        "project_id": project_id,
        "status": "completed",  # none, uploading, processing, completed, failed
        "progress": 100,
        "uploaded_at": "2026-02-11T10:00:00Z",
        "file_name": "memorial.pdf",
        "file_size_mb": 2.4,
        "page_count": 24,
        "analysis_score": 4.2
    }
