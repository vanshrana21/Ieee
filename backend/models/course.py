"""
backend/models/course.py
Course model for Indian law degree programs
"""
from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.orm import relationship
from backend.models.base import BaseModel


class Course(BaseModel):
    """
    Course model represents law degree programs offered in India.
    
    Examples:
    - BA LLB (5 years, 10 semesters)
    - BBA LLB (5 years, 10 semesters)
    - LLB (3 years, 6 semesters)
    
    Fields:
    - id: Primary key
    - name: Course name (e.g., "BA LLB")
    - code: Unique course code (e.g., "BA_LLB")
    - duration_years: Total years (3 or 5)
    - total_semesters: Total semesters (6 or 10)
    - description: Course description
    - created_at: When course was added
    - updated_at: Last modification time
    
    Relationships:
    - curriculum: List of subjects mapped to this course (via course_curriculum)
    - users: Students enrolled in this course
    """
    __tablename__ = "courses"
    
    # Basic Information
    name = Column(
        String(100),
        nullable=False,
        unique=True,
        comment="Course name (e.g., BA LLB, BBA LLB, LLB)"
    )
    
    code = Column(
        String(50),
        nullable=False,
        unique=True,
        index=True,
        comment="Unique course code for API queries"
    )
    
    duration_years = Column(
        Integer,
        nullable=False,
        comment="Total duration in years (3 or 5)"
    )
    
    total_semesters = Column(
        Integer,
        nullable=False,
        comment="Total number of semesters (6 or 10)"
    )
    
    description = Column(
        Text,
        nullable=True,
        comment="Detailed course description"
    )
    
    # Relationships
    curriculum = relationship(
        "CourseCurriculum",
        back_populates="course",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    
    users = relationship(
        "User",
        back_populates="course",
        lazy="selectin"
    )
    
    def __repr__(self):
        return f"<Course(id={self.id}, name='{self.name}', code='{self.code}')>"
    
    def to_dict(self):
        """Convert model to dictionary for API responses"""
        return {
            "id": self.id,
            "name": self.name,
            "code": self.code,
            "duration_years": self.duration_years,
            "total_semesters": self.total_semesters,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }