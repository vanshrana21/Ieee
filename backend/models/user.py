"""
backend/models/user.py
User model for students with course enrollment and progress tracking
"""
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from enum import Enum
from backend.models.base import BaseModel


class UserRole(str, Enum):
    """
    User roles in the system.
    
    - STUDENT: Regular student user
    - ADMIN: Platform administrator
    """
    STUDENT = "student"
    ADMIN = "admin"


class User(BaseModel):
    """
    User model represents students enrolled in law courses.
    
    Each user:
    - Enrolls in ONE course (BA LLB / BBA LLB / LLB)
    - Has a current semester (1 to 10)
    - Sees subjects based on semester (active/archived)
    - Tracks progress across subjects
    
    Fields:
    - id: Primary key
    - email: Unique email (login identifier)
    - full_name: Student's full name
    - password_hash: Hashed password (bcrypt)
    - role: student or admin
    - course_id: Enrolled course (FK to courses)
    - current_semester: Current semester number (1-10)
    - is_active: Account active/suspended
    - is_premium: Premium subscription status
    - credits_remaining: API/AI credits
    - created_at: Registration date
    - updated_at: Last update time
    
    Relationships:
    - course: The enrolled degree program
    - progress: Learning progress across subjects
    
    Important:
    - current_semester determines which subjects are visible
    - Future subjects (semester > current_semester) should be filtered
    """
    __tablename__ = "users"
    
    # Authentication
    email = Column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
        comment="User's email address (login identifier)"
    )
    
    full_name = Column(
        String(200),
        nullable=False,
        comment="Student's full name"
    )
    
    password_hash = Column(
        String(255),
        nullable=False,
        comment="Bcrypt hashed password"
    )
    
    role = Column(
        SQLEnum(UserRole),
        nullable=False,
        default=UserRole.STUDENT,
        index=True,
        comment="User role (student/admin)"
    )
    
    # Course Enrollment
    course_id = Column(
        Integer,
        ForeignKey("courses.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Enrolled course (can be NULL for new users)"
    )
    
    current_semester = Column(
        Integer,
        nullable=True,
        default=1,
        index=True,
        comment="Current semester (1-10)"
    )
    
    # Account Status
    is_active = Column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
        comment="False = suspended/banned account"
    )
    
    is_premium = Column(
        Boolean,
        default=False,
        nullable=False,
        comment="Premium subscription status"
    )
    
    credits_remaining = Column(
        Integer,
        default=500,
        nullable=False,
        comment="Credits for AI features"
    )
    
    # Relationships
    course = relationship(
        "Course",
        back_populates="users",
        lazy="joined"
    )
    
    progress = relationship(
        "UserProgress",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    
    def __repr__(self):
        return (
            f"<User("
            f"id={self.id}, "
            f"email='{self.email}', "
            f"course_id={self.course_id}, "
            f"semester={self.current_semester})>"
        )
    
    def to_dict(self):
        """Convert model to dictionary for API responses"""
        return {
            "id": self.id,
            "email": self.email,
            "full_name": self.full_name,
            "role": self.role.value if self.role else None,
            "course_id": self.course_id,
            "current_semester": self.current_semester,
            "is_active": self.is_active,
            "is_premium": self.is_premium,
            "credits_remaining": self.credits_remaining,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
    
    def to_dict_with_course(self):
        """Include course details in response"""
        data = self.to_dict()
        if self.course:
            data["course"] = self.course.to_dict()
        return data
    
    def can_access_semester(self, semester_number: int) -> bool:
        """
        Check if user can access subjects from a given semester.
        
        Rules:
        - Can access current and past semesters
        - Cannot access future semesters
        
        Args:
            semester_number: Semester to check
        
        Returns:
            True if user can access, False otherwise
        """
        if not self.current_semester:
            return False
        return semester_number <= self.current_semester
    
    def get_semester_status(self, semester_number: int) -> str:
        """
        Get status of a semester relative to user's current semester.
        
        Args:
            semester_number: Semester to check
        
        Returns:
            "active" | "archived" | "locked"
        """
        if not self.current_semester:
            return "locked"
        
        if semester_number == self.current_semester:
            return "active"
        elif semester_number < self.current_semester:
            return "archived"
        else:
            return "locked"