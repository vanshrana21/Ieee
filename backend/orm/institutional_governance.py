"""
Institutional Governance Models — Phase 6 (Multi-Tenant Academic Infrastructure)

Production-grade multi-institution governance framework.

Provides:
- Multi-tenant institution isolation
- Academic year management
- Policy-driven governance workflows
- Compliance ledger (blockchain-like append-only)
- Institution-level audit and metrics

Rules:
- All foreign keys use ON DELETE RESTRICT
- All tables are append-only (no updates to historical data)
- All timestamps are UTC
- All numeric uses Decimal (never float)
"""
import enum
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, 
    Text, Numeric, Index, UniqueConstraint, Enum, Boolean
)
from sqlalchemy.orm import relationship

from backend.orm.base import Base
from backend.orm.institution import Institution


class RankingVisibilityMode(str, enum.Enum):
    """
    Leaderboard visibility policy.
    
    PUBLIC: All authenticated users can view
    FACULTY_ONLY: Only faculty and above can view
    ANONYMOUS: Public but participant names hidden
    """
    PUBLIC = "public"
    FACULTY_ONLY = "faculty_only"
    ANONYMOUS = "anonymous"


class ApprovalStatus(str, enum.Enum):
    """Status of a governance approval request."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ReviewDecision(str, enum.Enum):
    """Decision from an evaluation review."""
    APPROVED = "approved"
    MODIFY = "modify"
    REJECT = "reject"


class PublicationMode(str, enum.Enum):
    """Publication lifecycle state for leaderboards."""
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"


class LedgerEntityType(str, enum.Enum):
    """Types of entities tracked in the institutional ledger."""
    SESSION = "session"
    LEADERBOARD = "leaderboard"
    EVALUATION = "evaluation"


class LedgerEventType(str, enum.Enum):
    """Types of events recorded in the institutional ledger."""
    FREEZE_FINALIZED = "freeze_finalized"
    FREEZE_PENDING_APPROVAL = "freeze_pending_approval"
    EVALUATION_OVERRIDDEN = "evaluation_overridden"
    SNAPSHOT_INVALIDATED = "snapshot_invalidated"
    SNAPSHOT_PUBLISHED = "snapshot_published"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_REJECTED = "approval_rejected"


class AcademicYear(Base):
    """
    Academic year within an institution.
    
    Provides temporal scoping for courses and sessions.
    
    Rules:
    - Date ranges must not overlap within same institution
    - Soft delete via is_active
    """
    __tablename__ = "academic_years"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Institution reference
    institution_id = Column(
        Integer,
        ForeignKey("institutions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )
    
    # Academic year details
    label = Column(String(50), nullable=False)  # e.g., "2026–2027"
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    
    # Status
    is_active = Column(Boolean, nullable=False, default=True)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Constraints
    __table_args__ = (
        UniqueConstraint("institution_id", "label", name="uq_institution_year_label"),
        Index("idx_academic_years_institution", "institution_id"),
        Index("idx_academic_years_dates", "start_date", "end_date"),
    )
    
    # Relationships
    institution = relationship("Institution", back_populates="academic_years")
    course_instances = relationship("CourseInstance", back_populates="academic_year")
    
    def __repr__(self) -> str:
        return f"<AcademicYear(id={self.id}, institution={self.institution_id}, label={self.label})>"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "institution_id": self.institution_id,
            "label": self.label,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class SessionPolicyProfile(Base):
    """
    Governance policy profile for classroom sessions.
    
    Defines the rules that govern:
    - Freeze requirements
    - Approval workflows
    - Review layers
    - Publication controls
    
    Rules:
    - Profiles are immutable after creation
    - Create new profile to change policy
    """
    __tablename__ = "session_policy_profiles"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Institution reference
    institution_id = Column(
        Integer,
        ForeignKey("institutions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )
    
    # Profile identification
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    
    # Freeze policy settings
    allow_overrides_after_freeze = Column(Boolean, nullable=False, default=False)
    require_dual_faculty_validation = Column(Boolean, nullable=False, default=False)
    require_external_examiner = Column(Boolean, nullable=False, default=False)
    freeze_requires_all_rounds = Column(Boolean, nullable=False, default=True)
    auto_freeze_enabled = Column(Boolean, nullable=False, default=False)
    
    # Visibility settings
    ranking_visibility_mode = Column(
        Enum(RankingVisibilityMode, name="visibility_mode_enum", create_constraint=True),
        nullable=False,
        default=RankingVisibilityMode.FACULTY_ONLY
    )
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Constraints
    __table_args__ = (
        UniqueConstraint("institution_id", "name", name="uq_institution_profile_name"),
        Index("idx_policy_profiles_institution", "institution_id"),
    )
    
    # Relationships
    institution = relationship("Institution", back_populates="policy_profiles")
    course_instances = relationship("CourseInstance", back_populates="policy_profile")
    
    def __repr__(self) -> str:
        return f"<SessionPolicyProfile(id={self.id}, institution={self.institution_id}, name={self.name})>"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "institution_id": self.institution_id,
            "name": self.name,
            "description": self.description,
            "allow_overrides_after_freeze": self.allow_overrides_after_freeze,
            "require_dual_faculty_validation": self.require_dual_faculty_validation,
            "require_external_examiner": self.require_external_examiner,
            "freeze_requires_all_rounds": self.freeze_requires_all_rounds,
            "auto_freeze_enabled": self.auto_freeze_enabled,
            "ranking_visibility_mode": self.ranking_visibility_mode.value if self.ranking_visibility_mode else None,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class CourseInstance(Base):
    """
    A specific instance of a course within an academic year.
    
    Links subjects to academic years with faculty assignment.
    
    Rules:
    - One faculty member is primary responsible
    - Policy profile defines governance rules
    """
    __tablename__ = "course_instances"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Academic year reference
    academic_year_id = Column(
        Integer,
        ForeignKey("academic_years.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )
    
    # Subject reference (existing table)
    subject_id = Column(
        Integer,
        ForeignKey("subjects.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )
    
    # Faculty assignment
    faculty_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )
    
    # Policy profile
    policy_profile_id = Column(
        Integer,
        ForeignKey("session_policy_profiles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )
    
    # Course details
    section = Column(String(20), nullable=True)  # e.g., "A", "B"
    capacity = Column(Integer, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Constraints
    __table_args__ = (
        UniqueConstraint("academic_year_id", "subject_id", "section", name="uq_course_instance"),
        Index("idx_course_instances_year", "academic_year_id"),
        Index("idx_course_instances_faculty", "faculty_id"),
        Index("idx_course_instances_policy", "policy_profile_id"),
    )
    
    # Relationships
    academic_year = relationship("AcademicYear", back_populates="course_instances")
    subject = relationship("Subject")
    faculty = relationship("User")
    policy_profile = relationship("SessionPolicyProfile", back_populates="course_instances")
    
    def __repr__(self) -> str:
        return f"<CourseInstance(id={self.id}, year={self.academic_year_id}, subject={self.subject_id})>"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "academic_year_id": self.academic_year_id,
            "subject_id": self.subject_id,
            "faculty_id": self.faculty_id,
            "policy_profile_id": self.policy_profile_id,
            "section": self.section,
            "capacity": self.capacity,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


# =============================================================================
# PART 2 — Governance Approval Workflow
# =============================================================================

class SessionApproval(Base):
    """
    Governance approval request for session operations.
    
    Tracks required approvals before leaderboard freeze finalization.
    
    Rules:
    - Append-only approval history
    - Required role must approve
    - Rejection blocks finalization
    """
    __tablename__ = "session_approvals"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Session reference
    session_id = Column(
        Integer,
        ForeignKey("classroom_sessions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )
    
    # Approval details
    required_role = Column(
        Enum("FACULTY", "HOD", "ADMIN", name="approval_role_enum", create_constraint=True),
        nullable=False
    )
    
    # Approval response
    approved_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    approved_at = Column(DateTime, nullable=True)
    
    # Status
    status = Column(
        Enum(ApprovalStatus, name="approval_status_enum", create_constraint=True),
        nullable=False,
        default=ApprovalStatus.PENDING
    )
    
    # Notes
    notes = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Constraints
    __table_args__ = (
        Index("idx_session_approvals_session", "session_id", "status"),
        Index("idx_session_approvals_required_role", "session_id", "required_role", "status"),
        Index("idx_session_approvals_approved_by", "approved_by"),
    )
    
    # Relationships
    session = relationship("ClassroomSession")
    approver = relationship("User", foreign_keys=[approved_by])
    
    def __repr__(self) -> str:
        return f"<SessionApproval(id={self.id}, session={self.session_id}, status={self.status})>"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "required_role": self.required_role,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "status": self.status.value if self.status else None,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


# =============================================================================
# PART 3 — Evaluation Review Layer
# =============================================================================

class EvaluationReview(Base):
    """
    External or faculty review of AI evaluations.
    
    Required layer before leaderboard freeze when policy requires it.
    
    Rules:
    - Multiple reviews allowed per evaluation
    - All required reviews must be APPROVED
    - Any REJECT blocks freeze
    """
    __tablename__ = "evaluation_reviews"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Evaluation reference
    evaluation_id = Column(
        Integer,
        ForeignKey("ai_evaluations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )
    
    # Reviewer details
    reviewer_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )
    reviewer_role = Column(
        Enum("FACULTY", "EXTERNAL", name="reviewer_role_enum", create_constraint=True),
        nullable=False
    )
    
    # Review decision
    decision = Column(
        Enum(ReviewDecision, name="review_decision_enum", create_constraint=True),
        nullable=False
    )
    
    # Review notes
    notes = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Constraints
    __table_args__ = (
        Index("idx_evaluation_reviews_evaluation", "evaluation_id", "decision"),
        Index("idx_evaluation_reviews_reviewer", "reviewer_id"),
        Index("idx_evaluation_reviews_role", "evaluation_id", "reviewer_role"),
    )
    
    # Relationships
    evaluation = relationship("AIEvaluation")
    reviewer = relationship("User")
    
    def __repr__(self) -> str:
        return f"<EvaluationReview(id={self.id}, evaluation={self.evaluation_id}, decision={self.decision})>"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "evaluation_id": self.evaluation_id,
            "reviewer_id": self.reviewer_id,
            "reviewer_role": self.reviewer_role,
            "decision": self.decision.value if self.decision else None,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


# =============================================================================
# PART 4 — Institutional Compliance Ledger (Blockchain-like)
# =============================================================================

class InstitutionalLedgerEntry(Base):
    """
    Append-only compliance ledger with cryptographic chaining.
    
    Each entry contains hash of previous entry, creating tamper-evident chain.
    
    Rules:
    - NEVER update after creation
    - Hash chain verifies integrity
    - Genesis entry has previous_hash = "GENESIS"
    """
    __tablename__ = "institutional_ledger_entries"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Institution reference
    institution_id = Column(
        Integer,
        ForeignKey("institutions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )
    
    # Entity reference
    entity_type = Column(
        Enum(LedgerEntityType, name="ledger_entity_type_enum", create_constraint=True),
        nullable=False
    )
    entity_id = Column(Integer, nullable=False, index=True)
    
    # Event details
    event_type = Column(
        Enum(LedgerEventType, name="ledger_event_type_enum", create_constraint=True),
        nullable=False
    )
    event_data_json = Column(Text, nullable=True)  # JSON payload
    
    # Cryptographic chain
    event_hash = Column(String(64), nullable=False)  # SHA256
    previous_hash = Column(String(64), nullable=False)  # Previous entry hash
    
    # Actor tracking
    actor_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Constraints
    __table_args__ = (
        UniqueConstraint("event_hash", name="uq_ledger_event_hash"),
        Index("idx_ledger_institution", "institution_id", "created_at"),
        Index("idx_ledger_entity", "entity_type", "entity_id"),
        Index("idx_ledger_event_type", "event_type"),
        Index("idx_ledger_previous_hash", "previous_hash"),
    )
    
    # Relationships
    institution = relationship("Institution", back_populates="ledger_entries")
    actor = relationship("User")
    
    def __repr__(self) -> str:
        return f"<InstitutionalLedgerEntry(id={self.id}, institution={self.institution_id}, event={self.event_type})>"
    
    def verify_chain_integrity(self, previous_entry_hash: str) -> bool:
        """Verify this entry correctly links to previous entry."""
        return self.previous_hash == previous_entry_hash
    
    def to_dict(self) -> Dict[str, Any]:
        import json
        return {
            "id": self.id,
            "institution_id": self.institution_id,
            "entity_type": self.entity_type.value if self.entity_type else None,
            "entity_id": self.entity_id,
            "event_type": self.event_type.value if self.event_type else None,
            "event_data": json.loads(self.event_data_json) if self.event_data_json else {},
            "event_hash": self.event_hash,
            "previous_hash": self.previous_hash,
            "actor_user_id": self.actor_user_id,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


# =============================================================================
# PART 6 — Monitoring & Metrics
# =============================================================================

class InstitutionMetrics(Base):
    """
    Running metrics counters for institution operations.
    
    Used for monitoring, alerting, and compliance reporting.
    
    Rules:
    - Increment counters in service layer
    - Never reset counters (historical record)
    - New row per time period (daily aggregation)
    """
    __tablename__ = "institution_metrics"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Institution reference
    institution_id = Column(
        Integer,
        ForeignKey("institutions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )
    
    # Metric period (daily granularity)
    metric_date = Column(DateTime, nullable=False)
    
    # Freeze metrics
    freeze_attempts = Column(Integer, nullable=False, default=0)
    freeze_successes = Column(Integer, nullable=False, default=0)
    freeze_failures = Column(Integer, nullable=False, default=0)
    
    # Integrity metrics
    integrity_failures = Column(Integer, nullable=False, default=0)
    
    # Override metrics
    override_count = Column(Integer, nullable=False, default=0)
    
    # Concurrency metrics
    concurrency_conflicts = Column(Integer, nullable=False, default=0)
    
    # Review metrics
    review_approvals = Column(Integer, nullable=False, default=0)
    review_rejections = Column(Integer, nullable=False, default=0)
    review_modifications = Column(Integer, nullable=False, default=0)
    
    # Approval metrics
    approval_grants = Column(Integer, nullable=False, default=0)
    approval_rejections = Column(Integer, nullable=False, default=0)
    
    # Publication metrics
    publications = Column(Integer, nullable=False, default=0)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Constraints
    __table_args__ = (
        UniqueConstraint("institution_id", "metric_date", name="uq_institution_metric_date"),
        Index("idx_metrics_institution", "institution_id", "metric_date"),
    )
    
    # Relationships
    institution = relationship("Institution", back_populates="metrics")
    
    def __repr__(self) -> str:
        return f"<InstitutionMetrics(id={self.id}, institution={self.institution_id}, date={self.metric_date})>"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "institution_id": self.institution_id,
            "metric_date": self.metric_date.isoformat() if self.metric_date else None,
            "freeze_attempts": self.freeze_attempts,
            "freeze_successes": self.freeze_successes,
            "freeze_failures": self.freeze_failures,
            "integrity_failures": self.integrity_failures,
            "override_count": self.override_count,
            "concurrency_conflicts": self.concurrency_conflicts,
            "review_approvals": self.review_approvals,
            "review_rejections": self.review_rejections,
            "review_modifications": self.review_modifications,
            "approval_grants": self.approval_grants,
            "approval_rejections": self.approval_rejections,
            "publications": self.publications,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
