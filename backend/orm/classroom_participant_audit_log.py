"""
Classroom Participant Audit Log Model

For tracking all participant assignment attempts and joins.
This is critical for dispute resolution in moot court competitions.
"""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Index
from sqlalchemy.sql import func

from backend.orm.base import Base


class ClassroomParticipantAuditLog(Base):
    """
    Audit log for participant joins and assignments.
    
    Every join attempt is logged with:
    - Success/failure status
    - Side and speaker number assigned (or attempted)
    - IP address for traceability
    - Timestamp for ordering
    
    This table is append-only. Never delete or modify records.
    """
    __tablename__ = "classroom_participant_audit_log"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Session and user references
    session_id = Column(Integer, ForeignKey("classroom_sessions.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Assignment details (what was assigned or attempted)
    side = Column(String(20), nullable=True)  # PETITIONER / RESPONDENT
    speaker_number = Column(Integer, nullable=True)  # 1 or 2
    position = Column(Integer, nullable=True)  # Join order position (1-4)
    
    # Outcome tracking
    is_successful = Column(Boolean, default=True)
    error_message = Column(String(255), nullable=True)
    
    # Metadata for forensics
    ip_address = Column(String(45), nullable=True)  # IPv6 compatible
    user_agent = Column(String(255), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Indexes for common queries
    __table_args__ = (
        # Query by session
        Index('idx_audit_session', 'session_id', 'created_at'),
        # Query by user
        Index('idx_audit_user', 'user_id', 'created_at'),
        # Query by session+user for duplicate detection
        Index('idx_audit_session_user', 'session_id', 'user_id'),
    )
    
    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "side": self.side,
            "speaker_number": self.speaker_number,
            "position": self.position,
            "is_successful": self.is_successful,
            "error_message": self.error_message,
            "ip_address": self.ip_address,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
