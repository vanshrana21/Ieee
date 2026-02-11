"""
backend/orm/ai_judge_evaluation.py
Phase 4: AI Judge Evaluation for Human Teams (Hybrid Mode 1)
Isolated from existing models - NEW FILE
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, Enum as SQLEnum, func
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
import json
from backend.orm.base import Base


class AIJudgeEvaluation(Base):
    """
    Phase 4: AI Judge evaluation of human arguments during oral rounds.
    Stores AI feedback, scores, and behavior badges for human arguments.
    Human judge can mark AI scores as official.
    """
    __tablename__ = "ai_judge_evaluations"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Foreign keys (safe references to existing tables)
    round_id = Column(Integer, ForeignKey("oral_rounds.id"), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    team_side = Column(SQLEnum("petitioner", "respondent", name="ai_judge_team_side"), nullable=False)
    submitted_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Argument content
    argument_text = Column(Text, nullable=False)
    submitted_at = Column(DateTime, default=func.now())
    
    # AI evaluation results
    ai_feedback = Column(Text, nullable=False)  # Human-readable AI feedback
    ai_scores_json = Column(Text, nullable=False)  # JSON: {legal_accuracy: 4, citation: 5, etiquette: 5}
    ai_behavior_data_json = Column(Text, nullable=False)  # JSON: {has_my_lord: true, valid_scc_citation: false}
    
    # Official status
    is_official = Column(Boolean, default=False)  # Human judge can mark as official
    marked_official_at = Column(DateTime, nullable=True)
    marked_official_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Metadata
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships (lazy loading to avoid circular imports)
    round = relationship("OralRound", foreign_keys=[round_id], lazy="selectin")
    team = relationship("Team", foreign_keys=[team_id], lazy="selectin")
    submitted_by = relationship("User", foreign_keys=[submitted_by_user_id], lazy="selectin")
    marked_official_by = relationship("User", foreign_keys=[marked_official_by_id], lazy="selectin")
    
    def set_ai_scores(self, scores: dict):
        """Store AI scores as JSON"""
        self.ai_scores_json = json.dumps(scores)
    
    def get_ai_scores(self) -> dict:
        """Retrieve AI scores from JSON"""
        return json.loads(self.ai_scores_json) if self.ai_scores_json else {}
    
    def set_behavior_data(self, behavior: dict):
        """Store behavior badges as JSON"""
        self.ai_behavior_data_json = json.dumps(behavior)
    
    def get_behavior_data(self) -> dict:
        """Retrieve behavior badges from JSON"""
        return json.loads(self.ai_behavior_data_json) if self.ai_behavior_data_json else {}
    
    def mark_official(self, judge_id: int):
        """Mark this AI evaluation as the official score"""
        self.is_official = True
        self.marked_official_by_id = judge_id
        self.marked_official_at = datetime.utcnow()
    
    def to_dict(self):
        """Convert evaluation to dictionary for API responses"""
        return {
            "id": self.id,
            "round_id": self.round_id,
            "team_id": self.team_id,
            "team_side": self.team_side.value if self.team_side else None,
            "submitted_by_user_id": self.submitted_by_user_id,
            "submitted_by_name": self.submitted_by.name if self.submitted_by else None,
            "argument_text": self.argument_text,
            "submitted_at": self.submitted_at.isoformat() if self.submitted_at else None,
            "ai_feedback": self.ai_feedback,
            "ai_scores": self.get_ai_scores(),
            "ai_behavior_data": self.get_behavior_data(),
            "is_official": self.is_official,
            "marked_official_at": self.marked_official_at.isoformat() if self.marked_official_at else None,
            "marked_official_by_id": self.marked_official_by_id,
            "marked_official_by_name": self.marked_official_by.name if self.marked_official_by else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
