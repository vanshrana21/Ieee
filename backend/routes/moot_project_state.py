"""
Moot Project State API Route

Returns current workflow state for project-to-courtroom progression.
"""
from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session
from typing import Optional

from backend.database import get_db


router = APIRouter(
    prefix="/api/moot-projects",
    tags=["moot-project-state"]
)


def get_current_user():
    """
    Get current authenticated user from token.
    Placeholder - replace with actual auth dependency.
    """
    return {
        "id": 1,
        "role": "team_captain",
        "team_id": 1
    }


@router.get("/{project_id}/state")
async def get_project_state(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get current state of moot project workflow.
    
    Returns progression state for:
    - Legal issues added
    - Memorial submission status
    - Round scheduling status
    - Courtroom readiness
    
    Response:
    {
        "project_id": 1,
        "has_legal_issues": true,
        "memorial_submitted": true,
        "memorial_status": "completed",
        "round_scheduled": true,
        "round_id": 42,
        "scheduled_time": "2026-02-12T14:00:00Z",
        "round_status": "scheduled",
        "participants_joined": 3,
        "petitioner_team": "Team Puttaswamy",
        "respondent_team": "Team Maneka",
        "case_title": "Privacy v. State"
    }
    """
    # TODO: Fetch actual project state from database
    # For now, return mock state based on project_id
    
    mock_states = {
        1: {
            "project_id": project_id,
            "has_legal_issues": True,
            "memorial_submitted": True,
            "memorial_status": "completed",
            "memorial_score": 4.2,
            "round_scheduled": True,
            "round_id": 42,
            "scheduled_time": "2026-02-12T14:00:00Z",
            "duration_minutes": 45,
            "round_status": "scheduled",
            "participants_joined": 3,
            "petitioner_team": "Team Puttaswamy",
            "respondent_team": "Team Maneka",
            "case_title": "Privacy v. State",
            "competition_id": 1
        },
        2: {
            "project_id": project_id,
            "has_legal_issues": True,
            "memorial_submitted": True,
            "memorial_status": "completed",
            "memorial_score": 3.8,
            "round_scheduled": False,
            "round_id": None,
            "scheduled_time": None,
            "duration_minutes": None,
            "round_status": "none",
            "participants_joined": 0,
            "petitioner_team": "Team Alpha",
            "respondent_team": "Team Beta",
            "case_title": "Constitutional Challenge",
            "competition_id": 1
        },
        3: {
            "project_id": project_id,
            "has_legal_issues": True,
            "memorial_submitted": False,
            "memorial_status": "none",
            "memorial_score": None,
            "round_scheduled": False,
            "round_id": None,
            "scheduled_time": None,
            "duration_minutes": None,
            "round_status": "none",
            "participants_joined": 0,
            "petitioner_team": "Team Gamma",
            "respondent_team": "Team Delta",
            "case_title": "Civil Rights Case",
            "competition_id": 1
        }
    }
    
    # Return mock state or default state
    state = mock_states.get(project_id, {
        "project_id": project_id,
        "has_legal_issues": False,
        "memorial_submitted": False,
        "memorial_status": "none",
        "memorial_score": None,
        "round_scheduled": False,
        "round_id": None,
        "scheduled_time": None,
        "duration_minutes": None,
        "round_status": "none",
        "participants_joined": 0,
        "petitioner_team": None,
        "respondent_team": None,
        "case_title": None,
        "competition_id": None
    })
    
    return state


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
        "status": "completed",
        "progress": 100,
        "uploaded_at": "2026-02-11T10:00:00Z",
        "file_name": "memorial.pdf",
        "file_size_mb": 2.4,
        "page_count": 24,
        "analysis_score": 4.2,
        "analysis_completed_at": "2026-02-11T10:01:30Z"
    }
