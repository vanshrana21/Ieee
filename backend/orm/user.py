"""
backend/orm/user.py
User model with course enrollment and semester tracking

PHASE 8 UPDATE: Added relationships for progress tracking
"""
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from enum import Enum
from backend.orm.classroom_session import ClassroomScore
from backend.orm.base import Base


class UserRole(str, Enum):
    """User roles - simplified to teacher and student only"""
    teacher = "teacher"
    student = "student"


class User(Base):
    """
    User model with curriculum integration.
    
    KEY FIELDS FOR PHASE 3:
    - course_id: Which law program (BA LLB / BBA LLB / LLB)
    - current_semester: Which semester (1-10)
    
    PHASE 8 ADDITIONS:
    - content_progress: Progress on individual content items
    - practice_attempts: Practice question submissions
    - subject_progress: Aggregate subject-level progress
    - notes: User's personal notes
    """
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    
    # Authentication
    email = Column(String(255), nullable=False, unique=True, index=True)
    full_name = Column(String(200), nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(SQLEnum(UserRole), nullable=False, default=UserRole.student, index=True)
    
    # Institution Context (Phase 5A)
    institution_id = Column(
        Integer,
        ForeignKey("institutions.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    
    # Refresh Token for session management (Phase 5A)
    refresh_token = Column(String(255), nullable=True)
    refresh_token_expires = Column(Integer, nullable=True)  # Unix timestamp
    
    # Course Enrollment
    course_id = Column(
        Integer,
        ForeignKey("courses.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    
    current_semester = Column(
        Integer,
        nullable=True,
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
        back_populates="enrolled_users"
    )

    bookmarks = relationship(
        "Bookmark",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    
    saved_searches = relationship(
        "SavedSearch",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin"
    )

    
    
    # PHASE 8: Progress tracking relationships
    content_progress = relationship(
        "UserContentProgress",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    
    practice_attempts = relationship(
        "PracticeAttempt",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    
    subject_progress = relationship(
        "SubjectProgress",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    
    notes = relationship(
        "UserNotes",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    
    exam_sessions = relationship(
        "ExamSession",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    
    # Classroom Mode relationships
    classroom_sessions = relationship(
        "ClassroomSession",
        back_populates="teacher",
        cascade="all, delete-orphan"
    )
    
    classroom_participations = relationship(
        "ClassroomParticipant",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    
    classroom_scores = relationship(
        "ClassroomScore",
        back_populates="user",
        foreign_keys=[ClassroomScore.user_id]
    )
    
    classroom_arguments = relationship(
        "ClassroomArgument",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    
    rounds_as_petitioner = relationship(
        "ClassroomRound",
        foreign_keys="ClassroomRound.petitioner_id",
        back_populates="petitioner"
    )
    
    rounds_as_respondent = relationship(
        "ClassroomRound",
        foreign_keys="ClassroomRound.respondent_id",
        back_populates="respondent"
    )
    
    rounds_as_judge = relationship(
        "ClassroomRound",
        foreign_keys="ClassroomRound.judge_id",
        back_populates="judge"
    )
    
    institution_admin_roles = relationship(
        "InstitutionAdmin",
        back_populates="user"
    )
    
    institution = relationship(
        "Institution"
    )
    
    bulk_upload_sessions = relationship(
        "BulkUploadSession",
        back_populates="uploaded_by"
    )
    
    smart_notes = relationship(
        "SmartNote",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    
    # Phase 4: Competitive Match relationships REMOVED to prevent back_populates issues
    # matches_as_player1 and matches_as_player2 removed
    # Use direct queries instead of reverse relationships
    
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
    
    def to_dict_with_course(self):
        """
        Convert user to dictionary including course details.
        
        Returns:
            dict: User data with nested course object
        """
        user_dict = {
            "id": self.id,
            "email": self.email,
            "full_name": self.full_name,
            "role": self.role.value if self.role else None,
            "course_id": self.course_id,
            "current_semester": self.current_semester,
            "is_active": self.is_active,
            "is_premium": self.is_premium,
            "credits_remaining": self.credits_remaining,
        }
        
        # Add course details if user is enrolled
        if self.course:
            user_dict["course"] = {
                "id": self.course.id,
                "name": self.course.name,
                "code": self.course.code,
                "duration_years": self.course.duration_years,
                "total_semesters": self.course.total_semesters,
            }
        else:
            user_dict["course"] = None
        
        return user_dict
