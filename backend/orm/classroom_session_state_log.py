"""
Classroom Session State Log Model

Audit trail for all session state transitions.
Tracks who made changes, when, and why.
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.orm.base import Base


class ClassroomSessionStateLog(Base):
    """
    Audit log for classroom session state transitions.
    
    Every state change is logged here for compliance and debugging.
    
    Attributes:
        id: Primary key
        session_id: FK to classroom_sessions
        from_state: Previous state
        to_state: New state
        triggered_by_user_id: Who initiated the transition (nullable for system triggers)
        trigger_type: Type of trigger (faculty_action, round_completed, etc.)
        reason: Optional explanation for the transition
        is_successful: Whether the transition succeeded
        error_message: Error details if transition failed
        created_at: When the log entry was created
    """
    __tablename__ = 'classroom_session_state_log'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey('classroom_sessions.id', ondelete='CASCADE'), nullable=False)
    from_state = Column(String(50), nullable=False)
    to_state = Column(String(50), nullable=False)
    triggered_by_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    trigger_type = Column(String(50), nullable=True)
    reason = Column(Text, nullable=True)
    is_successful = Column(Boolean, nullable=False, default=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    
    # Relationships
    session = relationship("ClassroomSession", back_populates="state_logs", lazy="selectin")
    triggered_by_user = relationship("User", lazy="selectin")
    
    __table_args__ = (
        Index('ix_classroom_session_state_log_session_id', 'session_id'),
        Index('ix_classroom_session_state_log_created_at', 'created_at'),
    )
    
    def __repr__(self):
        status = "SUCCESS" if self.is_successful else "FAILED"
        return f"<ClassroomSessionStateLog({self.from_state} -> {self.to_state}, {status})>"
    
    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            'id': self.id,
            'session_id': self.session_id,
            'from_state': self.from_state,
            'to_state': self.to_state,
            'triggered_by_user_id': self.triggered_by_user_id,
            'trigger_type': self.trigger_type,
            'reason': self.reason,
            'is_successful': self.is_successful,
            'error_message': self.error_message,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
