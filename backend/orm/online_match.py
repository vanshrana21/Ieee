"""
Online Match Database Models

Isolated tables for Online 1v1 Mode (B2C).
No shared tables with Classroom Mode.

Phase 4: Competitive Match Engine
- Adds structured 3-round scoring
- Enforces immutable finalized matches
- Reuses existing matches table for online 1v1 mode
"""
from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
    ForeignKey,
    Float,
    Text,
    Enum,
    CheckConstraint,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
from enum import Enum as PyEnum
import random
import string

from backend.orm.base import Base


class MatchState(PyEnum):
    """Online match states."""
    SEARCHING = "searching"
    MATCHED = "matched"
    PREP = "prep"
    LIVE = "live"
    SCORING = "scoring"
    RATING_UPDATE = "rating_update"
    FINISHED = "finished"


class MatchCategory(PyEnum):
    """Moot court categories."""
    CONSTITUTIONAL = "constitutional"
    CRIMINAL = "criminal"
    CYBER = "cyber"
    CIVIL = "civil"
    CORPORATE = "corporate"


class Match(Base):
    """Online 1v1 match table."""
    __tablename__ = "matches"
    
    id = Column(Integer, primary_key=True, index=True)
    match_code = Column(String(20), unique=True, index=True, nullable=False)
    player1_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    # Phase 4: allow AI fallback matches where player2_id can be NULL
    player2_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    player1_role = Column(String(50), nullable=False)  # petitioner, respondent
    player2_role = Column(String(50), nullable=False)
    topic = Column(String(255), nullable=False)
    category = Column(String(50), default=MatchCategory.CONSTITUTIONAL.value)
    current_state = Column(String(50), default=MatchState.SEARCHING.value)
    winner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Phase 4: structured competitive match fields
    # Logical state machine for ranked engine:
    # queued | matched | in_progress | completed | finalized
    state = Column(String(20), default="queued")
    player_1_score = Column(Float, nullable=True)
    player_2_score = Column(Float, nullable=True)
    # Optional aggregate for tie-breaker step 3
    player_1_legal_reasoning = Column(Float, nullable=True)
    player_2_legal_reasoning = Column(Float, nullable=True)
    is_ai_match = Column(Boolean, default=False, nullable=False)
    is_locked = Column(Boolean, default=False, nullable=False)
    # Phase 5: ensure rating is processed exactly once
    rating_processed = Column(Boolean, default=False, nullable=False)
    # Phase 6: season tracking (nullable for now)
    season_id = Column(Integer, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    finalized_at = Column(DateTime(timezone=True), nullable=True)
    
    __table_args__ = (
        # Phase 4: cannot finalize without both scores present
        CheckConstraint(
            "(state != 'finalized') OR (player_1_score IS NOT NULL AND player_2_score IS NOT NULL)",
            name="ck_matches_scores_before_finalize",
        ),
    )
    
    # Relationships
    player1 = relationship("User", foreign_keys=[player1_id])
    player2 = relationship("User", foreign_keys=[player2_id])
    winner = relationship("User", foreign_keys=[winner_id])
    participants = relationship("MatchParticipant", back_populates="match", cascade="all, delete-orphan")
    scores = relationship("MatchScore", back_populates="match", cascade="all, delete-orphan")
    
    def generate_match_code(self):
        """Generate unique match code."""
        prefix = "MATCH"
        suffix = ''.join(random.choices(string.digits, k=5))
        return f"{prefix}-{suffix}"
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.match_code:
            self.match_code = self.generate_match_code()
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            "id": self.id,
            "match_code": self.match_code,
            "player1_id": self.player1_id,
            "player2_id": self.player2_id,
            "player1_role": self.player1_role,
            "player2_role": self.player2_role,
            "topic": self.topic,
            "category": self.category,
            "current_state": self.current_state,
            "winner_id": self.winner_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None
        }


class MatchParticipant(Base):
    """Match participant table."""
    __tablename__ = "match_participants"
    
    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(String(50), nullable=False)  # petitioner, respondent
    joined_at = Column(DateTime(timezone=True), server_default=func.now())
    disconnected_at = Column(DateTime(timezone=True), nullable=True)
    is_ready = Column(Boolean, default=False)
    
    # Relationships
    match = relationship("Match", back_populates="participants")
    user = relationship("User", foreign_keys=[user_id])
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            "id": self.id,
            "match_id": self.match_id,
            "user_id": self.user_id,
            "role": self.role,
            "joined_at": self.joined_at.isoformat() if self.joined_at else None,
            "disconnected_at": self.disconnected_at.isoformat() if self.disconnected_at else None,
            "is_ready": self.is_ready
        }


class MatchScore(Base):
    """Match score table."""
    __tablename__ = "match_scores"
    
    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Score criteria (1-5 scale)
    legal_reasoning = Column(Integer, nullable=True)
    citation_format = Column(Integer, nullable=True)
    courtroom_etiquette = Column(Integer, nullable=True)
    responsiveness = Column(Integer, nullable=True)
    time_management = Column(Integer, nullable=True)
    total_score = Column(Float, nullable=True)
    
    # AI feedback (JSON stored as string)
    ai_feedback = Column(Text, nullable=True)
    calculated_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    match = relationship("Match", back_populates="scores")
    user = relationship("User", foreign_keys=[user_id])
    
    def calculate_total(self):
        """Calculate total score from criteria."""
        scores = [
            self.legal_reasoning,
            self.citation_format,
            self.courtroom_etiquette,
            self.responsiveness,
            self.time_management
        ]
        valid_scores = [s for s in scores if s is not None]
        if valid_scores:
            self.total_score = sum(valid_scores) / len(valid_scores) * 5  # Scale to 25
        return self.total_score
    
    def to_dict(self):
        """Convert to dictionary."""
        import json
        ai_feedback_dict = None
        if self.ai_feedback:
            try:
                ai_feedback_dict = json.loads(self.ai_feedback)
            except:
                pass
        
        return {
            "id": self.id,
            "match_id": self.match_id,
            "user_id": self.user_id,
            "legal_reasoning": self.legal_reasoning,
            "citation_format": self.citation_format,
            "courtroom_etiquette": self.courtroom_etiquette,
            "responsiveness": self.responsiveness,
            "time_management": self.time_management,
            "total_score": self.total_score,
            "ai_feedback": ai_feedback_dict,
            "calculated_at": self.calculated_at.isoformat() if self.calculated_at else None
        }


class MatchArgument(Base):
    """Match argument table."""
    __tablename__ = "match_arguments"
    
    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(String(50), nullable=False)  # petitioner, respondent
    text = Column(Text, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    ai_score = Column(Float, nullable=True)
    
    # Relationships
    match = relationship("Match")
    user = relationship("User", foreign_keys=[user_id])
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            "id": self.id,
            "match_id": self.match_id,
            "user_id": self.user_id,
            "role": self.role,
            "text": self.text,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "ai_score": self.ai_score
        }


class MatchRound(Base):
    """
    Phase 4: Structured competitive match rounds.
    
    Each ranked match creates 6 rows:
    - 3 rounds for player 1
    - 3 rounds for player 2
    
    Round numbers:
    1 = Opening
    2 = Rebuttal
    3 = Closing
    """
    __tablename__ = "match_rounds"
    
    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False)
    player_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    round_number = Column(Integer, nullable=False)
    argument_text = Column(Text, nullable=True)
    final_score = Column(Float, nullable=True)
    
    is_submitted = Column(Boolean, default=False, nullable=False)
    is_locked = Column(Boolean, default=False, nullable=False)
    
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    
    __table_args__ = (
        # One row per (match, player, round)
        UniqueConstraint(
            "match_id",
            "player_id",
            "round_number",
            name="uq_match_round_player_round",
        ),
        CheckConstraint(
            "round_number >= 1 AND round_number <= 3",
            name="ck_match_round_number_valid",
        ),
    )
    
    match = relationship("Match")
    player = relationship("User")


# Phase 4: ORM-level lock enforcement
@event.listens_for(Match, "before_update")
def prevent_match_update_if_locked(mapper, connection, target):
    """Prevent modification of locked matches at model level."""
    if getattr(target, "is_locked", False):
        raise Exception("Locked match cannot be modified")


@event.listens_for(Match, "before_delete")
def prevent_match_delete_if_locked(mapper, connection, target):
    """Prevent deletion of locked matches at model level."""
    if getattr(target, "is_locked", False):
        raise Exception("Locked match cannot be deleted")


@event.listens_for(MatchRound, "before_update")
def prevent_round_update_if_locked(mapper, connection, target):
    """Prevent modification of locked rounds at model level."""
    if getattr(target, "is_locked", False):
        raise Exception("Locked round cannot be modified")


@event.listens_for(MatchRound, "before_delete")
def prevent_round_delete_if_locked(mapper, connection, target):
    """Prevent deletion of locked rounds at model level."""
    if getattr(target, "is_locked", False):
        raise Exception("Locked round cannot be deleted")


# User relationships removed to prevent back_populates conflicts
# Use direct queries instead of reverse relationships
