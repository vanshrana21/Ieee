"""
backend/orm/user.py
Updated User model with role field
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum
from sqlalchemy.sql import func
import enum
from backend.database import Base


class UserRole(str, enum.Enum):
    """User role enumeration for role-based access"""
    LAWYER = "lawyer"
    STUDENT = "student"


class User(Base):
    """
    User ORM model with role-based authentication support.
    
    Changes made:
    - Added 'role' column with LAWYER/STUDENT enum
    - Role is required and has no default (must be set during signup)
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    
    # NEW: Role field for lawyer/student differentiation
    role = Column(Enum(UserRole), nullable=False, index=True)
    
    # Existing fields (unchanged)
    is_active = Column(Boolean, default=True)
    is_premium = Column(Boolean, default=False)
    credits_remaining = Column(Integer, default=500)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}', role='{self.role}')>"