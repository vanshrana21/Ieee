"""
backend/orm/topic_mastery.py
Phase 9B: Topic mastery tracking for adaptive practice
"""

from sqlalchemy import Column, Integer, String, Float, ForeignKey, Index, DateTime, UniqueConstraint
from datetime import datetime
from backend.orm.base import BaseModel


class TopicMastery(BaseModel):
    """
    Track user's mastery level for specific topics.
    
    Updated after each practice attempt to enable adaptive difficulty.
    One record per (user, subject, topic_tag) combination.
    
    Mastery score calculation:
    - 0.0-0.3: Beginner (needs easy questions)
    - 0.3-0.7: Intermediate (medium questions)
    - 0.7-1.0: Advanced (hard questions)
    
    Note: No relationship to User to avoid backref conflicts.
    """
    
    __tablename__ = "topic_mastery"
    
    # Foreign keys (no relationships)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User ID"
    )
    
    subject_id = Column(
        Integer,
        ForeignKey("subjects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Subject ID"
    )
    
    # Topic identification
    topic_tag = Column(
        String(100),
        nullable=False,
        index=True,
        comment="Topic tag from practice questions (e.g., 'article-21')"
    )
    
    # Mastery metrics
    mastery_score = Column(
        Float,
        nullable=False,
        default=0.0,
        comment="Mastery score: 0.0 (beginner) to 1.0 (expert)"
    )
    
    attempt_count = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Total practice attempts for this topic"
    )
    
    last_practiced_at = Column(
        DateTime,
        nullable=True,
        comment="Last practice attempt timestamp"
    )
    
    difficulty_level = Column(
        String(10),
        nullable=False,
        default="easy",
        comment="Current recommended difficulty: easy, medium, hard"
    )
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('user_id', 'subject_id', 'topic_tag', name='uq_user_subject_topic'),
        Index('ix_mastery_user_subject', 'user_id', 'subject_id'),
        Index('ix_mastery_score', 'mastery_score'),
    )
    
    def __repr__(self):
        return f"<TopicMastery(user={self.user_id}, topic={self.topic_tag}, score={self.mastery_score:.2f})>"
    
    def update_mastery(self, new_score: float):
        """Update mastery score and difficulty level"""
        self.mastery_score = min(max(new_score, 0.0), 1.0)  # Clamp 0-1
        self.last_practiced_at = datetime.utcnow()
        
        # Set difficulty level based on score
        if self.mastery_score < 0.3:
            self.difficulty_level = "easy"
        elif self.mastery_score < 0.7:
            self.difficulty_level = "medium"
        else:
            self.difficulty_level = "hard"
    
    def to_dict(self):
        """Convert to API response format"""
        return {
            "user_id": self.user_id,
            "subject_id": self.subject_id,
            "topic_tag": self.topic_tag,
            "mastery_score": round(self.mastery_score, 3),
            "attempt_count": self.attempt_count,
            "last_practiced_at": self.last_practiced_at.isoformat() if self.last_practiced_at else None,
            "difficulty_level": self.difficulty_level
        }
