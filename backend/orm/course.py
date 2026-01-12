"""
backend/orm/course.py
Course model for law degree programs (BA LLB, BBA LLB, LLB)
"""
from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.orm import relationship
from backend.database import Base


class Course(Base):
    """
    Stores law degree programs.
    
    Examples:
    - BA LLB (5 years, 10 semesters)
    - BBA LLB (5 years, 10 semesters)  
    - LLB (3 years, 6 semesters)
    
    Why this exists:
    - Different courses have different durations
    - Each user enrolls in ONE course
    - Curriculum is mapped per course
    """
    __tablename__ = "courses"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)  # "BA LLB"
    code = Column(String(50), nullable=False, unique=True, index=True)  # "BA_LLB"
    duration_years = Column(Integer, nullable=False)  # 3 or 5
    total_semesters = Column(Integer, nullable=False)  # 6 or 10
    description = Column(Text, nullable=True)
    
    # Relationships
    curriculum = relationship(
        "CourseCurriculum",
        back_populates="course",
        cascade="all, delete-orphan"
    )
    
    def __repr__(self):
        return f"<Course(id={self.id}, name='{self.name}')>"