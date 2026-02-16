"""
Phase 1 — Moot Problem & Memorial Infrastructure ORM

Pre-oral infrastructure for moot court competitions:
- Moot problem creation and versioning
- Clarification system with deterministic ordering
- Memorial submission with file integrity hashing
- Memorial evaluation with deterministic scoring
- Score freeze for immutability

Security:
- All file uploads SHA256 hashed
- No float usage (Decimal only)
- Institution-scoped queries
- Immutable freeze layer
- Blind review mode support
"""
import hashlib
import json
import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, Dict, Any, List

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text,
    Numeric, Enum as SQLEnum, Index, UniqueConstraint, event
)
from sqlalchemy.orm import relationship, validates

from backend.orm.base import Base
from backend.core.db_types import UniversalJSON


# =============================================================================
# Enums
# =============================================================================

class MemorialSide(str, Enum):
    """Side of the memorial (Petitioner or Respondent)."""
    PETITIONER = "petitioner"
    RESPONDENT = "respondent"


# =============================================================================
# Model: MootProblem
# =============================================================================

class MootProblem(Base):
    """
    Represents a moot court problem/case.
    
    Supports versioning and tournament association.
    Multi-tenant safe with institution scoping.
    """
    __tablename__ = "moot_problems"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    institution_id = Column(
        Integer,
        ForeignKey("institutions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Institution owning this problem"
    )
    tournament_id = Column(
        Integer,
        ForeignKey("national_tournaments.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
        comment="Associated tournament (optional)"
    )
    
    title = Column(
        String(200),
        nullable=False,
        comment="Problem title"
    )
    description = Column(
        Text,
        nullable=False,
        comment="Full problem description"
    )
    
    official_release_at = Column(
        DateTime,
        nullable=False,
        comment="When problem is officially released"
    )
    version_number = Column(
        Integer,
        nullable=False,
        default=1,
        comment="Problem version for tracking changes"
    )
    
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether problem is currently active"
    )
    
    blind_review = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="If TRUE, judges see only team_code, not institution"
    )
    
    created_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        comment="User who created the problem"
    )
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        comment="Record creation timestamp"
    )
    
    # Relationships
    institution = relationship("Institution", foreign_keys=[institution_id])
    tournament = relationship("NationalTournament", foreign_keys=[tournament_id])
    creator = relationship("User", foreign_keys=[created_by])
    clarifications = relationship("MootClarification", back_populates="moot_problem", lazy="selectin")
    memorial_submissions = relationship("MemorialSubmission", back_populates="moot_problem", lazy="selectin")
    
    # Table constraints
    __table_args__ = (
        UniqueConstraint('tournament_id', 'version_number', name='uq_moot_problem_tournament_version'),
        Index('idx_moot_problems_institution', 'institution_id', 'is_active'),
        Index('idx_moot_problems_release', 'official_release_at'),
    )
    
    def to_dict(self, include_sensitive: bool = True) -> Dict[str, Any]:
        """Serialize to dictionary."""
        data = {
            "id": self.id,
            "institution_id": self.institution_id,
            "tournament_id": self.tournament_id,
            "title": self.title,
            "description": self.description,
            "official_release_at": self.official_release_at.isoformat() if self.official_release_at else None,
            "version_number": self.version_number,
            "is_active": self.is_active,
            "blind_review": self.blind_review,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        return data


# =============================================================================
# Model: MootClarification
# =============================================================================

class MootClarification(Base):
    """
    Clarifications to moot problems.
    
    Released in sequence with deterministic ordering.
    Immutable after release (no updates allowed).
    """
    __tablename__ = "moot_clarifications"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    moot_problem_id = Column(
        Integer,
        ForeignKey("moot_problems.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Associated moot problem"
    )
    
    question_text = Column(
        Text,
        nullable=False,
        comment="The question being clarified"
    )
    official_response = Column(
        Text,
        nullable=False,
        comment="Official answer/response"
    )
    
    released_at = Column(
        DateTime,
        nullable=False,
        comment="When clarification was released"
    )
    release_sequence = Column(
        Integer,
        nullable=False,
        comment="Deterministic ordering sequence number"
    )
    
    created_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        comment="User who created the clarification"
    )
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        comment="Record creation timestamp"
    )
    
    # Relationships
    moot_problem = relationship("MootProblem", back_populates="clarifications")
    creator = relationship("User", foreign_keys=[created_by])
    
    # Table constraints
    __table_args__ = (
        UniqueConstraint('moot_problem_id', 'release_sequence', name='uq_clarification_problem_sequence'),
        Index('idx_clarifications_problem', 'moot_problem_id', 'release_sequence'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "moot_problem_id": self.moot_problem_id,
            "question_text": self.question_text,
            "official_response": self.official_response,
            "released_at": self.released_at.isoformat() if self.released_at else None,
            "release_sequence": self.release_sequence,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# =============================================================================
# Model: MemorialSubmission
# =============================================================================

class MemorialSubmission(Base):
    """
    Memorial (written submission) from teams.
    
    File security:
    - SHA256 hash stored
    - File size validated
    - UUID-based internal filename
    - Only PDF allowed
    
    Immutable after lock.
    """
    __tablename__ = "memorial_submissions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    tournament_team_id = Column(
        Integer,
        ForeignKey("tournament_teams.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Team making the submission"
    )
    moot_problem_id = Column(
        Integer,
        ForeignKey("moot_problems.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Problem being addressed"
    )
    
    side = Column(
        SQLEnum(MemorialSide, create_constraint=True, name="memorialside"),
        nullable=False,
        comment="Petitioner or Respondent"
    )
    
    # File security fields
    file_path = Column(
        String(500),
        nullable=False,
        comment="Internal storage path (UUID-based)"
    )
    file_hash_sha256 = Column(
        String(64),
        nullable=False,
        comment="SHA256 hash of file for integrity"
    )
    file_size_bytes = Column(
        Integer,
        nullable=False,
        comment="File size in bytes"
    )
    original_filename = Column(
        String(255),
        nullable=False,
        comment="Original filename provided by user"
    )
    internal_filename = Column(
        String(100),
        nullable=False,
        comment="UUID-based internal filename"
    )
    
    submitted_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        comment="Submission timestamp"
    )
    deadline_at = Column(
        DateTime,
        nullable=False,
        comment="Submission deadline"
    )
    
    is_late = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="True if submitted after deadline"
    )
    
    resubmission_number = Column(
        Integer,
        nullable=False,
        default=1,
        comment="Incremented on each resubmission"
    )
    
    is_locked = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="If TRUE, no further modifications allowed"
    )
    
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        comment="Record creation timestamp"
    )
    
    # Relationships
    tournament_team = relationship("TournamentTeam", foreign_keys=[tournament_team_id])
    moot_problem = relationship("MootProblem", back_populates="memorial_submissions")
    evaluations = relationship("MemorialEvaluation", back_populates="memorial_submission", lazy="selectin")
    
    # Table constraints
    __table_args__ = (
        UniqueConstraint('tournament_team_id', 'side', 'resubmission_number', 
                        name='uq_memorial_team_side_resubmission'),
        Index('idx_memorials_team', 'tournament_team_id', 'moot_problem_id'),
        Index('idx_memorials_deadline', 'deadline_at', 'is_late'),
    )
    
    @validates('file_size_bytes')
    def validate_file_size(self, key, value):
        """Enforce file size limit (20MB = 20,971,520 bytes)."""
        MAX_SIZE = 20 * 1024 * 1024  # 20MB
        if value > MAX_SIZE:
            raise ValueError(f"File size exceeds 20MB limit: {value} bytes")
        return value
    
    @validates('original_filename')
    def validate_filename(self, key, value):
        """Validate filename security."""
        # Reject double extensions
        if value.count('.') > 1:
            raise ValueError("Double extensions not allowed")
        
        # Must end with .pdf
        if not value.lower().endswith('.pdf'):
            raise ValueError("Only PDF files are allowed")
        
        # Basic sanitization
        dangerous_chars = ['<', '>', ':', '"', '|', '?', '*', '..', '//']
        for char in dangerous_chars:
            if char in value:
                raise ValueError(f"Invalid characters in filename: {char}")
        
        return value
    
    def compute_late_status(self) -> bool:
        """Compute if submission is late based on timestamps."""
        if self.submitted_at and self.deadline_at:
            return self.submitted_at > self.deadline_at
        return False
    
    def to_dict(self, include_file_path: bool = False, blind_mode: bool = False) -> Dict[str, Any]:
        """Serialize to dictionary."""
        if blind_mode:
            # Minimal data in blind mode - no identifying information
            return {
                "id": self.id,
                "side": self.side.value if self.side else None,
                "moot_problem_id": self.moot_problem_id,
                "is_late": self.is_late,
                "resubmission_number": self.resubmission_number,
                "is_locked": self.is_locked,
            }
        
        # Full data in non-blind mode
        data = {
            "id": self.id,
            "tournament_team_id": self.tournament_team_id,
            "moot_problem_id": self.moot_problem_id,
            "side": self.side.value if self.side else None,
            "file_hash_sha256": self.file_hash_sha256,
            "file_size_bytes": self.file_size_bytes,
            "original_filename": self.original_filename,
            "internal_filename": self.internal_filename,
            "submitted_at": self.submitted_at.isoformat() if self.submitted_at else None,
            "deadline_at": self.deadline_at.isoformat() if self.deadline_at else None,
            "is_late": self.is_late,
            "resubmission_number": self.resubmission_number,
            "is_locked": self.is_locked,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        
        if include_file_path:
            data["file_path"] = self.file_path
        
        return data


# =============================================================================
# Model: MemorialEvaluation
# =============================================================================

class MemorialEvaluation(Base):
    """
    Judge evaluation of a memorial submission.
    
    All scores use Decimal (Numeric).
    Deterministic hash for integrity verification.
    """
    __tablename__ = "memorial_evaluations"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    memorial_submission_id = Column(
        Integer,
        ForeignKey("memorial_submissions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Submission being evaluated"
    )
    judge_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Judge performing evaluation"
    )
    rubric_version_id = Column(
        Integer,
        ForeignKey("ai_rubric_versions.id", ondelete="RESTRICT"),
        nullable=True,
        comment="AI rubric version used (if any)"
    )
    
    # Score components (all Decimal 5,2)
    legal_analysis_score = Column(
        Numeric(5, 2),
        nullable=False,
        comment="Quality of legal argumentation"
    )
    research_depth_score = Column(
        Numeric(5, 2),
        nullable=False,
        comment="Depth and breadth of research"
    )
    clarity_score = Column(
        Numeric(5, 2),
        nullable=False,
        comment="Clarity and organization"
    )
    citation_format_score = Column(
        Numeric(5, 2),
        nullable=False,
        comment="Proper citation formatting"
    )
    
    # Computed total
    total_score = Column(
        Numeric(6, 2),
        nullable=False,
        comment="Sum of all component scores"
    )
    
    # Integrity hash
    evaluation_hash = Column(
        String(64),
        nullable=False,
        comment="SHA256 hash of ordered score fields"
    )
    
    evaluated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        comment="Evaluation timestamp"
    )
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        comment="Record creation timestamp"
    )
    
    # Relationships
    memorial_submission = relationship("MemorialSubmission", back_populates="evaluations")
    judge = relationship("User", foreign_keys=[judge_id])
    rubric_version = relationship("AIRubricVersion", foreign_keys=[rubric_version_id])
    
    # Table constraints
    __table_args__ = (
        UniqueConstraint('memorial_submission_id', 'judge_id', name='uq_evaluation_submission_judge'),
        Index('idx_evaluations_judge', 'judge_id', 'evaluated_at'),
        Index('idx_evaluations_scores', 'total_score', 'evaluated_at'),
    )
    
    @validates(
        'legal_analysis_score', 'research_depth_score',
        'clarity_score', 'citation_format_score', 'total_score'
    )
    def validate_decimal_score(self, key, value):
        """Ensure all scores are valid Decimal between 0 and 100."""
        if value is None:
            raise ValueError(f"{key} cannot be None")
        decimal_val = Decimal(str(value))
        if decimal_val < Decimal("0") or decimal_val > Decimal("100"):
            raise ValueError(f"{key} must be between 0.00 and 100.00")
        return decimal_val.quantize(Decimal("0.01"))
    
    def compute_total_score(self) -> Decimal:
        """
        Compute total score from component scores.
        
        Formula: total = legal + research + clarity + citation
        """
        total = (
            Decimal(str(self.legal_analysis_score)) +
            Decimal(str(self.research_depth_score)) +
            Decimal(str(self.clarity_score)) +
            Decimal(str(self.citation_format_score))
        )
        return total.quantize(Decimal("0.01"))
    
    def compute_evaluation_hash(self) -> str:
        """
        Compute SHA256 hash of evaluation for integrity.
        
        Formula: SHA256("legal|research|clarity|citation|total")
        """
        combined = (
            f"{self.legal_analysis_score}|"
            f"{self.research_depth_score}|"
            f"{self.clarity_score}|"
            f"{self.citation_format_score}|"
            f"{self.total_score:.2f}"
        )
        return hashlib.sha256(combined.encode()).hexdigest()
    
    def verify_hash(self) -> bool:
        """Verify the stored hash matches computed value."""
        return self.evaluation_hash == self.compute_evaluation_hash()
    
    def to_dict(self, blind_mode: bool = False) -> Dict[str, Any]:
        """Serialize to dictionary."""
        data = {
            "id": self.id,
            "memorial_submission_id": self.memorial_submission_id,
            "judge_id": self.judge_id if not blind_mode else None,
            "rubric_version_id": self.rubric_version_id,
            "legal_analysis_score": str(self.legal_analysis_score),
            "research_depth_score": str(self.research_depth_score),
            "clarity_score": str(self.clarity_score),
            "citation_format_score": str(self.citation_format_score),
            "total_score": str(self.total_score),
            "evaluation_hash": self.evaluation_hash,
            "hash_valid": self.verify_hash(),
            "evaluated_at": self.evaluated_at.isoformat() if self.evaluated_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        return data


# =============================================================================
# Model: MemorialScoreFreeze
# =============================================================================

class MemorialScoreFreeze(Base):
    """
    Immutable freeze of memorial scores for a moot problem.
    
    After freeze:
    - No new evaluations allowed
    - No modifications to existing evaluations
    - Checksum provides tamper detection
    - Immutable snapshot stored for verification
    """
    __tablename__ = "memorial_score_freeze"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    moot_problem_id = Column(
        Integer,
        ForeignKey("moot_problems.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        index=True,
        comment="Problem whose scores are frozen"
    )
    
    frozen_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        comment="When freeze was applied"
    )
    frozen_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        comment="User who applied the freeze"
    )
    
    checksum = Column(
        String(64),
        nullable=False,
        comment="SHA256 of all evaluation hashes in order"
    )
    
    is_final = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether freeze is final (irreversible)"
    )
    
    total_evaluations = Column(
        Integer,
        nullable=False,
        comment="Number of evaluations frozen"
    )
    
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        comment="Record creation timestamp"
    )
    
    evaluation_snapshot_json = Column(
        JSONB,
        nullable=False,
        default=list,
        comment="Immutable snapshot of evaluation hashes at freeze time"
    )
    freezer = relationship("User", foreign_keys=[frozen_by])
    
    def compute_freeze_checksum(self, evaluation_hashes: List[str]) -> str:
        """
        Compute freeze checksum from evaluation hashes.
        
        Hashes are sorted by submission_id for determinism.
        """
        # Sort for determinism
        sorted_hashes = sorted(evaluation_hashes)
        combined = "|".join(sorted_hashes)
        return hashlib.sha256(combined.encode()).hexdigest()
    
    # Relationships
    moot_problem = relationship("MootProblem", foreign_keys=[moot_problem_id])
    
    def to_dict(self, include_snapshot: bool = False) -> Dict[str, Any]:
        """Serialize to dictionary."""
        data = {
            "id": self.id,
            "moot_problem_id": self.moot_problem_id,
            "frozen_at": self.frozen_at.isoformat() if self.frozen_at else None,
            "frozen_by": self.frozen_by,
            "checksum": self.checksum,
            "is_final": self.is_final,
            "total_evaluations": self.total_evaluations,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        
        if include_snapshot:
            data["evaluation_snapshot"] = self.evaluation_snapshot_json
        
        return data


# =============================================================================
# ORM Event Guards
# =============================================================================

@event.listens_for(MootClarification, 'before_update')
def prevent_clarification_update(mapper, connection, target):
    """
    Prevent updates to clarifications after release.
    
    Clarifications are immutable once released.
    """
    raise Exception(
        "MootClarification is immutable after creation. "
        "Create a new clarification instead."
    )


@event.listens_for(MootClarification, 'before_delete')
def prevent_clarification_delete(mapper, connection, target):
    """Prevent deletion of clarifications (append-only)."""
    raise Exception(
        "MootClarification is append-only. Deletions are prohibited."
    )


@event.listens_for(MemorialSubmission, 'before_update')
def check_submission_lock(mapper, connection, target):
    """
    Check if submission is locked before allowing update.
    
    Locked submissions cannot be modified.
    """
    # This is handled in the service layer for more control
    pass


@event.listens_for(MemorialScoreFreeze, 'before_update')
def prevent_freeze_update(mapper, connection, target):
    """
    Prevent updates to finalized freezes.
    
    Frozen scores are immutable.
    """
    if target.is_final:
        raise Exception(
            "MemorialScoreFreeze is immutable when is_final=True. "
            "Create a new freeze record if needed."
        )


@event.listens_for(MemorialScoreFreeze, 'before_delete')
def prevent_freeze_delete(mapper, connection, target):
    """Prevent deletion of freeze records (immutable audit trail)."""
    raise Exception(
        "MemorialScoreFreeze records cannot be deleted. "
        "They serve as an immutable audit trail."
    )


# =============================================================================
# Helper Functions
# =============================================================================

def generate_internal_filename() -> str:
    """Generate UUID-based internal filename for security."""
    return f"{uuid.uuid4().hex}.pdf"


def compute_file_hash(file_bytes: bytes) -> str:
    """Compute SHA256 hash of file bytes."""
    return hashlib.sha256(file_bytes).hexdigest()
