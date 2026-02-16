"""
backend/orm/institution.py
Phase 5A + 6: Institution model for multi-tenancy and white labeling
"""
import enum
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Enum as SQLEnum, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.orm.base import Base


class SubscriptionTier(str, enum.Enum):
    FREE = "free"
    STANDARD = "standard"
    PREMIUM = "premium"
    ENTERPRISE = "enterprise"


class Institution(Base):
    """
    Institution model for organizing users into schools/universities.
    Phase 6: Added white labeling (colors, logo) and subscription management.
    """
    __tablename__ = "institutions"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Basic Info
    name = Column(String(255), nullable=False)
    short_name = Column(String(50), nullable=True)
    code = Column(String(50), nullable=False, unique=True, index=True)
    domain = Column(String(255), nullable=True, index=True)
    website = Column(String(200), nullable=True)
    description = Column(Text, nullable=True)
    
    # Phase 6: White Labeling
    logo_url = Column(String(500), nullable=True)
    primary_color = Column(String(7), default="#8B0000", nullable=False)
    secondary_color = Column(String(7), default="#D4AF37", nullable=False)
    accent_color = Column(String(7), default="#2C3E50", nullable=False)
    
    # Contact
    email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    address = Column(Text, nullable=True)
    
    # Status
    status = Column(String(20), default='active', nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Phase 6: Subscription Management
    subscription_tier = Column(SQLEnum(SubscriptionTier), default=SubscriptionTier.FREE, nullable=False)
    subscription_start = Column(DateTime, nullable=True)
    subscription_end = Column(DateTime, nullable=True)
    max_students = Column(Integer, default=500, nullable=False)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    users = relationship("User", back_populates="institution", lazy="selectin")
    competitions = relationship("Competition", back_populates="institution", lazy="selectin", cascade="all, delete-orphan")
    
    # Phase 6: New relationships
    admins = relationship("InstitutionAdmin", back_populates="institution", cascade="all, delete-orphan")
    sso_configs = relationship("SSOConfiguration", back_populates="institution", cascade="all, delete-orphan")
    bulk_upload_sessions = relationship("BulkUploadSession", back_populates="institution")
    
    def __repr__(self):
        return f"<Institution(id={self.id}, code='{self.code}', name='{self.name}')>"
    
    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "short_name": self.short_name,
            "code": self.code,
            "domain": self.domain,
            "website": self.website,
            "description": self.description,
            "logo_url": self.logo_url,
            "primary_color": self.primary_color,
            "secondary_color": self.secondary_color,
            "accent_color": self.accent_color,
            "email": self.email,
            "phone": self.phone,
            "address": self.address,
            "status": self.status,
            "is_active": self.is_active,
            "subscription_tier": self.subscription_tier.value if self.subscription_tier else None,
            "subscription_start": self.subscription_start.isoformat() if self.subscription_start else None,
            "subscription_end": self.subscription_end.isoformat() if self.subscription_end else None,
            "max_students": self.max_students,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "user_count": len(self.users) if self.users else 0,
            "competition_count": len(self.competitions) if self.competitions else 0
        }
    
    def to_branding_dict(self):
        """Public branding info (no auth required)"""
        return {
            "name": self.short_name or self.name,
            "logo_url": self.logo_url,
            "primary_color": self.primary_color,
            "secondary_color": self.secondary_color,
            "accent_color": self.accent_color
        }
