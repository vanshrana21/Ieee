"""
backend/orm/judge_evaluation.py
Phase 9: Judging, Evaluation & Competition Scoring System

Court-accurate judging and evaluation workflow with blind evaluation,
rubric-based scoring, immutable final results, and full audit trail.
Zero AI involvement in scoring.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Text, JSON, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
from enum import Enum as PyEnum

from backend.orm.base import Base


class EvaluationAction(str, PyEnum):
    """Actions for evaluation audit logging"""
    CREATED = "created"
    UPDATED = "updated"
    FINALIZED = "finalized"
    VIEWED = "viewed"


class JudgeAssignment(Base):
    """
    Phase 9: Judge Assignment
    
    Links judges to teams/projects/rounds for evaluation.
    Supports blind judging - judges never see student names.
    """
    __tablename__ = "judge_assignments"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Institution scoping
    institution_id = Column(
        Integer,
        ForeignKey("institutions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Competition context
    competition_id = Column(
        Integer,
        ForeignKey("competitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Judge
    judge_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Assignment targets (at least one must be set)
    team_id = Column(
        Integer,
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    project_id = Column(
        Integer,
        ForeignKey("moot_projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    round_id = Column(
        Integer,
        ForeignKey("oral_rounds.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    
    # Blind evaluation setting
    is_blind = Column(Boolean, default=True, nullable=False)
    
    # Assignment metadata
    assigned_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    assigned_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    
    # Relationships
    institution = relationship("Institution", lazy="selectin")
    competition = relationship("Competition", lazy="selectin")
    judge = relationship("User", foreign_keys=[judge_id], lazy="selectin")
    team = relationship("Team", lazy="selectin")
    project = relationship("MootProject", lazy="selectin")
    
    def __repr__(self):
        return f"<JudgeAssignment(judge={self.judge_id}, competition={self.competition_id})>"
    
    def to_dict(self):
        return {
            "id": self.id,
            "institution_id": self.institution_id,
            "competition_id": self.competition_id,
            "judge_id": self.judge_id,
            "team_id": self.team_id,
            "project_id": self.project_id,
            "round_id": self.round_id,
            "is_blind": self.is_blind,
            "assigned_at": self.assigned_at.isoformat() if self.assigned_at else None,
            "is_active": self.is_active,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class EvaluationRubric(Base):
    """
    Phase 9: Evaluation Rubric
    
    Defines scoring criteria for evaluations.
    JSON-based criteria for flexibility.
    """
    __tablename__ = "evaluation_rubrics"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Institution scoping
    institution_id = Column(
        Integer,
        ForeignKey("institutions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Competition context (nullable for reusable rubrics)
    competition_id = Column(
        Integer,
        ForeignKey("competitions.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    
    # Rubric details
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    # Criteria JSON structure:
    # [
    #   { "key": "issue_framing", "label": "Issue Framing", "max": 10, "description": "..." },
    #   { "key": "legal_reasoning", "label": "Legal Reasoning", "max": 20, "description": "..." },
    # ]
    criteria = Column(JSON, nullable=False)
    
    # Total possible score (sum of criteria max values)
    total_score = Column(Integer, nullable=False)
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    
    # Relationships
    institution = relationship("Institution", lazy="selectin")
    competition = relationship("Competition", lazy="selectin")
    
    def __repr__(self):
        return f"<EvaluationRubric({self.title}, total={self.total_score})>"
    
    def to_dict(self):
        return {
            "id": self.id,
            "institution_id": self.institution_id,
            "competition_id": self.competition_id,
            "title": self.title,
            "description": self.description,
            "criteria": self.criteria,
            "total_score": self.total_score,
            "is_active": self.is_active,
            "is_default": self.is_default,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class JudgeEvaluation(Base):
    """
    Phase 9: Judge Evaluation (CORE ENTITY)
    
    The actual evaluation/scoring by a judge.
    Supports draft mode and finalization (immutable).
    """
    __tablename__ = "judge_evaluations"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Institution scoping
    institution_id = Column(
        Integer,
        ForeignKey("institutions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Judge
    judge_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Assignment reference
    assignment_id = Column(
        Integer,
        ForeignKey("judge_assignments.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Evaluation targets
    project_id = Column(
        Integer,
        ForeignKey("moot_projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    round_id = Column(
        Integer,
        ForeignKey("oral_rounds.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    
    # Rubric used
    rubric_id = Column(
        Integer,
        ForeignKey("evaluation_rubrics.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    
    # Scores JSON structure:
    # { "issue_framing": 8, "legal_reasoning": 18, ... }
    scores = Column(JSON, nullable=True)
    
    # Total score (calculated from scores)
    total_score = Column(Integer, nullable=True)
    
    # Remarks/comments
    remarks = Column(Text, nullable=True)
    
    # Status
    is_draft = Column(Boolean, default=True, nullable=False)
    is_final = Column(Boolean, default=False, nullable=False)
    
    # Finalization (LOCK FOREVER)
    finalized_at = Column(DateTime, nullable=True)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    institution = relationship("Institution", lazy="selectin")
    judge = relationship("User", lazy="selectin")
    assignment = relationship("JudgeAssignment", lazy="selectin")
    project = relationship("MootProject", lazy="selectin")
    rubric = relationship("EvaluationRubric", lazy="selectin")
    
    def __repr__(self):
        status = "FINAL" if self.is_final else "DRAFT"
        return f"<JudgeEvaluation({status}, judge={self.judge_id}, score={self.total_score})>"
    
    def to_dict(self, include_scores=True):
        data = {
            "id": self.id,
            "institution_id": self.institution_id,
            "judge_id": self.judge_id,
            "assignment_id": self.assignment_id,
            "project_id": self.project_id,
            "round_id": self.round_id,
            "rubric_id": self.rubric_id,
            "is_draft": self.is_draft,
            "is_final": self.is_final,
            "finalized_at": self.finalized_at.isoformat() if self.finalized_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        
        if include_scores:
            data["scores"] = self.scores
            data["total_score"] = self.total_score
            data["remarks"] = self.remarks
        
        return data
    
    def validate_scores(self, rubric_criteria):
        """Validate scores against rubric criteria"""
        if not self.scores:
            return False, "No scores provided"
        
        for criterion in rubric_criteria:
            key = criterion.get("key")
            max_score = criterion.get("max")
            
            if key not in self.scores:
                return False, f"Missing score for criterion: {key}"
            
            score = self.scores[key]
            if score < 0 or score > max_score:
                return False, f"Score for {key} ({score}) exceeds max ({max_score})"
        
        return True, "Valid"


class EvaluationAuditLog(Base):
    """
    Phase 9: Evaluation Audit Log
    
    Immutable audit trail for all evaluation actions.
    Tracks who did what, when, and from where.
    """
    __tablename__ = "evaluation_audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Institution scoping
    institution_id = Column(
        Integer,
        ForeignKey("institutions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Judge who performed the action
    judge_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Evaluation being acted upon
    evaluation_id = Column(
        Integer,
        ForeignKey("judge_evaluations.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Action performed
    action = Column(SQLEnum(EvaluationAction), nullable=False)
    
    # Timestamp
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # IP address for audit
    ip_address = Column(String(45), nullable=True)
    
    # Additional context (JSON, limited)
    context = Column(JSON, nullable=True)
    
    # Relationships
    institution = relationship("Institution", lazy="selectin")
    judge = relationship("User", lazy="selectin")
    evaluation = relationship("JudgeEvaluation", lazy="selectin")
    
    def __repr__(self):
        return f"<EvaluationAuditLog({self.action.value}, eval={self.evaluation_id})>"
    
    def to_dict(self):
        return {
            "id": self.id,
            "institution_id": self.institution_id,
            "judge_id": self.judge_id,
            "evaluation_id": self.evaluation_id,
            "action": self.action.value if self.action else None,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "ip_address": self.ip_address,
            "context": self.context,
        }
