"""
backend/orm/sso_configuration.py
Phase 6: SSO configuration for Google/Microsoft OAuth2
"""
import enum
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.orm.base import Base


class SSOProvider(str, enum.Enum):
    GOOGLE = "google"
    MICROSOFT = "microsoft"
    CUSTOM = "custom"


class SSOConfiguration(Base):
    """
    SSO OAuth2 configuration per institution.
    Phase 6: Client secrets encrypted at rest using AES-256.
    """
    __tablename__ = "sso_configurations"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    institution_id = Column(Integer, ForeignKey("institutions.id"), nullable=False)
    provider = Column(String(20), nullable=False)
    client_id = Column(String(200), nullable=False)
    client_secret_encrypted = Column(Text, nullable=False)  # AES-256 encrypted
    authorization_url = Column(String(500), nullable=False)
    token_url = Column(String(500), nullable=False)
    userinfo_url = Column(String(500), nullable=False)
    scope = Column(String(200), default="openid email profile", nullable=False)
    is_enabled = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    institution = relationship("Institution", back_populates="sso_configs")
    
    # Unique constraint: one config per provider per institution
    __table_args__ = (
        UniqueConstraint('institution_id', 'provider', name='uq_institution_sso'),
    )
    
    def __repr__(self):
        return f"<SSOConfiguration(id={self.id}, institution_id={self.institution_id}, provider={self.provider})>"
    
    def to_dict(self, include_secrets=False):
        """
        Return config data. Secrets only included if explicitly requested (admin only).
        """
        result = {
            "id": self.id,
            "institution_id": self.institution_id,
            "provider": self.provider,
            "client_id": self.client_id,
            "authorization_url": self.authorization_url,
            "token_url": self.token_url,
            "userinfo_url": self.userinfo_url,
            "scope": self.scope,
            "is_enabled": self.is_enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
        if include_secrets:
            result["client_secret_encrypted"] = self.client_secret_encrypted
        return result
