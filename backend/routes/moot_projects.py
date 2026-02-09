"""
backend/routes/moot_projects.py
Phase 5C: Moot project persistence API routes
Replaces localStorage with database-backed storage
"""
import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, func
from sqlalchemy.orm import selectinload

from backend.database import get_db
from backend.orm.moot_project import MootProject, MootIssue, IRACBlock, ProjectStatus, IssueStatus
from backend.orm.competition import Competition, CompetitionStatus
from backend.orm.user import User, UserRole
from backend.orm.team import TeamRole
from backend.rbac import get_current_user
from backend.errors import ErrorCode

# Phase 6B: Permission guards
from backend.services.permission_guards import (
    require_irac_write_permission,
    require_issue_crud_permission,
    require_read_permission,
    check_project_lock
)

# Phase 6C: Activity logging
from backend.services.activity_logger import (
    log_project_created,
    log_project_submitted,
    log_project_locked,
    log_project_unlocked,
    log_irac_saved,
    log_issue_created,
    log_issue_updated,
    log_issue_deleted
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/moot-projects", tags=["Moot Projects"])


# ================= PHASE 5D: LOCK GUARD =================

async def check_project_edit_allowed(
    project: MootProject,
    db,
    current_user: User
) -> bool:
    """
    Phase 5D: Check if project editing is allowed.
    Returns True if editing is permitted, False otherwise.
    """
    # Admins can always edit (for override purposes)
    if current_user.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
        return True
    
    # If project is explicitly locked or submitted
    if project.is_locked or project.is_submitted:
        return False
    
    # If project is in locked status
    if project.status in [ProjectStatus.LOCKED, ProjectStatus.SUBMITTED, ProjectStatus.EVALUATION]:
        return False
    
    # Check competition status if project is linked to competition
    if project.competition_id:
        comp_result = await db.execute(
            select(Competition).where(Competition.id == project.competition_id)
        )
        competition = comp_result.scalar_one_or_none()
        if competition and competition.status in [
            CompetitionStatus.SUBMISSION_CLOSED,
            CompetitionStatus.EVALUATION,
            CompetitionStatus.CLOSED
        ]:
            return False
    
    return True


# ================= SCHEMAS =================

class ProjectCreate(BaseModel):
    """Schema for creating a moot project"""
    title: str = Field(..., min_length=1, max_length=255)
    proposition: Optional[str] = None
    side: str = Field(default="petitioner", pattern="^(petitioner|respondent)$")
    court: Optional[str] = None
    domain: Optional[str] = None
    competition_id: Optional[int] = None
    team_id: Optional[int] = None


class ProjectUpdate(BaseModel):
    """Schema for updating a moot project"""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    proposition: Optional[str] = None
    side: Optional[str] = Field(None, pattern="^(petitioner|respondent)$")
    court: Optional[str] = None
    domain: Optional[str] = None
    status: Optional[str] = Field(None, pattern="^(draft|active|completed|archived)$")


class IssueCreate(BaseModel):
    """Schema for creating an issue"""
    title: Optional[str] = None
    description: Optional[str] = None
    issue_order: int = 0


class IssueUpdate(BaseModel):
    """Schema for updating an issue"""
    title: Optional[str] = None
    description: Optional[str] = None
    issue_order: Optional[int] = None
    status: Optional[str] = Field(None, pattern="^(not_started|partial|complete)$")


class IRACSave(BaseModel):
    """Schema for saving IRAC content (creates new version)"""
    issue_id: int
    block_type: str = Field(..., pattern="^(issue|rule|application|conclusion)$")
    content: str


# ================= PROJECT CRUD =================

@router.post("", status_code=201)
async def create_project(
    data: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 5C: Create a new moot project.
    Replaces localStorage project creation.
    """
    project = MootProject(
        institution_id=current_user.institution_id,
        competition_id=data.competition_id,
        team_id=data.team_id,
        title=data.title,
        proposition=data.proposition,
        side=data.side,
        court=data.court,
        domain=data.domain,
        status=ProjectStatus.DRAFT,
        created_by=current_user.id
    )
    
    db.add(project)
    await db.commit()
    await db.refresh(project)
    
    logger.info(f"Moot project created: {project.id} by user {current_user.id}")
    
    return {
        "success": True,
        "project": project.to_dict()
    }


@router.get("", status_code=200)
async def list_projects(
    status: Optional[str] = Query(None, description="Filter by status"),
    competition_id: Optional[int] = Query(None),
    include_issues: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 5C: List moot projects for the user's institution.
    Students see their own projects, admins see all in institution.
    """
    query = select(MootProject).where(
        and_(
            MootProject.institution_id == current_user.institution_id,
            MootProject.is_active == True,
            MootProject.deleted_at.is_(None)
        )
    )
    
    # Students only see their own projects
    if current_user.role == UserRole.STUDENT:
        query = query.where(MootProject.created_by == current_user.id)
    
    if status:
        query = query.where(MootProject.status == status)
    
    if competition_id:
        query = query.where(MootProject.competition_id == competition_id)
    
    query = query.order_by(desc(MootProject.updated_at))
    
    result = await db.execute(query)
    projects = result.scalars().all()
    
    return {
        "success": True,
        "projects": [p.to_dict(include_issues=include_issues) for p in projects],
        "count": len(projects)
    }


@router.get("/{project_id}", status_code=200)
async def get_project(
    project_id: int,
    include_issues: bool = Query(True),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 5C: Get a specific moot project with all details.
    """
    result = await db.execute(
        select(MootProject).where(
            and_(
                MootProject.id == project_id,
                MootProject.is_active == True,
                MootProject.deleted_at.is_(None)
            )
        )
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Check institution access
    if current_user.role != UserRole.SUPER_ADMIN and current_user.institution_id != project.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Students can only access their own projects
    if current_user.role == UserRole.STUDENT and project.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return {
        "success": True,
        "project": project.to_dict(include_issues=include_issues)
    }


@router.patch("/{project_id}", status_code=200)
async def update_project(
    project_id: int,
    data: ProjectUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 5C: Update moot project metadata.
    """
    result = await db.execute(
        select(MootProject).where(
            and_(
                MootProject.id == project_id,
                MootProject.is_active == True
            )
        )
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Check permissions
    if current_user.role != UserRole.SUPER_ADMIN and current_user.institution_id != project.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if current_user.role == UserRole.STUDENT and project.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Phase 6B: Check team permission (CAPTAIN only for project metadata updates)
    await require_issue_crud_permission(current_user, project, db)
    
    # Update fields
    if data.title is not None:
        project.title = data.title
    if data.proposition is not None:
        project.proposition = data.proposition
    if data.side is not None:
        project.side = data.side
    if data.court is not None:
        project.court = data.court
    if data.domain is not None:
        project.domain = data.domain
    if data.status is not None:
        project.status = ProjectStatus(data.status)
    
    project.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(project)
    
    return {
        "success": True,
        "project": project.to_dict()
    }


@router.delete("/{project_id}", status_code=200)
async def delete_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 5C: Soft delete a moot project.
    """
    result = await db.execute(
        select(MootProject).where(
            and_(
                MootProject.id == project_id,
                MootProject.is_active == True
            )
        )
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Check permissions
    if current_user.role != UserRole.SUPER_ADMIN and current_user.institution_id != project.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if current_user.role == UserRole.STUDENT and project.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Phase 6B: Check team permission (CAPTAIN only for project delete)
    await require_issue_crud_permission(current_user, project, db)
    
    # Soft delete
    project.is_active = False
    project.deleted_at = datetime.utcnow()
    
    await db.commit()
    
    logger.info(f"Moot project soft deleted: {project_id}")
    
    return {
        "success": True,
        "message": "Project deleted successfully"
    }


# ================= ISSUE MANAGEMENT =================

@router.post("/{project_id}/issues", status_code=201)
async def create_issue(
    project_id: int,
    data: IssueCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 5C: Add an issue to a moot project.
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
    
    if current_user.role != UserRole.SUPER_ADMIN and current_user.institution_id != project.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if current_user.role == UserRole.STUDENT and project.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Phase 6B: Check team permission for issue CRUD (CAPTAIN, SPEAKER)
    await require_issue_crud_permission(current_user, project, db)
    
    # Get next order if not specified
    if data.issue_order is None:
        max_order_result = await db.execute(
            select(func.max(MootIssue.issue_order)).where(MootIssue.project_id == project_id)
        )
        max_order = max_order_result.scalar() or 0
        issue_order = max_order + 1
    else:
        issue_order = data.issue_order
    
    issue = MootIssue(
        institution_id=project.institution_id,
        project_id=project_id,
        issue_order=issue_order,
        title=data.title,
        description=data.description,
        status=IssueStatus.NOT_STARTED
    )
    
    db.add(issue)
    await db.commit()
    await db.refresh(issue)
    
    # Phase 6C: Log issue creation
    await log_issue_created(
        db=db,
        project=project,
        actor=current_user,
        issue=issue
    )
    
    return {
        "success": True,
        "issue": issue.to_dict()
    }


@router.get("/{project_id}/issues", status_code=200)
async def list_issues(
    project_id: int,
    include_irac: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 5C: List all issues for a project.
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
    
    if current_user.role != UserRole.SUPER_ADMIN and current_user.institution_id != project.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if current_user.role == UserRole.STUDENT and project.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    result = await db.execute(
        select(MootIssue).where(MootIssue.project_id == project_id).order_by(MootIssue.issue_order)
    )
    issues = result.scalars().all()
    
    return {
        "success": True,
        "issues": [i.to_dict(include_irac=include_irac) for i in issues],
        "count": len(issues)
    }


@router.patch("/{project_id}/issues/{issue_id}", status_code=200)
async def update_issue(
    project_id: int,
    issue_id: int,
    data: IssueUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 5C: Update an issue.
    """
    result = await db.execute(
        select(MootIssue).where(
            and_(
                MootIssue.id == issue_id,
                MootIssue.project_id == project_id
            )
        )
    )
    issue = result.scalar_one_or_none()
    
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    
    # Verify project access
    project_result = await db.execute(
        select(MootProject).where(MootProject.id == project_id)
    )
    project = project_result.scalar_one_or_none()
    
    if current_user.role != UserRole.SUPER_ADMIN and current_user.institution_id != project.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if current_user.role == UserRole.STUDENT and project.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Phase 6B: Check team permission for issue CRUD (CAPTAIN, SPEAKER)
    await require_issue_crud_permission(current_user, project, db)
    
    # Update fields
    if data.title is not None:
        issue.title = data.title
    if data.description is not None:
        issue.description = data.description
    if data.issue_order is not None:
        issue.issue_order = data.issue_order
    if data.status is not None:
        issue.status = IssueStatus(data.status)
    
    issue.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(issue)
    
    # Phase 6C: Log issue update
    await log_issue_updated(
        db=db,
        project=project,
        actor=current_user,
        issue=issue
    )
    
    return {
        "success": True,
        "issue": issue.to_dict()
    }


@router.delete("/{project_id}/issues/{issue_id}", status_code=200)
async def delete_issue(
    project_id: int,
    issue_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 5C: Delete an issue and all its IRAC blocks.
    """
    result = await db.execute(
        select(MootIssue).where(
            and_(
                MootIssue.id == issue_id,
                MootIssue.project_id == project_id
            )
        )
    )
    issue = result.scalar_one_or_none()
    
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    
    # Verify project access
    project_result = await db.execute(
        select(MootProject).where(MootProject.id == project_id)
    )
    project = project_result.scalar_one_or_none()
    
    if current_user.role != UserRole.SUPER_ADMIN and current_user.institution_id != project.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if current_user.role == UserRole.STUDENT and project.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Phase 6B: Check team permission for issue CRUD (CAPTAIN, SPEAKER)
    await require_issue_crud_permission(current_user, project, db)
    
    # Get issue name for logging before deletion
    issue_name = issue.title or f"Issue #{issue.issue_order}"
    
    await db.delete(issue)
    await db.commit()
    
    # Phase 6C: Log issue deletion
    await log_issue_deleted(
        db=db,
        project=project,
        actor=current_user,
        issue_id=issue_id,
        issue_name=issue_name
    )
    
    return {
        "success": True,
        "message": "Issue deleted successfully"
    }


# ================= IRAC VERSIONING =================

@router.post("/{project_id}/irac", status_code=201)
async def save_irac(
    project_id: int,
    data: IRACSave,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 5C: Save IRAC content (creates new version - no overwrites).
    Each save creates a new version for audit history.
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
    
    if current_user.role != UserRole.SUPER_ADMIN and current_user.institution_id != project.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if current_user.role == UserRole.STUDENT and project.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Phase 6B: Check team permission for IRAC write (CAPTAIN, SPEAKER, RESEARCHER)
    await require_irac_write_permission(current_user, project, db)
    
    # Verify issue belongs to project
    issue_result = await db.execute(
        select(MootIssue).where(
            and_(
                MootIssue.id == data.issue_id,
                MootIssue.project_id == project_id
            )
        )
    )
    issue = issue_result.scalar_one_or_none()
    
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found in this project")
    
    # Get next version number
    max_version_result = await db.execute(
        select(func.max(IRACBlock.version)).where(
            and_(
                IRACBlock.issue_id == data.issue_id,
                IRACBlock.block_type == data.block_type
            )
        )
    )
    max_version = max_version_result.scalar() or 0
    
    # Mark previous versions as inactive
    await db.execute(
        IRACBlock.__table__.update().where(
            and_(
                IRACBlock.issue_id == data.issue_id,
                IRACBlock.block_type == data.block_type,
                IRACBlock.is_active == True
            )
        ).values(is_active=False)
    )
    
    # Create new version
    block = IRACBlock(
        institution_id=project.institution_id,
        project_id=project_id,
        issue_id=data.issue_id,
        block_type=data.block_type,
        content=data.content,
        version=max_version + 1,
        is_active=True,
        created_by=current_user.id
    )
    
    db.add(block)
    await db.commit()
    await db.refresh(block)
    
    # Update issue status if this is the first content
    if issue.status == IssueStatus.NOT_STARTED:
        issue.status = IssueStatus.PARTIAL
        await db.commit()
    
    # Phase 6C: Log IRAC save (high-level, no content)
    await log_irac_saved(
        db=db,
        project=project,
        actor=current_user,
        issue_id=data.issue_id,
        block_type=data.block_type
    )
    
    return {
        "success": True,
        "irac_block": block.to_dict(),
        "message": f"IRAC {data.block_type} saved (version {block.version})"
    }


@router.get("/{project_id}/irac/history", status_code=200)
async def get_irac_history(
    project_id: int,
    issue_id: Optional[int] = Query(None),
    block_type: Optional[str] = Query(None, pattern="^(issue|rule|application|conclusion)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 5C: Get IRAC version history for audit purposes.
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
    
    if current_user.role == UserRole.STUDENT and project.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    query = select(IRACBlock).where(IRACBlock.project_id == project_id)
    
    if issue_id:
        query = query.where(IRACBlock.issue_id == issue_id)
    if block_type:
        query = query.where(IRACBlock.block_type == block_type)
    
    query = query.order_by(desc(IRACBlock.created_at))
    
    result = await db.execute(query)
    blocks = result.scalars().all()
    
    return {
        "success": True,
        "history": [b.to_dict() for b in blocks],
        "count": len(blocks)
    }
