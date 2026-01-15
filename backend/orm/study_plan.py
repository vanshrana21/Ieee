"""
backend/orm/study_plan.py
Phase 9C: Study plan tracking
"""

from sqlalchemy import Column, Integer, String, Text, ForeignKey, Boolean, Index
from backend.orm.base import BaseModel


class StudyPlan(BaseModel):
    """
    User's personalized study plan.
    
    Generated based on:
    - Topic mastery scores
    - Tutor interaction patterns
    - Practice attempt history
    
    Only ONE active plan per user at a time.
    Old plans are deactivated when new plan is created.
    
    Note: No relationship to User to avoid backref conflicts.
    """
    
    __tablename__ = "study_plans"
    
    # Foreign key (no relationship)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User ID"
    )
    
    # Plan metadata
    duration_weeks = Column(
        Integer,
        nullable=False,
        comment="Plan duration in weeks"
    )
    
    summary = Column(
        Text,
        nullable=False,
        comment="Human-readable plan summary"
    )
    
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
        comment="Only one active plan per user"
    )
    
    # Indexes
    __table_args__ = (
        Index('ix_study_plan_user_active', 'user_id', 'is_active'),
    )
    
    def __repr__(self):
        return f"<StudyPlan(id={self.id}, user={self.user_id}, weeks={self.duration_weeks}, active={self.is_active})>"
    
    def deactivate(self):
        """Deactivate this plan"""
        self.is_active = False
    
    def to_dict(self):
        """Convert to API response format"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "duration_weeks": self.duration_weeks,
            "summary": self.summary,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
