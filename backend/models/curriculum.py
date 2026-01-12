"""
backend/models/curriculum.py
CourseCurriculum model - Maps subjects to courses and semesters (THE BRAIN OF THE APP)
"""
from sqlalchemy import Column, Integer, Boolean, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from backend.models.base import BaseModel


class CourseCurriculum(BaseModel):
    """
    CourseCurriculum is the CORE BRAIN of JurisAI.
    
    This table answers:
    - Which subjects belong to which course?
    - In which semester is a subject taught?
    - Is this subject mandatory or elective?
    
    Example mappings:
    - BA LLB, Semester 1, Contract Law (mandatory)
    - BA LLB, Semester 3, Criminal Law (mandatory)
    - LLB, Semester 5, Intellectual Property Law (elective)
    
    This enables semester-based subject unlocking:
    - Active subjects: current_semester = semester_number
    - Archive subjects: current_semester > semester_number
    - Future subjects: current_semester < semester_number (hidden)
    
    Fields:
    - id: Primary key
    - course_id: Foreign key to courses
    - subject_id: Foreign key to subjects
    - semester_number: Which semester (1-10)
    - is_elective: Mandatory or optional
    - display_order: Order of subjects in UI
    - is_active: Enable/disable without deletion
    - created_at: When mapping was created
    - updated_at: Last modification time
    
    Relationships:
    - course: The degree program
    - subject: The law subject
    
    Constraints:
    - Unique: (course_id, subject_id, semester_number)
      → Same subject can appear in multiple semesters of different courses
      → But not twice in the same course-semester combo
    """
    __tablename__ = "course_curriculum"
    
    # Foreign Keys
    course_id = Column(
        Integer,
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Reference to courses table"
    )
    
    subject_id = Column(
        Integer,
        ForeignKey("subjects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Reference to subjects table"
    )
    
    # Semester Information
    semester_number = Column(
        Integer,
        nullable=False,
        index=True,
        comment="Semester when this subject is taught (1-10)"
    )
    
    # Subject Properties
    is_elective = Column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
        comment="True if subject is optional/elective"
    )
    
    display_order = Column(
        Integer,
        default=0,
        nullable=False,
        comment="Order in which subject appears in UI"
    )
    
    is_active = Column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
        comment="False to hide subject without deleting"
    )
    
    # Relationships
    course = relationship(
        "Course",
        back_populates="curriculum",
        lazy="joined"
    )
    
    subject = relationship(
        "Subject",
        back_populates="curriculum",
        lazy="joined"
    )
    
    # Database Constraints
    __table_args__ = (
        # Prevent duplicate mappings
        UniqueConstraint(
            "course_id",
            "subject_id",
            "semester_number",
            name="uq_course_subject_semester"
        ),
        # Composite index for common queries
        Index(
            "ix_course_semester_active",
            "course_id",
            "semester_number",
            "is_active"
        ),
    )
    
    def __repr__(self):
        return (
            f"<CourseCurriculum("
            f"course_id={self.course_id}, "
            f"subject_id={self.subject_id}, "
            f"semester={self.semester_number})>"
        )
    
    def to_dict(self):
        """Convert model to dictionary for API responses"""
        return {
            "id": self.id,
            "course_id": self.course_id,
            "subject_id": self.subject_id,
            "semester_number": self.semester_number,
            "is_elective": self.is_elective,
            "display_order": self.display_order,
            "is_active": self.is_active,
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

async def get_active_subjects(db_session, course_id: int, current_semester: int):
    """
    Get subjects for current semester (ACTIVE).
    
    Args:
        db_session: AsyncSession
        course_id: User's enrolled course
        current_semester: User's current semester
    
    Returns:
        List of subjects for current semester
    """
    from sqlalchemy import select
    
    stmt = (
        select(CourseCurriculum)
        .where(
            CourseCurriculum.course_id == course_id,
            CourseCurriculum.semester_number == current_semester,
            CourseCurriculum.is_active == True
        )
        .order_by(CourseCurriculum.display_order, CourseCurriculum.id)
    )
    
    result = await db_session.execute(stmt)
    return result.scalars().all()


async def get_archived_subjects(db_session, course_id: int, current_semester: int):
    """
    Get subjects from past semesters (ARCHIVED).
    
    Args:
        db_session: AsyncSession
        course_id: User's enrolled course
        current_semester: User's current semester
    
    Returns:
        List of subjects from past semesters
    """
    from sqlalchemy import select
    
    stmt = (
        select(CourseCurriculum)
        .where(
            CourseCurriculum.course_id == course_id,
            CourseCurriculum.semester_number < current_semester,
            CourseCurriculum.is_active == True
        )
        .order_by(
            CourseCurriculum.semester_number.desc(),
            CourseCurriculum.display_order,
            CourseCurriculum.id
        )
    )
    
    result = await db_session.execute(stmt)
    return result.scalars().all()


async def get_subjects_by_semester_range(
    db_session,
    course_id: int,
    start_semester: int,
    end_semester: int
):
    """
    Get subjects for a range of semesters.
    
    Args:
        db_session: AsyncSession
        course_id: Course ID
        start_semester: Starting semester (inclusive)
        end_semester: Ending semester (inclusive)
    
    Returns:
        List of subjects in semester range
    """
    from sqlalchemy import select
    
    stmt = (
        select(CourseCurriculum)
        .where(
            CourseCurriculum.course_id == course_id,
            CourseCurriculum.semester_number >= start_semester,
            CourseCurriculum.semester_number <= end_semester,
            CourseCurriculum.is_active == True
        )
        .order_by(
            CourseCurriculum.semester_number,
            CourseCurriculum.display_order,
            CourseCurriculum.id
        )
    )
    
    result = await db_session.execute(stmt)
    return result.scalars().all()