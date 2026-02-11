"""
Classroom Session Database Models

Isolated tables for Classroom Mode (B2B).
No shared tables with Online 1v1 Mode.
"""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Float, Text, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
from enum import Enum as PyEnum
import uuid

from backend.database import Base


class SessionState(PyEnum):
    """Classroom session states."""
    CREATED = "created"
    PREPARING = "preparing"
    STUDY = "study"
    MOOT = "moot"
    SCORING = "scoring"
    COMPLETED = "completed"


class SessionCategory(PyEnum):
    """Moot court categories."""
    CONSTITUTIONAL = "constitutional"
    CRIMINAL = "criminal"
    CYBER = "cyber"
    CIVIL = "civil"
    CORPORATE = "corporate"


class ClassroomSession(Base):
    """Classroom session table."""
    __tablename__ = "classroom_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    session_code = Column(String(20), unique=True, index=True, nullable=False)
    teacher_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    topic = Column(String(255), nullable=False)
    category = Column(String(50), default=SessionCategory.CONSTITUTIONAL.value)
    prep_time_minutes = Column(Integer, default=30)
    oral_time_minutes = Column(Integer, default=45)
    ai_judge_enabled = Column(Boolean, default=True)
    current_state = Column(String(50), default=SessionState.CREATED.value)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    teacher = relationship("User", back_populates="classroom_sessions")
    participants = relationship("ClassroomParticipant", back_populates="session", cascade="all, delete-orphan")
    scores = relationship("ClassroomScore", back_populates="session", cascade="all, delete-orphan")
    arguments = relationship("ClassroomArgument", back_populates="session", cascade="all, delete-orphan")
    
    def generate_session_code(self):
        """Generate unique session code."""
        import random
        import string
        prefix = "JURIS"
        suffix = ''.join(random.choices(string.digits, k=4))
        return f"{prefix}-{suffix}"
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.session_code:
            self.session_code = self.generate_session_code()
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            "id": self.id,
            "session_code": self.session_code,
            "teacher_id": self.teacher_id,
            "topic": self.topic,
            "category": self.category,
            "prep_time_minutes": self.prep_time_minutes,
            "oral_time_minutes": self.oral_time_minutes,
            "ai_judge_enabled": self.ai_judge_enabled,
            "current_state": self.current_state,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "participants_count": len(self.participants) if self.participants else 0
        }


class ClassroomParticipant(Base):
    """Classroom participant table."""
    __tablename__ = "classroom_participants"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("classroom_sessions.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(String(50), default="observer")  # petitioner, respondent, observer
    joined_at = Column(DateTime(timezone=True), server_default=func.now())
    score_id = Column(Integer, ForeignKey("classroom_scores.id"), nullable=True)
    
    # Relationships
    session = relationship("ClassroomSession", back_populates="participants")
    user = relationship("User", back_populates="classroom_participations")
    score = relationship("ClassroomScore", back_populates="participant")
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "role": self.role,
            "joined_at": self.joined_at.isoformat() if self.joined_at else None,
            "score_id": self.score_id
        }


class ClassroomScore(Base):
    """Classroom score table."""
    __tablename__ = "classroom_scores"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("classroom_sessions.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Score criteria (1-5 scale)
    legal_reasoning = Column(Integer, nullable=True)
    citation_format = Column(Integer, nullable=True)
    courtroom_etiquette = Column(Integer, nullable=True)
    responsiveness = Column(Integer, nullable=True)
    time_management = Column(Integer, nullable=True)
    total_score = Column(Float, nullable=True)
    
    # Feedback
    feedback_text = Column(Text, nullable=True)
    submitted_by = Column(Integer, ForeignKey("users.id"), nullable=True)  # teacher or AI
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())
    is_draft = Column(Boolean, default=True)
    
    # Relationships
    session = relationship("ClassroomSession", back_populates="scores")
    user = relationship("User", foreign_keys=[user_id], back_populates="classroom_scores")
    submitted_by_user = relationship("User", foreign_keys=[submitted_by])
    
    def calculate_total(self):
        """Calculate total score from criteria."""
        scores = [
            self.legal_reasoning,
            self.citation_format,
            self.courtroom_etiquette,
            self.responsiveness,
            self.time_management
        ]
        valid_scores = [s for s in scores if s is not None]
        if valid_scores:
            self.total_score = sum(valid_scores) / len(valid_scores) * 5  # Scale to 25
        return self.total_score
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "legal_reasoning": self.legal_reasoning,
            "citation_format": self.citation_format,
            "courtroom_etiquette": self.courtroom_etiquette,
            "responsiveness": self.responsiveness,
            "time_management": self.time_management,
            "total_score": self.total_score,
            "feedback_text": self.feedback_text,
            "submitted_by": self.submitted_by,
            "submitted_at": self.submitted_at.isoformat() if self.submitted_at else None,
            "is_draft": self.is_draft
        }


class ClassroomArgument(Base):
    """Classroom argument table."""
    __tablename__ = "classroom_arguments"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("classroom_sessions.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(String(50), nullable=False)  # petitioner, respondent
    text = Column(Text, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    ai_score = Column(Float, nullable=True)
    judge_notes = Column(Text, nullable=True)
    
    # Relationships
    session = relationship("ClassroomSession", back_populates="arguments")
    user = relationship("User", back_populates="classroom_arguments")
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "role": self.role,
            "text": self.text,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "ai_score": self.ai_score,
            "judge_notes": self.judge_notes
        }


# Add relationships to User model
# These should be added to the existing User model
def add_user_relationships():
    """Add classroom relationships to User model."""
    from backend.orm.user import User
    
    User.classroom_sessions = relationship("ClassroomSession", back_populates="teacher")
    User.classroom_participations = relationship("ClassroomParticipant", back_populates="user")
    User.classroom_scores = relationship("ClassroomScore", foreign_keys=[ClassroomScore.user_id], back_populates="user")
    User.classroom_arguments = relationship("ClassroomArgument", back_populates="user")
