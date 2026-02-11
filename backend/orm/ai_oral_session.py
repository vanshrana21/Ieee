"""
backend/orm/ai_oral_session.py
Phase 2 MVP: AI Moot Court Practice Mode - ORM Models

Solo practice sessions with AI judge. No teams, no opponents.
Text-only interaction with Indian Supreme Court style.
"""
from datetime import datetime
from typing import Optional, List

from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text

from backend.orm.base import Base


class AIOralSession(Base):
    """
    Phase 2: Solo AI moot court practice session.
    
    A user practices against an AI judge for a specific problem.
    Each session has 3 turns maximum.
    """
    __tablename__ = "ai_oral_sessions"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    
    # User who created this session
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Problem being argued (MootProject ID as plain integer reference - no FK constraint for MVP)
    problem_id = Column(
        Integer,
        nullable=False,
        index=True
    )
    
    # Side the user is arguing for
    side = Column(String(20), nullable=False)  # "petitioner" or "respondent"
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    
    def __repr__(self):
        return f"<AIOralSession(id={self.id}, user={self.user_id}, problem={self.problem_id})>"


class AIOralTurn(Base):
    """
    Phase 2: A single turn in an AI oral session.
    
    Each turn contains user's argument and AI judge's feedback with scores.
    """
    __tablename__ = "ai_oral_turns"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    
    # Parent session
    session_id = Column(
        Integer,
        ForeignKey("ai_oral_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Turn sequence (1, 2, or 3)
    turn_number = Column(Integer, nullable=False)
    
    # User's argument (max 250 chars enforced at API layer)
    user_argument = Column(Text, nullable=False)
    
    # AI feedback (max 300 chars)
    ai_feedback = Column(Text, nullable=False)
    
    # Scores (0-5 scale)
    legal_accuracy_score = Column(Integer, nullable=False, default=0)
    citation_score = Column(Integer, nullable=False, default=0)
    etiquette_score = Column(Integer, nullable=False, default=0)
    
    # Timestamp
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    def __repr__(self):
        return f"<AIOralTurn(session={self.session_id}, turn={self.turn_number})>"
