"""
backend/orm/tutor_message.py
Phase 9A: Tutor conversation messages
"""

from sqlalchemy import Column, Integer, String, Text, ForeignKey, JSON, Float, Index
from backend.orm.base import BaseModel


class TutorMessage(BaseModel):
    """
    Individual messages in a tutor conversation.
    
    Stores both user questions and assistant responses with
    full provenance and confidence tracking.
    """
    
    __tablename__ = "tutor_messages"
    
    # Session reference
    session_id = Column(
        String(50),
        ForeignKey("tutor_sessions.session_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Session this message belongs to"
    )
    
    # Message metadata
    role = Column(
        String(10),
        nullable=False,
        comment="Message role: 'user' or 'assistant'"
    )
    
    content = Column(
        Text,
        nullable=False,
        comment="Message content"
    )
    
    # Provenance (assistant messages only)
    provenance = Column(
        JSON,
        nullable=True,
        comment="List of source documents used: [{doc_id, doc_type, score, snippet}]"
    )
    
    confidence_score = Column(
        Float,
        nullable=True,
        comment="Confidence score (0-1) for assistant responses"
    )
    
    # Indexes
    __table_args__ = (
        Index('ix_tutor_message_session_created', 'session_id', 'created_at'),
    )
    
    def __repr__(self):
        return f"<TutorMessage(id={self.id}, role={self.role}, session={self.session_id})>"
    
    def to_dict(self):
        """Convert to API response format"""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "provenance": self.provenance or [],
            "confidence_score": self.confidence_score,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
