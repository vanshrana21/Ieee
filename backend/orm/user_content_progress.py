"""
backend/orm/user_content_progress.py
UserContentProgress - Tracks individual content items completed by users

PHASE 8: Learning Progress Tracking

This model records EVERY piece of content a user interacts with:
- LearnContent items read
- CaseContent items reviewed
- PracticeQuestion items attempted

Purpose:
- Track what user has seen/completed
- Resume learning from last position
- Calculate completion percentages
- Foundation for analytics

Key Design Decisions:
- Polymorphic tracking (content_type + content_id)
- Separate table from attempts (attempts have their own table)
- Immutable completion timestamp
- Nullable last_viewed_at for re-visits
"""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Index, UniqueConstraint, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
from enum import Enum
from backend.orm.base import BaseModel


class ContentType(str, Enum):
    """
    Types of content that can be tracked.
    
    - LEARN: LearnContent items (theory/concepts)
    - CASE: CaseContent items (case law)
    - PRACTICE: PracticeQuestion items (questions/exercises)
    
    Note: UserNotes are NOT tracked here (user-owned content)
    """
    LEARN = "learn"
    CASE = "case"
    PRACTICE = "practice"


class UserContentProgress(BaseModel):
    """
    Tracks individual content item completion and viewing.
    
    Examples:
    - User reads "What is Contract?" (LearnContent) → Record created
    - User reviews "Carlill v Carbolic" (CaseContent) → Record created
    - User attempts MCQ question → Record created (separate from attempt)
    
    Fields:
    - id: Primary key
    - user_id: Who interacted with content (FK)
    - content_type: Type of content (learn/case/practice)
    - content_id: ID of the content item
    - is_completed: True when user marks as complete
    - completed_at: When marked complete (NULL if not completed)
    - last_viewed_at: Most recent view timestamp
    - view_count: Number of times viewed
    - time_spent_seconds: Total time spent (optional, for future analytics)
    - created_at: First interaction timestamp
    - updated_at: Last modification
    
    Relationships:
    - user: The user who viewed/completed content
    
    Constraints:
    - Unique: (user_id, content_type, content_id) → One record per user per content
    
    Business Logic:
    - First view → Record created with is_completed=False
    - Mark complete → Set is_completed=True, completed_at=NOW
    - Re-visit → Update last_viewed_at, increment view_count
    - Cannot uncomplete (completion is permanent)
    
    Usage:
    - GET /api/progress/subject/{id} → Returns completion stats
    - POST /api/progress/content/complete → Marks content complete
    - GET /api/progress/resume → Returns last_viewed_at content
    """
    __tablename__ = "user_content_progress"
    
    # Foreign Keys
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User who interacted with content"
    )
    
    # Polymorphic Content Reference
    content_type = Column(
        SQLEnum(ContentType),
        nullable=False,
        index=True,
        comment="Type of content (learn/case/practice)"
    )
    
    content_id = Column(
        Integer,
        nullable=False,
        index=True,
        comment="ID of the content item (polymorphic reference)"
    )
    
    # Completion Tracking
    is_completed = Column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
        comment="True when user marks content as complete"
    )
    
    completed_at = Column(
        DateTime,
        nullable=True,
        index=True,
        comment="Timestamp when marked complete (NULL if not completed)"
    )
    
    # Activity Tracking
    last_viewed_at = Column(
        DateTime,
        nullable=False,
        index=True,
        default=datetime.utcnow,
        comment="Most recent view timestamp (for resume learning)"
    )
    
    view_count = Column(
        Integer,
        default=1,
        nullable=False,
        comment="Number of times user viewed this content"
    )
    
    time_spent_seconds = Column(
        Integer,
        nullable=True,
        comment="Total time spent on content (optional, for analytics)"
    )
    
    # Relationships
    user = relationship(
        "User",
        back_populates="content_progress",
        lazy="joined"
    )
    
    # Database Constraints
    __table_args__ = (
        # Prevent duplicate progress records per user per content
        UniqueConstraint(
            "user_id",
            "content_type",
            "content_id",
            name="uq_user_content_progress"
        ),
        # Composite index for user's progress queries
        Index(
            "ix_user_completion_status",
            "user_id",
            "is_completed",
            "last_viewed_at"
        ),
        # Index for resume learning (recent activity)
        Index(
            "ix_user_recent_activity",
            "user_id",
            "last_viewed_at"
        ),
        # Index for content type queries
        Index(
            "ix_content_type_id",
            "content_type",
            "content_id"
        ),
    )
    
    def __repr__(self):
        return (
            f"<UserContentProgress("
            f"user_id={self.user_id}, "
            f"type={self.content_type}, "
            f"content_id={self.content_id}, "
            f"completed={self.is_completed})>"
        )
    
    def mark_complete(self):
        """
        Mark content as completed.
        
        Rules:
        - Sets is_completed=True
        - Sets completed_at=NOW (only if not already set)
        - Cannot uncomplete (idempotent operation)
        """
        if not self.is_completed:
            self.is_completed = True
            self.completed_at = datetime.utcnow()
    
    def record_view(self, time_spent: int = None):
        """
        Record a content view.
        
        Args:
            time_spent: Optional time spent in seconds
        
        Updates:
        - last_viewed_at to NOW
        - Increments view_count
        - Adds to time_spent_seconds if provided
        """
        self.last_viewed_at = datetime.utcnow()
        self.view_count += 1
        
        if time_spent is not None:
            if self.time_spent_seconds is None:
                self.time_spent_seconds = 0
            self.time_spent_seconds += time_spent
    
    def to_dict(self):
        """Convert model to dictionary for API responses"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "content_type": self.content_type.value if self.content_type else None,
            "content_id": self.content_id,
            "is_completed": self.is_completed,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "last_viewed_at": self.last_viewed_at.isoformat() if self.last_viewed_at else None,
            "view_count": self.view_count,
            "time_spent_seconds": self.time_spent_seconds,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }