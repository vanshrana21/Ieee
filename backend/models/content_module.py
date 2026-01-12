"""
backend/models/content_module.py
ContentModule model for storing learning content attached to subjects
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey, Enum as SQLEnum, JSON
from sqlalchemy.orm import relationship
from enum import Enum
from backend.models.base import BaseModel


class ModuleType(str, Enum):
    """
    Types of content modules available for each subject.
    
    - LEARN: Educational content, lessons, theory
    - CASES: Case law database, judgments
    - PRACTICE: MCQs, problem-solving exercises
    - NOTES: Study notes, summaries, quick references
    """
    LEARN = "learn"
    CASES = "cases"
    PRACTICE = "practice"
    NOTES = "notes"


class ContentModule(BaseModel):
    """
    ContentModule stores learning content for subjects.
    
    Each subject has multiple modules (Learn, Cases, Practice, Notes).
    Content is stored as JSON for flexibility.
    
    Example structures:
    
    LEARN module:
    {
        "title": "Introduction to Contract Law",
        "sections": [
            {"heading": "What is a Contract?", "content": "...", "order": 1},
            {"heading": "Elements of Contract", "content": "...", "order": 2}
        ],
        "videos": [...],
        "resources": [...]
    }
    
    CASES module:
    {
        "cases": [
            {
                "case_name": "Carlill v Carbolic Smoke Ball Co",
                "year": 1893,
                "summary": "...",
                "facts": "...",
                "judgment": "...",
                "importance": "..."
            }
        ]
    }
    
    PRACTICE module:
    {
        "questions": [
            {
                "id": "q1",
                "question": "What are the essential elements of a valid contract?",
                "options": ["A", "B", "C", "D"],
                "correct_answer": "B",
                "explanation": "..."
            }
        ]
    }
    
    NOTES module:
    {
        "notes": [
            {
                "title": "Key Concepts",
                "content": "...",
                "category": "summary"
            }
        ]
    }
    
    Fields:
    - id: Primary key
    - subject_id: Foreign key to subjects
    - module_type: Type of content (learn/cases/practice/notes)
    - title: Module title
    - description: Brief description
    - data_payload: JSON content (flexible structure)
    - is_published: Draft or published
    - display_order: Order in UI
    - created_at: When module was created
    - updated_at: Last modification time
    
    Relationships:
    - subject: The law subject this content belongs to
    - user_progress: Student progress in this module
    """
    __tablename__ = "content_modules"
    
    # Foreign Key
    subject_id = Column(
        Integer,
        ForeignKey("subjects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Reference to subjects table"
    )
    
    # Module Information
    module_type = Column(
        SQLEnum(ModuleType),
        nullable=False,
        index=True,
        comment="Type of content module"
    )
    
    title = Column(
        String(200),
        nullable=False,
        comment="Module title"
    )
    
    description = Column(
        Text,
        nullable=True,
        comment="Brief module description"
    )
    
    # Content Storage (JSON for flexibility)
    data_payload = Column(
        JSON,
        nullable=True,
        comment="Module content stored as JSON"
    )
    
    # Publishing
    is_published = Column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
        comment="False = draft, True = published"
    )
    
    display_order = Column(
        Integer,
        default=0,
        nullable=False,
        comment="Order in which module appears in UI"
    )
    
    # Relationships
    subject = relationship(
        "Subject",
        back_populates="content_modules",
        lazy="joined"
    )
    
    user_progress = relationship(
        "UserProgress",
        back_populates="module",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    
    def __repr__(self):
        return (
            f"<ContentModule("
            f"id={self.id}, "
            f"subject_id={self.subject_id}, "
            f"type='{self.module_type}')>"
        )
    
    def to_dict(self):
        """Convert model to dictionary for API responses"""
        return {
            "id": self.id,
            "subject_id": self.subject_id,
            "module_type": self.module_type.value if self.module_type else None,
            "title": self.title,
            "description": self.description,
            "data_payload": self.data_payload,
            "is_published": self.is_published,
            "display_order": self.display_order,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
    
    def to_dict_with_subject(self):
        """Include subject details in response"""
        data = self.to_dict()
        if self.subject:
            data["subject"] = self.subject.to_dict()
        return data


# ============================================
# QUERY HELPER FUNCTIONS
# ============================================

async def get_published_modules_for_subject(db_session, subject_id: int):
    """
    Get all published modules for a subject.
    
    Args:
        db_session: AsyncSession
        subject_id: Subject ID
    
    Returns:
        List of published modules ordered by display_order
    """
    from sqlalchemy import select
    
    stmt = (
        select(ContentModule)
        .where(
            ContentModule.subject_id == subject_id,
            ContentModule.is_published == True
        )
        .order_by(ContentModule.display_order, ContentModule.id)
    )
    
    result = await db_session.execute(stmt)
    return result.scalars().all()


async def get_module_by_type(db_session, subject_id: int, module_type: ModuleType):
    """
    Get specific module type for a subject.
    
    Args:
        db_session: AsyncSession
        subject_id: Subject ID
        module_type: Type of module (learn/cases/practice/notes)
    
    Returns:
        ContentModule or None
    """
    from sqlalchemy import select
    
    stmt = (
        select(ContentModule)
        .where(
            ContentModule.subject_id == subject_id,
            ContentModule.module_type == module_type,
            ContentModule.is_published == True
        )
        .order_by(ContentModule.display_order)
        .limit(1)
    )
    
    result = await db_session.execute(stmt)
    return result.scalar_one_or_none()