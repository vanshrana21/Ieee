"""
backend/orm/exam_session.py
Phase 7.2: Timed Mock Exam Session Model

Tracks mock exam sessions with timing and completion status.

Key Design:
- Each mock exam creates a new session
- Session tracks start/end times for timer enforcement
- Supports session recovery after page refresh
- No answer modification after submission
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Index, Enum as SQLEnum, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from enum import Enum
from backend.orm.base import BaseModel


class ExamSessionStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    AUTO_SUBMITTED = "auto_submitted"
    ABANDONED = "abandoned"


class ExamSession(BaseModel):
    """
    Tracks a single mock exam session.
    
    Lifecycle:
    1. User starts exam → Session created (status=in_progress)
    2. User answers questions → Answers saved as ExamAnswer records
    3. User submits OR time expires → Session completed/auto_submitted
    4. Session locked → No further modifications
    
    Timer Enforcement:
    - started_at + duration_minutes = deadline
    - If current_time > deadline, auto-submit
    - Frontend uses remaining time from API
    """
    
    __tablename__ = "exam_sessions"
    
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User taking the exam"
    )
    
    exam_type = Column(
        String(50),
        nullable=False,
        index=True,
        comment="Type: mock_exam, end_semester, unit_test, internal_assessment"
    )
    
    subject_id = Column(
        Integer,
        ForeignKey("subjects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Subject if subject-specific exam"
    )
    
    blueprint_data = Column(
        JSON,
        nullable=False,
        comment="Serialized blueprint used for this exam"
    )
    
    total_marks = Column(
        Integer,
        nullable=False,
        comment="Total marks for this exam"
    )
    
    duration_minutes = Column(
        Integer,
        nullable=False,
        comment="Allowed duration in minutes"
    )
    
    started_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        comment="When exam was started"
    )
    
    submitted_at = Column(
        DateTime,
        nullable=True,
        comment="When exam was submitted (NULL if in progress)"
    )
    
    status = Column(
        SQLEnum(ExamSessionStatus),
        nullable=False,
        default=ExamSessionStatus.IN_PROGRESS,
        index=True,
        comment="Current session status"
    )
    
    total_time_taken_seconds = Column(
        Integer,
        nullable=True,
        comment="Actual time taken in seconds"
    )
    
    questions_attempted = Column(
        Integer,
        nullable=True,
        default=0,
        comment="Number of questions answered"
    )
    
    total_questions = Column(
        Integer,
        nullable=False,
        comment="Total questions in exam"
    )
    
    user = relationship(
        "User",
        back_populates="exam_sessions",
        lazy="joined"
    )
    
    subject = relationship(
        "Subject",
        lazy="joined"
    )
    
    answers = relationship(
        "ExamAnswer",
        back_populates="exam_session",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    
    __table_args__ = (
        Index("ix_user_exam_sessions", "user_id", "status"),
        Index("ix_exam_session_started", "started_at"),
    )
    
    def __repr__(self):
        return f"<ExamSession(id={self.id}, user_id={self.user_id}, status={self.status})>"
    
    def get_remaining_seconds(self) -> int:
        """Calculate remaining time in seconds."""
        if self.status != ExamSessionStatus.IN_PROGRESS:
            return 0
        
        now = datetime.utcnow()
        elapsed = (now - self.started_at).total_seconds()
        total_seconds = self.duration_minutes * 60
        remaining = total_seconds - elapsed
        
        return max(0, int(remaining))
    
    def is_expired(self) -> bool:
        """Check if exam time has expired."""
        return self.get_remaining_seconds() <= 0
    
    def to_dict(self, include_blueprint: bool = False) -> dict:
        """Convert to dictionary for API responses."""
        data = {
            "id": self.id,
            "user_id": self.user_id,
            "exam_type": self.exam_type,
            "subject_id": self.subject_id,
            "subject_name": self.subject.title if self.subject else None,
            "total_marks": self.total_marks,
            "duration_minutes": self.duration_minutes,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "submitted_at": self.submitted_at.isoformat() if self.submitted_at else None,
            "status": self.status.value,
            "total_time_taken_seconds": self.total_time_taken_seconds,
            "questions_attempted": self.questions_attempted,
            "total_questions": self.total_questions,
            "remaining_seconds": self.get_remaining_seconds(),
            "is_expired": self.is_expired(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        
        if include_blueprint:
            data["blueprint"] = self.blueprint_data
        
        return data
