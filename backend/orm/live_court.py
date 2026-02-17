"""
Phase 5 — Hardened Live Courtroom State Machine ORM Models

Server-authoritative with:
- Deterministic event chain hashing
- Immutability constraints
- No float(), no random(), no datetime.now()
- All JSON dumps with sort_keys=True
"""
import hashlib
import json
from datetime import datetime
from enum import Enum as PyEnum
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, 
    Index, UniqueConstraint, Enum, Boolean, Text, Numeric
)
from sqlalchemy.orm import relationship, validates, synonym
from sqlalchemy import event

from backend.database import Base
from backend.orm.live_objection import LiveObjection
from backend.orm.exhibit import SessionExhibit
from backend.core.db_types import UniversalJSON


# =============================================================================
# Enums
# =============================================================================

class LiveCourtStatus(PyEnum):
    NOT_STARTED = "not_started"
    LIVE = "live"
    PAUSED = "paused"
    COMPLETED = "completed"


class OralSide(PyEnum):
    PETITIONER = "petitioner"
    RESPONDENT = "respondent"


class OralTurnType(PyEnum):
    PRESENTATION = "presentation"
    OPENING = "opening"
    ARGUMENT = "argument"
    REBUTTAL = "rebuttal"
    SURREBUTTAL = "surrebuttal"
    SUR_REBUTTAL = "sur_rebuttal"
    QUESTION = "question"
    ANSWER = "answer"


class LiveTurnState(PyEnum):
    PENDING = "pending"
    ACTIVE = "active"
    ENDED = "ended"


class LiveEventType:
    """Event types for live courtroom."""
    SESSION_STARTED = "SESSION_STARTED"
    SESSION_PAUSED = "SESSION_PAUSED"
    SESSION_RESUMED = "SESSION_RESUMED"
    SESSION_COMPLETED = "SESSION_COMPLETED"
    TURN_STARTED = "TURN_STARTED"
    TURN_ENDED = "TURN_ENDED"
    TURN_EXPIRED = "TURN_EXPIRED"
    TIMER_TICK = "TIMER_TICK"
    TURN_INTERRUPTED = "TURN_INTERRUPTED"
    OBJECTION_RAISED = "OBJECTION_RAISED"
    OBJECTION_RESOLVED = "OBJECTION_RESOLVED"
    OBJECTION_SUSTAINED = "OBJECTION_SUSTAINED"
    OBJECTION_OVERRULED = "OBJECTION_OVERRULED"
    TURN_PAUSED_FOR_OBJECTION = "TURN_PAUSED_FOR_OBJECTION"
    TURN_RESUMED_AFTER_OBJECTION = "TURN_RESUMED_AFTER_OBJECTION"
    SCORE_SUBMITTED = "SCORE_SUBMITTED"
    JUDGE_ASSIGNED = "JUDGE_ASSIGNED"
    SPEAKER_CHANGED = "SPEAKER_CHANGED"


class VisibilityMode:
    PRIVATE = "private"
    INSTITUTION = "institution"
    NATIONAL = "national"
    PUBLIC = "public"


class ScoreVisibility:
    HIDDEN = "hidden"
    LIVE = "live"
    AFTER_COMPLETION = "after_completion"


class LiveScoreType:
    ARGUMENT = "argument"
    REBUTTAL = "rebuttal"
    COURTROOM_ETIQUETTE = "courtroom_etiquette"


# =============================================================================
# Model 1: LiveCourtSession
# =============================================================================

class LiveCourtSession(Base):
    __tablename__ = "live_court_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    round_id = Column(
        Integer,
        ForeignKey("tournament_rounds.id", ondelete="RESTRICT"),
        nullable=True
    )
    session_id = Column(
        Integer,
        ForeignKey("classroom_sessions.id", ondelete="RESTRICT"),
        nullable=True,
        index=True
    )
    tournament_match_id = Column(
        Integer,
        ForeignKey("tournament_matches.id", ondelete="RESTRICT"),
        nullable=True,
        index=True
    )
    institution_id = Column(
        Integer,
        ForeignKey("institutions.id", ondelete="RESTRICT"),
        nullable=False
    )
    status = Column(
        Enum(LiveCourtStatus, create_constraint=True),
        nullable=False,
        default=LiveCourtStatus.NOT_STARTED
    )
    current_turn_id = Column(
        Integer,
        ForeignKey("live_turns.id", ondelete="SET NULL"),
        nullable=True
    )
    current_speaker_id = Column(
        Integer,
        ForeignKey("classroom_participants.id", ondelete="SET NULL"),
        nullable=True
    )
    current_side = Column(String(20), nullable=True)
    visibility_mode = Column(
        String(20),
        nullable=False,
        default=VisibilityMode.INSTITUTION
    )
    score_visibility = Column(
        String(20),
        nullable=False,
        default=ScoreVisibility.AFTER_COMPLETION
    )
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    round = relationship("TournamentRound")
    session = relationship("ClassroomSession", foreign_keys=[session_id])
    tournament_match = relationship("TournamentMatch", foreign_keys=[tournament_match_id])
    institution = relationship("Institution")
    current_turn = relationship("LiveTurn", foreign_keys=[current_turn_id])
    current_speaker = relationship("ClassroomParticipant", foreign_keys=[current_speaker_id])
    turns = relationship("LiveTurn", back_populates="session", foreign_keys="LiveTurn.session_id")
    events = relationship("LiveEventLog", back_populates="session")
    objections = relationship("LiveObjection", back_populates="session")  # Phase 6
    exhibits = relationship("SessionExhibit", back_populates="session")  # Phase 7
    judge_scores = relationship("LiveJudgeScore", back_populates="session")
    
    __table_args__ = (
        Index('idx_live_session_round', 'round_id'),
        Index('idx_live_session_institution_status', 'institution_id', 'status'),
        Index('idx_live_session_classroom', 'session_id', 'status'),
        Index('idx_live_session_match', 'tournament_match_id', 'status'),
    )
    
    def is_active(self) -> bool:
        """Check if session is live or paused (started but not completed)."""
        return self.status in (LiveCourtStatus.LIVE, LiveCourtStatus.PAUSED)
    
    def is_completed(self) -> bool:
        """Check if session is completed."""
        return self.status == LiveCourtStatus.COMPLETED
    
    def to_dict(self, include_turns: bool = False, include_events: bool = False) -> Dict[str, Any]:
        """Serialize to dictionary."""
        result = {
            "id": self.id,
            "round_id": self.round_id,
            "session_id": self.session_id,
            "tournament_match_id": self.tournament_match_id,
            "institution_id": self.institution_id,
            "status": self.status.value if self.status else None,
            "current_turn_id": self.current_turn_id,
            "current_speaker_id": self.current_speaker_id,
            "current_side": self.current_side,
            "visibility_mode": self.visibility_mode,
            "score_visibility": self.score_visibility,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        
        if include_turns:
            result["turns"] = [t.to_dict() for t in sorted(
                self.turns, key=lambda x: x.id or 0
            )]
        
        if include_events:
            result["events"] = [e.to_dict() for e in sorted(
                self.events, key=lambda x: x.event_sequence
            )]
        
        return result


# =============================================================================
# Model 2: LiveTurn
# =============================================================================

class LiveTurn(Base):
    __tablename__ = "live_turns"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(
        Integer,
        ForeignKey("live_court_sessions.id", ondelete="RESTRICT"),
        nullable=False
    )
    participant_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False
    )
    side = Column(
        Enum(OralSide, create_constraint=True),
        nullable=False
    )
    turn_type = Column(
        Enum(OralTurnType, create_constraint=True),
        nullable=False
    )
    allocated_seconds = Column(Integer, nullable=False)
    actual_seconds = Column(Integer, nullable=True)
    state = Column(
        Enum(LiveTurnState, create_constraint=True),
        nullable=False,
        default=LiveTurnState.PENDING
    )
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    violation_flag = Column(Boolean, nullable=False, default=False)
    is_timer_paused = Column(Boolean, nullable=False, default=False)  # Phase 6: objection pause
    is_interrupted = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    session = relationship("LiveCourtSession", back_populates="turns", foreign_keys=[session_id])
    participant = relationship("User")
    objections = relationship("LiveObjection", back_populates="turn")  # Phase 6
    exhibits = relationship("SessionExhibit", back_populates="turn")  # Phase 7
    live_session_id = synonym("session_id")
    
    __table_args__ = (
        Index('idx_live_turn_session', 'session_id'),
        Index('idx_live_turn_session_state', 'session_id', 'state'),
    )
    
    def get_elapsed_seconds(self) -> int:
        """
        Calculate elapsed time since turn started.
        Returns 0 if not started yet.
        """
        if not self.started_at:
            return 0
        
        # If ended, return actual duration
        if self.ended_at:
            elapsed = (self.ended_at - self.started_at).total_seconds()
        else:
            # Still active, return elapsed from start to now
            elapsed = (datetime.utcnow() - self.started_at).total_seconds()
        
        # Always return integer (avoid float)
        return int(elapsed)

    def is_active(self) -> bool:
        return self.state == LiveTurnState.ACTIVE
    
    def get_remaining_seconds(self) -> int:
        """
        Calculate remaining time.
        Returns 0 if turn has ended or time exceeded.
        """
        if self.state == LiveTurnState.ENDED or self.violation_flag:
            return 0
        
        if not self.started_at:
            return self.allocated_seconds
        
        elapsed = self.get_elapsed_seconds()
        remaining = self.allocated_seconds - elapsed
        
        # Return max 0 (never negative)
        return max(0, remaining)
    
    def is_time_expired(self) -> bool:
        """Check if time has exceeded allocation."""
        if not self.started_at:
            return False
        
        elapsed = self.get_elapsed_seconds()
        return elapsed > self.allocated_seconds
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "live_session_id": self.session_id,
            "participant_id": self.participant_id,
            "side": self.side.value if self.side else None,
            "turn_type": self.turn_type.value if self.turn_type else None,
            "allocated_seconds": self.allocated_seconds,
            "actual_seconds": self.actual_seconds,
            "state": self.state.value if self.state else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "violation_flag": self.violation_flag,
            "is_timer_paused": self.is_timer_paused,
            "is_interrupted": self.is_interrupted,
            "elapsed_seconds": self.get_elapsed_seconds(),
            "remaining_seconds": self.get_remaining_seconds(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# =============================================================================
# Model 3: LiveEventLog (Append Only)
# =============================================================================

class LiveEventLog(Base):
    __tablename__ = "live_event_log"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(
        Integer,
        ForeignKey("live_court_sessions.id", ondelete="RESTRICT"),
        nullable=False
    )
    event_sequence = Column(Integer, nullable=False)
    event_type = Column(String(40), nullable=False)
    event_payload_json = Column(UniversalJSON, nullable=False, default=dict)
    previous_hash = Column(String(64), nullable=False)
    event_hash = Column(String(64), nullable=False, unique=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    session = relationship("LiveCourtSession", back_populates="events")
    live_session_id = synonym("session_id")
    
    __table_args__ = (
        UniqueConstraint('session_id', 'event_sequence', name='uq_event_session_seq'),
        Index('idx_live_event_session_seq', 'session_id', 'event_sequence'),
        Index('idx_live_event_session', 'session_id'),
    )
    
    @classmethod
    def compute_event_hash(
        cls,
        previous_hash: str,
        event_sequence: int,
        event_type: str,
        payload: Dict[str, Any],
        created_at: datetime
    ) -> str:
        """
        Compute deterministic SHA256 hash for event chain.
        
        Formula:
        SHA256(previous_hash + event_sequence + sorted_json(payload) + created_at_iso)
        """
        # Serialize payload with sort_keys for determinism
        payload_json = json.dumps(payload, sort_keys=True)
        created_at_iso = created_at.isoformat()
        
        combined = (
            str(previous_hash) +
            str(event_sequence) +
            payload_json +
            created_at_iso
        )
        
        return hashlib.sha256(combined.encode()).hexdigest()
    
    def verify_hash(self) -> bool:
        """Verify stored hash matches computed hash."""
        computed = self.compute_event_hash(
            previous_hash=self.previous_hash,
            event_sequence=self.event_sequence,
            event_type=self.event_type,
            payload=self.event_payload_json,
            created_at=self.created_at
        )
        return self.event_hash == computed
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "live_session_id": self.session_id,
            "event_sequence": self.event_sequence,
            "event_type": self.event_type,
            "event_payload_json": self.event_payload_json,
            "previous_hash": self.previous_hash,
            "event_hash": self.event_hash,
            "hash_valid": self.verify_hash(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class LiveJudgeScore(Base):
    __tablename__ = "live_judge_scores"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(
        Integer,
        ForeignKey("live_court_sessions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )
    judge_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )
    participant_id = Column(
        Integer,
        ForeignKey("classroom_participants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )
    score_type = Column(String(50), nullable=False)
    provisional_score = Column(Numeric(10, 2), nullable=False)
    is_final = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    session = relationship("LiveCourtSession", back_populates="judge_scores")
    judge = relationship("User", foreign_keys=[judge_id])
    participant = relationship("ClassroomParticipant", foreign_keys=[participant_id])
    live_session_id = synonym("session_id")

    __table_args__ = (
        Index("idx_live_judge_score_session", "session_id"),
        Index("idx_live_judge_score_judge", "judge_id"),
        Index("idx_live_judge_score_participant", "participant_id"),
        UniqueConstraint("session_id", "judge_id", "participant_id", "score_type", name="uq_live_judge_score"),
    )


# =============================================================================
# Helper Functions
# =============================================================================

async def get_next_event_sequence(session_id: int, db) -> int:
    """
    Get the next event sequence number for a session.
    This should be called within a transaction with appropriate locking.
    """
    from sqlalchemy import select, func
    
    result = await db.execute(
        select(func.coalesce(func.max(LiveEventLog.event_sequence), 0) + 1)
        .where(LiveEventLog.session_id == session_id)
    )
    return result.scalar_one()


def compute_event_hash(
    previous_hash: str,
    event_sequence_or_payload: Any,
    event_payload_or_timestamp: Any,
    timestamp_str: Optional[str] = None
) -> str:
    if timestamp_str is None:
        event_sequence = 0
        payload = event_sequence_or_payload
        timestamp = event_payload_or_timestamp
    else:
        event_sequence = event_sequence_or_payload
        payload = event_payload_or_timestamp
        timestamp = timestamp_str

    if hasattr(timestamp, "isoformat"):
        timestamp_value = timestamp.isoformat()
    else:
        timestamp_value = str(timestamp)

    payload_json = json.dumps(payload or {}, sort_keys=True)
    combined = str(previous_hash) + str(event_sequence) + payload_json + timestamp_value
    return hashlib.sha256(combined.encode()).hexdigest()


# =============================================================================
# ORM Event Listeners (Additional Guards)
# =============================================================================

@event.listens_for(LiveEventLog, 'before_insert')
def validate_event_before_insert(mapper, connection, target):
    """Validate event data before insertion."""
    if target.event_sequence is None or target.event_sequence < 1:
        raise ValueError("event_sequence must be a positive integer")
    
    if not target.event_hash:
        raise ValueError("event_hash is required")
    
    if not target.previous_hash:
        # Genesis event can have empty previous_hash
        target.previous_hash = "0" * 64


@event.listens_for(LiveTurn, 'before_insert')
def validate_turn_before_insert(mapper, connection, target):
    """Validate turn data before insertion."""
    if target.allocated_seconds is None or target.allocated_seconds < 1:
        raise ValueError("allocated_seconds must be a positive integer")


@event.listens_for(LiveCourtSession, 'before_insert')
def validate_session_before_insert(mapper, connection, target):
    """Validate session data before insertion."""
    if not target.status:
        target.status = LiveCourtStatus.NOT_STARTED


LiveSessionStatus = LiveCourtStatus
LiveTurnType = OralTurnType
LiveSessionEvent = LiveEventLog
