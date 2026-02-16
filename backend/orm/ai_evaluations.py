"""
AI Evaluation Models — Phase 4

Core tables for AI judge evaluations with full audit trail.
Ensures determinism, immutability, and faculty oversight.
"""
import enum
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, 
    Text, JSON, Numeric, Index, UniqueConstraint, Enum
)
from sqlalchemy.orm import relationship

from backend.orm.base import Base


class EvaluationStatus(enum.Enum):
    """
    Status of AI evaluation.
    
    PostgreSQL-compatible ENUM for production safety.
    """
    PENDING = "pending"           # Initial state - not yet started
    PROCESSING = "processing"     # Evaluation in progress
    COMPLETED = "completed"       # Successfully evaluated
    FAILED = "failed"             # Fatal error (not retryable)
    REQUIRES_REVIEW = "requires_review"  # Max retries exceeded, needs faculty
    OVERRIDDEN = "overridden"     # Faculty overrode AI score

    def __str__(self):
        return self.value


class AIEvaluation(Base):
    """
    Final persisted evaluation per round/participant.
    
    Immutable once finalized. Faculty overrides create
    separate records in faculty_overrides table.
    """
    __tablename__ = "ai_evaluations"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # References
    session_id = Column(Integer, ForeignKey("classroom_sessions.id", ondelete="RESTRICT"), nullable=False)
    round_id = Column(Integer, ForeignKey("classroom_rounds.id", ondelete="RESTRICT"), nullable=False)
    participant_id = Column(Integer, ForeignKey("classroom_participants.id", ondelete="RESTRICT"), nullable=False)
    turn_id = Column(Integer, ForeignKey("classroom_turns.id", ondelete="RESTRICT"), nullable=True)
    
    # Rubric version (immutable snapshot)
    rubric_version_id = Column(Integer, ForeignKey("ai_rubric_versions.id", ondelete="RESTRICT"), nullable=False)
    
    # Scoring
    final_score = Column(Numeric(5, 2), nullable=True)  # e.g., 87.50
    score_breakdown = Column(Text, nullable=True)  # JSON: {criterion: score, ...}
    weights_used = Column(Text, nullable=True)  # JSON: {criterion: weight, ...}
    
    # AI model info for reproducibility
    ai_model = Column(String(100), nullable=False)  # e.g., "gemini-1.5-pro"
    ai_model_version = Column(String(100), nullable=True)  # e.g., "2024-02"
    
    # Status and lifecycle - EXPLICIT, NEVER INFERRED
    status = Column(
        Enum(EvaluationStatus, name="evaluation_status_enum", create_constraint=True),
        nullable=False,
        default=EvaluationStatus.PENDING
    )
    
    # Processing metadata
    processing_started_at = Column(DateTime, nullable=True)
    processing_completed_at = Column(DateTime, nullable=True)
    
    # Canonical attempt that passed validation
    canonical_attempt_id = Column(Integer, ForeignKey("ai_evaluation_attempts.id"), nullable=True)
    
    # Faculty override info
    finalized_by_faculty_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    finalized_at = Column(DateTime, nullable=True)
    
    # Metadata
    evaluation_timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    evaluation_epoch = Column(Integer, nullable=False, default=lambda: int(datetime.utcnow().timestamp()))
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True, onupdate=datetime.utcnow)
    
    # Prevent duplicate evaluations - DB ENFORCED IDEMPOTENCY
    __table_args__ = (
        UniqueConstraint(
            "round_id", 
            "participant_id", 
            name="uq_round_participant_evaluation"
        ),
        Index("idx_evaluations_session_round", "session_id", "round_id"),
        Index("idx_evaluations_round_participant", "round_id", "participant_id"),
        Index("idx_evaluations_status", "status"),
        Index("idx_evaluations_rubric", "rubric_version_id"),
    )
    
    # Relationships
    session = relationship("ClassroomSession")
    round = relationship("ClassroomRound")
    participant = relationship("ClassroomParticipant")
    turn = relationship("ClassroomTurn")
    rubric_version = relationship("AIRubricVersion", back_populates="evaluations")
    canonical_attempt = relationship("AIEvaluationAttempt", foreign_keys=[canonical_attempt_id])
    finalized_by = relationship("User", foreign_keys=[finalized_by_faculty_id])
    attempts = relationship("AIEvaluationAttempt", back_populates="evaluation", foreign_keys="AIEvaluationAttempt.evaluation_id")
    overrides = relationship("FacultyOverride", back_populates="evaluation")
    
    def __repr__(self) -> str:
        return f"<AIEvaluation(id={self.id}, round={self.round_id}, participant={self.participant_id}, score={self.final_score})>"
    
    @property
    def is_finalized(self) -> bool:
        """Check if evaluation is finalized (completed or overridden)."""
        return self.status in (
            EvaluationStatus.COMPLETED, 
            EvaluationStatus.OVERRIDDEN
        )
    
    @property
    def is_processing(self) -> bool:
        """Check if evaluation is currently processing."""
        return self.status == EvaluationStatus.PROCESSING
    
    @property
    def can_retry(self) -> bool:
        """Check if evaluation can be retried."""
        return self.status in (
            EvaluationStatus.PENDING,
            EvaluationStatus.REQUIRES_REVIEW
        )


class ParseStatus(str, enum.Enum):
    """Parse status for LLM response validation."""
    OK = "ok"                    # Valid JSON, all criteria met
    MALFORMED = "malformed"      # Invalid JSON or missing keys
    TIMEOUT = "timeout"          # LLM call timed out
    ERROR = "error"              # System error during parsing
    VALIDATION_FAILED = "validation_failed"  # JSON valid but criteria failed


class AIEvaluationAttempt(Base):
    """
    Raw LLM responses + metadata for retries and debugging.
    
    Append-only. Multiple attempts per evaluation.
    One attempt marked as canonical (passed validation).
    """
    __tablename__ = "ai_evaluation_attempts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Link to evaluation (nullable until successful/final)
    evaluation_id = Column(Integer, ForeignKey("ai_evaluations.id", ondelete="SET NULL"), nullable=True)
    
    # Attempt metadata
    attempt_number = Column(Integer, nullable=False, default=1)  # 1, 2, 3...
    
    # Prompt info
    prompt_sent = Column(Text, nullable=False)
    prompt_hash = Column(String(64), nullable=False, index=True)  # SHA256 hash
    
    # LLM response
    llm_raw_response = Column(Text, nullable=True)
    parsed_json = Column(Text, nullable=True)  # JSON after parsing
    
    # Parse validation
    parse_status = Column(String(32), nullable=False, default=ParseStatus.OK.value)
    parse_errors = Column(Text, nullable=True)  # JSON array of validation errors
    
    # LLM metadata
    ai_model = Column(String(100), nullable=False)
    ai_model_version = Column(String(100), nullable=True)
    llm_latency_ms = Column(Integer, nullable=True)
    llm_token_usage_input = Column(Integer, nullable=True)
    llm_token_usage_output = Column(Integer, nullable=True)
    
    # Is this the canonical (successful) attempt?
    is_canonical = Column(Integer, default=0)  # 0 or 1
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    # Constraints
    __table_args__ = (
        Index("idx_attempts_evaluation", "evaluation_id"),
        Index("idx_attempts_status", "parse_status"),
        Index("idx_attempts_prompt_hash", "prompt_hash"),
    )
    
    # Relationships
    evaluation = relationship("AIEvaluation", back_populates="attempts", foreign_keys=[evaluation_id])
    
    def __repr__(self) -> str:
        return f"<AIEvaluationAttempt(id={self.id}, eval={self.evaluation_id}, attempt={self.attempt_number}, status={self.parse_status})>"


class FacultyOverride(Base):
    """
    Faculty manual score adjustments.
    
    Never mutates original evaluation. Creates separate record
    for audit trail. Original AI output remains reproducible.
    """
    __tablename__ = "faculty_overrides"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Link to evaluation
    ai_evaluation_id = Column(Integer, ForeignKey("ai_evaluations.id", ondelete="RESTRICT"), nullable=False)
    
    # Override details
    previous_score = Column(Numeric(5, 2), nullable=False)
    new_score = Column(Numeric(5, 2), nullable=False)
    previous_breakdown = Column(Text, nullable=True)  # JSON snapshot
    new_breakdown = Column(Text, nullable=True)  # JSON
    
    # Faculty info
    faculty_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    reason = Column(Text, nullable=False)  # Required justification
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Constraints
    __table_args__ = (
        Index("idx_overrides_evaluation", "ai_evaluation_id"),
        Index("idx_overrides_faculty", "faculty_id"),
    )
    
    # Relationships
    evaluation = relationship("AIEvaluation", back_populates="overrides")
    faculty = relationship("User")
    
    def __repr__(self) -> str:
        return f"<FacultyOverride(id={self.id}, eval={self.ai_evaluation_id}, faculty={self.faculty_id}, {self.previous_score}->{self.new_score})>"


class AIEvaluationAudit(Base):
    """
    Append-only audit log for all evaluation lifecycle events.
    
    Records: started, completed, failed, overridden, etc.
    """
    __tablename__ = "ai_evaluation_audit"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # What was acted upon
    evaluation_id = Column(Integer, ForeignKey("ai_evaluations.id", ondelete="CASCADE"), nullable=False)
    attempt_id = Column(Integer, ForeignKey("ai_evaluation_attempts.id", ondelete="SET NULL"), nullable=True)
    
    # Action details
    action = Column(String(32), nullable=False)  # EVALUATION_STARTED, EVALUATION_COMPLETED, etc.
    actor_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # System = null
    
    # Payload
    payload_json = Column(Text, nullable=True)  # Additional context
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Constraints
    __table_args__ = (
        Index("idx_audit_evaluation", "evaluation_id"),
        Index("idx_audit_action", "action"),
        Index("idx_audit_created", "created_at"),
    )
    
    def __repr__(self) -> str:
        return f"<AIEvaluationAudit(id={self.id}, eval={self.evaluation_id}, action={self.action})>"
