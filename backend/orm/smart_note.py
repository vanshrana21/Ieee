"""
backend/orm/smart_note.py
Phase 7: Smart Notes with Entity Linking & Tags

DISTINCTION:
- user_notes → Legacy subject-only notes (PRESERVED)
- smart_notes → New flexible notes with entity linking
"""

from sqlalchemy import Column, Integer, String, Text, ForeignKey, Index, JSON, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from backend.orm.base import BaseModel


class ImportanceLevel(str, enum.Enum):
    """Note importance levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SmartNote(BaseModel):
    """
    SmartNote - User's flexible notes with entity linking.
    
    Features:
    - Link to any entity (subject, case, learn content, practice question)
    - Tags for organization
    - Importance levels
    - Full-text content
    - User-owned and private
    
    Differences from UserNotes:
    - Multiple notes per entity allowed
    - Polymorphic entity linking
    - Tag support
    - No unique constraint (users can have multiple notes per entity)
    
    Examples:
    - "Key reasoning in Kesavananda Bharati" → linked to case_id=42
    - "Exam tip: Offer vs Invitation" → linked to subject_id=5, tags=["exam", "contracts"]
    - "Mnemonic for IPC sections" → linked to learn_content_id=120, importance=HIGH
    """
    
    __tablename__ = "smart_notes"
    
    # Ownership
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Owner of this note"
    )
    
    # Content
    title = Column(
        String(300),
        nullable=False,
        comment="Note title"
    )
    
    content = Column(
        Text,
        nullable=False,
        comment="Note content (markdown supported)"
    )
    
    # Polymorphic Entity Linking (optional)
    linked_entity_type = Column(
        String(50),
        nullable=True,
        index=True,
        comment="Entity type: subject, case, learn, practice, or NULL for standalone"
    )
    
    linked_entity_id = Column(
        Integer,
        nullable=True,
        index=True,
        comment="ID of linked entity"
    )
    
    # Organization
    tags = Column(
        JSON,
        nullable=True,
        default=list,
        comment="List of user tags (e.g., ['exam', 'important', 'revision'])"
    )
    
    importance = Column(
    String(10),
    nullable=False,
    default=ImportanceLevel.MEDIUM.value,
    index=True
)

    
    is_pinned = Column(
        Integer,  # SQLite Boolean
        default=0,
        nullable=False,
        index=True,
        comment="1 if pinned to top, 0 otherwise"
    )
    
    # Relationships
    user = relationship(
        "User",
        backref="smart_notes",
        lazy="selectin"
    )
    
    # Database Constraints
    __table_args__ = (
        # Index for user's notes list
        Index(
            'ix_smart_note_user_created',
            'user_id',
            'created_at'
        ),
        # Index for entity lookup
        Index(
            'ix_smart_note_entity',
            'linked_entity_type',
            'linked_entity_id'
        ),
        # Index for user's pinned notes
        Index(
            'ix_smart_note_user_pinned',
            'user_id',
            'is_pinned',
            'importance'
        ),
    )
    
    def __repr__(self):
        entity_str = f" → {self.linked_entity_type}:{self.linked_entity_id}" if self.linked_entity_type else ""
        return f"<SmartNote(id={self.id}, user={self.user_id}, '{self.title[:30]}'{entity_str})>"
    
    def to_dict(self):
        """Convert to API response format"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "content": self.content,
            "linked_entity_type": self.linked_entity_type,
            "linked_entity_id": self.linked_entity_id,
            "tags": self.tags or [],
            "importance": self.importance.value if self.importance else "medium",
            "is_pinned": bool(self.is_pinned),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
