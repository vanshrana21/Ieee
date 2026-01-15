"""
backend/orm/bookmark.py
Phase 6.2: User Bookmarks
Polymorphic design supporting multiple content types
"""

from sqlalchemy import Column, Integer, String, ForeignKey, Index, UniqueConstraint, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.orm.base import Base

class Bookmark(Base):
    """
    User bookmarks for any content type.
    
    Design:
    - Polymorphic: Single table for all content types
    - content_type: 'subject' | 'learn' | 'case' | 'practice'
    - content_id: ID of the bookmarked item
    - Unique constraint prevents duplicates per user
    
    Security:
    - Access control validated at API level
    - Course/semester restrictions enforced on retrieval
    - No direct foreign keys to allow flexible content types
    
    Examples:
    - Bookmark subject: content_type='subject', content_id=5
    - Bookmark case: content_type='case', content_id=120
    - Bookmark practice: content_type='practice', content_id=45
    """
    
    __tablename__ = "bookmarks"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # User relationship
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User who created the bookmark"
    )
    
    # Polymorphic content reference
    content_type = Column(
        String(20),
        nullable=False,
        index=True,
        comment="Type: subject, learn, case, practice"
    )
    
    content_id = Column(
        Integer,
        nullable=False,
        index=True,
        comment="ID of the bookmarked content"
    )
    
    # Optional note
    note = Column(
        String(500),
        nullable=True,
        comment="Optional user note for this bookmark"
    )
    
    # Timestamps
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        index=True,
        comment="When bookmark was created"
    )
    
    # Relationships
    user = relationship(
    "User",
    back_populates="bookmarks",
    lazy="selectin"
)

    
    # Database Constraints
    __table_args__ = (
        # Prevent duplicate bookmarks
        UniqueConstraint(
            'user_id', 
            'content_type', 
            'content_id',
            name='uq_user_content_bookmark'
        ),
        # Composite index for user's bookmarks by type
        Index(
            'ix_bookmark_user_type',
            'user_id',
            'content_type',
            'created_at'
        ),
        # Index for content lookup
        Index(
            'ix_bookmark_content',
            'content_type',
            'content_id'
        ),
    )
    
    def __repr__(self):
        return f"<Bookmark(user_id={self.user_id}, type={self.content_type}, content_id={self.content_id})>"
    
    def to_dict(self):
        """Convert bookmark to dictionary"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "content_type": self.content_type,
            "content_id": self.content_id,
            "note": self.note,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
