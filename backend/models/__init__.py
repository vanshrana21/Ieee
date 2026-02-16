"""
backend/models/__init__.py
Export all database models for easy imports
DEPRECATED: Use backend.orm.* instead
"""

# Import from canonical ORM modules
from backend.orm.user import User, UserRole
from backend.orm.subject import Subject
from backend.orm.course import Course
from backend.orm.curriculum import CourseCurriculum
from backend.orm.content_module import ContentModule
from backend.orm.user_progress import UserProgress

# Import base
from backend.orm.base import Base

__all__ = [
    # Base
    "Base",
    
    # Models
    "User",
    "UserRole",
    "Subject",
    "Course",
    "CourseCurriculum",
    "ContentModule",
    "UserProgress",
]
