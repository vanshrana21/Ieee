"""
backend/orm/institution.py
Phase 5A + 6: Institution model for multi-tenancy and white labeling
"""
import enum
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Enum as SQLEnum, Index, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.orm.base import Base
from backend.core.db_types import UniversalJSON


class SubscriptionTier(str, enum.Enum):
    FREE = "free"
    STANDARD = "standard"
    PREMIUM = "premium"
    ENTERPRISE = "enterprise"


class ComplianceMode(str, enum.Enum):
    STANDARD = "standard"
    STRICT = "strict"


class InstitutionRole(Base):
    __tablename__ = "institution_roles"
    
    id = Column(Integer, primary_key=True, index=True)
    institution_id = Column(Integer, ForeignKey("institutions.id", ondelete="RESTRICT"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    role = Column(String(30), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    institution = relationship("Institution", foreign_keys=[institution_id])
    user = relationship("User", foreign_keys=[user_id])
    
    __table_args__ = (
        UniqueConstraint("institution_id", "user_id", name="uq_institution_role"),
        Index("idx_institution_roles_institution", "institution_id"),
        Index("idx_institution_roles_user", "user_id"),
    )
    

class InstitutionAuditLog(Base):
    __tablename__ = "institution_audit_log"
    
    id = Column(Integer, primary_key=True, index=True)
    institution_id = Column(Integer, ForeignKey("institutions.id", ondelete="RESTRICT"), nullable=False)
    actor_user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    action_type = Column(String(50), nullable=False)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(Integer, nullable=True)
    payload_json = Column(UniversalJSON, nullable=False, default=dict)
    payload_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    institution = relationship("Institution", foreign_keys=[institution_id])
    actor = relationship("User", foreign_keys=[actor_user_id])
    
    __table_args__ = (
        Index("idx_institution_audit_institution", "institution_id"),
        Index("idx_institution_audit_actor", "actor_user_id"),
        Index("idx_institution_audit_created", "created_at"),
    )


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
    slug = Column(String(50), nullable=True, unique=True, index=True)
    domain = Column(String(255), nullable=True, index=True)
    website = Column(String(200), nullable=True)
    description = Column(Text, nullable=True)
    settings_json = Column(Text, nullable=True)
    compliance_mode = Column(SQLEnum(ComplianceMode), default=ComplianceMode.STANDARD, nullable=False)
    
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
    is_verified = Column(Boolean, default=False, nullable=False)
    
    # Phase 6: Subscription Management
    subscription_tier = Column(SQLEnum(SubscriptionTier), default=SubscriptionTier.FREE, nullable=False)
    subscription_start = Column(DateTime, nullable=True)
    subscription_end = Column(DateTime, nullable=True)
    max_students = Column(Integer, default=500, nullable=False)
    max_tournaments = Column(Integer, default=5, nullable=False)
    max_concurrent_sessions = Column(Integer, default=10, nullable=False)
    allow_audit_export = Column(Boolean, default=True, nullable=False)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    # User relationship removed - use explicit queries instead
    competitions = relationship("Competition", back_populates="institution", lazy="selectin", cascade="all, delete-orphan")
    
    # Phase 6: New relationships
    admins = relationship("InstitutionAdmin", back_populates="institution", cascade="all, delete-orphan")
    sso_configs = relationship("SSOConfiguration", back_populates="institution", cascade="all, delete-orphan")
    bulk_upload_sessions = relationship("BulkUploadSession", back_populates="institution")
    academic_years = relationship("AcademicYear", back_populates="institution")
    policy_profiles = relationship("SessionPolicyProfile", back_populates="institution")
    ledger_entries = relationship("InstitutionalLedgerEntry", back_populates="institution")
    metrics = relationship("InstitutionMetrics", back_populates="institution")
    
    def __repr__(self):
        return f"<Institution(id={self.id}, code='{self.code}', name='{self.name}')>"
    
    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "short_name": self.short_name,
            "code": self.code,
            "slug": self.slug,
            "domain": self.domain,
            "website": self.website,
            "description": self.description,
            "settings_json": self.settings_json,
            "compliance_mode": self.compliance_mode.value if self.compliance_mode else None,
            "logo_url": self.logo_url,
            "primary_color": self.primary_color,
            "secondary_color": self.secondary_color,
            "accent_color": self.accent_color,
            "email": self.email,
            "phone": self.phone,
            "address": self.address,
            "status": self.status,
            "is_active": self.is_active,
            "is_verified": self.is_verified,
            "subscription_tier": self.subscription_tier.value if self.subscription_tier else None,
            "subscription_start": self.subscription_start.isoformat() if self.subscription_start else None,
            "subscription_end": self.subscription_end.isoformat() if self.subscription_end else None,
            "max_students": self.max_students,
            "max_tournaments": self.max_tournaments,
            "max_concurrent_sessions": self.max_concurrent_sessions,
            "allow_audit_export": self.allow_audit_export,
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
