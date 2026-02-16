"""
Classroom Round Model - Phase 7
Represents individual moot court rounds within a classroom session.
"""
import enum
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text, 
    JSON, Enum, Boolean, Float, Index
)
from sqlalchemy.orm import relationship, validates
from sqlalchemy.sql import func

from backend.orm.base import Base


class RoundState(str, enum.Enum):
    """Canonical round state machine states."""
    WAITING = "waiting"
    ARGUMENT_PETITIONER = "argument_petitioner"
    ARGUMENT_RESPONDENT = "argument_respondent"
    REBUTTAL = "rebuttal"
    SUR_REBUTTAL = "sur_rebuttal"
    JUDGE_QUESTIONS = "judge_questions"
    SCORING = "scoring"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class PairingMode(str, enum.Enum):
    """Pairing modes for assigning students to rounds."""
    RANDOM = "random"
    MANUAL = "manual"
    SKILL = "skill"
    AI_FALLBACK = "ai_fallback"


class ClassroomRound(Base):
    """
    Individual moot court round within a classroom session.
    
    Each round represents a single debate between petitioner and respondent,
    overseen by a judge, with strict state machine enforcement.
    """
    __tablename__ = "classroom_rounds"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Foreign keys
    session_id = Column(Integer, ForeignKey("classroom_sessions.id", ondelete="CASCADE"), 
                        nullable=False, index=True)
    
    # Participants
    petitioner_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # Can be AI
    respondent_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # Can be AI
    judge_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # Can be AI/teacher
    
    # AI fallback tracking
    petitioner_is_ai = Column(Boolean, default=False)
    respondent_is_ai = Column(Boolean, default=False)
    judge_is_ai = Column(Boolean, default=False)
    ai_opponent_session_id = Column(Integer, ForeignKey("ai_opponent_sessions.id"), nullable=True)
    
    # State machine
    state = Column(Enum(RoundState), default=RoundState.WAITING, nullable=False, index=True)
    previous_state = Column(Enum(RoundState), nullable=True)  # For pause/resume
    
    # Timing
    time_limit_seconds = Column(Integer, default=600)  # 10 minutes default
    started_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    state_started_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Timer persistence (DB-authoritative)
    phase_start_timestamp = Column(DateTime(timezone=True), nullable=True)
    phase_duration_seconds = Column(Integer, nullable=True)
    
    # Scoring
    petitioner_score = Column(Float, nullable=True)
    respondent_score = Column(Float, nullable=True)
    winner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Content
    case_title = Column(String(255), nullable=True)
    case_summary = Column(Text, nullable=True)
    logs = Column(JSON, default=list)  # Event log for this round
    transcript = Column(Text, nullable=True)  # Full round transcript
    
    # Metadata
    round_number = Column(Integer, default=1)  # Round sequence in session
    pairing_mode = Column(Enum(PairingMode), default=PairingMode.RANDOM)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    version = Column(Integer, default=1)  # Optimistic locking
    
    # Indexes for common queries
    __table_args__ = (
        Index('ix_classroom_rounds_session_state', 'session_id', 'state'),
        Index('ix_classroom_rounds_petitioner', 'petitioner_id'),
        Index('ix_classroom_rounds_respondent', 'respondent_id'),
    )
    
    # Relationships
    session = relationship("ClassroomSession", back_populates="rounds")
    petitioner = relationship("User", foreign_keys=[petitioner_id], 
                            back_populates="rounds_as_petitioner")
    respondent = relationship("User", foreign_keys=[respondent_id], 
                            back_populates="rounds_as_respondent")
    judge = relationship("User", foreign_keys=[judge_id], 
                      back_populates="rounds_as_judge")
    winner = relationship("User", foreign_keys=[winner_id])
    actions = relationship("ClassroomRoundAction", back_populates="round", 
                          cascade="all, delete-orphan", lazy="dynamic")
    turns = relationship("ClassroomTurn", back_populates="round", 
                      cascade="all, delete-orphan", order_by="ClassroomTurn.turn_order")
    
    # AI session reference
    ai_session = relationship("AIOpponentSession", foreign_keys=[ai_opponent_session_id])
    
    def __repr__(self):
        return f"<ClassroomRound(id={self.id}, state={self.state}, session_id={self.session_id})>"
    
    @validates('state')
    def validate_state(self, key, state):
        """Validate state transitions (enforced server-side)."""
        if isinstance(state, str):
            state = RoundState(state)
        return state
    
    def get_remaining_seconds(self) -> Optional[int]:
        """Calculate remaining time for current phase (server-authoritative)."""
        if not self.phase_start_timestamp or not self.phase_duration_seconds:
            return None
        
        elapsed = (datetime.utcnow() - self.phase_start_timestamp).total_seconds()
        remaining = self.phase_duration_seconds - elapsed
        return max(0, int(remaining))
    
    @property
    def remaining_time(self) -> Optional[int]:
        """Server-calculated remaining time property."""
        return self.get_remaining_seconds()
    
    def is_phase_expired(self) -> bool:
        """Check if current phase timer has expired."""
        remaining = self.get_remaining_seconds()
        return remaining is not None and remaining <= 0
    
    def start_phase(self, phase_name: str, duration_seconds: int):
        """Start a new phase with timer persistence."""
        from backend.state_machines.round_state import RoundState
        
        if isinstance(phase_name, str):
            phase_name = RoundState(phase_name)
        
        self.state = phase_name
        self.phase_start_timestamp = datetime.utcnow()
        self.phase_duration_seconds = duration_seconds
        
        if phase_name == RoundState.ARGUMENT_PETITIONER and not self.started_at:
            self.started_at = datetime.utcnow()
    
    def add_log_entry(self, action_type: str, actor_id: int, 
                     payload: Optional[Dict[str, Any]] = None):
        """Add an entry to the round logs."""
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "action_type": action_type,
            "actor_id": actor_id,
            "payload": payload or {},
            "state": self.state.value if self.state else None
        }
        if self.logs is None:
            self.logs = []
        self.logs.append(entry)
    
    def pause(self):
        """Pause the round, preserving state for resume."""
        self.previous_state = self.state
        self.state = RoundState.PAUSED
        self.add_log_entry("round_paused", 0, {"from_state": self.previous_state.value if self.previous_state else None})
    
    def resume(self):
        """Resume the round from paused state."""
        if self.previous_state:
            self.state = self.previous_state
            self.previous_state = None
            self.add_log_entry("round_resumed", 0, {"to_state": self.state.value})
    
    def complete(self, winner_id: Optional[int] = None):
        """Mark round as completed."""
        self.state = RoundState.COMPLETED
        self.ended_at = datetime.utcnow()
        if winner_id:
            self.winner_id = winner_id
        self.add_log_entry("round_completed", 0, {"winner_id": winner_id})
    
    def to_dict(self, include_logs: bool = False) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        result = {
            "id": self.id,
            "session_id": self.session_id,
            "round_number": self.round_number,
            "state": self.state.value if self.state else None,
            "previous_state": self.previous_state.value if self.previous_state else None,
            
            # Participants
            "petitioner_id": self.petitioner_id,
            "petitioner_is_ai": self.petitioner_is_ai,
            "respondent_id": self.respondent_id,
            "respondent_is_ai": self.respondent_is_ai,
            "judge_id": self.judge_id,
            "judge_is_ai": self.judge_is_ai,
            
            # Timing
            "time_limit_seconds": self.time_limit_seconds,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "remaining_seconds": self.get_remaining_seconds(),
            "is_phase_expired": self.is_phase_expired(),
            
            # Scoring
            "petitioner_score": self.petitioner_score,
            "respondent_score": self.respondent_score,
            "winner_id": self.winner_id,
            
            # Content
            "case_title": self.case_title,
            "case_summary": self.case_summary,
            
            # Metadata
            "pairing_mode": self.pairing_mode.value if self.pairing_mode else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "version": self.version
        }
        
        if include_logs and self.logs:
            result["logs"] = self.logs
        
        return result
    
    def to_minimal_dict(self) -> Dict[str, Any]:
        """Minimal representation for list views."""
        return {
            "id": self.id,
            "round_number": self.round_number,
            "state": self.state.value if self.state else None,
            "petitioner_id": self.petitioner_id,
            "respondent_id": self.respondent_id,
            "winner_id": self.winner_id,
            "remaining_seconds": self.get_remaining_seconds()
        }
