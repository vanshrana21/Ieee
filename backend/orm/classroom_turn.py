"""
Classroom Turn ORM Model — Phase 3

Represents an individual turn within a classroom round.
Each turn tracks speaking time, transcript, and submission status.
"""
from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, 
    UniqueConstraint, Index, Boolean, Text
)
from sqlalchemy.orm import relationship

from backend.orm.base import Base


class ClassroomTurn(Base):
    """
    Represents a single speaking turn within a round.
    
    Each turn has:
    - A participant who speaks
    - An order within the round (1..M)
    - Allowed speaking time in seconds
    - Timestamps for start and submission
    - Transcript and word count
    - Submission status tracking
    """
    __tablename__ = "classroom_turns"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    round_id = Column(
        Integer, 
        ForeignKey("classroom_rounds.id", ondelete="CASCADE"), 
        nullable=False
    )
    participant_id = Column(
        Integer, 
        ForeignKey("classroom_participants.id", ondelete="CASCADE"), 
        nullable=False
    )
    turn_order = Column(Integer, nullable=False)  # 1..M order within round
    allowed_seconds = Column(Integer, nullable=False)  # speaking time allowed
    
    # Timing
    started_at = Column(DateTime, nullable=True)
    submitted_at = Column(DateTime, nullable=True)
    
    # Content
    transcript = Column(Text, nullable=True)
    word_count = Column(Integer, nullable=True)
    
    # Status
    is_submitted = Column(Boolean, nullable=False, default=False)
    
    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True, onupdate=datetime.utcnow)
    
    # Constraints
    __table_args__ = (
        UniqueConstraint("round_id", "turn_order", name="uq_turn_round_order"),
        UniqueConstraint("round_id", "participant_id", name="uq_turn_round_participant"),
        Index("idx_turns_round", "round_id"),
        Index("idx_turns_participant", "participant_id"),
    )
    
    # Relationships
    round = relationship("ClassroomRound", back_populates="turns")
    participant = relationship("ClassroomParticipant", back_populates="turns")
    audit_logs = relationship(
        "ClassroomTurnAudit",
        back_populates="turn",
        cascade="all, delete-orphan",
        order_by="ClassroomTurnAudit.created_at"
    )
    
    def __repr__(self) -> str:
        return (
            f"<ClassroomTurn(id={self.id}, round_id={self.round_id}, "
            f"participant_id={self.participant_id}, order={self.turn_order}, "
            f"submitted={self.is_submitted})>"
        )
    
    @property
    def is_started(self) -> bool:
        """Check if turn has been started."""
        return self.started_at is not None
    
    @property
    def duration_seconds(self) -> Optional[int]:
        """Calculate turn duration if submitted."""
        if self.started_at and self.submitted_at:
            return int((self.submitted_at - self.started_at).total_seconds())
        return None
    
    @property
    def is_late(self) -> bool:
        """Check if submission was after allowed time."""
        if self.started_at and self.submitted_at:
            actual_duration = (self.submitted_at - self.started_at).total_seconds()
            return actual_duration > self.allowed_seconds
        return False
    
    @property
    def remaining_seconds(self) -> Optional[int]:
        """Calculate remaining time if turn is active."""
        if self.started_at and not self.is_submitted:
            elapsed = (datetime.utcnow() - self.started_at).total_seconds()
            remaining = self.allowed_seconds - elapsed
            return max(0, int(remaining))
        return None
    
    @property
    def is_expired(self) -> bool:
        """Check if turn time has expired."""
        remaining = self.remaining_seconds
        return remaining is not None and remaining <= 0


class ClassroomTurnAudit(Base):
    """
    Append-only audit log for turn actions.
    
    Records all significant events:
    - START: Turn started by participant
    - SUBMIT: Transcript submitted
    - AUTO_SUBMIT: Auto-submitted on timeout
    - TIME_EXPIRED: Timer expired
    - OVERRIDE: Faculty force action
    """
    __tablename__ = "classroom_turn_audit"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    turn_id = Column(
        Integer, 
        ForeignKey("classroom_turns.id", ondelete="CASCADE"), 
        nullable=False
    )
    action = Column(String(32), nullable=False)  # START, SUBMIT, AUTO_SUBMIT, TIME_EXPIRED, OVERRIDE
    actor_user_id = Column(Integer, nullable=False)
    payload_json = Column(Text, nullable=True)  # JSON string for additional data
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Index for efficient querying
    __table_args__ = (
        Index("idx_turn_audit_turn", "turn_id"),
        Index("idx_turn_audit_created", "created_at"),
    )
    
    # Relationships
    turn = relationship("ClassroomTurn", back_populates="audit_logs")
    
    def __repr__(self) -> str:
        return (
            f"<ClassroomTurnAudit(id={self.id}, turn_id={self.turn_id}, "
            f"action={self.action}, actor={self.actor_user_id})>"
        )
