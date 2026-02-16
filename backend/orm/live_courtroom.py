"""
Live Courtroom ORM Models — Phase 8

Real-time courtroom session management with:
- Deterministic turn state machine
- Server-authoritative timer enforcement
- Objection workflow engine
- Live judge scoring system
- Append-only hash-chained event log

Security:
- All tables use ON DELETE RESTRICT
- All numeric values use Decimal
- Append-only enforcement on LiveSessionEvent
- Institution-scoped access
"""
import hashlib
import json
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any, List

from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ForeignKey,
    Enum as SQLEnum, Numeric, Index, UniqueConstraint, event
)
from sqlalchemy.orm import relationship, validates

from backend.orm.base import Base
from backend.orm.national_network import SideType


# =============================================================================
# Enums
# =============================================================================

class LiveSessionStatus(str):
    """Live session status states."""
    NOT_STARTED = "not_started"
    LIVE = "live"
    PAUSED = "paused"
    COMPLETED = "completed"


class LiveTurnType(str):
    """Types of courtroom turns."""
    OPENING = "opening"
    ARGUMENT = "argument"
    REBUTTAL = "rebuttal"
    SUR_REBUTTAL = "sur_rebuttal"


class ObjectionType(str):
    """Types of objections that can be raised."""
    LEADING = "leading"
    IRRELEVANT = "irrelevant"
    MISREPRESENTATION = "misrepresentation"
    PROCEDURAL = "procedural"


class ObjectionStatus(str):
    """Status of an objection."""
    PENDING = "pending"
    SUSTAINED = "sustained"
    OVERRULED = "overruled"


class VisibilityMode(str):
    """Visibility modes for live sessions."""
    PRIVATE = "private"
    INSTITUTION = "institution"
    NATIONAL = "national"
    PUBLIC = "public"


class ScoreVisibility(str):
    """When scores are visible to participants."""
    HIDDEN = "hidden"
    LIVE = "live"
    AFTER_COMPLETION = "after_completion"


class LiveScoreType(str):
    """Types of scores judges can submit."""
    ARGUMENT = "argument"
    REBUTTAL = "rebuttal"
    COURTROOM_ETIQUETTE = "courtroom_etiquette"


class LiveEventType(str):
    """Types of events in the live session event log."""
    SESSION_STARTED = "session_started"
    SESSION_PAUSED = "session_paused"
    SESSION_RESUMED = "session_resumed"
    SESSION_COMPLETED = "session_completed"
    TURN_STARTED = "turn_started"
    TURN_ENDED = "turn_ended"
    TURN_EXPIRED = "turn_expired"
    TURN_INTERRUPTED = "turn_interrupted"
    OBJECTION_RAISED = "objection_raised"
    OBJECTION_RESOLVED = "objection_resolved"
    SCORE_SUBMITTED = "score_submitted"
    JUDGE_ASSIGNED = "judge_assigned"
    SPEAKER_CHANGED = "speaker_changed"


# =============================================================================
# Model: LiveCourtSession
# =============================================================================

class LiveCourtSession(Base):
    """
    Represents a live courtroom session.
    
    Can be linked to either a classroom session (practice) or
    a tournament match (competition).
    
    Constraints:
    - Only one LIVE session per tournament_match_id at any time
    - Institution-scoped access control
    """
    __tablename__ = "live_court_sessions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Foreign key relationships (nullable for flexibility)
    session_id = Column(
        Integer,
        ForeignKey("classroom_sessions.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
        comment="FK to classroom_sessions for practice sessions"
    )
    tournament_match_id = Column(
        Integer,
        ForeignKey("tournament_matches.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
        comment="FK to tournament_matches for competition sessions"
    )
    institution_id = Column(
        Integer,
        ForeignKey("institutions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Institution hosting the live session"
    )
    
    # Session state
    status = Column(
        String(20),
        nullable=False,
        default=LiveSessionStatus.NOT_STARTED,
        comment="Session status: not_started, live, paused, completed"
    )
    
    # Current turn tracking
    current_turn_id = Column(
        Integer,
        ForeignKey("live_turns.id", ondelete="SET NULL"),
        nullable=True,
        comment="Currently active turn"
    )
    current_speaker_id = Column(
        Integer,
        ForeignKey("classroom_participants.id", ondelete="SET NULL"),
        nullable=True,
        comment="Current speaker participant"
    )
    current_side = Column(
        String(20),
        nullable=True,
        comment="Current side: petitioner or respondent"
    )
    
    # Visibility settings
    visibility_mode = Column(
        String(20),
        nullable=False,
        default=VisibilityMode.INSTITUTION,
        comment="Visibility: private, institution, national, public"
    )
    score_visibility = Column(
        String(20),
        nullable=False,
        default=ScoreVisibility.AFTER_COMPLETION,
        comment="When scores are visible: hidden, live, after_completion"
    )
    
    # Timing
    started_at = Column(DateTime, nullable=True, comment="When session started")
    ended_at = Column(DateTime, nullable=True, comment="When session ended")
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        comment="Record creation timestamp (UTC)"
    )
    
    # Relationships
    session = relationship("ClassroomSession", foreign_keys=[session_id], back_populates="live_sessions")
    tournament_match = relationship("TournamentMatch", foreign_keys=[tournament_match_id], back_populates="live_sessions")
    institution = relationship("Institution", foreign_keys=[institution_id])
    
    current_turn = relationship("LiveTurn", foreign_keys=[current_turn_id], post_update=True)
    current_speaker = relationship("ClassroomParticipant", foreign_keys=[current_speaker_id])
    
    turns = relationship(
        "LiveTurn",
        foreign_keys="LiveTurn.live_session_id",
        back_populates="live_session",
        order_by="LiveTurn.started_at.asc()"
    )
    objections = relationship(
        "LiveObjection",
        secondary="live_turns",
        primaryjoin="LiveCourtSession.id == LiveTurn.live_session_id",
        secondaryjoin="LiveTurn.id == LiveObjection.live_turn_id",
        viewonly=True
    )
    judge_scores = relationship(
        "LiveJudgeScore",
        foreign_keys="LiveJudgeScore.live_session_id",
        back_populates="live_session"
    )
    events = relationship(
        "LiveSessionEvent",
        foreign_keys="LiveSessionEvent.live_session_id",
        back_populates="live_session",
        order_by="LiveSessionEvent.id.asc()"
    )
    
    # Table constraints
    __table_args__ = (
        # Partial unique index: only one LIVE session per tournament match
        Index(
            'idx_unique_live_per_match',
            'tournament_match_id',
            unique=True,
            postgresql_where=text("status = 'live' AND tournament_match_id IS NOT NULL")
        ),
        # Index for querying by status and institution
        Index('idx_live_sessions_institution_status', 'institution_id', 'status'),
        # Index for session lookup
        Index('idx_live_sessions_session', 'session_id', 'status'),
    )
    
    @validates('status')
    def validate_status(self, key, value):
        allowed = [
            LiveSessionStatus.NOT_STARTED,
            LiveSessionStatus.LIVE,
            LiveSessionStatus.PAUSED,
            LiveSessionStatus.COMPLETED
        ]
        if value not in allowed:
            raise ValueError(f"Invalid status: {value}. Must be one of {allowed}")
        return value
    
    @validates('current_side')
    def validate_current_side(self, key, value):
        if value is None:
            return value
        allowed = [SideType.PETITIONER, SideType.RESPONDENT]
        if value not in allowed:
            raise ValueError(f"Invalid side: {value}. Must be one of {allowed}")
        return value
    
    @validates('visibility_mode')
    def validate_visibility_mode(self, key, value):
        allowed = [
            VisibilityMode.PRIVATE,
            VisibilityMode.INSTITUTION,
            VisibilityMode.NATIONAL,
            VisibilityMode.PUBLIC
        ]
        if value not in allowed:
            raise ValueError(f"Invalid visibility_mode: {value}")
        return value
    
    @validates('score_visibility')
    def validate_score_visibility(self, key, value):
        allowed = [
            ScoreVisibility.HIDDEN,
            ScoreVisibility.LIVE,
            ScoreVisibility.AFTER_COMPLETION
        ]
        if value not in allowed:
            raise ValueError(f"Invalid score_visibility: {value}")
        return value
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "tournament_match_id": self.tournament_match_id,
            "institution_id": self.institution_id,
            "status": self.status,
            "current_turn_id": self.current_turn_id,
            "current_speaker_id": self.current_speaker_id,
            "current_side": self.current_side,
            "visibility_mode": self.visibility_mode,
            "score_visibility": self.score_visibility,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# =============================================================================
# Model: LiveTurn
# =============================================================================

class LiveTurn(Base):
    """
    Represents a single turn/speech in a live courtroom session.
    
    Tracks allocated vs actual time, interruptions, and violations.
    """
    __tablename__ = "live_turns"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    live_session_id = Column(
        Integer,
        ForeignKey("live_court_sessions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )
    participant_id = Column(
        Integer,
        ForeignKey("classroom_participants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Participant giving this turn"
    )
    side = Column(
        String(20),
        nullable=False,
        comment="Side: petitioner or respondent"
    )
    turn_type = Column(
        String(20),
        nullable=False,
        default=LiveTurnType.ARGUMENT,
        comment="Type: opening, argument, rebuttal, sur_rebuttal"
    )
    
    # Timing
    allocated_seconds = Column(
        Integer,
        nullable=False,
        default=300,
        comment="Time allocated for this turn in seconds"
    )
    actual_seconds = Column(
        Integer,
        nullable=True,
        default=0,
        comment="Actual time taken in seconds"
    )
    
    # State tracking
    started_at = Column(DateTime, nullable=True, comment="When turn started")
    ended_at = Column(DateTime, nullable=True, comment="When turn ended")
    is_interrupted = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether turn was interrupted by objection"
    )
    violation_flag = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether time limit was violated"
    )
    
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow
    )
    
    # Relationships
    live_session = relationship(
        "LiveCourtSession",
        foreign_keys=[live_session_id],
        back_populates="turns"
    )
    participant = relationship("ClassroomParticipant", foreign_keys=[participant_id])
    objections = relationship(
        "LiveObjection",
        foreign_keys="LiveObjection.live_turn_id",
        back_populates="turn",
        order_by="LiveObjection.created_at.asc()"
    )
    
    # Table constraints
    __table_args__ = (
        Index('idx_live_turns_session_started', 'live_session_id', 'started_at'),
        Index('idx_live_turns_participant', 'participant_id', 'live_session_id'),
    )
    
    @validates('side')
    def validate_side(self, key, value):
        allowed = [SideType.PETITIONER, SideType.RESPONDENT]
        if value not in allowed:
            raise ValueError(f"Invalid side: {value}. Must be one of {allowed}")
        return value
    
    @validates('turn_type')
    def validate_turn_type(self, key, value):
        allowed = [
            LiveTurnType.OPENING,
            LiveTurnType.ARGUMENT,
            LiveTurnType.REBUTTAL,
            LiveTurnType.SUR_REBUTTAL
        ]
        if value not in allowed:
            raise ValueError(f"Invalid turn_type: {value}")
        return value
    
    def is_active(self) -> bool:
        """Check if turn is currently active."""
        return self.started_at is not None and self.ended_at is None
    
    def get_elapsed_seconds(self) -> int:
        """Get elapsed seconds since turn started."""
        if self.started_at is None:
            return 0
        if self.ended_at is not None:
            return self.actual_seconds or 0
        elapsed = (datetime.utcnow() - self.started_at).total_seconds()
        return int(elapsed)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "live_session_id": self.live_session_id,
            "participant_id": self.participant_id,
            "side": self.side,
            "turn_type": self.turn_type,
            "allocated_seconds": self.allocated_seconds,
            "actual_seconds": self.actual_seconds,
            "elapsed_seconds": self.get_elapsed_seconds(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "is_interrupted": self.is_interrupted,
            "violation_flag": self.violation_flag,
            "is_active": self.is_active(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# =============================================================================
# Model: LiveObjection
# =============================================================================

