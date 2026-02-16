"""
Session State Transition Model

Defines allowed state transitions for the classroom session state machine.
This is a data-driven approach where transitions are stored in the database.
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Index
from sqlalchemy.sql import func

from backend.orm.base import Base


class SessionStateTransition(Base):
    """
    Defines allowed state transitions for classroom sessions.
    
    Attributes:
        id: Primary key
        from_state: Source state (e.g., 'CREATED', 'PREPARING')
        to_state: Target state (e.g., 'PREPARING', 'ARGUING_PETITIONER')
        trigger_type: What triggers this transition (e.g., 'faculty_action', 'round_completed')
        requires_all_rounds_complete: Whether all rounds must be completed before this transition
        requires_faculty: Whether faculty authorization is required
        created_at: When this transition rule was created
    """
    __tablename__ = 'session_state_transitions'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    from_state = Column(String(50), nullable=False)
    to_state = Column(String(50), nullable=False)
    trigger_type = Column(String(50), nullable=True)
    requires_all_rounds_complete = Column(Boolean, nullable=False, default=False)
    requires_faculty = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    
    __table_args__ = (
        Index('ix_session_state_transitions_from_state', 'from_state'),
    )
    
    def __repr__(self):
        return f"<SessionStateTransition({self.from_state} -> {self.to_state})>"
    
    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            'id': self.id,
            'from_state': self.from_state,
            'to_state': self.to_state,
            'trigger_type': self.trigger_type,
            'requires_all_rounds_complete': self.requires_all_rounds_complete,
            'requires_faculty': self.requires_faculty,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
