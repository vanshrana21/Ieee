"""
Phase 19 — Moot Courtroom Operations & Live Session Management.

ORM models for deterministic live courtroom session tracking and replay.
"""
from enum import Enum
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Boolean, ForeignKey, DateTime, Text,
    UniqueConstraint, CheckConstraint, Index, text, JSON
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from backend.orm.base import Base


class SessionStatus(str, Enum):
    """Courtroom session status state machine."""
    PENDING = "pending"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"


class ParticipantRole(str, Enum):
    """Roles for session participants."""
    PETITIONER = "petitioner"
    RESPONDENT = "respondent"
    JUDGE = "judge"
    MODERATOR = "moderator"


class ParticipantStatus(str, Enum):
    """Participant connection status."""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"


class CourtroomSession(Base):
    """
    Live courtroom session for scheduled matches.
    
    Links to assignment_id from Phase 18.
    Immutable once COMPLETED.
    
    Attributes:
        id: UUID primary key
        assignment_id: FK to match_schedule_assignments (Phase 18)
        status: Session status
        started_at, ended_at: Session timing
        recording_url: Optional recording storage
        integrity_hash: SHA256 for completed sessions
    """
    __tablename__ = "courtroom_sessions"
    
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()")
    )
    assignment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("match_schedule_assignments.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True
    )
    status = Column(
        String(20),
        nullable=False,
        default=SessionStatus.PENDING
    )
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    recording_url = Column(String(500), nullable=True)
    meta_data_json = Column("metadata", JSON, nullable=True)
    integrity_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    participations = relationship(
        "SessionParticipation",
        back_populates="session",
        cascade="all, delete-orphan"
    )
    observations = relationship(
        "SessionObservation",
        back_populates="session",
        cascade="all, delete-orphan"
    )
    logs = relationship(
        "SessionLogEntry",
        back_populates="session",
        cascade="all, delete-orphan"
    )
    
    __table_args__ = (
        CheckConstraint(
            f"status IN ('{SessionStatus.PENDING}', '{SessionStatus.ACTIVE}', "
            f"'{SessionStatus.PAUSED}', '{SessionStatus.COMPLETED}')",
            name="ck_session_status_valid"
        ),
        Index("idx_session_assignment", "assignment_id"),
        Index("idx_session_status", "status"),
    )
    
    def to_dict(self):
        return {
            "id": str(self.id),
            "assignment_id": str(self.assignment_id),
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "recording_url": self.recording_url,
            "metadata": self.meta_data_json,
            "integrity_hash": self.integrity_hash,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class SessionParticipation(Base):
    """
    Participant entry/exit tracking for replay.
    
    Records every connection/disconnection for deterministic replay.
    
    Attributes:
        id: UUID primary key
        session_id: FK to courtroom_sessions
        user_id: FK to users
        role: Participant role (petitioner/respondent/judge/moderator)
        status: Connection status
        joined_at, left_at: Timing
        connection_count: Reconnection tracking
    """
    __tablename__ = "session_participations"
    
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()")
    )
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("courtroom_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    role = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default=ParticipantStatus.CONNECTED)
    joined_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    left_at = Column(DateTime, nullable=True)
    connection_count = Column(Integer, default=1, nullable=False)
    client_info = Column(JSON, nullable=True)  # IP, user agent hash
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    session = relationship("CourtroomSession", back_populates="participations")
    
    __table_args__ = (
        CheckConstraint(
            f"role IN ('{ParticipantRole.PETITIONER}', '{ParticipantRole.RESPONDENT}', "
            f"'{ParticipantRole.JUDGE}', '{ParticipantRole.MODERATOR}')",
            name="ck_participant_role_valid"
        ),
        CheckConstraint(
            f"status IN ('{ParticipantStatus.CONNECTED}', '{ParticipantStatus.DISCONNECTED}', "
            f"'{ParticipantStatus.RECONNECTING}')",
            name="ck_participant_status_valid"
        ),
        CheckConstraint(
            "connection_count > 0",
            name="ck_connection_count_positive"
        ),
        Index("idx_participation_session", "session_id"),
        Index("idx_participation_user", "user_id"),
    )
    
    def to_dict(self):
        return {
            "id": str(self.id),
            "session_id": str(self.session_id),
            "user_id": str(self.user_id),
            "role": self.role,
            "status": self.status,
            "joined_at": self.joined_at.isoformat() if self.joined_at else None,
            "left_at": self.left_at.isoformat() if self.left_at else None,
            "connection_count": self.connection_count,
            "client_info": self.client_info,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class SessionObservation(Base):
    """
    Observer (audience) tracking for session replay.
    
    Tracks who observed the session and when (for access logs).
    
    Attributes:
        id: UUID primary key
        session_id: FK to courtroom_sessions
        user_id: FK to users (nullable for anonymous)
        observed_at: When they joined as observer
        left_at: When they left
    """
    __tablename__ = "session_observations"
    
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()")
    )
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("courtroom_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    observed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    left_at = Column(DateTime, nullable=True)
    client_info = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    session = relationship("CourtroomSession", back_populates="observations")
    
    __table_args__ = (
        Index("idx_observation_session", "session_id"),
        Index("idx_observation_user", "user_id"),
    )
    
    def to_dict(self):
        return {
            "id": str(self.id),
            "session_id": str(self.session_id),
            "user_id": str(self.user_id) if self.user_id else None,
            "observed_at": self.observed_at.isoformat() if self.observed_at else None,
            "left_at": self.left_at.isoformat() if self.left_at else None,
            "client_info": self.client_info,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class SessionLogEntry(Base):
    """
    Immutable audit log for courtroom operations.
    
    Records all significant events for replay and compliance.
    
    Attributes:
        id: UUID primary key
        session_id: FK to courtroom_sessions
        timestamp: When event occurred
        event_type: Type of event
        actor_id: Who performed the action
        details: JSON event details
        hash_chain: SHA256 linking to previous log entry
    """
    __tablename__ = "session_log_entries"
    
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()")
    )
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("courtroom_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    event_type = Column(String(50), nullable=False, index=True)
    actor_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    details = Column(JSON, nullable=False)
    hash_chain = Column(String(64), nullable=False)
    sequence_number = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    session = relationship("CourtroomSession", back_populates="logs")
    
    __table_args__ = (
        # Unique sequence per session
        UniqueConstraint(
            "session_id", "sequence_number",
            name="uq_log_sequence"
        ),
        Index("idx_log_session", "session_id"),
        Index("idx_log_timestamp", "timestamp"),
        Index("idx_log_event_type", "event_type"),
        Index("idx_log_actor", "actor_id"),
    )
    
    def to_dict(self):
        return {
            "id": str(self.id),
            "session_id": str(self.session_id),
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "event_type": self.event_type,
            "actor_id": str(self.actor_id) if self.actor_id else None,
            "details": self.details,
            "hash_chain": self.hash_chain,
            "sequence_number": self.sequence_number,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
