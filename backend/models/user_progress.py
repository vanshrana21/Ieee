"""
backend/models/user_progress.py
UserProgress model for tracking student learning progress
"""
from sqlalchemy import (
    Column,
    Integer,
    String,
    ForeignKey,
    Enum as SQLEnum,
    UniqueConstraint,
    Index,
    Float,
    DateTime
)
from sqlalchemy.orm import relationship
from enum import Enum
from datetime import datetime
from backend.models.base import BaseModel


class ProgressStatus(str, Enum):
    """
    Progress status for content modules.
    
    - NOT_STARTED: User hasn't begun this module
    - IN_PROGRESS: User is currently working on this module
    - COMPLETED: User has finished this module
    """
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class UserProgress(BaseModel):
    """
    UserProgress tracks student learning progress across subjects and modules.
    
    Tracks:
    - Which modules a user has started
    - Which modules are in progress
    - Which modules are completed
    - Time spent on each module
    - Last access time
    
    This enables:
    - Dashboard showing progress overview
    - Resume functionality (continue where you left off)
    - Analytics and insights
    - Completion certificates
    
    Fields:
    - id: Primary key
    - user_id: Foreign key to users
    - subject_id: Foreign key to subjects
    - module_id: Foreign key to content_modules
    - status: not_started / in_progress / completed
    - progress_percentage: 0-100 (for granular tracking)
    - time_spent_minutes: Total time spent in minutes
    - last_accessed_at: Last time user opened this module
    - completed_at: When module was completed
    - created_at: When progress tracking started
    - updated_at: Last update time
    
    Relationships:
    - user: The student
    - subject: The law subject
    - module: The specific content module
    
    Constraints:
    - Unique: (user_id, module_id)
      → One progress record per user per module
    """
    __tablename__ = "user_progress"
    
    # Foreign Keys
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Reference to users table"
    )
    
    subject_id = Column(
        Integer,
        ForeignKey("subjects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Reference to subjects table"
    )
    
    module_id = Column(
        Integer,
        ForeignKey("content_modules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Reference to content_modules table"
    )
    
    # Progress Information
    status = Column(
        SQLEnum(ProgressStatus),
        nullable=False,
        default=ProgressStatus.NOT_STARTED,
        index=True,
        comment="Current progress status"
    )
    
    progress_percentage = Column(
        Float,
        default=0.0,
        nullable=False,
        comment="Progress percentage (0.0 to 100.0)"
    )
    
    time_spent_minutes = Column(
        Integer,
        default=0,
        nullable=False,
        comment="Total time spent in minutes"
    )
    
    # Timestamps
    last_accessed_at = Column(
        DateTime,
        nullable=True,
        comment="Last time user accessed this module"
    )
    
    completed_at = Column(
        DateTime,
        nullable=True,
        comment="When module was completed"
    )
    
    # Relationships
    user = relationship(
        "User",
        back_populates="progress",
        lazy="joined"
    )
    
    subject = relationship(
        "Subject",
        back_populates="user_progress",
        lazy="joined"
    )
    
    module = relationship(
        "ContentModule",
        back_populates="user_progress",
        lazy="joined"
    )
    
    # Database Constraints
    __table_args__ = (
        # Prevent duplicate progress records
        UniqueConstraint(
            "user_id",
            "module_id",
            name="uq_user_module_progress"
        ),
        # Composite index for common queries
        Index(
            "ix_user_subject_status",
            "user_id",
            "subject_id",
            "status"
        ),
    )
    
    def __repr__(self):
        return (
            f"<UserProgress("
            f"user_id={self.user_id}, "
            f"module_id={self.module_id}, "
            f"status='{self.status}')>"
        )
    
    def to_dict(self):
        """Convert model to dictionary for API responses"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "subject_id": self.subject_id,
            "module_id": self.module_id,
            "status": self.status.value if self.status else None,
            "progress_percentage": self.progress_percentage,
            "time_spent_minutes": self.time_spent_minutes,
            "last_accessed_at": self.last_accessed_at.isoformat() if self.last_accessed_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
    
    def mark_in_progress(self):
        """Mark module as in progress"""
        if self.status == ProgressStatus.NOT_STARTED:
            self.status = ProgressStatus.IN_PROGRESS
        self.last_accessed_at = datetime.utcnow()
    
    def mark_completed(self):
        """Mark module as completed"""
        self.status = ProgressStatus.COMPLETED
        self.progress_percentage = 100.0
        self.completed_at = datetime.utcnow()
        self.last_accessed_at = datetime.utcnow()
    
    def update_progress(self, percentage: float):
        """
        Update progress percentage.
        
        Args:
            percentage: Progress percentage (0-100)
        """
        self.progress_percentage = max(0.0, min(100.0, percentage))
        self.last_accessed_at = datetime.utcnow()
        
        # Auto-complete if 100%
        if self.progress_percentage >= 100.0 and self.status != ProgressStatus.COMPLETED:
            self.mark_completed()
        elif self.status == ProgressStatus.NOT_STARTED:
            self.status = ProgressStatus.IN_PROGRESS
    
    def add_time_spent(self, minutes: int):
        """
        Add time spent on this module.
        
        Args:
            minutes: Minutes to add
        """
        self.time_spent_minutes += minutes
        self.last_accessed_at = datetime.utcnow()


# ============================================
# QUERY HELPER FUNCTIONS
# ============================================

async def get_user_progress_for_subject(db_session, user_id: int, subject_id: int):
    """
    Get all progress records for a user in a subject.
    
    Args:
        db_session: AsyncSession
        user_id: User ID
        subject_id: Subject ID
    
    Returns:
        List of progress records
    """
    from sqlalchemy import select
    
    stmt = (
        select(UserProgress)
        .where(
            UserProgress.user_id == user_id,
            UserProgress.subject_id == subject_id
        )
        .order_by(UserProgress.updated_at.desc())
    )
    
    result = await db_session.execute(stmt)
    return result.scalars().all()


async def get_user_progress_for_module(db_session, user_id: int, module_id: int):
    """
    Get progress record for a specific module.
    
    Args:
        db_session: AsyncSession
        user_id: User ID
        module_id: Module ID
    
    Returns:
        UserProgress or None
    """
    from sqlalchemy import select
    
    stmt = (
        select(UserProgress)
        .where(
            UserProgress.user_id == user_id,
            UserProgress.module_id == module_id
        )
    )
    
    result = await db_session.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_overall_progress(db_session, user_id: int):
    """
    Get overall progress statistics for a user.
    
    Args:
        db_session: AsyncSession
        user_id: User ID
    
    Returns:
        Dictionary with progress statistics
    """
    from sqlalchemy import select, func
    
    # Count by status
    stmt = (
        select(
            UserProgress.status,
            func.count(UserProgress.id).label("count")
        )
        .where(UserProgress.user_id == user_id)
        .group_by(UserProgress.status)
    )
    
    result = await db_session.execute(stmt)
    status_counts = {row.status.value: row.count for row in result}
    
    # Get total time spent
    time_stmt = (
        select(func.sum(UserProgress.time_spent_minutes))
        .where(UserProgress.user_id == user_id)
    )
    
    time_result = await db_session.execute(time_stmt)
    total_time = time_result.scalar() or 0
    
    return {
        "not_started": status_counts.get("not_started", 0),
        "in_progress": status_counts.get("in_progress", 0),
        "completed": status_counts.get("completed", 0),
        "total_time_minutes": total_time
    }


async def create_or_update_progress(
    db_session,
    user_id: int,
    module_id: int,
    subject_id: int,
    status: ProgressStatus = None,
    progress_percentage: float = None,
    time_spent: int = None
):
    """
    Create or update progress record for a module.
    
    Args:
        db_session: AsyncSession
        user_id: User ID
        module_id: Module ID
        subject_id: Subject ID
        status: Optional new status
        progress_percentage: Optional progress percentage
        time_spent: Optional time to add (minutes)
    
    Returns:
        UserProgress record
    """
    from sqlalchemy import select
    
    # Check if progress exists
    stmt = (
        select(UserProgress)
        .where(
            UserProgress.user_id == user_id,
            UserProgress.module_id == module_id
        )
    )
    
    result = await db_session.execute(stmt)
    progress = result.scalar_one_or_none()
    
    if not progress:
        # Create new progress record
        progress = UserProgress(
            user_id=user_id,
            module_id=module_id,
            subject_id=subject_id,
            status=status or ProgressStatus.NOT_STARTED
        )
        db_session.add(progress)
    
    # Update fields
    if status:
        progress.status = status
    
    if progress_percentage is not None:
        progress.update_progress(progress_percentage)
    
    if time_spent:
        progress.add_time_spent(time_spent)
    
    await db_session.commit()
    await db_session.refresh(progress)
    
    return progress