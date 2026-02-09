"""
backend/services/progress_calculator.py
Phase 7: Progress Metrics Calculator

Computes objective, measurable progress signals for faculty oversight.
NO subjective scoring. NO AI evaluation. NO grades.
"""
from typing import Dict, List, Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from datetime import datetime

from backend.orm.moot_project import MootProject
from backend.orm.moot_project import MootIssue, IssueStatus
from backend.orm.moot_project import IRACBlock
from backend.orm.oral_round import OralRound, OralResponse, RoundTranscript
from backend.orm.team_activity import TeamActivityLog


class ProjectProgressMetrics:
    """Container for computed project progress metrics"""
    
    def __init__(
        self,
        project_id: int,
        project_title: str,
        team_id: int,
        submission_status: str,
        last_activity: Optional[datetime] = None,
        irac_completeness: float = 0.0,
        issues_count: int = 0,
        issues_completed: int = 0,
        oral_rounds_count: int = 0,
        oral_responses_count: int = 0,
        has_transcript: bool = False,
        faculty_notes_count: int = 0
    ):
        self.project_id = project_id
        self.project_title = project_title
        self.team_id = team_id
        self.submission_status = submission_status
        self.last_activity = last_activity
        self.irac_completeness = irac_completeness  # 0-100 percentage
        self.issues_count = issues_count
        self.issues_completed = issues_completed
        self.oral_rounds_count = oral_rounds_count
        self.oral_responses_count = oral_responses_count
        self.has_transcript = has_transcript
        self.faculty_notes_count = faculty_notes_count
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "project_title": self.project_title,
            "team_id": self.team_id,
            "submission_status": self.submission_status,
            "last_activity": self.last_activity.isoformat() if self.last_activity else None,
            "irac_completeness": round(self.irac_completeness, 1),
            "issues_count": self.issues_count,
            "issues_completed": self.issues_completed,
            "issues_completion_rate": round(
                (self.issues_completed / self.issues_count * 100) if self.issues_count > 0 else 0, 1
            ),
            "oral_rounds_count": self.oral_rounds_count,
            "oral_responses_count": self.oral_responses_count,
            "has_transcript": self.has_transcript,
            "faculty_notes_count": self.faculty_notes_count,
        }


async def calculate_project_progress(
    db: AsyncSession,
    project: MootProject,
    faculty_id: Optional[int] = None
) -> ProjectProgressMetrics:
    """
    Phase 7: Calculate objective progress metrics for a project.
    
    All metrics are computed from existing data:
    - IRAC completeness: % of required blocks present
    - Issues: count and completion status
    - Oral rounds: number and responses
    - Activity: timestamp of last action
    - Faculty notes: count of notes by this faculty
    
    NO subjective scoring. NO AI evaluation.
    """
    
    # Get submission status
    submission_status = "draft"
    if project.is_locked:
        submission_status = "locked"
    elif hasattr(project, 'submitted_at') and project.submitted_at:
        submission_status = "submitted"
    
    # Count issues
    issues_result = await db.execute(
        select(MootIssue).where(MootIssue.project_id == project.id)
    )
    issues = issues_result.scalars().all()
    issues_count = len(issues)
    issues_completed = sum(1 for i in issues if i.status == IssueStatus.COMPLETED)
    
    # Calculate IRAC completeness
    irac_completeness = await calculate_irac_completeness(db, project.id, issues_count)
    
    # Count oral rounds
    rounds_result = await db.execute(
        select(OralRound).where(OralRound.project_id == project.id)
    )
    rounds = rounds_result.scalars().all()
    oral_rounds_count = len(rounds)
    
    # Count oral responses
    if rounds:
        round_ids = [r.id for r in rounds]
        responses_result = await db.execute(
            select(OralResponse).where(OralResponse.round_id.in_(round_ids))
        )
        oral_responses_count = len(responses_result.scalars().all())
    else:
        oral_responses_count = 0
    
    # Check for transcript
    if rounds:
        round_ids = [r.id for r in rounds]
        transcript_result = await db.execute(
            select(RoundTranscript).where(RoundTranscript.round_id.in_(round_ids))
        )
        has_transcript = transcript_result.scalar_one_or_none() is not None
    else:
        has_transcript = False
    
    # Get last activity timestamp
    last_activity = await get_last_activity_timestamp(db, project.id)
    
    # Count faculty notes
    faculty_notes_count = 0
    if faculty_id:
        from backend.orm.faculty_note import FacultyNote
        notes_result = await db.execute(
            select(func.count(FacultyNote.id)).where(
                and_(
                    FacultyNote.project_id == project.id,
                    FacultyNote.faculty_id == faculty_id
                )
            )
        )
        faculty_notes_count = notes_result.scalar() or 0
    
    return ProjectProgressMetrics(
        project_id=project.id,
        project_title=project.title,
        team_id=project.team_id,
        submission_status=submission_status,
        last_activity=last_activity,
        irac_completeness=irac_completeness,
        issues_count=issues_count,
        issues_completed=issues_completed,
        oral_rounds_count=oral_rounds_count,
        oral_responses_count=oral_responses_count,
        has_transcript=has_transcript,
        faculty_notes_count=faculty_notes_count
    )


async def calculate_irac_completeness(
    db: AsyncSession,
    project_id: int,
    issues_count: int
) -> float:
    """
    Calculate IRAC completeness percentage.
    
    For each issue, check if Issue, Rule, Application, Conclusion blocks exist.
    Completeness = (filled blocks / total required blocks) * 100
    
    Total required blocks = issues_count * 4 (I/R/A/C)
    """
    if issues_count == 0:
        return 0.0
    
    # Get all IRAC blocks for this project
    blocks_result = await db.execute(
        select(IRACBlock).where(
            and_(
                IRACBlock.project_id == project_id,
                IRACBlock.is_active == True
            )
        )
    )
    blocks = blocks_result.scalars().all()
    
    # Count unique block types per issue
    issue_blocks: Dict[int, set] = {}
    for block in blocks:
        if block.issue_id not in issue_blocks:
            issue_blocks[block.issue_id] = set()
        issue_blocks[block.issue_id].add(block.block_type)
    
    # Calculate completeness
    total_required = issues_count * 4  # I/R/A/C for each issue
    total_filled = sum(len(blocks) for blocks in issue_blocks.values())
    
    # Cap at total_required (in case of duplicate blocks)
    total_filled = min(total_filled, total_required)
    
    return (total_filled / total_required * 100) if total_required > 0 else 0.0


async def get_last_activity_timestamp(
    db: AsyncSession,
    project_id: int
) -> Optional[datetime]:
    """
    Get the timestamp of the most recent activity for a project.
    Searches TeamActivityLog for project-related actions.
    """
    result = await db.execute(
        select(TeamActivityLog).where(
            TeamActivityLog.project_id == project_id
        ).order_by(TeamActivityLog.timestamp.desc()).limit(1)
    )
    last_log = result.scalar_one_or_none()
    
    return last_log.timestamp if last_log else None


async def get_institution_wide_metrics(
    db: AsyncSession,
    institution_id: int
) -> Dict[str, Any]:
    """
    Phase 7: Get high-level metrics for faculty dashboard.
    
    Returns:
    - Total projects
    - Projects by status (draft/submitted/locked)
    - Teams with active projects
    - Average IRAC completeness
    - Average issues per project
    """
    # Get all projects for institution
    projects_result = await db.execute(
        select(MootProject).where(
            and_(
                MootProject.institution_id == institution_id,
                MootProject.is_active == True
            )
        )
    )
    projects = projects_result.scalars().all()
    
    total_projects = len(projects)
    
    # Status breakdown
    draft_count = sum(1 for p in projects if not p.is_locked)
    locked_count = sum(1 for p in projects if p.is_locked)
    
    # Unique teams
    team_ids = set(p.team_id for p in projects)
    teams_count = len(team_ids)
    
    # Calculate averages
    if total_projects > 0:
        # Get all issues for these projects
        project_ids = [p.id for p in projects]
        
        issues_result = await db.execute(
            select(func.count(MootIssue.id)).where(
                MootIssue.project_id.in_(project_ids)
            )
        )
        total_issues = issues_result.scalar() or 0
        avg_issues = total_issues / total_projects
        
        # Average IRAC completeness
        total_completeness = 0.0
        for project in projects:
            issues_result = await db.execute(
                select(func.count(MootIssue.id)).where(
                    MootIssue.project_id == project.id
                )
            )
            project_issues = issues_result.scalar() or 0
            completeness = await calculate_irac_completeness(db, project.id, project_issues)
            total_completeness += completeness
        
        avg_irac_completeness = total_completeness / total_projects
    else:
        avg_issues = 0.0
        avg_irac_completeness = 0.0
    
    return {
        "total_projects": total_projects,
        "draft_projects": draft_count,
        "locked_projects": locked_count,
        "active_teams": teams_count,
        "average_issues_per_project": round(avg_issues, 1),
        "average_irac_completeness": round(avg_irac_completeness, 1),
    }
