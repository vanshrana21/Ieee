"""
backend/orm/learn_content.py
LearnContent model - Theoretical learning content for LEARN modules

Each LearnContent item represents one lesson/topic in a subject.
Examples:
- "What is a Contract?" (Contract Law)
- "Elements of Criminal Liability" (Criminal Law)
- "Doctrine of Precedent" (Legal Methods)
"""
from sqlalchemy import Column, Integer, String, Text, ForeignKey, Index
from sqlalchemy.orm import relationship
from backend.orm.base import BaseModel


class LearnContent(BaseModel):
    """
    LearnContent stores theoretical learning material.
    
    Structure:
    - Title: Topic name
    - Summary: Brief overview (for cards/lists)
    - Body: Full content (Markdown supported)
    - Order: Display sequence
    
    Relationships:
    - module: Parent ContentModule (module_type must be LEARN)
    
    Access Control:
    - Inherits from parent module's access rules
    - If module is locked/premium → content is locked/premium
    
    Frontend Usage:
    - List view: Show title + summary + estimated_time
    - Detail view: Show full body (fetched separately)
    """
    __tablename__ = "learn_content"
    
    # Foreign Key
    module_id = Column(
        Integer,
        ForeignKey("content_modules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Reference to parent content module"
    )
    
    # Content Fields
    title = Column(
        String(300),
        nullable=False,
        index=True,
        comment="Topic title (e.g., 'What is a Contract?')"
    )
    
    summary = Column(
        Text,
        nullable=True,
        comment="Brief overview for list/card view (1-2 sentences)"
    )
    
    body = Column(
        Text,
        nullable=False,
        comment="Full learning content (Markdown supported)"
    )
    
    # Display Configuration
    order_index = Column(
        Integer,
        default=0,
        nullable=False,
        index=True,
        comment="Display order within module (lower = first)"
    )
    
    estimated_time_minutes = Column(
        Integer,
        nullable=True,
        comment="Estimated reading time in minutes"
    )
    
    # Relationships
    module = relationship(
        "ContentModule",
        back_populates="learn_items",
        lazy="joined"
    )
    
    # Indexes
    __table_args__ = (
        Index("ix_learn_module_order", "module_id", "order_index"),
    )
    
    def __repr__(self):
        return f"<LearnContent(id={self.id}, title='{self.title[:30]}...')>"
    
    def to_dict(self, include_body: bool = False):
        """
        Convert to dictionary for API responses.
        
        Args:
            include_body: If False, excludes heavy 'body' field (for list views)
        """
        data = {
            "id": self.id,
            "module_id": self.module_id,
            "title": self.title,
            "summary": self.summary,
            "order_index": self.order_index,
            "estimated_time_minutes": self.estimated_time_minutes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        
        if include_body:
            data["body"] = self.body
        
        return data