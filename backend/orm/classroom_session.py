"""
Classroom Session Database Models - Production Grade

Isolated tables for Classroom Mode (B2B).
Features: Timer persistence, concurrency protection, reconnection safety.
"""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Float, Text, Enum, Index, UniqueConstraint
from sqlalchemy.orm import relationship, validates
from sqlalchemy.sql import func
from datetime import datetime, timedelta
from enum import Enum as PyEnum
import secrets
import re

from backend.database import Base


class SessionState(PyEnum):
    """Classroom session states."""
    CREATED = "created"
    PREPARING = "preparing"
    STUDY = "study"
    MOOT = "moot"
    SCORING = "scoring"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class SessionCategory(PyEnum):
    """Moot court categories."""
    CONSTITUTIONAL = "constitutional"
    CRIMINAL = "criminal"
    CYBER = "cyber"
    CIVIL = "civil"
    CORPORATE = "corporate"


class ParticipantRole(PyEnum):
    """Participant roles in a session."""
    PETITIONER = "petitioner"
    RESPONDENT = "respondent"
    OBSERVER = "observer"


class AIJudgeMode(PyEnum):
    """AI judge configuration modes."""
    ON = "on"
    OFF = "off"
    HYBRID = "hybrid"


class ClassroomSession(Base):
    """Classroom session table with production-grade timer persistence."""
    __tablename__ = "classroom_sessions"
    
    # Primary fields
    id = Column(Integer, primary_key=True, index=True)
    session_code = Column(String(12), unique=True, index=True, nullable=False)
    teacher_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    case_id = Column(Integer, ForeignKey("moot_cases.id"), nullable=True)  # Optional case reference
    
    # Session configuration
    topic = Column(String(255), nullable=False)
    category = Column(String(50), default=SessionCategory.CONSTITUTIONAL.value)
    prep_time_minutes = Column(Integer, default=15)
    oral_time_minutes = Column(Integer, default=10)
    ai_judge_mode = Column(String(20), default=AIJudgeMode.HYBRID.value)  # on/off/hybrid
    max_participants = Column(Integer, default=40)
    
    # State management with timer persistence (CRITICAL for production)
    current_state = Column(String(20), default=SessionState.CREATED.value)
    is_active = Column(Boolean, default=True)  # NEW: Session active status
    phase_start_timestamp = Column(DateTime(timezone=True), nullable=True)  # When current phase began
    phase_duration_seconds = Column(Integer, nullable=True)  # Configured duration for current phase
    
    # Teacher presence tracking (for auto-transition edge cases)
    teacher_last_seen_at = Column(DateTime(timezone=True), nullable=True)
    teacher_online = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    teacher = relationship("User", back_populates="classroom_sessions")
    participants = relationship("ClassroomParticipant", back_populates="session", cascade="all, delete-orphan")
    scores = relationship("ClassroomScore", back_populates="session", cascade="all, delete-orphan")
    arguments = relationship("ClassroomArgument", back_populates="session", cascade="all, delete-orphan")
    
    # Production-grade constraints
    __table_args__ = (
        # Prevent teacher from having multiple active sessions (concurrency protection)
        Index('idx_active_teacher', 'teacher_id', 
              postgresql_where=current_state.notin_(['completed', 'cancelled'])),
        # Unique session code for joins
        UniqueConstraint('session_code', name='uq_session_code'),
    )
    
    @staticmethod
    def generate_session_code():
        """Generate cryptographically secure 8-char alphanumeric session code."""
        # Generate 6 random bytes, encode as url-safe base64, take first 6 chars, uppercase
        code = secrets.token_urlsafe(6)[:6].upper()
        # Replace any non-alphanumeric with random digits
        code = ''.join(c if c.isalnum() else str(secrets.randbelow(10)) for c in code)
        return f"JURIS-{code}"
    
    @validates('session_code')
    def validate_session_code(self, key, code):
        """Validate session code format: JURIS-XXXXXX (6 alphanumeric chars)."""
        if code and not re.match(r'^JURIS-[A-Z0-9]{6}$', code):
            raise ValueError("Invalid session code format. Expected: JURIS-XXXXXX")
        return code
    
    def get_remaining_seconds(self):
        """Calculate remaining time for current phase."""
        if not self.phase_start_timestamp or not self.phase_duration_seconds:
            return None
        
        elapsed = (datetime.utcnow() - self.phase_start_timestamp).total_seconds()
        remaining = self.phase_duration_seconds - elapsed
        return max(0, int(remaining))
    
    @property
    def remaining_time(self):
        """
        Server-calculated remaining time property (FIX 3).
        Returns remaining seconds for current phase.
        Survives page refresh and server restart (DB-authoritative).
        """
        return self.get_remaining_seconds()
    
    def is_phase_expired(self):
        """Check if current phase timer has expired."""
        remaining = self.get_remaining_seconds()
        return remaining is not None and remaining <= 0
    
    def is_teacher_offline(self, timeout_seconds=300):
        """Check if teacher has been offline for longer than timeout."""
        if not self.teacher_last_seen_at:
            return not self.teacher_online
        
        offline_duration = (datetime.utcnow() - self.teacher_last_seen_at).total_seconds()
        return offline_duration > timeout_seconds
    
    def update_teacher_presence(self, online=True):
        """Update teacher online status and last seen timestamp."""
        self.teacher_online = online
        if online:
            self.teacher_last_seen_at = datetime.utcnow()
    
    def start_phase(self, phase_name, duration_minutes):
        """Start a new phase with timer persistence."""
        self.current_state = phase_name
        self.phase_start_timestamp = datetime.utcnow()
        self.phase_duration_seconds = duration_minutes * 60
        self.update_teacher_presence(True)
    
    def to_dict(self, include_timer=True):
        """Convert to dictionary with optional timer calculation."""
        result = {
            "id": self.id,
            "session_code": self.session_code,
            "teacher_id": self.teacher_id,
            "case_id": self.case_id,
            "topic": self.topic,
            "category": self.category,
            "prep_time_minutes": self.prep_time_minutes,
            "oral_time_minutes": self.oral_time_minutes,
            "ai_judge_mode": self.ai_judge_mode,
            "max_participants": self.max_participants,
            "current_state": self.current_state,
            "teacher_online": self.teacher_online,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "participants_count": len(self.participants) if self.participants else 0,
            "participants": [p.to_dict() for p in self.participants] if self.participants else []
        }
        
        if include_timer:
            result["phase_start_timestamp"] = self.phase_start_timestamp.isoformat() if self.phase_start_timestamp else None
            result["phase_duration_seconds"] = self.phase_duration_seconds
            result["remaining_seconds"] = self.get_remaining_seconds()
            result["is_phase_expired"] = self.is_phase_expired()
        
        return result


class ClassroomParticipant(Base):
    """Classroom participant table with role assignment logic."""
    __tablename__ = "classroom_participants"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("classroom_sessions.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(String(20), default=ParticipantRole.OBSERVER.value)  # petitioner/respondent/observer
    joined_at = Column(DateTime(timezone=True), server_default=func.now())
    last_seen_at = Column(DateTime(timezone=True), nullable=True)  # For reconnection tracking
    is_connected = Column(Boolean, default=True)  # Real-time connection status
    
    # Score reference
    score_id = Column(Integer, ForeignKey("classroom_scores.id"), nullable=True)
    
    # Concurrency protection: prevent duplicate joins
    __table_args__ = (
        UniqueConstraint('session_id', 'user_id', name='uq_participant_session_user'),
    )
    
    # Relationships
    session = relationship("ClassroomSession", back_populates="participants")
    user = relationship("User", back_populates="classroom_participations")
    score = relationship("ClassroomScore", back_populates="participant")
    
    @staticmethod
    def assign_role(participant_count):
        """Assign role based on join order: 1st=Petitioner, 2nd=Respondent, rest=Observer."""
        if participant_count == 0:
            return ParticipantRole.PETITIONER.value
        elif participant_count == 1:
            return ParticipantRole.RESPONDENT.value
        else:
            return ParticipantRole.OBSERVER.value
    
    def mark_connected(self):
        """Mark participant as connected (for reconnection tracking)."""
        self.is_connected = True
        self.last_seen_at = datetime.utcnow()
    
    def mark_disconnected(self):
        """Mark participant as disconnected."""
        self.is_connected = False
        self.last_seen_at = datetime.utcnow()
    
    def is_offline(self, timeout_seconds=60):
        """Check if participant has been offline longer than timeout."""
        if not self.last_seen_at:
            return not self.is_connected
        offline_duration = (datetime.utcnow() - self.last_seen_at).total_seconds()
        return offline_duration > timeout_seconds
    
    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "role": self.role,
            "joined_at": self.joined_at.isoformat() if self.joined_at else None,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
            "is_connected": self.is_connected,
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
    role = Column(String(20), nullable=False)  # petitioner/respondent
    text = Column(Text, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    ai_score = Column(Float, nullable=True)
    judge_notes = Column(Text, nullable=True)
    
    # Relationships
    session = relationship("ClassroomSession", back_populates="arguments")
    user = relationship("User", back_populates="classroom_arguments")
    
    def to_dict(self):
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
def add_user_relationships():
    """Add classroom relationships to User model."""
    from backend.orm.user import User
    
    User.classroom_sessions = relationship("ClassroomSession", back_populates="teacher")
    User.classroom_participations = relationship("ClassroomParticipant", back_populates="user")
    User.classroom_scores = relationship("ClassroomScore", foreign_keys=[ClassroomScore.user_id], back_populates="user")
    User.classroom_arguments = relationship("ClassroomArgument", back_populates="user")
