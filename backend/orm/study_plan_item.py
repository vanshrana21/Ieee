"""
backend/orm/study_plan_item.py
Phase 9C: Individual study plan items (weekly tasks)
"""

from sqlalchemy import Column, Integer, String, Text, ForeignKey, JSON, Index
from backend.orm.base import BaseModel


class StudyPlanItem(BaseModel):
    """
    Individual item in a study plan (one topic for one week).
    
    Each item represents:
    - WHAT to study (topic_tag)
    - WHEN to study it (week_number)
    - WHY to study it (rationale)
    - HOW MUCH time (estimated_hours)
    - WHAT ACTIONS to take (recommended_actions)
    
    All recommendations are explainable and derived from:
    - Mastery scores
    - Tutor interaction frequency
    - Practice performance
    """
    
    __tablename__ = "study_plan_items"
    
    # Foreign key
    plan_id = Column(
        Integer,
        ForeignKey("study_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Parent study plan"
    )
    
    # Scheduling
    week_number = Column(
        Integer,
        nullable=False,
        comment="Week number in plan (1-based)"
    )
    
    # Content identification
    subject_id = Column(
        Integer,
        ForeignKey("subjects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Subject ID"
    )
    
    topic_tag = Column(
        String(100),
        nullable=False,
        index=True,
        comment="Topic tag (from topic_mastery)"
    )
    
    # Recommendations
    recommended_actions = Column(
        JSON,
        nullable=False,
        comment="List of specific actions: ['Review cases', 'Practice 3 questions']"
    )
    
    estimated_hours = Column(
        Integer,
        nullable=False,
        default=2,
        comment="Estimated study hours for this topic"
    )
    
    priority = Column(
        String(10),
        nullable=False,
        comment="Priority level: high, medium, low"
    )
    
    rationale = Column(
        Text,
        nullable=False,
        comment="Explanation of why this topic is included"
    )
    
    # Indexes
    __table_args__ = (
        Index('ix_plan_item_plan_week', 'plan_id', 'week_number'),
    )
    
    def __repr__(self):
        return f"<StudyPlanItem(plan={self.plan_id}, week={self.week_number}, topic={self.topic_tag})>"
    
    def to_dict(self):
        """Convert to API response format"""
        return {
            "id": self.id,
            "plan_id": self.plan_id,
            "week_number": self.week_number,
            "subject_id": self.subject_id,
            "topic_tag": self.topic_tag,
            "recommended_actions": self.recommended_actions or [],
            "estimated_hours": self.estimated_hours,
            "priority": self.priority,
            "rationale": self.rationale
        }
