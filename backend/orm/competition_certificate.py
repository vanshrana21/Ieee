"""
backend/orm/competition_certificate.py
Phase 5: Analytics Dashboards - Certificate Model
Isolated from existing models - NEW FILE
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, func, Index
from sqlalchemy.orm import relationship
from datetime import datetime
import secrets
import string
from backend.orm.base import Base


def generate_certificate_code() -> str:
    """Generate cryptographically secure 64-character certificate code"""
    # URL-safe base64 alphabet
    alphabet = string.ascii_letters + string.digits + "-_"
    return ''.join(secrets.choice(alphabet) for _ in range(64))


class CompetitionCertificate(Base):
    """
    Phase 5: Competition completion certificates for students.
    NLSIU-branded PDF certificates with QR verification.
    """
    __tablename__ = "competition_certificates"
    
    __table_args__ = (
        Index('idx_certificate_code', 'certificate_code'),
    )
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Foreign keys
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    competition_id = Column(Integer, ForeignKey("competitions.id"), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    
    # Competition results
    final_rank = Column(Integer, nullable=False)  # 1=Winner, 2=Runner-up, etc.
    total_score = Column(Float, nullable=False)  # Overall competition score
    
    # Certificate data
    certificate_code = Column(String(64), nullable=False, unique=True, default=generate_certificate_code)
    pdf_file_path = Column(String(500), nullable=False)
    qr_image_path = Column(String(500), nullable=True)
    digital_signature = Column(String(128), nullable=True)  # SHA-256 hash
    
    # Metadata
    issued_at = Column(DateTime, default=func.now())
    verified_count = Column(Integer, default=0)
    is_revoked = Column(Boolean, default=False)
    revoked_at = Column(DateTime, nullable=True)
    revoked_reason = Column(String(500), nullable=True)
    
    # Relationships
    user = relationship("User", lazy="selectin")
    competition = relationship("Competition", lazy="selectin")
    team = relationship("Team", lazy="selectin")
    
    def __init__(self, user_id: int, competition_id: int, team_id: int,
                 final_rank: int, total_score: float, pdf_file_path: str,
                 qr_image_path: str = None, digital_signature: str = None):
        self.user_id = user_id
        self.competition_id = competition_id
        self.team_id = team_id
        self.final_rank = final_rank
        self.total_score = total_score
        self.pdf_file_path = pdf_file_path
        self.qr_image_path = qr_image_path
        self.digital_signature = digital_signature
    
    def to_dict(self, include_paths: bool = False):
        """Convert to dictionary for API responses"""
        result = {
            "id": self.id,
            "user_id": self.user_id,
            "user_name": self.user.name if self.user else None,
            "competition_id": self.competition_id,
            "competition_title": self.competition.title if self.competition else None,
            "team_id": self.team_id,
            "team_name": self.team.name if self.team else None,
            "final_rank": self.final_rank,
            "total_score": self.total_score,
            "certificate_code": self.certificate_code,
            "issued_at": self.issued_at.isoformat() if self.issued_at else None,
            "verified_count": self.verified_count,
            "is_revoked": self.is_revoked,
            "download_url": f"/api/analytics/certificates/{self.certificate_code}/download"
        }
        
        if include_paths:
            result["pdf_file_path"] = self.pdf_file_path
            result["qr_image_path"] = self.qr_image_path
            result["digital_signature"] = self.digital_signature
        
        return result
    
    def verify(self) -> dict:
        """Verify certificate and return verification data"""
        self.verified_count += 1
        
        return {
            "valid": not self.is_revoked,
            "revoked": self.is_revoked,
            "revoked_reason": self.revoked_reason if self.is_revoked else None,
            "student_name": self.user.name if self.user else "Unknown",
            "competition": self.competition.title if self.competition else "Unknown",
            "rank": self._get_rank_display(),
            "score": self.total_score,
            "issued_date": self.issued_at.date().isoformat() if self.issued_at else None,
            "verified_at": datetime.utcnow().isoformat()
        }
    
    def _get_rank_display(self) -> str:
        """Get human-readable rank display"""
        rank_suffixes = {1: "st", 2: "nd", 3: "rd"}
        suffix = rank_suffixes.get(self.final_rank, "th")
        return f"{self.final_rank}{suffix} Place"
    
    def revoke(self, reason: str = None):
        """Revoke certificate"""
        self.is_revoked = True
        self.revoked_at = datetime.utcnow()
        self.revoked_reason = reason
    
    def regenerate_code(self):
        """Generate new certificate code (useful for reissuing)"""
        self.certificate_code = generate_certificate_code()


def get_rank_suffix(rank: int) -> str:
    """Get ordinal suffix for rank (1st, 2nd, 3rd, etc.)"""
    if 10 <= rank % 100 <= 20:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(rank % 10, "th")
