"""
backend/orm/subject.py
Subject model for law subjects
"""
from sqlalchemy import Column, Integer, String, Text, Enum as SQLEnum
from sqlalchemy.orm import relationship
from enum import Enum
from backend.database import Base


class SubjectCategory(str, Enum):
    """Categories for legal subjects"""
    FOUNDATION = "foundation"  # Legal Methods, Jurisprudence
    CORE = "core"  # Contract, Criminal, Tort
    PROCEDURAL = "procedural"  # CPC, CrPC, Evidence
    ELECTIVE = "elective"  # IP Law, Cyber Law


class Subject(Base):
    """
    Stores law subjects (reusable across courses).
    
    Examples:
    - Contract Law (Core)
    - Criminal Law (Core)
    - IP Law (Elective)
    
    Why this exists:
    - Same subject can appear in multiple courses
    - Same subject can appear in different semesters
    - Curriculum table maps Subject → Course → Semester
    """
    __tablename__ = "subjects"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False, index=True)  # "Contract Law"
    code = Column(String(50), nullable=False, unique=True, index=True)  # "LAW201"
    description = Column(Text, nullable=True)
    category = Column(SQLEnum(SubjectCategory), nullable=False, index=True)
    syllabus = Column(Text, nullable=True)
    
    # Relationships
    curriculum = relationship(
        "CourseCurriculum",
        back_populates="subject",
        cascade="all, delete-orphan"
    )
    
    content_modules = relationship(
        "ContentModule",
        back_populates="subject",
        cascade="all, delete-orphan"
    )
    
    user_progress = relationship(
        "UserProgress",
        back_populates="subject",
        cascade="all, delete-orphan"
    )
    
    def __repr__(self):
        return f"<Subject(id={self.id}, title='{self.title}')>"