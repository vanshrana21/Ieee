"""
backend/orm/submission.py
Phase 5C: Formal submissions with deadlines and lock/unlock system
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Enum as SQLEnum, Float
from sqlalchemy.orm import relationship
from datetime import datetime
from enum import Enum as PyEnum
from backend.orm.base import Base


class SubmissionType(str, PyEnum):
    """Types of submissions"""
    MEMORIAL_PETITIONER = "memorial_petitioner"
    MEMORIAL_RESPONDENT = "memorial_respondent"
    REPLY = "reply"
    REJOINDER = "rejoinder"


class SubmissionStatus(str, PyEnum):
    """Submission lifecycle status"""
    DRAFT = "draft"              # Being edited by student
    SUBMITTED = "submitted"      # Final submission received
    LATE = "late"                # Submitted after deadline
    LOCKED = "locked"            # Auto-locked by system
    WITHDRAWN = "withdrawn"      # Withdrawn by student


class Submission(Base):
    """
    Formal submission (memorial, reply, rejoinder) from a team.
    Includes file storage reference and submission timeline tracking.
    """
    __tablename__ = "submissions"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Institution and Competition scoping (Phase 5B)
    institution_id = Column(
        Integer,
        ForeignKey("institutions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    competition_id = Column(
        Integer,
        ForeignKey("competitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    team_id = Column(
        Integer,
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Submission details
    submission_type = Column(SQLEnum(SubmissionType), nullable=False)
    status = Column(SQLEnum(SubmissionStatus), default=SubmissionStatus.DRAFT, nullable=False)
    
    # File storage
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)  # Storage path/URL
    file_size = Column(Integer, nullable=True)  # Size in bytes
    file_hash = Column(String(64), nullable=True)  # SHA-256 for integrity
    mime_type = Column(String(100), nullable=True)  # application/pdf, etc.
    
    # Word count (auto-calculated for DOCX, manual for PDF)
    word_count = Column(Integer, nullable=True)
    
    # Timeline (Phase 5C critical fields)
    draft_started_at = Column(DateTime, default=datetime.utcnow)  # First save
    last_edited_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    submitted_at = Column(DateTime, nullable=True)  # Final submission timestamp
    locked_at = Column(DateTime, nullable=True)  # Auto-locked timestamp
    
    # Deadline tracking
    is_late = Column(Boolean, default=False)
    minutes_late = Column(Integer, default=0)  # For grace period calculations
    
    # Judge override (Phase 5C: Judges can unlock for late submissions)
    unlocked_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    unlocked_at = Column(DateTime, nullable=True)
    unlock_reason = Column(Text, nullable=True)
    
    # Plagiarism check (future)
    plagiarism_score = Column(Float, nullable=True)  # 0-100%
    plagiarism_checked_at = Column(DateTime, nullable=True)
    
    # Notes
    student_notes = Column(Text, nullable=True)
    admin_notes = Column(Text, nullable=True)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<Submission(id={self.id}, type={self.submission_type}, status={self.status})>"
    
    def to_dict(self, include_file_path=False):
        data = {
            "id": self.id,
            "institution_id": self.institution_id,
            "competition_id": self.competition_id,
            "team_id": self.team_id,
            "submission_type": self.submission_type.value if self.submission_type else None,
            "status": self.status.value if self.status else None,
            "file_name": self.file_name,
            "file_size": self.file_size,
            "mime_type": self.mime_type,
            "word_count": self.word_count,
            "draft_started_at": self.draft_started_at.isoformat() if self.draft_started_at else None,
            "last_edited_at": self.last_edited_at.isoformat() if self.last_edited_at else None,
            "submitted_at": self.submitted_at.isoformat() if self.submitted_at else None,
            "locked_at": self.locked_at.isoformat() if self.locked_at else None,
            "is_late": self.is_late,
            "minutes_late": self.minutes_late,
            "unlocked_by": self.unlocked_by,
            "unlocked_at": self.unlocked_at.isoformat() if self.unlocked_at else None,
            "unlock_reason": self.unlock_reason,
            "student_notes": self.student_notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
        
        if include_file_path:
            data["file_path"] = self.file_path
            
        return data


class SubmissionDeadline(Base):
    """
    Competition-wide submission deadlines.
    Each submission type has its own timeline.
    """
    __tablename__ = "submission_deadlines"
    
    id = Column(Integer, primary_key=True, index=True)
    
    institution_id = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False, index=True)
    competition_id = Column(Integer, ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True)
    
    submission_type = Column(SQLEnum(SubmissionType), nullable=False)
    
    # Phase 5C: Dual deadline system
    draft_deadline = Column(DateTime, nullable=False)  # Auto-lock at this time
    final_deadline = Column(DateTime, nullable=False)  # Window closes at this time
    
    # Grace period (minutes after draft_deadline where submission is "late" but allowed)
    grace_period_minutes = Column(Integer, default=0)
    
    # Display
    timezone = Column(String(50), default="UTC")
    notes = Column(Text, nullable=True)
    
    # Metadata
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        now = datetime.utcnow()
        
        return {
            "id": self.id,
            "institution_id": self.institution_id,
            "competition_id": self.competition_id,
            "submission_type": self.submission_type.value if self.submission_type else None,
            "draft_deadline": self.draft_deadline.isoformat() if self.draft_deadline else None,
            "final_deadline": self.final_deadline.isoformat() if self.final_deadline else None,
            "grace_period_minutes": self.grace_period_minutes,
            "timezone": self.timezone,
            "notes": self.notes,
            
            # Computed fields
            "is_draft_locked": now >= self.draft_deadline if self.draft_deadline else False,
            "is_final_closed": now >= self.final_deadline if self.final_deadline else False,
            "minutes_until_draft_lock": max(0, (self.draft_deadline - now).total_seconds() // 60) if self.draft_deadline and now < self.draft_deadline else 0,
            "minutes_until_final_close": max(0, (self.final_deadline - now).total_seconds() // 60) if self.final_deadline and now < self.final_deadline else 0
        }


class SubmissionLog(Base):
    """
    Audit log for all submission actions (upload, lock, unlock, etc.)
    """
    __tablename__ = "submission_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    submission_id = Column(Integer, ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False, index=True)
    
    action = Column(String(50), nullable=False)  # upload, submit, lock, unlock, replace, etc.
    performed_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    performed_at = Column(DateTime, default=datetime.utcnow)
    
    details = Column(Text, nullable=True)  # JSON with additional info
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    
    def to_dict(self):
        return {
            "id": self.id,
            "submission_id": self.submission_id,
            "action": self.action,
            "performed_by": self.performed_by,
            "performed_at": self.performed_at.isoformat() if self.performed_at else None,
            "details": self.details
        }
