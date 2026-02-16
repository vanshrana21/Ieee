"""
backend/orm/moot_project.py
Phase 5C: Moot court project persistence models
Replaces localStorage with database-backed storage
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Enum as SQLEnum, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from enum import Enum as PyEnum
from backend.orm.base import Base


class ProjectStatus(str, PyEnum):
    """Moot project lifecycle status - Phase 5D Extended"""
    DRAFT = "draft"
    ACTIVE = "active"
    SUBMITTED = "submitted"      # Phase 5D: Explicitly submitted
    LOCKED = "locked"            # Phase 5D: Locked (deadline/admin)
    EVALUATION = "evaluation"    # Phase 5D: Under evaluation
    COMPLETED = "completed"
    ARCHIVED = "archived"


class LockReason(str, PyEnum):
    """Phase 5D: Reasons for project lock"""
    DEADLINE = "deadline"           # Automatic deadline lock
    ADMIN_LOCK = "admin_lock"       # Admin manually locked
    EVALUATION = "evaluation"       # Competition in evaluation phase
    SUBMISSION = "submission"       # Student submitted
    NOT_LOCKED = "not_locked"       # Not locked


class IssueStatus(str, PyEnum):
    """Issue completion status"""
    NOT_STARTED = "not_started"
    PARTIAL = "partial"
    COMPLETE = "complete"


class MootProject(Base):
    """
    Phase 5C: Moot court project - replaces localStorage projects
    Scoped to institution, competition, and team
    """
    __tablename__ = "moot_projects"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Institution scoping (Phase 5B)
    institution_id = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Competition and Team scoping
    competition_id = Column(Integer, ForeignKey("competitions.id", ondelete="CASCADE"), nullable=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=True, index=True)
    
    # Project details
    title = Column(String(255), nullable=False)
    proposition = Column(Text, nullable=True)
    side = Column(String(20), default="petitioner", nullable=False)  # petitioner/respondent
    court = Column(String(100), nullable=True)
    domain = Column(String(100), nullable=True)
    
    # Status
    status = Column(SQLEnum(ProjectStatus), default=ProjectStatus.DRAFT, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Phase 5D: Submission locking fields
    is_submitted = Column(Boolean, default=False, nullable=False)
    submitted_at = Column(DateTime, nullable=True)
    is_locked = Column(Boolean, default=False, nullable=False)
    locked_reason = Column(SQLEnum(LockReason), default=LockReason.NOT_LOCKED, nullable=False)
    locked_at = Column(DateTime, nullable=True)
    locked_by = Column(Integer, ForeignKey("users.id"), nullable=True)  # Admin who locked/unlocked
    
    # Ownership
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)  # Soft delete
    
    # Relationships
    issues = relationship("MootIssue", back_populates="project", lazy="selectin", cascade="all, delete-orphan")
    oral_rounds = relationship("OralRound", back_populates="moot_project", lazy="selectin", cascade="all, delete-orphan")
    evaluations = relationship("MootEvaluation", back_populates="project", lazy="selectin", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<MootProject(id={self.id}, title='{self.title}', institution={self.institution_id})>"
    
    def to_dict(self, include_issues=False):
        data = {
            "id": self.id,
            "institution_id": self.institution_id,
            "competition_id": self.competition_id,
            "team_id": self.team_id,
            "title": self.title,
            "proposition": self.proposition,
            "side": self.side,
            "court": self.court,
            "domain": self.domain,
            "status": self.status.value if self.status else None,
            "is_active": self.is_active,
            # Phase 5D fields
            "is_submitted": self.is_submitted,
            "submitted_at": self.submitted_at.isoformat() if self.submitted_at else None,
            "is_locked": self.is_locked,
            "locked_reason": self.locked_reason.value if self.locked_reason else None,
            "locked_at": self.locked_at.isoformat() if self.locked_at else None,
            "locked_by": self.locked_by,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
        
        if include_issues and self.issues:
            data["issues"] = [issue.to_dict() for issue in self.issues]
        
        return data


class MootIssue(Base):
    """
    Phase 5C: Issues within a moot project
    """
    __tablename__ = "moot_issues"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Scoping
    institution_id = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("moot_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Issue details
    issue_order = Column(Integer, nullable=False, default=0)
    title = Column(String(500), nullable=True)
    description = Column(Text, nullable=True)
    status = Column(SQLEnum(IssueStatus), default=IssueStatus.NOT_STARTED, nullable=False)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    project = relationship("MootProject", back_populates="issues")
    # irac_blocks = relationship("IRACBlock", backref="issue", lazy="selectin", cascade="all, delete-orphan")  # TODO: Implement IRACBlock model if needed
    
    def to_dict(self, include_irac=False):
        data = {
            "id": self.id,
            "project_id": self.project_id,
            "issue_order": self.issue_order,
            "title": self.title,
            "description": self.description,
            "status": self.status.value if self.status else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
        
        if include_irac and self.irac_blocks:
            # Get the latest version of each block type
            latest_blocks = {}
            for block in sorted(self.irac_blocks, key=lambda x: x.version, reverse=True):
                if block.block_type not in latest_blocks:
                    latest_blocks[block.block_type] = block.to_dict()
            data["irac_blocks"] = list(latest_blocks.values())
        
        return data


class IRACBlock(Base):
    """
    Phase 5C: IRAC content blocks with versioning
    Each save creates a new version - no overwrites
    """
    __tablename__ = "irac_blocks"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Scoping
    institution_id = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("moot_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    issue_id = Column(Integer, ForeignKey("moot_issues.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Block type: issue, rule, application, conclusion
    block_type = Column(String(20), nullable=False)
    
    # Content
    content = Column(Text, nullable=True)
    
    # Versioning
    version = Column(Integer, default=1, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)  # Latest version is active
    
    # Metadata
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            "id": self.id,
            "project_id": self.project_id,
            "issue_id": self.issue_id,
            "block_type": self.block_type,
            "content": self.content,
            "version": self.version,
            "is_active": self.is_active,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


# ============================================================================
# PHASE 3 PLACEHOLDERS - Satisfy route imports without breaking Phase 2
# ============================================================================
class MootProjectRound(Base):
    __tablename__ = "moot_project_rounds"
    id = Column(Integer, primary_key=True, autoincrement=True)

class MootProjectSubmission(Base):
    __tablename__ = "moot_project_submissions"
    id = Column(Integer, primary_key=True, autoincrement=True)
