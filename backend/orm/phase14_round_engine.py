"""
Phase 14 — Deterministic Round Engine ORM Models

Core courtroom infrastructure:
- Deterministic speaker flow
- Transaction-safe state machine
- Immutable after freeze
- Concurrency hardened
- Crash recoverable

Uses UUID primary keys.
"""
import hashlib
import json
from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional, List, Dict, Any
import uuid

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text, Boolean,
    UniqueConstraint, Index, Numeric, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, validates

from backend.database import Base


# =============================================================================
# Enums
# =============================================================================

class RoundType(PyEnum):
    PRELIM = "prelim"
    QUARTER_FINAL = "quarter_final"
    SEMI_FINAL = "semi_final"
    FINAL = "final"


class RoundStatus(PyEnum):
    SCHEDULED = "scheduled"
    LIVE = "live"
    COMPLETED = "completed"
    FROZEN = "frozen"


class MatchStatus(PyEnum):
    SCHEDULED = "scheduled"
    LIVE = "live"
    SCORING = "scoring"
    COMPLETED = "completed"
    FROZEN = "frozen"


class TurnStatus(PyEnum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    LOCKED = "locked"


class SpeakerRole(PyEnum):
    P1 = "p1"
    P2 = "p2"
    R1 = "r1"
    R2 = "r2"
    REBUTTAL_P = "rebuttal_p"
    REBUTTAL_R = "rebuttal_r"


# Deterministic speaker flow sequence
SPEAKER_FLOW_SEQUENCE = [
    SpeakerRole.P1,
    SpeakerRole.P2,
    SpeakerRole.R1,
    SpeakerRole.R2,
    SpeakerRole.REBUTTAL_P,
    SpeakerRole.REBUTTAL_R,
]


# =============================================================================
# Table: tournament_rounds
# =============================================================================

class TournamentRound(Base):
    """
    Tournament round with strict state machine.
    
    State transitions:
        SCHEDULED → LIVE → COMPLETED → FROZEN
    """
    __tablename__ = "tournament_rounds"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tournament_id = Column(
        UUID(as_uuid=True),
        ForeignKey('tournaments.id', ondelete='RESTRICT'),
        nullable=False,
        index=True
    )
    round_number = Column(Integer, nullable=False)
    round_type = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default='scheduled')
    bench_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    matches = relationship("TournamentMatch", back_populates="round", lazy='selectin')
    
    __table_args__ = (
        UniqueConstraint('tournament_id', 'round_number', name='uq_round_tournament_number'),
        Index('idx_round_status', 'status'),
        Index('idx_round_tournament', 'tournament_id'),
        CheckConstraint("round_number > 0", name="ck_round_number_positive"),
        CheckConstraint("bench_count >= 0", name="ck_bench_count_non_negative"),
        CheckConstraint(
            "status IN ('scheduled', 'live', 'completed', 'frozen')",
            name="ck_round_status_valid"
        ),
    )
    
    @validates('status')
    def validate_status(self, key, value):
        valid_transitions = {
            'scheduled': ['live'],
            'live': ['completed'],
            'completed': ['frozen'],
            'frozen': [],  # Terminal state
        }
        if self.status and value not in valid_transitions.get(self.status, []):
            raise ValueError(f"Invalid status transition: {self.status} → {value}")
        return value


# =============================================================================
# Table: tournament_matches
# =============================================================================

class TournamentMatch(Base):
    """
    Individual match within a round.
    
    State transitions:
        SCHEDULED → LIVE → SCORING → COMPLETED → FROZEN
    """
    __tablename__ = "tournament_matches"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    round_id = Column(
        UUID(as_uuid=True),
        ForeignKey('tournament_rounds.id', ondelete='RESTRICT'),
        nullable=False,
        index=True
    )
    bench_number = Column(Integer, nullable=False)
    team_petitioner_id = Column(
        UUID(as_uuid=True),
        ForeignKey('tournament_teams.id', ondelete='RESTRICT'),
        nullable=False
    )
    team_respondent_id = Column(
        UUID(as_uuid=True),
        ForeignKey('tournament_teams.id', ondelete='RESTRICT'),
        nullable=False
    )
    status = Column(String(20), nullable=False, default='scheduled')
    winner_team_id = Column(
        UUID(as_uuid=True),
        ForeignKey('tournament_teams.id', ondelete='SET NULL'),
        nullable=True
    )
    locked = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    round = relationship("TournamentRound", back_populates="matches")
    speaker_turns = relationship("MatchSpeakerTurn", back_populates="match", order_by="MatchSpeakerTurn.turn_order", lazy='selectin')
    timer_state = relationship("MatchTimerState", back_populates="match", uselist=False, lazy='selectin')
    score_lock = relationship("MatchScoreLock", back_populates="match", uselist=False, lazy='selectin')
    
    __table_args__ = (
        UniqueConstraint('round_id', 'bench_number', name='uq_match_round_bench'),
        Index('idx_match_status', 'status'),
        Index('idx_match_round', 'round_id'),
        Index('idx_match_petitioner', 'team_petitioner_id'),
        Index('idx_match_respondent', 'team_respondent_id'),
        CheckConstraint("bench_number > 0", name="ck_bench_number_positive"),
        CheckConstraint(
            "status IN ('scheduled', 'live', 'scoring', 'completed', 'frozen')",
            name="ck_match_status_valid"
        ),
    )
    
    @validates('status')
    def validate_status(self, key, value):
        valid_transitions = {
            'scheduled': ['live'],
            'live': ['scoring', 'completed'],
            'scoring': ['completed'],
            'completed': ['frozen'],
            'frozen': [],  # Terminal state
        }
        if self.status and value not in valid_transitions.get(self.status, []):
            raise ValueError(f"Invalid status transition: {self.status} → {value}")
        return value


# =============================================================================
# Table: match_speaker_turns
# =============================================================================

class MatchSpeakerTurn(Base):
    """
    Pre-generated speaker turns for deterministic flow.
    
    All turns generated BEFORE match starts.
    No insertion allowed after match LIVE.
    """
    __tablename__ = "match_speaker_turns"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    match_id = Column(
        UUID(as_uuid=True),
        ForeignKey('tournament_matches.id', ondelete='RESTRICT'),
        nullable=False,
        index=True
    )
    team_id = Column(
        UUID(as_uuid=True),
        ForeignKey('tournament_teams.id', ondelete='RESTRICT'),
        nullable=False
    )
    speaker_role = Column(String(20), nullable=False)
    turn_order = Column(Integer, nullable=False)
    allocated_seconds = Column(Integer, nullable=False, default=600)  # 10 min default
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    status = Column(String(20), nullable=False, default='pending')
    
    # Relationships
    match = relationship("TournamentMatch", back_populates="speaker_turns")
    
    __table_args__ = (
        UniqueConstraint('match_id', 'turn_order', name='uq_turn_match_order'),
        Index('idx_turn_status', 'status'),
        Index('idx_turn_match', 'match_id'),
        Index('idx_turn_team', 'team_id'),
        CheckConstraint("turn_order > 0", name="ck_turn_order_positive"),
        CheckConstraint("allocated_seconds > 0", name="ck_allocated_seconds_positive"),
        CheckConstraint(
            "status IN ('pending', 'active', 'completed', 'locked')",
            name="ck_turn_status_valid"
        ),
        CheckConstraint(
            "speaker_role IN ('p1', 'p2', 'r1', 'r2', 'rebuttal_p', 'rebuttal_r')",
            name="ck_speaker_role_valid"
        ),
    )
    
    @validates('status')
    def validate_status(self, key, value):
        valid_transitions = {
            'pending': ['active'],
            'active': ['completed'],
            'completed': ['locked'],
            'locked': [],  # Terminal state
        }
        if self.status and value not in valid_transitions.get(self.status, []):
            raise ValueError(f"Invalid status transition: {self.status} → {value}")
        return value


# =============================================================================
# Table: match_timer_state
# =============================================================================

class MatchTimerState(Base):
    """
    Crash-recoverable timer state.
    
    Single row per match. Updated on every tick.
    """
    __tablename__ = "match_timer_state"
    
    match_id = Column(
        UUID(as_uuid=True),
        ForeignKey('tournament_matches.id', ondelete='CASCADE'),
        primary_key=True
    )
    active_turn_id = Column(
        UUID(as_uuid=True),
        ForeignKey('match_speaker_turns.id', ondelete='SET NULL'),
        nullable=True
    )
    remaining_seconds = Column(Integer, nullable=False, default=0)
    paused = Column(Boolean, nullable=False, default=False)
    last_tick = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    match = relationship("TournamentMatch", back_populates="timer_state")
    active_turn = relationship("MatchSpeakerTurn", lazy='selectin')
    
    __table_args__ = (
        CheckConstraint("remaining_seconds >= 0", name="ck_timer_remaining_non_negative"),
    )


# =============================================================================
# Table: match_score_lock
# =============================================================================

class MatchScoreLock(Base):
    """
    Immutable match result after freeze.
    
    Once written, no modifications allowed.
    Includes integrity hash for verification.
    """
    __tablename__ = "match_score_lock"
    
    match_id = Column(
        UUID(as_uuid=True),
        ForeignKey('tournament_matches.id', ondelete='CASCADE'),
        primary_key=True
    )
    total_petitioner_score = Column(Numeric(5, 2), nullable=False)
    total_respondent_score = Column(Numeric(5, 2), nullable=False)
    winner_team_id = Column(
        UUID(as_uuid=True),
        ForeignKey('tournament_teams.id', ondelete='RESTRICT'),
        nullable=True
    )
    frozen_hash = Column(Text, nullable=False)
    frozen_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    match = relationship("TournamentMatch", back_populates="score_lock")
    
    __table_args__ = (
        CheckConstraint("total_petitioner_score >= 0", name="ck_score_petitioner_non_negative"),
        CheckConstraint("total_respondent_score >= 0", name="ck_score_respondent_non_negative"),
        CheckConstraint(
            "total_petitioner_score <= 1000",
            name="ck_score_petitioner_max"
        ),
        CheckConstraint(
            "total_respondent_score <= 1000",
            name="ck_score_respondent_max"
        ),
    )
    
    def compute_integrity_hash(self, turn_ids: List[str], judge_ids: List[str]) -> str:
        """
        Compute deterministic hash for integrity verification.
        
        Hash formula:
            SHA256(ordered_turn_ids + final_scores + judge_ids + timestamps)
        """
        data = {
            'match_id': str(self.match_id),
            'turn_ids': sorted([str(tid) for tid in turn_ids]),
            'petitioner_score': str(self.total_petitioner_score),
            'respondent_score': str(self.total_respondent_score),
            'winner_id': str(self.winner_team_id) if self.winner_team_id else None,
            'judge_ids': sorted([str(jid) for jid in judge_ids]),
            'frozen_at': self.frozen_at.isoformat() if self.frozen_at else None,
        }
        canonical = json.dumps(data, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical.encode()).hexdigest()
