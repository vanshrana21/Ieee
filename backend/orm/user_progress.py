"""
backend/orm/user_progress.py
UserProgress - Tracks student learning (minimal for Phase 3)
"""
from sqlalchemy import Column, Integer, Float, ForeignKey, Enum as SQLEnum, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from enum import Enum
from backend.orm.base import Base


class ProgressStatus(str, Enum):
    """Progress status for modules"""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class UserProgress(Base):
    """
    Tracks which modules each user has started/completed.
    
    Phase 3: Basic structure only
    Phase 4: Will add time tracking, percentage, etc.
    """
    __tablename__ = "user_progress"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign Keys
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    subject_id = Column(
        Integer,
        ForeignKey("subjects.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    module_id = Column(
        Integer,
        ForeignKey("content_modules.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Progress tracking
    status = Column(
        SQLEnum(ProgressStatus),
        nullable=False,
        default=ProgressStatus.NOT_STARTED,
        index=True
    )
    
    progress_percentage = Column(Float, default=0.0, nullable=False)
    
    # Relationships
    # ✅ CORRECT (unidirectional)
    subject = relationship("Subject", lazy="joined")
    module = relationship("ContentModule", lazy="joined")


    
    # Constraints
    __table_args__ = (
        UniqueConstraint("user_id", "module_id", name="uq_user_module_progress"),
        Index("ix_user_subject_status", "user_id", "subject_id", "status"),
    )
    
    def __repr__(self):
        return f"<UserProgress(user_id={self.user_id}, module_id={self.module_id})>"