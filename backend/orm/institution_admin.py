"""
backend/orm/institution_admin.py
Phase 6: Institution admin role assignments
"""
import enum
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.orm.base import Base


class InstitutionAdminRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    FACULTY_COORDINATOR = "faculty_coordinator"


class InstitutionAdmin(Base):
    """
    Institution admin assignments - links users to institutions with admin roles.
    Phase 6: Enables institution-level admin delegation.
    """
    __tablename__ = "institution_admins"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    institution_id = Column(Integer, ForeignKey("institutions.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(String(30), default=InstitutionAdminRole.ADMIN.value, nullable=False)
    permissions_json = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    institution = relationship("Institution", back_populates="admins")
    user = relationship("User", foreign_keys=[user_id], back_populates="institution_admin_roles")
    
    # Unique constraint: one admin role per institution per user
    __table_args__ = (
        UniqueConstraint('institution_id', 'user_id', name='uq_institution_admin'),
    )
    
    def __repr__(self):
        return f"<InstitutionAdmin(id={self.id}, institution_id={self.institution_id}, user_id={self.user_id}, role={self.role})>"
    
    def to_dict(self):
        return {
            "id": self.id,
            "institution_id": self.institution_id,
            "user_id": self.user_id,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "user": {
                "id": self.user.id,
                "name": self.user.name if hasattr(self.user, 'name') else None,
                "email": self.user.email if hasattr(self.user, 'email') else None
            } if self.user else None
        }
