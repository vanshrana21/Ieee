"""
backend/orm/user_notes.py
UserNotes model - User's personal notes

IMPORTANT DISTINCTION:
- LearnContent, CaseContent, PracticeQuestion → SUBJECT-OWNED (admin-created)
- UserNotes → USER-OWNED (student-created)

Each user can have multiple notes per subject.
Notes are private and not shared with other users.

Structure: User → UserNotes (many-to-many with subjects)
"""
from sqlalchemy import Column, Integer, String, Text, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import relationship
from backend.orm.base import BaseModel


class UserNotes(BaseModel):
    """
    UserNotes represents a user's personal note for a subject.
    
    Unlike other content models, notes are USER-OWNED:
    - Each user creates their own notes
    - Notes are private (not visible to other users)
    - One note per user per subject (can be updated)
    
    Examples:
    - User's summary of "Contract Law"
    - Personal exam tips for "Criminal Law"
    - Mnemonics and shortcuts
    
    Fields:
    - id: Primary key
    - user_id: Owner of the note (FK)
    - subject_id: Subject this note is about (FK)
    - title: Note title (optional, defaults to subject name)
    - content: The actual note content (markdown supported)
    - is_pinned: True if user wants this note at top
    - created_at: When note was created
    - updated_at: Last modification time
    
    Relationships:
    - user: The student who owns this note
    - subject: The subject this note is about
    
    Constraints:
    - Unique: (user_id, subject_id) → One note per user per subject
    
    Usage:
    - Accessed via GET /api/subjects/{id}/notes (user-specific)
    - Create/Update via POST/PUT /api/subjects/{id}/notes
    - Only the owner can read/edit their notes
    """
    __tablename__ = "user_notes"
    
    # Foreign Keys
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Owner of this note"
    )
    
    subject_id = Column(
        Integer,
        ForeignKey("subjects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Subject this note is about"
    )
    
    # Note Content
    title = Column(
        String(300),
        nullable=True,
        comment="Note title (optional, defaults to subject name)"
    )
    
    content = Column(
        Text,
        nullable=False,
        comment="The actual note content (markdown supported)"
    )
    
    # Metadata
    is_pinned = Column(
        Integer,  # SQLite doesn't have Boolean, using 0/1
        default=0,
        nullable=False,
        index=True,
        comment="1 if user wants this note at top, 0 otherwise"
    )
    
    # Relationships
    user = relationship(
        "User",
        back_populates="notes",
        lazy="joined"
    )
    
    subject = relationship(
        "Subject",
        back_populates="user_notes",
        lazy="joined"
    )
    
    # Database Constraints
    __table_args__ = (
        # Prevent duplicate notes for same user-subject combo
        UniqueConstraint(
            "user_id",
            "subject_id",
            name="uq_user_subject_note"
        ),
        # Composite index for user's notes list
        Index(
            "ix_user_pinned",
            "user_id",
            "is_pinned"
        ),
    )
    
    def __repr__(self):
        return (
            f"<UserNotes("
            f"id={self.id}, "
            f"user_id={self.user_id}, "
            f"subject_id={self.subject_id})>"
        )
    
    def to_dict(self):
        """Convert model to dictionary for API responses"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "subject_id": self.subject_id,
            "title": self.title,
            "content": self.content,
            "is_pinned": bool(self.is_pinned),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }