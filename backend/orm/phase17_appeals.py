"""
Phase 17 — Appeals & Governance Override Engine.

ORM models for appeal processing, reviews, decisions, and override records.
"""
import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Column, String, DateTime, ForeignKey, Text, Index,
    CheckConstraint, UniqueConstraint, Enum as SQLEnum,
    Numeric
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.database import Base


# =============================================================================
# Enums
# =============================================================================

class AppealReasonCode(enum.Enum):
    """Reason codes for filing an appeal."""
    SCORING_ERROR = "scoring_error"
    PROCEDURAL_ERROR = "procedural_error"
    JUDGE_BIAS = "judge_bias"
    TECHNICAL_ISSUE = "technical_issue"


class AppealStatus(enum.Enum):
    """Status flow for appeals: FILED → UNDER_REVIEW → DECIDED → CLOSED."""
    FILED = "filed"
    UNDER_REVIEW = "under_review"
    DECIDED = "decided"
    REJECTED = "rejected"
    CLOSED = "closed"


class RecommendedAction(enum.Enum):
    """Actions a judge can recommend during review."""
    UPHOLD = "uphold"
    MODIFY_SCORE = "modify_score"
    REVERSE_WINNER = "reverse_winner"


class WinnerSide(enum.Enum):
    """Winner side options."""
    PETITIONER = "petitioner"
    RESPONDENT = "respondent"


# =============================================================================
# Models
# =============================================================================

class Appeal(Base):
    """
    Main appeal record filed by a team for a match.
    Status flows: FILED → UNDER_REVIEW → DECIDED → CLOSED
    """
    __tablename__ = "appeals"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    match_id = Column(String(36), ForeignKey("tournament_matches.id"), nullable=False, index=True)
    filed_by_user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    team_id = Column(String(36), ForeignKey("tournament_teams.id"), nullable=False)
    
    reason_code = Column(SQLEnum(AppealReasonCode), nullable=False)
    detailed_reason = Column(Text, nullable=True)
    
    status = Column(SQLEnum(AppealStatus), nullable=False, default=AppealStatus.FILED)
    review_deadline = Column(DateTime, nullable=True)
    decision_hash = Column(String(64), nullable=True)  # SHA256 of final decision
    
    filed_at = Column(DateTime, server_default=func.now(), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, onupdate=func.now(), nullable=True)
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('match_id', 'team_id', name='uq_appeal_match_team'),
        CheckConstraint(
            "status IN ('filed', 'under_review', 'decided', 'rejected', 'closed')",
            name='ck_appeal_status_valid'
        ),
        CheckConstraint(
            "reason_code IN ('scoring_error', 'procedural_error', 'judge_bias', 'technical_issue')",
            name='ck_appeal_reason_valid'
        ),
        Index('idx_appeals_match', 'match_id'),
        Index('idx_appeals_status', 'status'),
        Index('idx_appeals_team', 'team_id'),
    )
    
    # Relationships
    reviews = relationship("AppealReview", back_populates="appeal", cascade="all, delete-orphan")
    decision = relationship("AppealDecision", back_populates="appeal", uselist=False, cascade="all, delete-orphan")
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "match_id": self.match_id,
            "filed_by_user_id": self.filed_by_user_id,
            "team_id": self.team_id,
            "reason_code": self.reason_code.value if self.reason_code else None,
            "detailed_reason": self.detailed_reason,
            "status": self.status.value if self.status else None,
            "review_deadline": self.review_deadline.isoformat() if self.review_deadline else None,
            "decision_hash": self.decision_hash,
            "filed_at": self.filed_at.isoformat() if self.filed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class AppealReview(Base):
    """
    Individual judge review for an appeal.
    Multiple reviews allowed for multi-judge appeals.
    """
    __tablename__ = "appeal_reviews"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    appeal_id = Column(String(36), ForeignKey("appeals.id"), nullable=False)
    judge_user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    
    recommended_action = Column(SQLEnum(RecommendedAction), nullable=False)
    justification = Column(Text, nullable=False)
    confidence_score = Column(Numeric(4, 3), nullable=False, default=Decimal("0.500"))
    
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('appeal_id', 'judge_user_id', name='uq_review_appeal_judge'),
        CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 1",
            name='ck_review_confidence_range'
        ),
        CheckConstraint(
            "recommended_action IN ('uphold', 'modify_score', 'reverse_winner')",
            name='ck_review_action_valid'
        ),
        Index('idx_reviews_appeal', 'appeal_id'),
        Index('idx_reviews_judge', 'judge_user_id'),
    )
    
    # Relationships
    appeal = relationship("Appeal", back_populates="reviews")
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "appeal_id": self.appeal_id,
            "judge_user_id": self.judge_user_id,
            "recommended_action": self.recommended_action.value if self.recommended_action else None,
            "justification": self.justification,
            "confidence_score": float(self.confidence_score) if self.confidence_score else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AppealDecision(Base):
    """
    Final decision on an appeal.
    Immutable after creation - represents the authoritative ruling.
    """
    __tablename__ = "appeal_decisions"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    appeal_id = Column(String(36), ForeignKey("appeals.id"), nullable=False, unique=True)
    
    final_action = Column(SQLEnum(RecommendedAction), nullable=False)
    final_petitioner_score = Column(Numeric(5, 2), nullable=True)
    final_respondent_score = Column(Numeric(5, 2), nullable=True)
    new_winner = Column(SQLEnum(WinnerSide), nullable=True)
    
    decided_by_user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    decision_summary = Column(Text, nullable=True)
    integrity_hash = Column(String(64), nullable=False)  # SHA256 for verification
    
    decided_at = Column(DateTime, server_default=func.now(), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    
    # Constraints
    __table_args__ = (
        CheckConstraint(
            "final_petitioner_score IS NULL OR (final_petitioner_score >= 0 AND final_petitioner_score <= 100)",
            name='ck_decision_petitioner_score_range'
        ),
        CheckConstraint(
            "final_respondent_score IS NULL OR (final_respondent_score >= 0 AND final_respondent_score <= 100)",
            name='ck_decision_respondent_score_range'
        ),
        CheckConstraint(
            "final_action IN ('uphold', 'modify_score', 'reverse_winner')",
            name='ck_decision_action_valid'
        ),
        CheckConstraint(
            "new_winner IS NULL OR new_winner IN ('petitioner', 'respondent')",
            name='ck_decision_winner_valid'
        ),
        Index('idx_decision_appeal', 'appeal_id'),
        Index('idx_decision_integrity', 'integrity_hash'),
    )
    
    # Relationships
    appeal = relationship("Appeal", back_populates="decision")
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "appeal_id": self.appeal_id,
            "final_action": self.final_action.value if self.final_action else None,
            "final_petitioner_score": float(self.final_petitioner_score) if self.final_petitioner_score else None,
            "final_respondent_score": float(self.final_respondent_score) if self.final_respondent_score else None,
            "new_winner": self.new_winner.value if self.new_winner else None,
            "decided_by_user_id": self.decided_by_user_id,
            "decision_summary": self.decision_summary,
            "integrity_hash": self.integrity_hash,
            "decided_at": self.decided_at.isoformat() if self.decided_at else None,
        }


class AppealOverrideResult(Base):
    """
    Shadow record storing the override of match results.
    Original match is never modified - this record is the source of truth for effective results.
    """
    __tablename__ = "appeal_override_results"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    match_id = Column(String(36), ForeignKey("tournament_matches.id"), nullable=False, unique=True)
    
    original_winner = Column(SQLEnum(WinnerSide), nullable=False)
    overridden_winner = Column(SQLEnum(WinnerSide), nullable=False)
    override_reason = Column(String(100), nullable=True)
    override_hash = Column(String(64), nullable=False)  # SHA256 for verification
    
    applied_to_rankings = Column(String(1), nullable=False, default="N")  # Y/N
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('match_id', name='uq_override_match'),
        CheckConstraint(
            "original_winner IN ('petitioner', 'respondent')",
            name='ck_override_original_winner_valid'
        ),
        CheckConstraint(
            "overridden_winner IN ('petitioner', 'respondent')",
            name='ck_override_overridden_winner_valid'
        ),
        CheckConstraint(
            "applied_to_rankings IN ('Y', 'N')",
            name='ck_override_applied_valid'
        ),
        Index('idx_override_match', 'match_id'),
        Index('idx_override_applied', 'applied_to_rankings'),
    )
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "match_id": self.match_id,
            "original_winner": self.original_winner.value if self.original_winner else None,
            "overridden_winner": self.overridden_winner.value if self.overridden_winner else None,
            "override_reason": self.override_reason,
            "override_hash": self.override_hash,
            "applied_to_rankings": self.applied_to_rankings == "Y",
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
    
    def get_effective_winner(self) -> str:
        """Return the effective winner after override."""
        return self.overridden_winner.value if self.overridden_winner else None
