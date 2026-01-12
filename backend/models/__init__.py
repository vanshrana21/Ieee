"""
backend/models/__init__.py
Export all database models for easy imports
"""

# Import base first
from backend.models.base import Base, BaseModel, TimestampMixin

# Import enums
from backend.models.subject import SubjectCategory
from backend.models.user import UserRole
from backend.models.content_module import ModuleType
from backend.models.user_progress import ProgressStatus

# Import models
from backend.models.course import Course
from backend.models.subject import Subject
from backend.models.curriculum import CourseCurriculum
from backend.models.user import User
from backend.models.content_module import ContentModule
from backend.models.user_progress import UserProgress

# Import query helpers
from backend.models.curriculum import (
    get_active_subjects,
    get_archived_subjects,
    get_subjects_by_semester_range
)
from backend.models.content_module import (
    get_published_modules_for_subject,
    get_module_by_type
)
from backend.models.user_progress import (
    get_user_progress_for_subject,
    get_user_progress_for_module,
    get_user_overall_progress,
    create_or_update_progress
)

__all__ = [
    # Base
    "Base",
    "BaseModel",
    "TimestampMixin",
    
    # Enums
    "SubjectCategory",
    "UserRole",
    "ModuleType",
    "ProgressStatus",
    
    # Models
    "Course",
    "Subject",
    "CourseCurriculum",
    "User",
    "ContentModule",
    "UserProgress",
    
    # Query Helpers - Curriculum
    "get_active_subjects",
    "get_archived_subjects",
    "get_subjects_by_semester_range",
    
    # Query Helpers - Content
    "get_published_modules_for_subject",
    "get_module_by_type",
    
    # Query Helpers - Progress
    "get_user_progress_for_subject",
    "get_user_progress_for_module",
    "get_user_overall_progress",
    "create_or_update_progress",
]