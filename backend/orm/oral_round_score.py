"""
Phase 0: Virtual Courtroom Infrastructure - Oral Round Scores ORM Model
Judge scoring system with criteria-based evaluation and draft/submit workflow.
"""
from sqlalchemy import Column, Integer, ForeignKey, DateTime, Enum as SQLEnum, func, String, Text, Boolean, Float, Index
from sqlalchemy.orm import relationship
import enum
import json
from backend.orm.base import Base


class TeamSide(str, enum.Enum):
    """Team side in the oral round."""
    PETITIONER = "petitioner"
    RESPONDENT = "respondent"


class OralRoundScore(Base):
    """
    Scores table for judge evaluation of oral round performance.
    
    Tracks scores across 5 criteria (1-5 scale each), written feedback,
    and workflow states (draft vs submitted). Drafts are editable,
    submitted scores are final.
    """
    __tablename__ = "oral_round_scores"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Core fields - Round, judge, and team identification
    round_id = Column(Integer, ForeignKey("oral_rounds.id"), nullable=False)
    judge_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    team_side = Column(SQLEnum(TeamSide), nullable=False)
    
    # Score criteria (1-5 scale per criterion)
    legal_reasoning = Column(Integer, nullable=False)  # Quality of legal arguments
    citation_format = Column(Integer, nullable=False)  # Proper case citations
    courtroom_etiquette = Column(Integer, nullable=False)  # Professional conduct
    responsiveness = Column(Integer, nullable=False)  # Answers to judge questions
    time_management = Column(Integer, nullable=False)  # Effective use of time
    
    # Calculated fields
    total_score = Column(Float, nullable=False)  # Average of 5 criteria
    max_possible = Column(Integer, default=25)  # 5 criteria × 5 max
    
    # Judge feedback
    written_feedback = Column(Text, nullable=True)
    strengths = Column(Text, nullable=True)  # JSON array of strength strings
    areas_for_improvement = Column(Text, nullable=True)  # JSON array of improvement areas
    
    # Workflow flags
    is_draft = Column(Boolean, default=True)  # Editable draft
    is_submitted = Column(Boolean, default=False)  # Final submission
    submitted_at = Column(DateTime, nullable=True)
    
    # Metadata
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    round = relationship("OralRound", back_populates="scores")
    judge = relationship("User", foreign_keys=[judge_id])
    team = relationship("Team", foreign_keys=[team_id])
    
    # Table indexes for common queries
    __table_args__ = (
        Index('idx_scores_round', 'round_id'),
        Index('idx_scores_judge', 'judge_id'),
        Index('idx_scores_team', 'team_id'),
        Index('idx_scores_submitted', 'is_submitted'),
    )
    
    def calculate_total(self):
        """Calculate total score from individual criteria."""
        scores = [
            self.legal_reasoning or 0,
            self.citation_format or 0,
            self.courtroom_etiquette or 0,
            self.responsiveness or 0,
            self.time_management or 0
        ]
        return sum(scores) / 5.0
    
    def finalize(self):
        """Mark score as submitted and final."""
        self.is_draft = False
        self.is_submitted = True
        self.submitted_at = func.now()
        self.total_score = self.calculate_total()
    
    def get_strengths_list(self):
        """Parse strengths JSON to Python list."""
        if self.strengths:
            try:
                return json.loads(self.strengths)
            except json.JSONDecodeError:
                return []
        return []
    
    def set_strengths_list(self, strengths_list):
        """Serialize strengths list to JSON string."""
        self.strengths = json.dumps(strengths_list) if strengths_list else None
    
    def get_improvements_list(self):
        """Parse areas for improvement JSON to Python list."""
        if self.areas_for_improvement:
            try:
                return json.loads(self.areas_for_improvement)
            except json.JSONDecodeError:
                return []
        return []
    
    def set_improvements_list(self, improvements_list):
        """Serialize improvements list to JSON string."""
        self.areas_for_improvement = json.dumps(improvements_list) if improvements_list else None
    
    def to_dict(self):
        """Convert score to dictionary for API responses."""
        return {
            "id": self.id,
            "round_id": self.round_id,
            "judge_id": self.judge_id,
            "team": {
                "id": self.team_id,
                "side": self.team_side.value if self.team_side else None
            },
            "scores": {
                "legal_reasoning": self.legal_reasoning,
                "citation_format": self.citation_format,
                "courtroom_etiquette": self.courtroom_etiquette,
                "responsiveness": self.responsiveness,
                "time_management": self.time_management,
                "total_score": self.total_score,
                "max_possible": self.max_possible
            },
            "feedback": {
                "written": self.written_feedback,
                "strengths": self.get_strengths_list(),
                "areas_for_improvement": self.get_improvements_list()
            },
            "workflow": {
                "is_draft": self.is_draft,
                "is_submitted": self.is_submitted,
                "submitted_at": self.submitted_at.isoformat() if self.submitted_at else None
            },
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
