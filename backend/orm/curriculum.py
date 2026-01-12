"""
backend/orm/curriculum.py
CourseCurriculum - THE BRAIN of the entire curriculum system
"""
from sqlalchemy import Column, Integer, Boolean, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from backend.database import Base


class CourseCurriculum(Base):
    """
    THIS IS THE MOST IMPORTANT TABLE IN PHASE 3.
    
    It answers THE critical question:
    "Which subjects should THIS user see in THIS semester?"
    
    How it works:
    ============
    User has:
    - course_id = 1 (BA LLB)
    - current_semester = 3
    
    Query:
    - WHERE course_id = 1 AND semester_number <= 3
    - Returns: All subjects from semesters 1, 2, 3
    - Semester 3 = ACTIVE
    - Semesters 1-2 = ARCHIVED
    - Semesters 4-10 = HIDDEN (never returned)
    
    Example Data:
    =============
    course_id=1, subject_id=5, semester_number=2, is_elective=False
    → BA LLB students take subject #5 in semester 2 (mandatory)
    
    course_id=1, subject_id=12, semester_number=8, is_elective=True
    → BA LLB students can take subject #12 in semester 8 (optional)
    
    Why this design:
    ================
    - Same subject can appear in different semesters for different courses
    - Easy to add new courses without changing subject data
    - Simple to query: "Give me all subjects for course X, semester Y"
    """
    __tablename__ = "course_curriculum"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign Keys
    course_id = Column(
        Integer,
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    subject_id = Column(
        Integer,
        ForeignKey("subjects.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Semester mapping
    semester_number = Column(Integer, nullable=False, index=True)
    
    # Subject properties
    is_elective = Column(Boolean, default=False, nullable=False, index=True)
    display_order = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    
    # Relationships
    course = relationship("Course", back_populates="curriculum")
    subject = relationship("Subject", back_populates="curriculum")
    
    # Constraints
    __table_args__ = (
        # Prevent duplicate mappings
        UniqueConstraint(
            "course_id",
            "subject_id",
            "semester_number",
            name="uq_course_subject_semester"
        ),
        # Fast queries
        Index("ix_course_semester_active", "course_id", "semester_number", "is_active"),
    )
    
    def __repr__(self):
        return (
            f"<CourseCurriculum(course_id={self.course_id}, "
            f"subject_id={self.subject_id}, semester={self.semester_number})>"
        )