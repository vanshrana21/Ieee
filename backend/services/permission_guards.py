"""
backend/services/permission_guards.py
Phase 6B: Permission-Aware Editing & Lock Enforcement
Enforces team role-based permissions with Phase 5D lock compliance.
"""
from datetime import datetime
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from backend.orm.moot_project import MootProject, ProjectStatus
from backend.orm.competition import Competition, CompetitionStatus
from backend.orm.team import TeamMember, TeamRole
from backend.orm.user import User, UserRole


# Phase 6B: Permission Matrix
# Role        | IRAC Write | Issue CRUD | Oral Responses | Read
# CAPTAIN     | ✅         | ✅         | ✅             | ✅
# SPEAKER     | ✅         | ✅         | ✅             | ✅
# RESEARCHER  | ✅         | ❌         | ❌             | ✅
# OBSERVER    | ❌         | ❌         | ❌             | ✅


class PermissionDeniedLog:
    """
    Phase 6B: In-memory log entry for permission denials.
    Note: For production, this should be persisted to database.
    """
    def __init__(
        self,
        user_id: int,
        team_id: int,
        project_id: int,
        attempted_action: str,
        role: str,
        reason: str
    ):
        self.user_id = user_id
        self.team_id = team_id
        self.project_id = project_id
        self.attempted_action = attempted_action
        self.role = role
        self.reason = reason
        self.timestamp = datetime.utcnow()
    
    def to_dict(self):
        return {
            "user_id": self.user_id,
            "team_id": self.team_id,
            "project_id": self.project_id,
            "attempted_action": self.attempted_action,
            "role": self.role,
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat()
        }


# In-memory store for denied actions ( Phase 6B )
_denied_logs: List[PermissionDeniedLog] = []


def log_permission_denial(
    user_id: int,
    team_id: int,
    project_id: int,
    attempted_action: str,
    role: str,
    reason: str
):
    """Log a permission denial for audit purposes."""
    log = PermissionDeniedLog(
        user_id=user_id,
        team_id=team_id,
        project_id=project_id,
        attempted_action=attempted_action,
        role=role,
        reason=reason
    )
    _denied_logs.append(log)
    return log


def get_denied_logs(
    user_id: Optional[int] = None,
    project_id: Optional[int] = None,
    limit: int = 100
) -> List[PermissionDeniedLog]:
    """Retrieve permission denial logs (for admin/debug purposes)."""
    logs = _denied_logs
    if user_id:
        logs = [l for l in logs if l.user_id == user_id]
    if project_id:
        logs = [l for l in logs if l.project_id == project_id]
    return logs[-limit:]


async def check_project_lock(
    project: MootProject,
    db: AsyncSession
) -> tuple[bool, str]:
    """
    Phase 5D/6B: Check if project is locked.
    Returns (is_locked, reason).
    """
    # Check explicit project locks
    if project.is_locked:
        return True, f"Project is locked: {project.locked_reason.value if project.locked_reason else 'admin lock'}"
    
    if project.is_submitted:
        return True, "Project has been submitted"
    
    if project.status in [ProjectStatus.LOCKED, ProjectStatus.SUBMITTED, ProjectStatus.EVALUATION]:
        return True, f"Project status is {project.status.value}"
    
    # Check competition status
    if project.competition_id:
        result = await db.execute(
            select(Competition).where(Competition.id == project.competition_id)
        )
        competition = result.scalar_one_or_none()
        if competition and competition.status in [
            CompetitionStatus.SUBMISSION_CLOSED,
            CompetitionStatus.EVALUATION,
            CompetitionStatus.CLOSED
        ]:
            return True, f"Competition status is {competition.status.value}"
    
    return False, ""


async def get_team_member(
    user: User,
    project: MootProject,
    db: AsyncSession
) -> Optional[TeamMember]:
    """
    Get TeamMember record for user on project's team.
    Returns None if not a member.
    """
    if not project.team_id:
        return None
    
    result = await db.execute(
        select(TeamMember).where(
            and_(
                TeamMember.team_id == project.team_id,
                TeamMember.user_id == user.id
            )
        )
    )
    return result.scalar_one_or_none()


async def require_team_permission(
    user: User,
    project: MootProject,
    db: AsyncSession,
    allowed_roles: List[TeamRole],
    action_name: str
) -> TeamMember:
    """
    Phase 6B: Main permission enforcement helper.
    
    Checks in order:
    1. Phase 5D: Project/Competition locks
    2. Institution isolation
    3. Team membership
    4. Role-based permissions
    
    Returns TeamMember on success, raises HTTPException on failure.
    """
    # 1. Phase 5D: Check locks FIRST
    is_locked, lock_reason = await check_project_lock(project, db)
    if is_locked:
        log_permission_denial(
            user_id=user.id,
            team_id=project.team_id or 0,
            project_id=project.id,
            attempted_action=action_name,
            role="N/A (locked)",
            reason=lock_reason
        )
        raise HTTPException(
            status_code=403,
            detail=f"Project is locked: {lock_reason}"
        )
    
    # 2. Institution isolation check
    if user.institution_id != project.institution_id:
        log_permission_denial(
            user_id=user.id,
            team_id=project.team_id or 0,
            project_id=project.id,
            attempted_action=action_name,
            role="N/A",
            reason="Cross-institution access denied"
        )
        raise HTTPException(
            status_code=403,
            detail="Cross-institution access denied"
        )
    
    # Super admins bypass remaining checks
    if user.role == UserRole.teacher:
        # Return a mock team member for super admin
        return TeamMember(
            institution_id=user.institution_id,
            team_id=project.team_id or 0,
            user_id=user.id,
            role=TeamRole.CAPTAIN
        )
    
    # 3. Check team membership
    team_member = await get_team_member(user, project, db)
    if not team_member:
        log_permission_denial(
            user_id=user.id,
            team_id=project.team_id or 0,
            project_id=project.id,
            attempted_action=action_name,
            role="non-member",
            reason="Not a team member"
        )
        raise HTTPException(
            status_code=403,
            detail="You are not a member of this project's team"
        )
    
    # 4. Check role-based permissions
    if team_member.role not in allowed_roles:
        log_permission_denial(
            user_id=user.id,
            team_id=project.team_id or 0,
            project_id=project.id,
            attempted_action=action_name,
            role=team_member.role.value if team_member.role else "unknown",
            reason=f"Role {team_member.role.value} not allowed for {action_name}"
        )
        allowed_names = [r.value for r in allowed_roles]
        raise HTTPException(
            status_code=403,
            detail=f"Your role ({team_member.role.value}) cannot perform this action. Required: {', '.join(allowed_names)}"
        )
    
    return team_member


# Convenience functions for specific permission types

async def require_irac_write_permission(
    user: User,
    project: MootProject,
    db: AsyncSession
) -> TeamMember:
    """
    IRAC write permission: CAPTAIN, SPEAKER, RESEARCHER
    """
    return await require_team_permission(
        user=user,
        project=project,
        db=db,
        allowed_roles=[TeamRole.CAPTAIN, TeamRole.SPEAKER, TeamRole.RESEARCHER],
        action_name="irac_write"
    )


async def require_issue_crud_permission(
    user: User,
    project: MootProject,
    db: AsyncSession
) -> TeamMember:
    """
    Issue CRUD permission: CAPTAIN, SPEAKER
    """
    return await require_team_permission(
        user=user,
        project=project,
        db=db,
        allowed_roles=[TeamRole.CAPTAIN, TeamRole.SPEAKER],
        action_name="issue_crud"
    )


async def require_oral_response_permission(
    user: User,
    project: MootProject,
    db: AsyncSession
) -> TeamMember:
    """
    Oral response permission: CAPTAIN, SPEAKER
    """
    return await require_team_permission(
        user=user,
        project=project,
        db=db,
        allowed_roles=[TeamRole.CAPTAIN, TeamRole.SPEAKER],
        action_name="oral_response"
    )


async def require_read_permission(
    user: User,
    project: MootProject,
    db: AsyncSession
) -> TeamMember:
    """
    Read permission: All team members (CAPTAIN, SPEAKER, RESEARCHER, OBSERVER)
    Does NOT check locks - reads are always allowed.
    """
    # Institution check only for reads
    if user.institution_id != project.institution_id:
        raise HTTPException(status_code=403, detail="Cross-institution access denied")
    
    if user.role == UserRole.teacher:
        return TeamMember(
            institution_id=user.institution_id,
            team_id=project.team_id or 0,
            user_id=user.id,
            role=TeamRole.CAPTAIN
        )
    
    team_member = await get_team_member(user, project, db)
    if not team_member:
        raise HTTPException(status_code=403, detail="You are not a member of this project's team")
    
    return team_member
