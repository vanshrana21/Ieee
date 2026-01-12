"""
backend/orm/user.py
User model with course enrollment and semester tracking
"""
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from enum import Enum
from backend.database import Base


class UserRole(str, Enum):
    """User roles"""
    STUDENT = "student"
    LAWYER = "lawyer"
    ADMIN = "admin"


class User(Base):
    """
    User model with curriculum integration.
    
    KEY FIELDS FOR PHASE 3:
    - course_id: Which law program (BA LLB / BBA LLB / LLB)
    - current_semester: Which semester (1-10)
    
    These two fields determine which subjects the user can see.
    """
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Authentication
    email = Column(String(255), nullable=False, unique=True, index=True)
    full_name = Column(String(200), nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(SQLEnum(UserRole), nullable=False, default=UserRole.STUDENT, index=True)
    
    # ⭐ PHASE 3: Course Enrollment
    course_id = Column(
        Integer,
        ForeignKey("courses.id", ondelete="SET NULL"),
        nullable=True,  # NULL = user hasn't selected course yet
        index=True
    )
    
    current_semester = Column(
        Integer,
        nullable=True,  # NULL = user hasn't started yet
        default=1,
        index=True
    )
    
    # Account Status
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    is_premium = Column(Boolean, default=False, nullable=False)
    credits_remaining = Column(Integer, default=500, nullable=False)
    
    # Relationships
    course = relationship(
        "Course",
        foreign_keys=[course_id],
        backref="enrolled_users"
    )
    
    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}', semester={self.current_semester})>"
    
    def can_access_semester(self, semester_number: int) -> bool:
        """
        Check if user can access subjects from a given semester.
        
        Rules:
        - Can access current and past semesters
        - Cannot access future semesters
        """
        if not self.current_semester:
            return False
        return semester_number <= self.current_semester
    
    def get_semester_status(self, semester_number: int) -> str:
        """
        Get status of a semester relative to user's current semester.
        
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
        notes = relationship(
    "UserNotes",
    back_populates="user",
    cascade="all, delete-orphan",
    lazy="selectin"
)