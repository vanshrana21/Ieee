"""
backend/orm/team.py
Phase 5B: Team model for moot court competition participants
Each team belongs to exactly one competition and one institution.
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Table, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
from enum import Enum as PyEnum
from backend.orm.base import Base


class TeamSide(str, PyEnum):
    """Team side in moot court"""
    PETITIONER = "petitioner"
    RESPONDENT = "respondent"
    BOTH = "both"  # For practice/friendly matches


class TeamStatus(str, PyEnum):
    """Team status"""
    PENDING = "pending"      # Registered but not confirmed
    ACTIVE = "active"        # Confirmed and participating
    DISQUALIFIED = "disqualified"
    WITHDRAWN = "withdrawn"


# ================= PHASE 6A: TEAM ROLES & MEMBERSHIP =================

class TeamRole(str, PyEnum):
    """
    Phase 6A: Team-level roles (separate from global UserRole).
    These define what a member can do within a team/project context.
    """
    CAPTAIN = "captain"       # Full control over team
    SPEAKER = "speaker"       # Writes IRAC + oral rounds
    RESEARCHER = "researcher" # Writes IRAC only
    OBSERVER = "observer"     # Read-only


class InvitationStatus(str, PyEnum):
    """Phase 6A: Status of team membership invitation"""
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"


# Association table for team members (many-to-many) - Phase 5B legacy
# Phase 6A replaces this with proper TeamMember model
team_members_legacy = Table(
    'team_members_legacy',
    Base.metadata,
    Column('team_id', Integer, ForeignKey('teams.id', ondelete='CASCADE'), primary_key=True),
    Column('user_id', Integer, ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    Column('role', String(50), default='member'),
    Column('joined_at', DateTime, default=datetime.utcnow)
)


class Team(Base):
    """
    Team model for moot court competition participants.
    Scoped to both competition and institution for data isolation.
    """
    __tablename__ = "teams"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Institution scoping - CRITICAL for multi-tenancy
    institution_id = Column(
        Integer,
        ForeignKey("institutions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Competition scoping
    competition_id = Column(
        Integer,
        ForeignKey("competitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Team info
    name = Column(String(255), nullable=False)
    code = Column(String(50), nullable=True, unique=True, index=True)  # Team registration code
    side = Column(SQLEnum(TeamSide), default=TeamSide.PETITIONER, nullable=False)
    status = Column(SQLEnum(TeamStatus), default=TeamStatus.PENDING, nullable=False)
    
    # Contact
    email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    
    # Institution details (for cross-institution competitions - future)
    representing_institution = Column(String(255), nullable=True)
    
    # Metadata
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships - Phase 6A: Use association-object pattern with TeamMember
    team_members = relationship(
        "TeamMember",
        back_populates="team",
        lazy="selectin",
        cascade="all, delete-orphan"
    )
    
    # Related records
    memorials = relationship("TeamMemorial", backref="team", lazy="selectin", cascade="all, delete-orphan")
    oral_rounds = relationship("TeamOralRound", backref="team", lazy="selectin", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Team(id={self.id}, name='{self.name}', competition={self.competition_id})>"
    
    def to_dict(self, include_members=False):
        data = {
            "id": self.id,
            "institution_id": self.institution_id,
            "competition_id": self.competition_id,
            "name": self.name,
            "code": self.code,
            "side": self.side.value if self.side else None,
            "status": self.status.value if self.status else None,
            "email": self.email,
            "phone": self.phone,
            "representing_institution": self.representing_institution,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "member_count": len(self.team_members) if self.team_members else 0
        }
        
        if include_members and self.team_members:
            data["members"] = [
                {
                    "id": tm.user.id if tm.user else None,
                    "full_name": tm.user.full_name if tm.user else None,
                    "email": tm.user.email if tm.user else None,
                    "role": tm.role.value if tm.role else None,
                    "joined_at": tm.joined_at.isoformat() if tm.joined_at else None
                }
                for tm in self.team_members
            ]
            
        return data


class TeamMemorial(Base):
    """
    Written submissions (memorials) submitted by teams
    """
    __tablename__ = "team_memorials"
    
    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    institution_id = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Memorial info
    side = Column(String(20), nullable=False)  # 'petitioner' or 'respondent'
    document_url = Column(String(500), nullable=True)
    submitted_at = Column(DateTime, default=datetime.utcnow)
    
    # Status
    is_late = Column(Boolean, default=False)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)


class TeamOralRound(Base):
    """
    Oral round records for teams
    """
    __tablename__ = "team_oral_rounds"
    
    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    institution_id = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False, index=True)
    round_id = Column(Integer, ForeignKey("competition_rounds.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Round info
    scheduled_time = Column(DateTime, nullable=True)
    actual_start = Column(DateTime, nullable=True)
    actual_end = Column(DateTime, nullable=True)
    
    # Status
    status = Column(String(20), default="scheduled", nullable=False)  # scheduled / in_progress / completed / no_show
    
    # Scores (populated by judges)
    total_score = Column(Integer, nullable=True)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)


# ================= PHASE 6A: TEAM MEMBERSHIP MODELS =================

class TeamMember(Base):
    """
    Phase 6A: Proper team membership with roles.
    Replaces the legacy team_members association table.
    Each user can be in multiple teams, but never across institutions.
    """
    __tablename__ = "team_members"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Institution scoping - CRITICAL for multi-tenancy
    institution_id = Column(
        Integer,
        ForeignKey("institutions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Relationships
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Phase 6A: Team role (CAPTAIN, SPEAKER, RESEARCHER, OBSERVER)
    role = Column(SQLEnum(TeamRole), default=TeamRole.RESEARCHER, nullable=False)
    
    # Metadata
    joined_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships for ORM
    team = relationship("Team", back_populates="team_members", lazy="selectin")
    user = relationship("User", backref="team_memberships", lazy="selectin")
    
    def __repr__(self):
        return f"<TeamMember(team={self.team_id}, user={self.user_id}, role={self.role})>"
    
    def to_dict(self):
        return {
            "id": self.id,
            "institution_id": self.institution_id,
            "team_id": self.team_id,
            "user_id": self.user_id,
            "role": self.role.value if self.role else None,
            "joined_at": self.joined_at.isoformat() if self.joined_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


class TeamInvitation(Base):
    """
    Phase 6A: Invitation-based team membership.
    Captain invites -> Invitee accepts/rejects -> TeamMember created on accept.
    """
    __tablename__ = "team_invitations"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Institution scoping
    institution_id = Column(
        Integer,
        ForeignKey("institutions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Team and invitee
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    invited_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Who sent the invitation
    invited_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Proposed role for the invitee
    proposed_role = Column(SQLEnum(TeamRole), default=TeamRole.RESEARCHER, nullable=False)
    
    # Invitation status
    status = Column(SQLEnum(InvitationStatus), default=InvitationStatus.PENDING, nullable=False)
    
    # Optional message from inviter
    message = Column(Text, nullable=True)
    
    # Expiration (default 7 days)
    expires_at = Column(DateTime, nullable=False)
    
    # Response tracking
    responded_at = Column(DateTime, nullable=True)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    team = relationship("Team", backref="invitations", lazy="selectin")
    invited_user = relationship("User", foreign_keys=[invited_user_id], backref="team_invitations", lazy="selectin")
    invited_by = relationship("User", foreign_keys=[invited_by_id], lazy="selectin")
    
    def __repr__(self):
        return f"<TeamInvitation(team={self.team_id}, user={self.invited_user_id}, status={self.status})>"
    
    def to_dict(self):
        return {
            "id": self.id,
            "institution_id": self.institution_id,
            "team_id": self.team_id,
            "invited_user_id": self.invited_user_id,
            "invited_by_id": self.invited_by_id,
            "proposed_role": self.proposed_role.value if self.proposed_role else None,
            "status": self.status.value if self.status else None,
            "message": self.message,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "responded_at": self.responded_at.isoformat() if self.responded_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class TeamAuditLog(Base):
    """
    Phase 6A: Audit log for all team actions.
    Every team mutation is logged for compliance and accountability.
    """
    __tablename__ = "team_audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Institution scoping
    institution_id = Column(
        Integer,
        ForeignKey("institutions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # What team was affected
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Who performed the action
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    actor_role = Column(String(50), nullable=False)  # Global role at time of action
    
    # Action details
    action = Column(String(50), nullable=False)  # invite, accept, reject, remove, role_change, captain_transfer
    target_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # Who was affected
    
    # Context
    old_role = Column(String(50), nullable=True)  # For role changes
    new_role = Column(String(50), nullable=True)
    reason = Column(Text, nullable=True)
    
    # Metadata
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<TeamAuditLog(team={self.team_id}, action={self.action}, actor={self.actor_id})>"
    
    def to_dict(self):
        return {
            "id": self.id,
            "institution_id": self.institution_id,
            "team_id": self.team_id,
            "actor_id": self.actor_id,
            "actor_role": self.actor_role,
            "action": self.action,
            "target_user_id": self.target_user_id,
            "old_role": self.old_role,
            "new_role": self.new_role,
            "reason": self.reason,
            "ip_address": self.ip_address,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
