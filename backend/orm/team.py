from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, DateTime, func, Enum as SQLEnum
from sqlalchemy.orm import relationship
import enum
from backend.orm.base import Base

class TeamRole(str, enum.Enum):
    SPEAKER_1 = "speaker_1"
    SPEAKER_2 = "speaker_2"
    RESEARCHER_1 = "researcher_1"
    RESEARCHER_2 = "researcher_2"

class Team(Base):
    __tablename__ = "teams"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    competition_id = Column(Integer, ForeignKey("competitions.id"), nullable=False)
    institution_id = Column(Integer, ForeignKey("institutions.id"), nullable=True)
    name = Column(String(100), nullable=False)
    side = Column(SQLEnum("petitioner", "respondent", name="team_side"), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    
    competition = relationship("Competition", back_populates="teams")
    members = relationship("TeamMember", back_populates="team", cascade="all, delete-orphan")
    memorials = relationship("MemorialSubmission", back_populates="team", cascade="all, delete-orphan")

class TeamMember(Base):
    __tablename__ = "team_members"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(SQLEnum(TeamRole), nullable=False)
    status = Column(String(20), default="active")
    joined_at = Column(DateTime, default=func.now())
    is_captain = Column(Boolean, default=False)
    
    team = relationship("Team", back_populates="members")
    user = relationship("User")


# ============================================================================
# PHASE 3 PLACEHOLDERS - Satisfy route imports without breaking Phase 2
# ============================================================================
class TeamInvitation(Base):
    __tablename__ = "team_invitations"
    id = Column(Integer, primary_key=True, autoincrement=True)

class TeamAuditLog(Base):
    __tablename__ = "team_audit_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)

class InvitationStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"
