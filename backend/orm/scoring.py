"""
backend/orm/scoring.py
Phase 5D: Judge scoring with numeric fields, publish control, and conflict resolution
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Float, JSON, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
from enum import Enum as PyEnum
from backend.orm.base import Base


class EvaluationStatus(str, PyEnum):
    """Evaluation lifecycle status"""
    DRAFT = "draft"           # Judge still editing
    SUBMITTED = "submitted"   # Judge finalized (not yet published)
    PUBLISHED = "published"   # Visible to students
    DISPUTED = "disputed"     # Conflict flagged
    RESOLVED = "resolved"     # Conflict resolved


class ScoreConflictStatus(str, PyEnum):
    """Conflict resolution status"""
    NONE = "none"             # No conflict
    PENDING = "pending"       # Conflict detected, awaiting resolution
    UNDER_REVIEW = "under_review"  # Admin reviewing
    RESOLVED = "resolved"     # Conflict resolved
    OVERRIDDEN = "overridden"  # Admin override applied


class JudgeScore(Base):
    """
    Individual judge's scores for a team/submission.
    Each judge creates one JudgeScore per evaluation.
    """
    __tablename__ = "judge_scores"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Institution and Competition scoping (Phase 5B)
    institution_id = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False, index=True)
    competition_id = Column(Integer, ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # What is being evaluated
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    submission_id = Column(Integer, ForeignKey("submissions.id", ondelete="SET NULL"), nullable=True, index=True)
    slot_id = Column(Integer, ForeignKey("submission_slots.id", ondelete="SET NULL"), nullable=True, index=True)
    
    # Who is evaluating
    judge_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Evaluation status (Phase 5D)
    status = Column(SQLEnum(EvaluationStatus), default=EvaluationStatus.DRAFT, nullable=False)
    
    # Rubric scores (Phase 5D: Numeric fields)
    # Each criterion 0-10 scale
    issue_framing_score = Column(Float, nullable=True)  # Issue Identification & Framing
    legal_reasoning_score = Column(Float, nullable=True)  # Legal Reasoning & Application
    use_of_authority_score = Column(Float, nullable=True)  # Use of Authority
    structure_clarity_score = Column(Float, nullable=True)  # Structure & Clarity
    oral_advocacy_score = Column(Float, nullable=True)  # Oral Advocacy (if applicable)
    responsiveness_score = Column(Float, nullable=True)  # Responsiveness to Bench
    
    # Computed total ( Phase 5D: Store per-judge total, no cross-judge aggregation)
    total_score = Column(Float, nullable=True)
    max_possible = Column(Float, default=60.0)  # 6 categories × 10 points
    percentage = Column(Float, nullable=True)  # (total / max) × 100
    
    # Criterion notes (Phase 5D: Per-criterion judge notes)
    issue_framing_notes = Column(Text, nullable=True)
    legal_reasoning_notes = Column(Text, nullable=True)
    use_of_authority_notes = Column(Text, nullable=True)
    structure_clarity_notes = Column(Text, nullable=True)
    oral_advocacy_notes = Column(Text, nullable=True)
    responsiveness_notes = Column(Text, nullable=True)
    
    # Overall evaluation (Phase 5D)
    overall_assessment = Column(Text, nullable=True)
    strengths = Column(Text, nullable=True)  # JSON array of strengths
    improvements = Column(Text, nullable=True)  # JSON array of improvements
    
    # Publish control (Phase 5D)
    is_published = Column(Boolean, default=False, nullable=False)
    published_at = Column(DateTime, nullable=True)
    published_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Conflict tracking (Phase 5D)
    conflict_status = Column(SQLEnum(ScoreConflictStatus), default=ScoreConflictStatus.NONE, nullable=False)
    conflict_reason = Column(Text, nullable=True)  # Why this was flagged
    
    # Metadata
    is_final = Column(Boolean, default=False, nullable=False)  # Judge has finalized
    finalized_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<JudgeScore(id={self.id}, judge={self.judge_id}, team={self.team_id}, status={self.status})>"
    
    def calculate_total(self):
        """Calculate total from individual scores"""
        scores = [
            self.issue_framing_score,
            self.legal_reasoning_score,
            self.use_of_authority_score,
            self.structure_clarity_score,
            self.oral_advocacy_score,
            self.responsiveness_score
        ]
        valid_scores = [s for s in scores if s is not None]
        self.total_score = sum(valid_scores) if valid_scores else None
        self.percentage = (self.total_score / self.max_possible * 100) if self.total_score else None
        return self.total_score
    
    def to_dict(self, include_notes=True):
        data = {
            "id": self.id,
            "institution_id": self.institution_id,
            "competition_id": self.competition_id,
            "team_id": self.team_id,
            "submission_id": self.submission_id,
            "slot_id": self.slot_id,
            "judge_id": self.judge_id,
            "status": self.status.value if self.status else None,
            "conflict_status": self.conflict_status.value if self.conflict_status else None,
            
            # Scores
            "scores": {
                "issue_framing": self.issue_framing_score,
                "legal_reasoning": self.legal_reasoning_score,
                "use_of_authority": self.use_of_authority_score,
                "structure_clarity": self.structure_clarity_score,
                "oral_advocacy": self.oral_advocacy_score,
                "responsiveness": self.responsiveness_score,
                "total": self.total_score,
                "max_possible": self.max_possible,
                "percentage": round(self.percentage, 1) if self.percentage else None
            },
            
            # Publication status
            "is_published": self.is_published,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "published_by": self.published_by,
            
            # Finalization
            "is_final": self.is_final,
            "finalized_at": self.finalized_at.isoformat() if self.finalized_at else None,
            
            # Metadata
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
        
        if include_notes:
            data["notes"] = {
                "issue_framing": self.issue_framing_notes,
                "legal_reasoning": self.legal_reasoning_notes,
                "use_of_authority": self.use_of_authority_notes,
                "structure_clarity": self.structure_clarity_notes,
                "oral_advocacy": self.oral_advocacy_notes,
                "responsiveness": self.responsiveness_notes,
                "overall": self.overall_assessment,
                "strengths": self.strengths,
                "improvements": self.improvements
            }
        
        return data


class ScoreConflict(Base):
    """
    Phase 5D: Conflict resolution when judges disagree significantly.
    Admin reviews and resolves conflicts.
    """
    __tablename__ = "score_conflicts"
    
    id = Column(Integer, primary_key=True, index=True)
    
    institution_id = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False, index=True)
    competition_id = Column(Integer, ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Involved scores
    judge_score_ids = Column(JSON, default=list)  # List of JudgeScore IDs in conflict
    
    # Conflict details
    criterion_in_conflict = Column(String(50), nullable=True)  # Which criterion varies most
    score_variance = Column(Float, nullable=True)  # Statistical variance
    max_difference = Column(Float, nullable=True)  # Max score difference
    
    # Status
    status = Column(String(20), default="pending", nullable=False)  # pending / under_review / resolved / overridden
    
    # Resolution
    resolution_notes = Column(Text, nullable=True)
    resolved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    override_score_id = Column(Integer, ForeignKey("judge_scores.id"), nullable=True)  # Which score to use as final
    
    # Metadata
    detected_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    detected_by = Column(Integer, ForeignKey("users.id"), nullable=True)  # System or admin
    
    def to_dict(self):
        return {
            "id": self.id,
            "institution_id": self.institution_id,
            "competition_id": self.competition_id,
            "team_id": self.team_id,
            "judge_score_ids": self.judge_score_ids,
            "criterion_in_conflict": self.criterion_in_conflict,
            "score_variance": self.score_variance,
            "max_difference": self.max_difference,
            "status": self.status,
            "resolution_notes": self.resolution_notes,
            "resolved_by": self.resolved_by,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "detected_at": self.detected_at.isoformat() if self.detected_at else None
        }


class ScoreAuditLog(Base):
    """
    Audit trail for all scoring actions.
    """
    __tablename__ = "score_audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    judge_score_id = Column(Integer, ForeignKey("judge_scores.id", ondelete="CASCADE"), nullable=False, index=True)
    
    action = Column(String(50), nullable=False)  # create, update, publish, unpublish, finalize, dispute, resolve
    performed_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    performed_at = Column(DateTime, default=datetime.utcnow)
    
    # Change details
    field_changed = Column(String(50), nullable=True)  # Which field
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    
    # Context
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    notes = Column(Text, nullable=True)
    
    def to_dict(self):
        return {
            "id": self.id,
            "judge_score_id": self.judge_score_id,
            "action": self.action,
            "performed_by": self.performed_by,
            "performed_at": self.performed_at.isoformat() if self.performed_at else None,
            "field_changed": self.field_changed,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "notes": self.notes
        }
