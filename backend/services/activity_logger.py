"""
backend/services/activity_logger.py
Phase 6C: Centralized team activity logging service

This module provides a single helper function `log_team_activity()` 
that all routes should use for consistent activity logging.

Logs are append-only and read-only. No edits, no deletions.
"""
import logging
from typing import Optional, Dict, Any
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.orm.team_activity import TeamActivityLog, ActionType, TargetType
from backend.orm.user import User

logger = logging.getLogger(__name__)


async def log_team_activity(
    db: AsyncSession,
    institution_id: int,
    team_id: int,
    actor: User,
    action_type: ActionType,
    target_type: TargetType,
    target_id: Optional[int] = None,
    target_name: Optional[str] = None,
    project_id: Optional[int] = None,
    context: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None
) -> TeamActivityLog:
    """
    Phase 6C: Centralized helper for logging team activity.
    
    Call this function AFTER successful action execution.
    
    Args:
        db: Database session
        institution_id: Institution scope (mandatory)
        team_id: Team scope (mandatory)
        actor: User who performed the action
        action_type: Type of action (from ActionType enum)
        target_type: Type of target entity (from TargetType enum)
        target_id: ID of target entity (optional)
        target_name: Human-readable name of target (optional)
        project_id: Project scope if applicable (optional)
        context: Additional JSON-serializable context (optional)
        ip_address: Client IP for audit (optional)
    
    Returns:
        Created TeamActivityLog entry
    
    Example usage:
        await log_team_activity(
            db=db,
            institution_id=project.institution_id,
            team_id=project.team_id,
            actor=current_user,
            action_type=ActionType.IRAC_SAVED,
            target_type=TargetType.IRAC,
            target_id=irac_block.id,
            target_name=f"Issue {issue_id} - Rule",
            project_id=project.id
        )
    """
    try:
        # Capture actor's role at time of action
        actor_role = actor.role.value if hasattr(actor, 'role') and actor.role else "unknown"
        
        log_entry = TeamActivityLog(
            institution_id=institution_id,
            team_id=team_id,
            project_id=project_id,
            actor_id=actor.id,
            actor_role_at_time=actor_role,
            action_type=action_type,
            target_type=target_type,
            target_id=target_id,
            target_name=target_name,
            context=context,
            timestamp=datetime.utcnow(),
            ip_address=ip_address
        )
        
        db.add(log_entry)
        await db.commit()
        await db.refresh(log_entry)
        
        logger.debug(
            f"Activity logged: {action_type.value} "
            f"by {actor.id} on {target_type.value} {target_id}"
        )
        
        return log_entry
        
    except Exception as e:
        # Log the error but don't fail the main operation
        # Activity logging is best-effort for accountability
        logger.error(f"Failed to log activity: {e}")
        # Return None to indicate logging failure
        return None


# Convenience functions for specific action types
# These make the calling code cleaner and more maintainable

async def log_project_created(
    db: AsyncSession,
    project,
    actor: User,
    ip_address: Optional[str] = None
):
    """Log project creation"""
    return await log_team_activity(
        db=db,
        institution_id=project.institution_id,
        team_id=project.team_id,
        actor=actor,
        action_type=ActionType.PROJECT_CREATED,
        target_type=TargetType.PROJECT,
        target_id=project.id,
        target_name=project.title,
        project_id=project.id,
        ip_address=ip_address
    )


async def log_project_submitted(
    db: AsyncSession,
    project,
    actor: User,
    ip_address: Optional[str] = None
):
    """Log project submission"""
    return await log_team_activity(
        db=db,
        institution_id=project.institution_id,
        team_id=project.team_id,
        actor=actor,
        action_type=ActionType.PROJECT_SUBMITTED,
        target_type=TargetType.PROJECT,
        target_id=project.id,
        target_name=project.title,
        project_id=project.id,
        ip_address=ip_address
    )


async def log_project_locked(
    db: AsyncSession,
    project,
    actor: User,
    reason: str,
    ip_address: Optional[str] = None
):
    """Log project lock"""
    return await log_team_activity(
        db=db,
        institution_id=project.institution_id,
        team_id=project.team_id,
        actor=actor,
        action_type=ActionType.PROJECT_LOCKED,
        target_type=TargetType.PROJECT,
        target_id=project.id,
        target_name=project.title,
        project_id=project.id,
        context={"reason": reason},
        ip_address=ip_address
    )


async def log_project_unlocked(
    db: AsyncSession,
    project,
    actor: User,
    ip_address: Optional[str] = None
):
    """Log project unlock"""
    return await log_team_activity(
        db=db,
        institution_id=project.institution_id,
        team_id=project.team_id,
        actor=actor,
        action_type=ActionType.PROJECT_UNLOCKED,
        target_type=TargetType.PROJECT,
        target_id=project.id,
        target_name=project.title,
        project_id=project.id,
        ip_address=ip_address
    )


async def log_irac_saved(
    db: AsyncSession,
    project,
    actor: User,
    issue_id: int,
    block_type: str,
    ip_address: Optional[str] = None
):
    """Log IRAC save (high-level only, no content)"""
    return await log_team_activity(
        db=db,
        institution_id=project.institution_id,
        team_id=project.team_id,
        actor=actor,
        action_type=ActionType.IRAC_SAVED,
        target_type=TargetType.IRAC,
        target_id=issue_id,
        target_name=f"Issue {issue_id} - {block_type}",
        project_id=project.id,
        context={"block_type": block_type},
        ip_address=ip_address
    )


async def log_issue_created(
    db: AsyncSession,
    project,
    actor: User,
    issue,
    ip_address: Optional[str] = None
):
    """Log issue creation"""
    return await log_team_activity(
        db=db,
        institution_id=project.institution_id,
        team_id=project.team_id,
        actor=actor,
        action_type=ActionType.ISSUE_CREATED,
        target_type=TargetType.ISSUE,
        target_id=issue.id,
        target_name=issue.title or f"Issue #{issue.issue_order}",
        project_id=project.id,
        ip_address=ip_address
    )


async def log_issue_updated(
    db: AsyncSession,
    project,
    actor: User,
    issue,
    ip_address: Optional[str] = None
):
    """Log issue update"""
    return await log_team_activity(
        db=db,
        institution_id=project.institution_id,
        team_id=project.team_id,
        actor=actor,
        action_type=ActionType.ISSUE_UPDATED,
        target_type=TargetType.ISSUE,
        target_id=issue.id,
        target_name=issue.title or f"Issue #{issue.issue_order}",
        project_id=project.id,
        ip_address=ip_address
    )


async def log_issue_deleted(
    db: AsyncSession,
    project,
    actor: User,
    issue_id: int,
    issue_name: str,
    ip_address: Optional[str] = None
):
    """Log issue deletion"""
    return await log_team_activity(
        db=db,
        institution_id=project.institution_id,
        team_id=project.team_id,
        actor=actor,
        action_type=ActionType.ISSUE_DELETED,
        target_type=TargetType.ISSUE,
        target_id=issue_id,
        target_name=issue_name,
        project_id=project.id,
        ip_address=ip_address
    )


async def log_oral_round_started(
    db: AsyncSession,
    project,
    actor: User,
    round_id: int,
    stage: str,
    ip_address: Optional[str] = None
):
    """Log oral round start"""
    return await log_team_activity(
        db=db,
        institution_id=project.institution_id,
        team_id=project.team_id,
        actor=actor,
        action_type=ActionType.ORAL_ROUND_STARTED,
        target_type=TargetType.ORAL_ROUND,
        target_id=round_id,
        target_name=f"{stage.title()} Round",
        project_id=project.id,
        context={"stage": stage},
        ip_address=ip_address
    )


async def log_oral_round_completed(
    db: AsyncSession,
    project,
    actor: User,
    round_id: int,
    stage: str,
    ip_address: Optional[str] = None
):
    """Log oral round completion"""
    return await log_team_activity(
        db=db,
        institution_id=project.institution_id,
        team_id=project.team_id,
        actor=actor,
        action_type=ActionType.ORAL_ROUND_COMPLETED,
        target_type=TargetType.ORAL_ROUND,
        target_id=round_id,
        target_name=f"{stage.title()} Round",
        project_id=project.id,
        context={"stage": stage},
        ip_address=ip_address
    )


async def log_oral_response_submitted(
    db: AsyncSession,
    project,
    actor: User,
    round_id: int,
    speaker_role: str,
    ip_address: Optional[str] = None
):
    """Log oral response submission (high-level only)"""
    return await log_team_activity(
        db=db,
        institution_id=project.institution_id,
        team_id=project.team_id,
        actor=actor,
        action_type=ActionType.ORAL_RESPONSE_SUBMITTED,
        target_type=TargetType.ORAL_ROUND,
        target_id=round_id,
        target_name=f"Round {round_id} - {speaker_role}",
        project_id=project.id,
        context={"speaker_role": speaker_role},
        ip_address=ip_address
    )


async def log_invite_sent(
    db: AsyncSession,
    team_id: int,
    institution_id: int,
    actor: User,
    invited_user_id: int,
    proposed_role: str,
    invitation_id: int,
    ip_address: Optional[str] = None
):
    """Log invitation sent"""
    return await log_team_activity(
        db=db,
        institution_id=institution_id,
        team_id=team_id,
        actor=actor,
        action_type=ActionType.INVITE_SENT,
        target_type=TargetType.INVITATION,
        target_id=invitation_id,
        target_name=f"Invitation to user {invited_user_id}",
        context={
            "invited_user_id": invited_user_id,
            "proposed_role": proposed_role
        },
        ip_address=ip_address
    )


async def log_invite_accepted(
    db: AsyncSession,
    team_id: int,
    institution_id: int,
    actor: User,
    invitation_id: int,
    ip_address: Optional[str] = None
):
    """Log invitation accepted"""
    return await log_team_activity(
        db=db,
        institution_id=institution_id,
        team_id=team_id,
        actor=actor,
        action_type=ActionType.INVITE_ACCEPTED,
        target_type=TargetType.INVITATION,
        target_id=invitation_id,
        ip_address=ip_address
    )


async def log_invite_rejected(
    db: AsyncSession,
    team_id: int,
    institution_id: int,
    actor: User,
    invitation_id: int,
    ip_address: Optional[str] = None
):
    """Log invitation rejected"""
    return await log_team_activity(
        db=db,
        institution_id=institution_id,
        team_id=team_id,
        actor=actor,
        action_type=ActionType.INVITE_REJECTED,
        target_type=TargetType.INVITATION,
        target_id=invitation_id,
        ip_address=ip_address
    )


async def log_member_removed(
    db: AsyncSession,
    team_id: int,
    institution_id: int,
    actor: User,
    removed_user_id: int,
    removed_user_name: str,
    ip_address: Optional[str] = None
):
    """Log member removal"""
    return await log_team_activity(
        db=db,
        institution_id=institution_id,
        team_id=team_id,
        actor=actor,
        action_type=ActionType.MEMBER_REMOVED,
        target_type=TargetType.MEMBER,
        target_id=removed_user_id,
        target_name=removed_user_name,
        context={"removed_user_id": removed_user_id},
        ip_address=ip_address
    )


async def log_role_changed(
    db: AsyncSession,
    team_id: int,
    institution_id: int,
    actor: User,
    target_user_id: int,
    target_user_name: str,
    old_role: str,
    new_role: str,
    ip_address: Optional[str] = None
):
    """Log role change"""
    return await log_team_activity(
        db=db,
        institution_id=institution_id,
        team_id=team_id,
        actor=actor,
        action_type=ActionType.ROLE_CHANGED,
        target_type=TargetType.MEMBER,
        target_id=target_user_id,
        target_name=target_user_name,
        context={
            "old_role": old_role,
            "new_role": new_role,
            "target_user_id": target_user_id
        },
        ip_address=ip_address
    )


async def log_captain_transferred(
    db: AsyncSession,
    team_id: int,
    institution_id: int,
    actor: User,
    new_captain_id: int,
    new_captain_name: str,
    ip_address: Optional[str] = None
):
    """Log captain transfer"""
    return await log_team_activity(
        db=db,
        institution_id=institution_id,
        team_id=team_id,
        actor=actor,
        action_type=ActionType.CAPTAIN_TRANSFERRED,
        target_type=TargetType.TEAM,
        target_id=team_id,
        target_name=f"Team {team_id}",
        context={
            "new_captain_id": new_captain_id,
            "new_captain_name": new_captain_name
        },
        ip_address=ip_address
    )


async def log_evaluation_finalized(
    db: AsyncSession,
    project,
    actor: User,
    evaluation_id: int,
    total_score: float,
    ip_address: Optional[str] = None
):
    """Log evaluation finalization"""
    return await log_team_activity(
        db=db,
        institution_id=project.institution_id,
        team_id=project.team_id,
        actor=actor,
        action_type=ActionType.EVALUATION_FINALIZED,
        target_type=TargetType.EVALUATION,
        target_id=evaluation_id,
        target_name=f"Evaluation for {project.title}",
        project_id=project.id,
        context={"total_score": total_score},
        ip_address=ip_address
    )


async def log_evaluation_draft_created(
    db: AsyncSession,
    project,
    actor: User,
    evaluation_id: int,
    ip_address: Optional[str] = None
):
    """Log evaluation draft creation"""
    return await log_team_activity(
        db=db,
        institution_id=project.institution_id,
        team_id=project.team_id,
        actor=actor,
        action_type=ActionType.EVALUATION_DRAFT_CREATED,
        target_type=TargetType.EVALUATION,
        target_id=evaluation_id,
        target_name=f"Draft for {project.title}",
        project_id=project.id,
        ip_address=ip_address
    )


async def log_faculty_view(
    db: AsyncSession,
    project,
    actor: User,
    ip_address: Optional[str] = None
):
    """Log faculty project view (Phase 7)"""
    return await log_team_activity(
        db=db,
        institution_id=project.institution_id,
        team_id=project.team_id,
        actor=actor,
        action_type=ActionType.FACULTY_VIEW,
        target_type=TargetType.PROJECT,
        target_id=project.id,
        target_name=f"Project {project.title}",
        project_id=project.id,
        context={"action": "faculty_view"},
        ip_address=ip_address
    )


async def log_faculty_note_added(
    db: AsyncSession,
    project,
    actor: User,
    note_id: int,
    ip_address: Optional[str] = None
):
    """Log faculty note added (Phase 7)"""
    return await log_team_activity(
        db=db,
        institution_id=project.institution_id,
        team_id=project.team_id,
        actor=actor,
        action_type=ActionType.FACULTY_NOTE_ADDED,
        target_type=TargetType.PROJECT,
        target_id=project.id,
        target_name=f"Project {project.title}",
        project_id=project.id,
        context={"note_id": note_id, "action": "faculty_note_added"},
        ip_address=ip_address
    )

