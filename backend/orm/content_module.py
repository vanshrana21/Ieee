"""
backend/orm/content_module.py
ContentModule model - Container for learning content types

Each subject has 4 module types:
- LEARN: Theory and concepts
- CASES: Case law database
- PRACTICE: Practice questions
- NOTES: User's personal notes

Modules can be:
- active: Available to enrolled users
- locked: Requires prerequisite or premium
- coming_soon: Placeholder for future content
"""
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import relationship
from enum import Enum
from backend.orm.base import BaseModel


class ModuleType(str, Enum):
    """
    Types of learning modules.
    
    - LEARN: Theoretical content (concepts, definitions, explanations)
    - CASES: Case law database (judgments, ratios, applications)
    - PRACTICE: Practice questions (MCQs, essay questions)
    - NOTES: User's personal notes (separate table - user_notes)
    """
    LEARN = "learn"
    CASES = "cases"
    PRACTICE = "practice"
    NOTES = "notes"


class ModuleStatus(str, Enum):
    """
    Module availability status.
    
    - ACTIVE: Content available to enrolled users
    - LOCKED: Requires prerequisite or premium subscription
    - COMING_SOON: Placeholder, content not ready yet
    """
    ACTIVE = "active"
    LOCKED = "locked"
    COMING_SOON = "coming_soon"


class ContentModule(BaseModel):
    """
    ContentModule represents a learning content container for a subject.
    
    Each subject has UP TO 4 modules (one per ModuleType).
    Modules act as containers for actual content items.
    
    Examples:
    - Subject: "Contract Law" → Module: LEARN → LearnContent items
    - Subject: "Criminal Law" → Module: CASES → CaseContent items
    
    Fields:
    - id: Primary key
    - subject_id: Parent subject (FK)
    - module_type: Type of content (learn/cases/practice/notes)
    - status: Availability (active/locked/coming_soon)
    - is_free: True if accessible without premium
    - title: Display name (e.g., "Learn Contract Law")
    - description: Brief description for UI
    - order_index: Display order in UI
    - created_at: When module was created
    - updated_at: Last modification time
    
    Relationships:
    - subject: Parent subject
    - learn_items: LearnContent items (if module_type == LEARN)
    - case_items: CaseContent items (if module_type == CASES)
    - practice_items: PracticeQuestion items (if module_type == PRACTICE)
    
    Constraints:
    - Unique: (subject_id, module_type) → One module per type per subject
    
    Access Control:
    - If status == LOCKED → Return 403 (no content)
    - If status == COMING_SOON → Return 200 + metadata (no content)
    - If is_free == False → Check user premium status
    """
    __tablename__ = "content_modules"
    
    # Foreign Keys
    subject_id = Column(
        Integer,
        ForeignKey("subjects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Reference to subjects table"
    )
    
    # Module Configuration
    module_type = Column(
        String(20),
        nullable=False,
        index=True,
        comment="Type of learning content"
    )
    
    status = Column(
        String(20),
        nullable=False,
        default="active",
        index=True,
        comment="Module availability status"
    )
    
    is_free = Column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
        comment="True if accessible without premium subscription"
    )
    
    # Display Information
    title = Column(
        String(200),
        nullable=False,
        comment="Display name (e.g., 'Learn Contract Law')"
    )
    
    description = Column(
        String(500),
        nullable=True,
        comment="Brief description for UI cards"
    )
    
    order_index = Column(
        Integer,
        default=0,
        nullable=False,
        comment="Display order in UI (lower = first)"
    )
    
    # Relationships
    subject = relationship(
        "Subject",
        back_populates="content_modules",
        lazy="joined"
    )
    
    learn_items = relationship(
        "LearnContent",
        back_populates="module",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="LearnContent.order_index"
    )
    
    case_items = relationship(
        "CaseContent",
        back_populates="module",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="CaseContent.case_name"
    )
    
    practice_items = relationship(
        "PracticeQuestion",
        back_populates="module",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="PracticeQuestion.order_index"
    )
    
    # Database Constraints
    __table_args__ = (
        # Prevent duplicate module titles per subject per type
        UniqueConstraint(
            "subject_id",
            "module_type",
            "title",
            name="uq_subject_module_title"
        ),
        # Composite index for common queries
        Index(
            "ix_subject_status_type",
            "subject_id",
            "status",
            "module_type"
        ),
    )
    
    def __repr__(self):
        return (
            f"<ContentModule("
            f"id={self.id}, "
            f"subject_id={self.subject_id}, "
            f"type={self.module_type}, "
            f"status={self.status})>"
        )
    
    def to_dict(self):
        """Convert model to dictionary for API responses"""
        return {
            "id": self.id,
            "subject_id": self.subject_id,
            "module_type": self.module_type.value if self.module_type else None,
            "status": self.status.value if self.status else None,
            "is_free": self.is_free,
            "title": self.title,
            "description": self.description,
            "order_index": self.order_index,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
    
    def can_user_access(self, user) -> tuple[bool, str]:
        """
        Check if user can access this module.
        
        Args:
            user: User object with premium status
        
        Returns:
            (can_access: bool, reason: str)
        """
        # Locked modules are always inaccessible
        if self.status == ModuleStatus.LOCKED:
            return False, "This module is currently locked"
        
        # Coming soon modules return metadata only
        if self.status == ModuleStatus.COMING_SOON:
            return False, "Content coming soon"
        
        # Premium content check
        if not self.is_free and not user.is_premium:
            return False, "Premium subscription required"
        
        # Active + accessible
        return True, "Access granted"
    
    def get_item_count(self) -> int:
        """Get total number of content items in this module"""
        if self.module_type == ModuleType.LEARN:
            return len(self.learn_items) if self.learn_items else 0
        elif self.module_type == ModuleType.CASES:
            return len(self.case_items) if self.case_items else 0
        elif self.module_type == ModuleType.PRACTICE:
            return len(self.practice_items) if self.practice_items else 0
        return 0