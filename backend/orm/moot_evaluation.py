"""
backend/orm/moot_evaluation.py
Phase 5C: Moot project evaluation persistence
Drafts editable, finalized evaluations locked forever
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Float, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.orm.base import Base


class MootEvaluation(Base):
    """
    Phase 5C: Judge evaluation of moot project
    Drafts are editable, finalized evaluations are immutable
    """
    __tablename__ = "moot_evaluations"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Scoping
    institution_id = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("moot_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Evaluator
    judge_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Rubric scores (0-10 scale per category)
    # These align with the scoring criteria from Phase 5D
    issue_framing_score = Column(Float, nullable=True)
    legal_reasoning_score = Column(Float, nullable=True)
    use_of_authority_score = Column(Float, nullable=True)
    structure_clarity_score = Column(Float, nullable=True)
    oral_advocacy_score = Column(Float, nullable=True)
    responsiveness_score = Column(Float, nullable=True)
    
    # Total score
    total_score = Column(Float, nullable=True)
    max_possible = Column(Float, default=60.0)
    percentage = Column(Float, nullable=True)
    
    # Detailed feedback
    category_comments = Column(Text, nullable=True)  # JSON: {category: comment}
    overall_comments = Column(Text, nullable=True)
    strengths = Column(Text, nullable=True)  # JSON array
    improvements = Column(Text, nullable=True)  # JSON array
    
    # Status
    is_draft = Column(Boolean, default=True, nullable=False)
    finalized_at = Column(DateTime, nullable=True)
    
    # Immutability flag (set when finalized)
    is_locked = Column(Boolean, default=False, nullable=False)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def calculate_total(self):
        """Calculate total score from individual categories"""
        scores = [
            self.issue_framing_score,
            self.legal_reasoning_score,
            self.use_of_authority_score,
            self.structure_clarity_score,
            self.oral_advocacy_score,
            self.responsiveness_score
        ]
        valid_scores = [s for s in scores if s is not None]
        if valid_scores:
            self.total_score = sum(valid_scores)
            self.percentage = (self.total_score / self.max_possible) * 100
        return self.total_score
    
    def to_dict(self, include_details=True):
        data = {
            "id": self.id,
            "institution_id": self.institution_id,
            "project_id": self.project_id,
            "judge_id": self.judge_id,
            "scores": {
                "issue_framing": self.issue_framing_score,
                "legal_reasoning": self.legal_reasoning_score,
                "use_of_authority": self.use_of_authority_score,
                "structure_clarity": self.structure_clarity_score,
                "oral_advocacy": self.oral_advocacy_score,
                "responsiveness": self.responsiveness_score,
                "total": self.total_score,
                "percentage": round(self.percentage, 1) if self.percentage else None
            } if include_details else None,
            "is_draft": self.is_draft,
            "finalized_at": self.finalized_at.isoformat() if self.finalized_at else None,
            "is_locked": self.is_locked,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
        
        if include_details:
            data["category_comments"] = self.category_comments
            data["overall_comments"] = self.overall_comments
            data["strengths"] = self.strengths
            data["improvements"] = self.improvements
        
        return data
