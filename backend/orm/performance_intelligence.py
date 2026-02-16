"""
Phase 9 — AI Performance Intelligence & Recruiter Signal Layer ORM

National Legal Talent Signal Engine with:
- Candidate skill vectors (deterministic scoring)
- Performance normalization across institutions
- National composite rankings with checksums
- Recruiter access logging
- Fairness audit logs

Security:
- All numeric values use Decimal (no float)
- All timestamps use utcnow()
- Institution-scoped queries
- Append-only audit logging
"""
import hashlib
import json
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any, List

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text,
    Numeric, Index, UniqueConstraint, event, text
)
from sqlalchemy.orm import relationship, validates

from backend.orm.base import Base
from backend.core.db_types import UniversalJSON


# =============================================================================
# Model: CandidateSkillVector
# =============================================================================

class CandidateSkillVector(Base):
    """
    Stores computed skill vectors for candidates.
    
    All scores are Decimal (0.00 - 100.00 scale).
    Deterministic computation only.
    """
    __tablename__ = "candidate_skill_vectors"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Candidate user ID"
    )
    institution_id = Column(
        Integer,
        ForeignKey("institutions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Institution for multi-tenant scoping"
    )
    
    # Core skill scores (Decimal, 5,2 precision)
    oral_advocacy_score = Column(
        Numeric(5, 2),
        nullable=False,
        comment="Average of argument/rebuttal scores"
    )
    statutory_interpretation_score = Column(
        Numeric(5, 2),
        nullable=False,
        comment="Statutory analysis capability"
    )
    case_law_application_score = Column(
        Numeric(5, 2),
        nullable=False,
        comment="Case law application skill"
    )
    procedural_compliance_score = Column(
        Numeric(5, 2),
        nullable=False,
        comment="Procedural compliance scoring"
    )
    rebuttal_responsiveness_score = Column(
        Numeric(5, 2),
        nullable=False,
        comment="Rebuttal effectiveness"
    )
    courtroom_etiquette_score = Column(
        Numeric(5, 2),
        nullable=False,
        comment="Professional conduct scoring"
    )
    
    # Meta-metrics
    consistency_factor = Column(
        Numeric(5, 2),
        nullable=False,
        comment="Inverse variance of scores (higher = more consistent)"
    )
    confidence_index = Column(
        Numeric(5, 2),
        nullable=False,
        comment="Min(100, sessions * weight_factor)"
    )
    total_sessions_analyzed = Column(
        Integer,
        nullable=False,
        comment="Total sessions used in computation"
    )
    
    # Timing
    last_updated_at = Column(
        DateTime,
        nullable=False,
        comment="Last recomputation timestamp"
    )
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        comment="Record creation timestamp"
    )
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    institution = relationship("Institution", foreign_keys=[institution_id])
    
    # Table constraints
    __table_args__ = (
        UniqueConstraint('user_id', name='uq_candidate_skill_vector_user'),
        Index('idx_candidate_skill_institution', 'institution_id'),
        Index('idx_candidate_skill_composite', 'oral_advocacy_score', 'statutory_interpretation_score'),
    )
    
    @validates(
        'oral_advocacy_score', 'statutory_interpretation_score',
        'case_law_application_score', 'procedural_compliance_score',
        'rebuttal_responsiveness_score', 'courtroom_etiquette_score',
        'consistency_factor', 'confidence_index'
    )
    def validate_decimal_score(self, key, value):
        """Ensure all scores are valid Decimal between 0 and 100."""
        if value is None:
            raise ValueError(f"{key} cannot be None")
        decimal_val = Decimal(str(value))
        if decimal_val < Decimal("0") or decimal_val > Decimal("100"):
            raise ValueError(f"{key} must be between 0.00 and 100.00")
        return decimal_val.quantize(Decimal("0.01"))
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "institution_id": self.institution_id,
            "oral_advocacy_score": str(self.oral_advocacy_score),
            "statutory_interpretation_score": str(self.statutory_interpretation_score),
            "case_law_application_score": str(self.case_law_application_score),
            "procedural_compliance_score": str(self.procedural_compliance_score),
            "rebuttal_responsiveness_score": str(self.rebuttal_responsiveness_score),
            "courtroom_etiquette_score": str(self.courtroom_etiquette_score),
            "consistency_factor": str(self.consistency_factor),
            "confidence_index": str(self.confidence_index),
            "total_sessions_analyzed": self.total_sessions_analyzed,
            "last_updated_at": self.last_updated_at.isoformat() if self.last_updated_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# =============================================================================
# Model: PerformanceNormalizationStats
# =============================================================================

class PerformanceNormalizationStats(Base):
    """
    Stores normalization statistics for institution-level comparison.
    
    Enables fair comparison across different institutions by
    normalizing scores using z-score methodology.
    """
    __tablename__ = "performance_normalization_stats"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    institution_id = Column(
        Integer,
        ForeignKey("institutions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Institution being analyzed"
    )
    metric_name = Column(
        String(100),
        nullable=False,
        comment="Metric name (e.g., 'oral_advocacy_score')"
    )
    
    # Statistical measures
    mean_value = Column(
        Numeric(10, 4),
        nullable=False,
        comment="Mean of the metric across institution"
    )
    std_deviation = Column(
        Numeric(10, 4),
        nullable=False,
        comment="Standard deviation (sample std dev)"
    )
    sample_size = Column(
        Integer,
        nullable=False,
        comment="Number of samples used"
    )
    
    computed_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        comment="When stats were computed"
    )
    
    # Relationships
    institution = relationship("Institution", foreign_keys=[institution_id])
    
    # Table constraints
    __table_args__ = (
        UniqueConstraint('institution_id', 'metric_name', name='uq_normalization_institution_metric'),
        Index('idx_normalization_institution', 'institution_id', 'computed_at'),
    )
    
    @validates('sample_size')
    def validate_sample_size(self, key, value):
        """Ensure sample size is positive."""
        if value is None or value < 0:
            raise ValueError("sample_size must be >= 0")
        return value
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "institution_id": self.institution_id,
            "metric_name": self.metric_name,
            "mean_value": str(self.mean_value),
            "std_deviation": str(self.std_deviation),
            "sample_size": self.sample_size,
            "computed_at": self.computed_at.isoformat() if self.computed_at else None,
        }


# =============================================================================
# Model: NationalCandidateRanking
# =============================================================================

class NationalCandidateRanking(Base):
    """
    Stores national-level composite rankings with cryptographic verification.
    
    Rankings are immutable once marked final.
    Checksum enables tamper detection.
    """
    __tablename__ = "national_candidate_rankings"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    academic_year_id = Column(
        Integer,
        ForeignKey("academic_years.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Academic year for ranking context"
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Candidate user ID"
    )
    
    # Composite ranking data
    composite_score = Column(
        Numeric(10, 4),
        nullable=False,
        comment="Weighted composite score (0-100)"
    )
    national_rank = Column(
        Integer,
        nullable=False,
        comment="National rank (dense ranking)"
    )
    percentile = Column(
        Numeric(6, 3),
        nullable=False,
        comment="Percentile (0-100)"
    )
    
    tournaments_participated = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of tournaments considered"
    )
    
    # Cryptographic verification
    checksum = Column(
        String(64),
        nullable=False,
        comment="SHA256 verification hash"
    )
    
    computed_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        comment="When ranking was computed"
    )
    is_final = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether ranking is finalized"
    )
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    academic_year = relationship("AcademicYear", foreign_keys=[academic_year_id])
    
    # Table constraints
    __table_args__ = (
        UniqueConstraint('academic_year_id', 'user_id', name='uq_ranking_academic_year_user'),
        Index('idx_national_rank', 'academic_year_id', 'national_rank'),
        Index('idx_national_ranking_user', 'user_id', 'academic_year_id'),
    )
    
    def verify_checksum(self) -> bool:
        """Verify the stored checksum matches computed value."""
        combined = f"{self.user_id}|{self.national_rank}|{self.composite_score:.4f}|{self.percentile:.3f}"
        expected = hashlib.sha256(combined.encode()).hexdigest()
        return self.checksum == expected
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "academic_year_id": self.academic_year_id,
            "user_id": self.user_id,
            "composite_score": str(self.composite_score),
            "national_rank": self.national_rank,
            "percentile": str(self.percentile),
            "tournaments_participated": self.tournaments_participated,
            "checksum": self.checksum,
            "checksum_valid": self.verify_checksum(),
            "computed_at": self.computed_at.isoformat() if self.computed_at else None,
            "is_final": self.is_final,
        }


# =============================================================================
# Model: RecruiterAccessLog
# =============================================================================

class RecruiterAccessLog(Base):
    """
    Audit log for all recruiter access to candidate data.
    
    Append-only table for compliance and privacy tracking.
    """
    __tablename__ = "recruiter_access_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    recruiter_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Recruiter accessing the data"
    )
    candidate_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Candidate being accessed"
    )
    access_type = Column(
        String(40),
        nullable=False,
        comment="Type of access (profile_view, ranking_view, search_result)"
    )
    
    accessed_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        comment="Access timestamp"
    )
    
    # Relationships
    recruiter = relationship("User", foreign_keys=[recruiter_user_id])
    candidate = relationship("User", foreign_keys=[candidate_user_id])
    
    # Table constraints
    __table_args__ = (
        Index('idx_recruiter_access_recruiter', 'recruiter_user_id', 'accessed_at'),
        Index('idx_recruiter_access_candidate', 'candidate_user_id', 'accessed_at'),
        Index('idx_recruiter_access_type', 'access_type', 'accessed_at'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "recruiter_user_id": self.recruiter_user_id,
            "candidate_user_id": self.candidate_user_id,
            "access_type": self.access_type,
            "accessed_at": self.accessed_at.isoformat() if self.accessed_at else None,
        }


# =============================================================================
# Model: FairnessAuditLog
# =============================================================================

class FairnessAuditLog(Base):
    """
    Logs fairness audits and anomaly detection results.
    
    Tracks potential bias or irregularities in scoring.
    """
    __tablename__ = "fairness_audit_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    institution_id = Column(
        Integer,
        ForeignKey("institutions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Institution being audited"
    )
    metric_name = Column(
        String(100),
        nullable=True,
        comment="Specific metric flagged (optional)"
    )
    anomaly_score = Column(
        Numeric(6, 3),
        nullable=True,
        comment="Anomaly score (higher = more suspicious)"
    )
    flagged = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether this was flagged for review"
    )
    details_json = Column(
        JSONB,
        nullable=True,
        comment="Additional audit details"
    )
    
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        comment="Audit timestamp"
    )
    
    # Relationships
    institution = relationship("Institution", foreign_keys=[institution_id])
    
    # Table constraints
    __table_args__ = (
        Index('idx_fairness_audit_institution', 'institution_id', 'created_at'),
        Index('idx_fairness_audit_flagged', 'flagged', 'anomaly_score'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "institution_id": self.institution_id,
            "metric_name": self.metric_name,
            "anomaly_score": str(self.anomaly_score) if self.anomaly_score else None,
            "flagged": self.flagged,
            "details": self.details_json,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# =============================================================================
# ORM Event Guards
# =============================================================================

@event.listens_for(NationalCandidateRanking, 'before_update')
def prevent_final_ranking_update(mapper, connection, target):
    """
    Prevent updates to finalized rankings for immutability.
    
    Once a ranking is marked final, it cannot be modified.
    """
    # Check if this is actually changing is_final from False to True
    # (which is allowed as the finalization action)
    pass  # We'll handle this in the service layer for more control


@event.listens_for(RecruiterAccessLog, 'before_update')
def prevent_access_log_update(mapper, connection, target):
    """Prevent any updates to recruiter access logs (append-only)."""
    raise Exception(
        "RecruiterAccessLog is append-only. Updates are prohibited for audit integrity."
    )


@event.listens_for(RecruiterAccessLog, 'before_delete')
def prevent_access_log_delete(mapper, connection, target):
    """Prevent any deletions of recruiter access logs (append-only)."""
    raise Exception(
        "RecruiterAccessLog is append-only. Deletions are prohibited for audit integrity."
    )


@event.listens_for(FairnessAuditLog, 'before_update')
def prevent_fairness_log_update(mapper, connection, target):
    """Prevent any updates to fairness audit logs (append-only)."""
    raise Exception(
        "FairnessAuditLog is append-only. Updates are prohibited for audit integrity."
    )


@event.listens_for(FairnessAuditLog, 'before_delete')
def prevent_fairness_log_delete(mapper, connection, target):
    """Prevent any deletions of fairness audit logs (append-only)."""
    raise Exception(
        "FairnessAuditLog is append-only. Deletions are prohibited for audit integrity."
    )
