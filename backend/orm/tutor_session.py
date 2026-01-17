"""
backend/orm/tutor_session.py
Phase 9A + 4.4: Tutor session tracking with memory support
"""

from sqlalchemy import Column, Integer, String, ForeignKey, Index, DateTime, JSON, Boolean
from datetime import datetime, timedelta
from backend.orm.base import BaseModel

DEFAULT_SESSION_TTL_HOURS = 24

class TutorSession(BaseModel):
    """
    Track tutor conversation sessions with memory support.
    
    Phase 4.4: Session-level continuity with ephemeral memory.
    """
    
    __tablename__ = "tutor_sessions"
    
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Owner of this session"
    )
    
    session_id = Column(
        String(50),
        nullable=False,
        unique=True,
        index=True,
        comment="UUID for this session"
    )
    
    session_name = Column(
        String(100),
        nullable=True,
        comment="User-friendly session name"
    )
    
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
    
    expires_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.utcnow() + timedelta(hours=DEFAULT_SESSION_TTL_HOURS),
        comment="Session expiration timestamp"
    )
    
    preferences = Column(
        JSON,
        nullable=True,
        default=dict,
        comment="Session preferences (tone, format, etc.)"
    )
    
    pinned_preferences = Column(
        JSON,
        nullable=True,
        default=dict,
        comment="Pinned study preferences for this session"
    )
    
    is_ephemeral = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="If true, session is subject to TTL eviction"
    )
    
    __table_args__ = (
        Index('ix_tutor_session_user_activity', 'user_id', 'last_activity_at'),
        Index('ix_tutor_session_expires', 'expires_at'),
    )
    
    def __repr__(self):
        return f"<TutorSession(id={self.id}, session_id={self.session_id}, messages={self.message_count})>"
    
    def increment_message_count(self):
        self.message_count += 1
        self.last_activity_at = datetime.utcnow()
        
    def is_expired(self):
        return datetime.utcnow() > self.expires_at
        
    def extend_ttl(self, hours: int = DEFAULT_SESSION_TTL_HOURS):
        self.expires_at = datetime.utcnow() + timedelta(hours=hours)
        
    def to_dict(self):
        return {
            "session_id": self.session_id,
            "session_name": self.session_name,
            "user_id": self.user_id,
            "message_count": self.message_count,
            "preferences": self.preferences or {},
            "pinned_preferences": self.pinned_preferences or {},
            "is_ephemeral": self.is_ephemeral,
            "started_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "last_activity_at": self.last_activity_at.isoformat() if self.last_activity_at else None
        }
