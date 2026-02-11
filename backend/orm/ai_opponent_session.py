"""
backend/orm/ai_opponent_session.py
Phase 4: AI Opponent Session for Oral Rounds (Hybrid Mode 2)
Isolated from existing models - NEW FILE
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, Enum as SQLEnum, func
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from backend.orm.base import Base


class AIOpponentRole(str, enum.Enum):
    """Role AI opponent can fill in a team"""
    SPEAKER_1 = "speaker_1"
    SPEAKER_2 = "speaker_2"
    RESEARCHER_1 = "researcher_1"
    RESEARCHER_2 = "researcher_2"


class AIOpponentSide(str, enum.Enum):
    """Side AI opponent is arguing for"""
    PETITIONER = "petitioner"
    RESPONDENT = "respondent"


class AIOpponentSession(Base):
    """
    Phase 4: AI Opponent session for oral rounds.
    AI fills in for missing teammate during oral arguments.
    """
    __tablename__ = "ai_opponent_sessions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Foreign keys
    round_id = Column(Integer, ForeignKey("oral_rounds.id"), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    
    # AI configuration
    ai_role = Column(SQLEnum(AIOpponentRole), nullable=False)
    opponent_side = Column(SQLEnum(AIOpponentSide), nullable=False)
    
    # Context
    context_summary = Column(Text, nullable=False)  # Round context (problem, previous arguments)
    moot_problem_id = Column(Integer, ForeignKey("moot_projects.id"), nullable=True)
    
    # Status
    is_active = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime, default=func.now())
    ended_at = Column(DateTime, nullable=True)
    
    # Metadata
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Relationships
    round = relationship("OralRound", foreign_keys=[round_id], lazy="selectin")
    team = relationship("Team", foreign_keys=[team_id], lazy="selectin")
    moot_problem = relationship("MootProject", foreign_keys=[moot_problem_id], lazy="selectin")
    created_by = relationship("User", foreign_keys=[created_by_user_id], lazy="selectin")
    
    def to_dict(self):
        """Convert session to dictionary for API responses"""
        return {
            "id": self.id,
            "round_id": self.round_id,
            "team_id": self.team_id,
            "team_name": self.team.name if self.team else None,
            "ai_role": self.ai_role.value if self.ai_role else None,
            "opponent_side": self.opponent_side.value if self.opponent_side else None,
            "context_summary": self.context_summary,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "created_by_user_id": self.created_by_user_id,
            "created_by_name": self.created_by.name if self.created_by else None
        }
    
    def end_session(self):
        """End the AI opponent session"""
        self.is_active = False
        self.ended_at = datetime.utcnow()


class AIOpponentArgument(Base):
    """
    Phase 4: AI Opponent-generated arguments stored in DB.
    Linked to transcript system for display.
    """
    __tablename__ = "ai_opponent_arguments"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Foreign keys
    session_id = Column(Integer, ForeignKey("ai_opponent_sessions.id"), nullable=False)
    round_id = Column(Integer, ForeignKey("oral_rounds.id"), nullable=False)
    
    # Argument content
    argument_text = Column(Text, nullable=False)
    round_stage = Column(String(50), nullable=True)  # e.g., "petitioner_rebuttal"
    
    # AI metadata
    ai_model_used = Column(String(100), nullable=True)  # e.g., "gemini-1.5-pro"
    confidence_score = Column(Integer, nullable=True)  # 1-10
    
    # Timestamps
    generated_at = Column(DateTime, default=func.now())
    
    # Relationships
    session = relationship("AIOpponentSession", foreign_keys=[session_id], lazy="selectin")
    round = relationship("OralRound", foreign_keys=[round_id], lazy="selectin")
    
    def to_dict(self):
        """Convert AI argument to dictionary"""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "round_id": self.round_id,
            "argument_text": self.argument_text,
            "round_stage": self.round_stage,
            "ai_model_used": self.ai_model_used,
            "confidence_score": self.confidence_score,
            "generated_at": self.generated_at.isoformat() if self.generated_at else None
        }
