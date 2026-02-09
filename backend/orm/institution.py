"""
backend/orm/institution.py
Phase 5A: Institution model for multi-tenancy
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.orm.base import Base


class Institution(Base):
    """
    Institution model for organizing users into schools/universities.
    Each user belongs to one institution (except Super Admin who manages all).
    """
    __tablename__ = "institutions"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Basic Info
    name = Column(String(255), nullable=False)
    code = Column(String(50), nullable=False, unique=True, index=True)
    domain = Column(String(255), nullable=True, index=True)  # Phase 5B: Institution domain for email validation
    description = Column(Text, nullable=True)
    
    # Contact
    email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    address = Column(Text, nullable=True)
    
    # Status - Phase 5B: Added 'suspended' status for soft-delete
    status = Column(String(20), default='active', nullable=False, index=True)  # active / suspended
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships - Phase 5B: Added competitions and teams
    users = relationship("User", backref="institution", lazy="selectin")
    competitions = relationship("Competition", backref="institution", lazy="selectin", cascade="all, delete-orphan")
    teams = relationship("Team", backref="institution", lazy="selectin", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Institution(id={self.id}, code='{self.code}', name='{self.name}')>"
    
    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "code": self.code,
            "domain": self.domain,  # Phase 5B
            "description": self.description,
            "email": self.email,
            "phone": self.phone,
            "address": self.address,
            "status": self.status,  # Phase 5B
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "user_count": len(self.users) if self.users else 0,
            "competition_count": len(self.competitions) if self.competitions else 0  # Phase 5B
        }
