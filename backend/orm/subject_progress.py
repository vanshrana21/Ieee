"""
backend/orm/subject_progress.py
SubjectProgress - Aggregate progress tracking per subject

PHASE 8: Subject-Level Progress

This model provides a SUMMARY view of user's progress in each subject:
- Overall completion percentage
- Last activity timestamp
- Auto-updated when content is completed
- Used for dashboard progress bars

Key Design Decisions:
- One record per user per subject
- Auto-calculated from UserContentProgress
- Denormalized for performance (no joins on dashboard)
- Updates via triggers or application logic
- Completion % = (completed items / total items) * 100
"""
from sqlalchemy import Column, Integer, Float, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.orm.base import BaseModel


class SubjectProgress(BaseModel):
    """
    Tracks overall progress for a subject.
    
    This is an AGGREGATE table that summarizes progress across all content modules
    in a subject. It's updated whenever user completes content.
    
    Examples:
    - Contract Law: 45% complete, last activity 2 hours ago
    - Criminal Law: 100% complete, last activity 3 days ago
    - Tort Law: 0% complete (not started)
    
    Fields:
    - id: Primary key
    - user_id: Who this progress belongs to (FK)
    - subject_id: Which subject (FK)
    - completion_percentage: 0.0 to 100.0
    - total_items: Total content items in subject
    - completed_items: Number of items completed
    - last_activity_at: Most recent interaction with any content in subject
    - created_at: When user first accessed subject
    - updated_at: Last recalculation
    
    Relationships:
    - user: The user
    - subject: The subject
    
    Constraints:
    - Unique: (user_id, subject_id) → One progress record per user per subject
    
    Business Logic:
    - Created on first content access in subject
    - Updated whenever content is completed
    - Completion % = (completed_items / total_items) * 100
    - total_items counts ALL content (learn + cases + practice)
    - last_activity_at updates on ANY content interaction
    
    Calculation Rules:
    - Total items = Count of (LearnContent + CaseContent + PracticeQuestion) for subject
    - Completed items = Count of UserContentProgress where is_completed=True
    - Division by zero protection (0% if total_items=0)
    
    Usage:
    - GET /api/curriculum/dashboard → Show progress bars
    - GET /api/progress/subject/{id} → Detailed progress breakdown
    - Auto-updated by content completion endpoints
    """
    __tablename__ = "subject_progress"
    
    # Foreign Keys
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User who this progress belongs to"
    )
    
    subject_id = Column(
        Integer,
        ForeignKey("subjects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Subject being tracked"
    )
    
    # Progress Metrics
    completion_percentage = Column(
        Float,
        default=0.0,
        nullable=False,
        index=True,
        comment="Overall completion: 0.0 to 100.0"
    )
    
    total_items = Column(
        Integer,
        default=0,
        nullable=False,
        comment="Total content items in subject (learn + cases + practice)"
    )
    
    completed_items = Column(
        Integer,
        default=0,
        nullable=False,
        comment="Number of items user has completed"
    )
    
    # Activity Tracking
    last_activity_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        index=True,
        comment="Most recent content interaction in this subject"
    )
    
    # Relationships
    user = relationship(
        "User",
        back_populates="subject_progress",
        lazy="joined"
    )
    
    subject = relationship(
        "Subject",
        back_populates="subject_progress",
        lazy="joined"
    )
    
    # Database Constraints
    __table_args__ = (
        # Prevent duplicate progress records per user per subject
        UniqueConstraint(
            "user_id",
            "subject_id",
            name="uq_user_subject_progress"
        ),
        # Index for dashboard queries
        Index(
            "ix_user_completion",
            "user_id",
            "completion_percentage"
        ),
        # Index for recent activity
        Index(
            "ix_user_last_activity",
            "user_id",
            "last_activity_at"
        ),
    )
    
    def __repr__(self):
        return (
            f"<SubjectProgress("
            f"user_id={self.user_id}, "
            f"subject_id={self.subject_id}, "
            f"completion={self.completion_percentage:.1f}%)>"
        )
    
    def recalculate_progress(self, completed_count: int, total_count: int):
        """
        Recalculate completion percentage.
        
        Args:
            completed_count: Number of completed items
            total_count: Total items in subject
        
        Updates:
        - completed_items
        - total_items
        - completion_percentage
        """
        self.completed_items = completed_count
        self.total_items = total_count
        
        if total_count > 0:
            self.completion_percentage = round((completed_count / total_count) * 100, 2)
        else:
            self.completion_percentage = 0.0
    
    def update_activity(self):
        """Update last activity timestamp"""
        self.last_activity_at = datetime.utcnow()
    
    def to_dict(self):
        """Convert model to dictionary for API responses"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "subject_id": self.subject_id,
            "completion_percentage": self.completion_percentage,
            "total_items": self.total_items,
            "completed_items": self.completed_items,
            "last_activity_at": self.last_activity_at.isoformat() if self.last_activity_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
    
    def get_status_label(self) -> str:
        """
        Get human-readable status label.
        
        Returns:
            "Not Started" | "In Progress" | "Completed"
        """
        if self.completion_percentage == 0:
            return "Not Started"
        elif self.completion_percentage >= 100:
            return "Completed"
        else:
            return "In Progress"