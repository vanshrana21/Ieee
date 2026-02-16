"""
backend/routes/teams.py
Phase 6A: Team Management API Routes
Implements invitation-based team membership with captain authority.
"""
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from backend.database import get_db
from backend.orm.team import Team, TeamMember, TeamInvitation, TeamAuditLog, TeamRole, InvitationStatus
from backend.orm.team_activity import TeamActivityLog
from backend.orm.user import User, UserRole
from backend.rbac import get_current_user

# Phase 6C: Activity logging
from backend.services.activity_logger import (
    log_invite_sent,
    log_invite_accepted,
    log_invite_rejected,
    log_member_removed,
    log_role_changed,
    log_captain_transferred
)

router = APIRouter(prefix="/teams", tags=["Teams"])


# ================= SCHEMAS =================

class InviteMemberRequest(BaseModel):
    """Request to invite a user to a team"""
    user_id: int = Field(..., description="User ID to invite")
    role: TeamRole = Field(default=TeamRole.RESEARCHER_1, description="Proposed team role")
    message: Optional[str] = Field(None, description="Optional invitation message")


class RoleChangeRequest(BaseModel):
    """Request to change a member's role"""
    role: TeamRole = Field(..., description="New team role")
    reason: Optional[str] = Field(None, description="Reason for role change")


class TransferCaptainRequest(BaseModel):
    """Request to transfer captaincy to another member"""
    new_captain_id: int = Field(..., description="User ID of new captain")
    reason: Optional[str] = Field(None, description="Reason for transfer")


class InvitationResponse(BaseModel):
    """Response to an invitation"""
    accept: bool = Field(..., description="True to accept, False to reject")


# ================= AUDIT LOGGING =================

async def log_team_action(
    db: AsyncSession,
    institution_id: int,
    team_id: int,
    actor: User,
    action: str,
    target_user_id: Optional[int] = None,
    old_role: Optional[str] = None,
    new_role: Optional[str] = None,
    reason: Optional[str] = None,
    ip_address: Optional[str] = None
):
    """
    Phase 6A: Log every team action for audit compliance.
    """
    log = TeamAuditLog(
        institution_id=institution_id,
        team_id=team_id,
        actor_id=actor.id,
        actor_role=actor.role.value if actor.role else None,
        action=action,
        target_user_id=target_user_id,
        old_role=old_role,
        new_role=new_role,
        reason=reason,
        ip_address=ip_address
    )
    db.add(log)
    await db.commit()


# ================= PERMISSION HELPERS =================

async def require_captain(
    team_id: int,
    current_user: User,
    db: AsyncSession
) -> Team:
    """
    Phase 6A: Verify the current user is captain of the team.
    Returns the team if authorized, raises 403 otherwise.
    """
    # Get team with institution check
    result = await db.execute(
        select(Team).where(
            and_(
                Team.id == team_id,
                Team.institution_id == current_user.institution_id
            )
        )
    )
    team = result.scalar_one_or_none()
    
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    
    # Super admins bypass captain check
    if current_user.role == UserRole.teacher:
        return team
    
    # Check if user is captain
    result = await db.execute(
        select(TeamMember).where(
            and_(
                TeamMember.team_id == team_id,
                TeamMember.user_id == current_user.id,
                TeamMember.role == TeamRole.CAPTAIN
            )
        )
    )
    captain_record = result.scalar_one_or_none()
    
    if not captain_record:
        raise HTTPException(status_code=403, detail="Only team captain can perform this action")
    
    return team


async def require_team_member(
    team_id: int,
    current_user: User,
    db: AsyncSession
) -> Team:
    """
    Phase 6A: Verify the current user is a member of the team.
    Returns the team if authorized, raises 403 otherwise.
    """
    # Get team with institution check
    result = await db.execute(
        select(Team).where(
            and_(
                Team.id == team_id,
                Team.institution_id == current_user.institution_id
            )
        )
    )
    team = result.scalar_one_or_none()
    
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    
    # Super admins bypass membership check
    if current_user.role == UserRole.teacher:
        return team
    
    # Check if user is a member
    result = await db.execute(
        select(TeamMember).where(
            and_(
                TeamMember.team_id == team_id,
                TeamMember.user_id == current_user.id
            )
        )
    )
    member_record = result.scalar_one_or_none()
    
    if not member_record:
        raise HTTPException(status_code=403, detail="You are not a member of this team")
    
    return team


# ================= TEAM MANAGEMENT ENDPOINTS =================

@router.post("/{team_id}/invite", status_code=201)
async def invite_member(
    team_id: int,
    data: InviteMemberRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 6A: Captain invites a user to join the team.
    Creates a pending invitation that the user must accept.
    """
    # Verify captain authority
    team = await require_captain(team_id, current_user, db)
    
    # Verify invited user exists and is in same institution
    result = await db.execute(
        select(User).where(
            and_(
                User.id == data.user_id,
                User.institution_id == current_user.institution_id,
                User.is_active == True
            )
        )
    )
    invited_user = result.scalar_one_or_none()
    
    if not invited_user:
        raise HTTPException(status_code=404, detail="User not found or not in your institution")
    
    # Check if user is already a member
    result = await db.execute(
        select(TeamMember).where(
            and_(
                TeamMember.team_id == team_id,
                TeamMember.user_id == data.user_id
            )
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="User is already a team member")
    
    # Check for existing pending invitation
    result = await db.execute(
        select(TeamInvitation).where(
            and_(
                TeamInvitation.team_id == team_id,
                TeamInvitation.invited_user_id == data.user_id,
                TeamInvitation.status == InvitationStatus.PENDING
            )
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Pending invitation already exists")
    
    # Create invitation (expires in 7 days)
    invitation = TeamInvitation(
        institution_id=current_user.institution_id,
        team_id=team_id,
        invited_user_id=data.user_id,
        invited_by_id=current_user.id,
        proposed_role=data.role,
        status=InvitationStatus.PENDING,
        message=data.message,
        expires_at=datetime.utcnow() + timedelta(days=7)
    )
    
    db.add(invitation)
    await db.commit()
    await db.refresh(invitation)
    
    # Log the action - Phase 6C
    await log_invite_sent(
        db=db,
        team_id=team_id,
        institution_id=current_user.institution_id,
        actor=current_user,
        invited_user_id=data.user_id,
        proposed_role=data.role.value,
        invitation_id=invitation.id,
        ip_address=request.client.host if request.client else None
    )
    
    return {
        "success": True,
        "message": f"Invitation sent to {invited_user.full_name}",
        "invitation_id": invitation.id,
        "expires_at": invitation.expires_at.isoformat()
    }


@router.post("/invitations/{invitation_id}/accept", status_code=200)
async def accept_invitation(
    invitation_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 6A: User accepts a team invitation.
    Creates a TeamMember record with the proposed role.
    """
    # Get the invitation
    result = await db.execute(
        select(TeamInvitation).where(
            and_(
                TeamInvitation.id == invitation_id,
                TeamInvitation.invited_user_id == current_user.id,
                TeamInvitation.status == InvitationStatus.PENDING
            )
        )
    )
    invitation = result.scalar_one_or_none()
    
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found or already processed")
    
    # Check if expired
    if invitation.expires_at < datetime.utcnow():
        invitation.status = InvitationStatus.EXPIRED
        await db.commit()
        raise HTTPException(status_code=400, detail="Invitation has expired")
    
    # Check institution match
    if invitation.institution_id != current_user.institution_id:
        raise HTTPException(status_code=403, detail="Cross-institution access denied")
    
    # Mark invitation as accepted
    invitation.status = InvitationStatus.ACCEPTED
    invitation.responded_at = datetime.utcnow()
    
    # Create team member record
    member = TeamMember(
        institution_id=current_user.institution_id,
        team_id=invitation.team_id,
        user_id=current_user.id,
        role=invitation.proposed_role
    )
    
    db.add(member)
    await db.commit()
    await db.refresh(member)
    
    # Log the action - Phase 6C
    await log_invite_accepted(
        db=db,
        team_id=invitation.team_id,
        institution_id=current_user.institution_id,
        actor=current_user,
        invitation_id=invitation.id,
        ip_address=request.client.host if request.client else None
    )
    
    return {
        "success": True,
        "message": "You have joined the team",
        "team_id": invitation.team_id,
        "role": invitation.proposed_role.value
    }


@router.post("/invitations/{invitation_id}/reject", status_code=200)
async def reject_invitation(
    invitation_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 6A: User rejects a team invitation.
    """
    # Get the invitation
    result = await db.execute(
        select(TeamInvitation).where(
            and_(
                TeamInvitation.id == invitation_id,
                TeamInvitation.invited_user_id == current_user.id,
                TeamInvitation.status == InvitationStatus.PENDING
            )
        )
    )
    invitation = result.scalar_one_or_none()
    
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found or already processed")
    
    # Check institution match
    if invitation.institution_id != current_user.institution_id:
        raise HTTPException(status_code=403, detail="Cross-institution access denied")
    
    # Mark invitation as rejected
    invitation.status = InvitationStatus.REJECTED
    invitation.responded_at = datetime.utcnow()
    
    await db.commit()
    
    # Log the action - Phase 6C
    await log_invite_rejected(
        db=db,
        team_id=invitation.team_id,
        institution_id=current_user.institution_id,
        actor=current_user,
        invitation_id=invitation.id,
        ip_address=request.client.host if request.client else None
    )
    
    return {
        "success": True,
        "message": "Invitation rejected"
    }


@router.delete("/{team_id}/members/{user_id}", status_code=200)
async def remove_member(
    team_id: int,
    user_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 6A: Captain removes a member from the team.
    Cannot remove the last captain.
    """
    # Verify captain authority
    team = await require_captain(team_id, current_user, db)
    
    # Get the member to remove
    result = await db.execute(
        select(TeamMember).where(
            and_(
                TeamMember.team_id == team_id,
                TeamMember.user_id == user_id
            )
        )
    )
    member = result.scalar_one_or_none()
    
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    
    # Check if trying to remove the last captain
    if member.role == TeamRole.CAPTAIN:
        # Count captains
        result = await db.execute(
            select(func.count(TeamMember.id)).where(
                and_(
                    TeamMember.team_id == team_id,
                    TeamMember.role == TeamRole.CAPTAIN
                )
            )
        )
        captain_count = result.scalar()
        
        if captain_count <= 1:
            raise HTTPException(
                status_code=400,
                detail="Cannot remove the last captain. Transfer captaincy first."
            )
    
    # Get role for audit log
    removed_role = member.role.value
    
    # Delete the member
    await db.delete(member)
    await db.commit()
    
    # Log the action - Phase 6C
    await log_member_removed(
        db=db,
        team_id=team_id,
        institution_id=current_user.institution_id,
        actor=current_user,
        removed_user_id=user_id,
        removed_user_name=removed_role,
        ip_address=request.client.host if request.client else None
    )
    
    return {
        "success": True,
        "message": "Member removed from team"
    }


@router.patch("/{team_id}/members/{user_id}/role", status_code=200)
async def change_member_role(
    team_id: int,
    user_id: int,
    data: RoleChangeRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 6A: Captain changes a member's team role.
    Cannot change role of the last captain.
    """
    # Verify captain authority
    team = await require_captain(team_id, current_user, db)
    
    # Get the member
    result = await db.execute(
        select(TeamMember).where(
            and_(
                TeamMember.team_id == team_id,
                TeamMember.user_id == user_id
            )
        )
    )
    member = result.scalar_one_or_none()
    
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    
    # Check if trying to demote the last captain
    if member.role == TeamRole.CAPTAIN and data.role != TeamRole.CAPTAIN:
        # Count captains
        result = await db.execute(
            select(func.count(TeamMember.id)).where(
                and_(
                    TeamMember.team_id == team_id,
                    TeamMember.role == TeamRole.CAPTAIN
                )
            )
        )
        captain_count = result.scalar()
        
        if captain_count <= 1:
            raise HTTPException(
                status_code=400,
                detail="Cannot demote the last captain. Transfer captaincy first."
            )
    
    # Track old role for audit
    old_role = member.role.value
    
    # Update role
    member.role = data.role
    member.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(member)
    
    # Log the action - Phase 6C
    await log_role_changed(
        db=db,
        team_id=team_id,
        institution_id=current_user.institution_id,
        actor=current_user,
        target_user_id=user_id,
        target_user_name=old_role,
        old_role=old_role,
        new_role=data.role.value,
        ip_address=request.client.host if request.client else None
    )
    
    return {
        "success": True,
        "message": f"Role changed to {data.role.value}",
        "user_id": user_id,
        "new_role": data.role.value
    }


@router.post("/{team_id}/transfer-captain", status_code=200)
async def transfer_captaincy(
    team_id: int,
    data: TransferCaptainRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 6A: Captain transfers captaincy to another team member.
    The new captain must already be a team member.
    """
    # Verify captain authority
    team = await require_captain(team_id, current_user, db)
    
    # Get new captain member record
    result = await db.execute(
        select(TeamMember).where(
            and_(
                TeamMember.team_id == team_id,
                TeamMember.user_id == data.new_captain_id
            )
        )
    )
    new_captain = result.scalar_one_or_none()
    
    if not new_captain:
        raise HTTPException(status_code=404, detail="New captain must be an existing team member")
    
    # Get current captain record
    result = await db.execute(
        select(TeamMember).where(
            and_(
                TeamMember.team_id == team_id,
                TeamMember.user_id == current_user.id,
                TeamMember.role == TeamRole.CAPTAIN
            )
        )
    )
    current_captain = result.scalar_one_or_none()
    
    if not current_captain:
        # Should not happen due to require_captain, but defensive check
        raise HTTPException(status_code=403, detail="You are not the captain")
    
    # Transfer roles
    current_captain.role = TeamRole.SPEAKER  # Former captain becomes speaker
    new_captain.role = TeamRole.CAPTAIN
    
    current_captain.updated_at = datetime.utcnow()
    new_captain.updated_at = datetime.utcnow()
    
    await db.commit()
    
    # Log the action - Phase 6C
    await log_captain_transferred(
        db=db,
        team_id=team_id,
        institution_id=current_user.institution_id,
        actor=current_user,
        new_captain_id=data.new_captain_id,
        new_captain_name=str(data.new_captain_id),
        ip_address=request.client.host if request.client else None
    )
    
    return {
        "success": True,
        "message": "Captaincy transferred",
        "new_captain_id": data.new_captain_id
    }


# ================= READ ENDPOINTS =================

@router.get("/{team_id}/members", status_code=200)
async def list_team_members(
    team_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 6A: List all members of a team.
    Only team members can view the member list.
    """
    # Verify team membership
    team = await require_team_member(team_id, current_user, db)
    
    # Get all members with user details
    result = await db.execute(
        select(TeamMember, User).join(
            User, TeamMember.user_id == User.id
        ).where(
            TeamMember.team_id == team_id
        ).order_by(TeamMember.joined_at)
    )
    members = result.all()
    
    return {
        "success": True,
        "team_id": team_id,
        "members": [
            {
                "user_id": user.id,
                "full_name": user.full_name,
                "email": user.email,
                "role": member.role.value,
                "joined_at": member.joined_at.isoformat()
            }
            for member, user in members
        ],
        "count": len(members)
    }


@router.get("/{team_id}/activity", status_code=200)
async def list_team_activity(
    team_id: int,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 6C: List team activity log.
    
    Team members, faculty, and admins can view activity.
    Chronological list (latest first), paginated.
    """
    # Verify user can access team (must be member, faculty, or admin)
    if current_user.role not in [UserRole.teacher, UserRole.teacher, UserRole.teacher]:
        # Check if user is a team member
        member_result = await db.execute(
            select(TeamMember).where(
                and_(
                    TeamMember.team_id == team_id,
                    TeamMember.user_id == current_user.id
                )
            )
        )
        if not member_result.scalar_one_or_none():
            raise HTTPException(status_code=403, detail="Access denied")
    
    # Get team for institution verification
    team_result = await db.execute(
        select(Team).where(
            and_(
                Team.id == team_id,
                Team.institution_id == current_user.institution_id
            )
        )
    )
    team = team_result.scalar_one_or_none()
    
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    
    # Get paginated activity logs (latest first)
    result = await db.execute(
        select(TeamActivityLog)
        .where(TeamActivityLog.team_id == team_id)
        .order_by(TeamActivityLog.timestamp.desc())
        .offset(offset)
        .limit(limit)
    )
    logs = result.scalars().all()
    
    # Get total count for pagination
    count_result = await db.execute(
        select(func.count(TeamActivityLog.id)).where(
            TeamActivityLog.team_id == team_id
        )
    )
    total = count_result.scalar()
    
    return {
        "success": True,
        "team_id": team_id,
        "activities": [log.to_dict(include_actor=True) for log in logs],
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.get("/invitations/pending", status_code=200)
async def list_pending_invitations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 6A: List all pending invitations for the current user.
    """
    result = await db.execute(
        select(TeamInvitation, Team).join(
            Team, TeamInvitation.team_id == Team.id
        ).where(
            and_(
                TeamInvitation.invited_user_id == current_user.id,
                TeamInvitation.status == InvitationStatus.PENDING,
                TeamInvitation.expires_at > datetime.utcnow()
            )
        ).order_by(TeamInvitation.created_at.desc())
    )
    invitations = result.all()
    
    return {
        "success": True,
        "invitations": [
            {
                "id": inv.id,
                "team_id": inv.team_id,
                "team_name": team.name,
                "proposed_role": inv.proposed_role.value,
                "message": inv.message,
                "invited_by_id": inv.invited_by_id,
                "expires_at": inv.expires_at.isoformat(),
                "created_at": inv.created_at.isoformat()
            }
            for inv, team in invitations
        ],
        "count": len(invitations)
    }
