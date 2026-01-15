"""
backend/orm/tutor_session.py
Phase 9A: Tutor session tracking
"""

from sqlalchemy import Column, Integer, String, ForeignKey, Index, DateTime
from datetime import datetime
from backend.orm.base import BaseModel


class TutorSession(BaseModel):
    """
    Track tutor conversation sessions.
    
    Each session represents one continuous conversation between
    a user and the AI tutor. Sessions persist across page refreshes.
    
    Note: No relationship to User to avoid backref conflicts.
    """
    
    __tablename__ = "tutor_sessions"
    
    # Foreign key (no relationship)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Owner of this session"
    )
    
    # Session identifier
    session_id = Column(
        String(50),
        nullable=False,
        unique=True,
        index=True,
        comment="UUID for this session"
    )
    
    # Metadata
    message_count = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of messages in this session"
    )
    
    last_activity_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        comment="Last message timestamp"
    )
    
    # Indexes
    __table_args__ = (
        Index('ix_tutor_session_user_activity', 'user_id', 'last_activity_at'),
    )
    
    def __repr__(self):
        return f"<TutorSession(id={self.id}, session_id={self.session_id}, messages={self.message_count})>"
    
    def increment_message_count(self):
        """Increment message count and update activity timestamp"""
        self.message_count += 1
        self.last_activity_at = datetime.utcnow()
