"""
backend/models/subject.py
Subject model for law subjects with categorization
"""
from sqlalchemy import Column, String, Text, Enum as SQLEnum
from sqlalchemy.orm import relationship
from enum import Enum
from backend.models.base import BaseModel


class SubjectCategory(str, Enum):
    """
    Categories for legal subjects in Indian law education.
    
    - FOUNDATION: Basic legal principles (e.g., Legal Methods, Jurisprudence)
    - CORE: Essential substantive law (e.g., Contract Law, Criminal Law)
    - PROCEDURAL: Court procedures (e.g., CPC, CrPC, Evidence)
    - ELECTIVE: Optional specialization subjects
    """
    FOUNDATION = "foundation"
    CORE = "core"
    PROCEDURAL = "procedural"
    ELECTIVE = "elective"


class Subject(BaseModel):
    """
    Subject model represents individual law subjects.
    
    Examples:
    - Contract Law (Core, Semester 2)
    - Criminal Law (Core, Semester 3)
    - Civil Procedure Code (Procedural, Semester 5)
    
    Fields:
    - id: Primary key
    - title: Subject name
    - code: Unique subject code
    - description: Subject description
    - category: Type of subject (Foundation/Core/Procedural/Elective)
    - syllabus: Detailed syllabus content
    - created_at: When subject was created
    - updated_at: Last modification time
    
    Relationships:
    - curriculum: Mappings to courses and semesters
    - content_modules: Learning content (Learn, Cases, Practice, Notes)
    
    NOTE: UserProgress references Subject, but Subject does NOT reference UserProgress back.
    This is a unidirectional relationship to avoid circular dependencies.
    """
    __tablename__ = "subjects"
    
    # Basic Information
    title = Column(
        String(200),
        nullable=False,
        index=True,
        comment="Subject name (e.g., Contract Law)"
    )
    
    code = Column(
        String(50),
        nullable=False,
        unique=True,
        index=True,
        comment="Unique subject code (e.g., LAW101)"
    )
    
    description = Column(
        Text,
        nullable=True,
        comment="Brief description of the subject"
    )
    
    category = Column(
        SQLEnum(SubjectCategory),
        nullable=False,
        index=True,
        comment="Subject category"
    )
    
    syllabus = Column(
        Text,
        nullable=True,
        comment="Detailed syllabus content"
    )
    
    # Relationships
    curriculum = relationship(
        "CourseCurriculum",
        back_populates="subject",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    
    content_modules = relationship(
        "ContentModule",
        back_populates="subject",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    
    # NO relationship to UserProgress - it's unidirectional from UserProgress -> Subject
    
    def __repr__(self):
        return f"<Subject(id={self.id}, title='{self.title}', category='{self.category}')>"
    
    def to_dict(self):
        """Convert model to dictionary for API responses"""
        return {
            "id": self.id,
            "title": self.title,
            "code": self.code,
            "description": self.description,
            "category": self.category.value if self.category else None,
            "syllabus": self.syllabus,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }