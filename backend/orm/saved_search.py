"""
backend/orm/saved_search.py
Phase 6.2: Saved Search Queries
Stores user's search preferences for quick re-execution
"""

from sqlalchemy import Column, Integer, String, Text, ForeignKey, Index, DateTime, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.orm.base import Base

class SavedSearch(Base):
    """
    User-saved search queries with filters.
    
    Design:
    - Stores search parameters, not results
    - Results computed at execution time
    - Access control applied dynamically
    - Named by user for organization
    
    Security:
    - Search execution respects current course/semester
    - Cannot retrieve locked/future content
    - Ownership strictly validated
    
    Examples:
    - "Constitutional Law Cases" → query="article 21", filters={content_types: ["case"], subject_id: 5}
    - "Contract Practice Questions" → query="offer acceptance", filters={content_types: ["practice"]}
    """
    
    __tablename__ = "saved_searches"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # User relationship
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User who saved this search"
    )
    
    # Search metadata
    name = Column(
        String(100),
        nullable=False,
        comment="User-defined name for this search"
    )
    
    description = Column(
        Text,
        nullable=True,
        comment="Optional description"
    )
    
    # Search parameters (stored as JSON)
    query = Column(
        String(500),
        nullable=False,
        comment="Search keyword(s)"
    )
    
    filters = Column(
        JSON,
        nullable=True,
        comment="Search filters: content_types, subject_id, semester, etc."
    )
    
    # Timestamps
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        index=True,
        comment="When search was saved"
    )
    
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="When search was last modified"
    )
    
    last_executed_at = Column(
        DateTime,
        nullable=True,
        comment="When search was last executed"
    )
    
    # Relationships
    user = relationship(
    "User",
    back_populates="saved_searches",
    lazy="selectin"
)
    
    # Database Constraints
    __table_args__ = (
        # Index for user's searches
        Index(
            'ix_saved_search_user',
            'user_id',
            'created_at'
        ),
    )
    
    def __repr__(self):
        return f"<SavedSearch(id={self.id}, user_id={self.user_id}, name='{self.name}')>"
    
    def to_dict(self):
        """Convert saved search to dictionary"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "description": self.description,
            "query": self.query,
            "filters": self.filters or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_executed_at": self.last_executed_at.isoformat() if self.last_executed_at else None
        }
