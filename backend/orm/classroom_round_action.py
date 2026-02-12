"""
Classroom Round Action Model - Phase 7
Immutable event log for round state transitions and actions.
"""
import enum
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text, 
    JSON, Enum, Index
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.orm.base import Base


class ActionType(str, enum.Enum):
    """Types of actions that can be logged for a round."""
    # State transitions
    ROUND_CREATED = "round_created"
    ROUND_STARTED = "round_started"
    STATE_TRANSITION = "state_transition"
    ROUND_PAUSED = "round_paused"
    ROUND_RESUMED = "round_resumed"
    ROUND_COMPLETED = "round_completed"
    ROUND_CANCELLED = "round_cancelled"
    
    # Participant actions
    PARTICIPANT_JOINED = "participant_joined"
    PARTICIPANT_LEFT = "participant_left"
    PARTICIPANT_DISCONNECTED = "participant_disconnected"
    PARTICIPANT_RECONNECTED = "participant_reconnected"
    ROLE_ASSIGNED = "role_assigned"
    
    # Moot actions
    ARGUMENT_SUBMITTED = "argument_submitted"
    OBJECTION_RAISED = "objection_raised"
    OBJECTION_RULED = "objection_ruled"
    QUESTION_ASKED = "question_asked"
    RESPONSE_GIVEN = "response_given"
    
    # Judge actions
    SCORE_SUBMITTED = "score_submitted"
    SCORE_OVERRIDDEN = "score_overridden"
    WINNER_DECLARED = "winner_declared"
    
    # Teacher actions
    FORCE_STATE_CHANGE = "force_state_change"
    TIME_EXTENDED = "time_extended"
    PARTICIPANT_REMOVED = "participant_removed"
    PAIRING_UPDATED = "pairing_updated"
    
    # System actions
    AUTO_TRANSITION = "auto_transition"
    AI_RESPONSE_GENERATED = "ai_response_generated"
    TIMER_EXPIRED = "timer_expired"


class ClassroomRoundAction(Base):
    """
    Immutable event log for classroom rounds.
    
    Every significant action in a round is logged here for audit,
    debugging, and replay purposes. This table should be append-only.
    """
    __tablename__ = "classroom_round_actions"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Foreign keys
    round_id = Column(Integer, ForeignKey("classroom_rounds.id", ondelete="CASCADE"), 
                     nullable=False, index=True)
    session_id = Column(Integer, ForeignKey("classroom_sessions.id", ondelete="CASCADE"), 
                       nullable=False, index=True)
    
    # Actor (who performed the action)
    actor_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    actor_type = Column(String(20), default="user")  # user, ai, system, teacher
    
    # Action details
    action_type = Column(Enum(ActionType), nullable=False, index=True)
    action_description = Column(String(255), nullable=True)
    
    # State context
    from_state = Column(String(50), nullable=True)
    to_state = Column(String(50), nullable=True)
    
    # Payload (arbitrary JSON data specific to action type)
    payload = Column(JSON, nullable=True)
    
    # Timing
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    client_timestamp = Column(DateTime(timezone=True), nullable=True)  # For latency calculation
    
    # Audit
    ip_address = Column(String(45), nullable=True)  # IPv6 compatible
    user_agent = Column(Text, nullable=True)
    
    # Optimistic concurrency (optional, for complex systems)
    sequence_number = Column(Integer, nullable=True)  # Global ordering within round
    
    # Indexes for common queries
    __table_args__ = (
        Index('ix_round_actions_session_type_time', 'session_id', 'action_type', 'created_at'),
        Index('ix_round_actions_round_time', 'round_id', 'created_at'),
        Index('ix_round_actions_actor', 'actor_user_id', 'created_at'),
    )
    
    # Relationships
    round = relationship("ClassroomRound", back_populates="actions")
    session = relationship("ClassroomSession", back_populates="round_actions")
    actor = relationship("User", foreign_keys=[actor_user_id])
    
    def __repr__(self):
        return (f"<ClassroomRoundAction(id={self.id}, type={self.action_type}, "
                f"round_id={self.round_id}, actor={self.actor_user_id})>")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "round_id": self.round_id,
            "session_id": self.session_id,
            "actor_user_id": self.actor_user_id,
            "actor_type": self.actor_type,
            "action_type": self.action_type.value if self.action_type else None,
            "action_description": self.action_description,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "payload": self.payload,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "client_timestamp": self.client_timestamp.isoformat() if self.client_timestamp else None,
            "sequence_number": self.sequence_number
        }
    
    def to_audit_dict(self) -> Dict[str, Any]:
        """Full audit representation including sensitive fields."""
        data = self.to_dict()
        data.update({
            "ip_address": self.ip_address,
            "user_agent": self.user_agent
        })
        return data
    
    @classmethod
    def from_transition(cls, round_id: int, session_id: int, 
                         actor_id: int, action_type: ActionType,
                         from_state: Optional[str], to_state: Optional[str],
                         payload: Optional[Dict] = None,
                         ip_address: Optional[str] = None,
                         user_agent: Optional[str] = None) -> "ClassroomRoundAction":
        """Factory method for creating transition actions."""
        return cls(
            round_id=round_id,
            session_id=session_id,
            actor_user_id=actor_id,
            action_type=action_type,
            from_state=from_state,
            to_state=to_state,
            payload=payload,
            ip_address=ip_address,
            user_agent=user_agent
        )
