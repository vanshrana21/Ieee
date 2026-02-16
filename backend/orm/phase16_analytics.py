"""
Phase 16 — Performance Analytics & Ranking Intelligence Layer ORM Models.

Pure deterministic analytics on top of Phase 14 and 15.
No LLM calls. 100% deterministic math.
All writes use FOR UPDATE locking for concurrency safety.
"""
import uuid
import enum
from datetime import datetime
from typing import Optional, Dict, Any
from decimal import Decimal

from sqlalchemy import (
    Column, String, Integer, Float, DateTime, ForeignKey,
    UniqueConstraint, Index, CheckConstraint, DECIMAL, Enum as SQLEnum
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.orm.base import Base


class EntityType(enum.Enum):
    """Entity types for rankings and trends."""
    SPEAKER = "speaker"
    TEAM = "team"
    INSTITUTION = "institution"


class RankingTier(enum.Enum):
    """Ranking tiers based on ELO rating."""
    S = "S"
    A = "A"
    B = "B"
    C = "C"


class StreakType(enum.Enum):
    """Types of performance streaks."""
    WIN = "win"
    LOSS = "loss"
    NONE = "none"


class SpeakerPerformanceStats(Base):
    """
    Performance statistics for individual speakers.
    Aggregated from FROZEN + evaluated matches only.
    """
    __tablename__ = "speaker_performance_stats"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    
    # Match statistics
    total_matches = Column(Integer, default=0, nullable=False)
    wins = Column(Integer, default=0, nullable=False)
    losses = Column(Integer, default=0, nullable=False)
    
    # Score metrics
    avg_score = Column(DECIMAL(5, 2), default=Decimal("0.00"), nullable=False)
    avg_ai_score = Column(DECIMAL(5, 2), default=Decimal("0.00"), nullable=False)
    confidence_weighted_score = Column(DECIMAL(6, 3), default=Decimal("0.000"), nullable=False)
    
    # Performance indicators
    rebuttal_success_rate = Column(DECIMAL(5, 2), default=Decimal("0.00"), nullable=False)
    consistency_index = Column(DECIMAL(6, 3), default=Decimal("0.000"), nullable=False)
    peak_score = Column(DECIMAL(5, 2), default=Decimal("0.00"), nullable=False)
    lowest_score = Column(DECIMAL(5, 2), default=Decimal("0.00"), nullable=False)
    
    # Trends
    improvement_trend = Column(DECIMAL(6, 3), default=Decimal("0.000"), nullable=False)
    
    # Metadata
    last_updated = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    
    # Constraints
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_speaker_stats_user_id"),
        CheckConstraint("total_matches >= 0", name="ck_speaker_total_matches_nonneg"),
        CheckConstraint("wins >= 0", name="ck_speaker_wins_nonneg"),
        CheckConstraint("losses >= 0", name="ck_speaker_losses_nonneg"),
        CheckConstraint("wins + losses <= total_matches", name="ck_speaker_wl_vs_total"),
        CheckConstraint("avg_score BETWEEN 0 AND 100", name="ck_speaker_avg_score_range"),
        CheckConstraint("avg_ai_score BETWEEN 0 AND 100", name="ck_speaker_ai_score_range"),
        CheckConstraint("confidence_weighted_score BETWEEN 0 AND 1", name="ck_speaker_conf_weight_range"),
        CheckConstraint("rebuttal_success_rate BETWEEN 0 AND 100", name="ck_speaker_rebuttal_range"),
        CheckConstraint("peak_score BETWEEN 0 AND 100", name="ck_speaker_peak_range"),
        CheckConstraint("lowest_score BETWEEN 0 AND 100", name="ck_speaker_lowest_range"),
        CheckConstraint("consistency_index >= 0", name="ck_speaker_consistency_nonneg"),
        Index("idx_speaker_stats_user_id", "user_id"),
        Index("idx_speaker_stats_avg_score", "avg_score"),
        Index("idx_speaker_stats_wins", "wins"),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "total_matches": self.total_matches,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": round(self.wins / self.total_matches * 100, 2) if self.total_matches > 0 else 0,
            "avg_score": float(self.avg_score),
            "avg_ai_score": float(self.avg_ai_score),
            "confidence_weighted_score": float(self.confidence_weighted_score),
            "rebuttal_success_rate": float(self.rebuttal_success_rate),
            "consistency_index": float(self.consistency_index),
            "peak_score": float(self.peak_score),
            "lowest_score": float(self.lowest_score),
            "improvement_trend": float(self.improvement_trend),
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
        }


class TeamPerformanceStats(Base):
    """
    Performance statistics for teams.
    Aggregated from FROZEN + evaluated matches only.
    """
    __tablename__ = "team_performance_stats"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    team_id = Column(String(36), ForeignKey("tournament_teams.id"), nullable=False, index=True)
    
    # Match statistics
    total_matches = Column(Integer, default=0, nullable=False)
    wins = Column(Integer, default=0, nullable=False)
    losses = Column(Integer, default=0, nullable=False)
    
    # Score metrics
    avg_score = Column(DECIMAL(5, 2), default=Decimal("0.00"), nullable=False)
    avg_ai_score = Column(DECIMAL(5, 2), default=Decimal("0.00"), nullable=False)
    
    # Team synergy and performance indicators
    team_synergy_index = Column(DECIMAL(6, 3), default=Decimal("0.000"), nullable=False)
    comeback_index = Column(DECIMAL(6, 3), default=Decimal("0.000"), nullable=False)
    freeze_integrity_score = Column(DECIMAL(6, 3), default=Decimal("0.000"), nullable=False)
    
    # Rankings
    rank_points = Column(DECIMAL(8, 2), default=Decimal("0.00"), nullable=False)
    national_rank = Column(Integer, default=0, nullable=False)
    institution_rank = Column(Integer, default=0, nullable=False)
    
    # Metadata
    last_updated = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    
    # Constraints
    __table_args__ = (
        UniqueConstraint("team_id", name="uq_team_stats_team_id"),
        CheckConstraint("total_matches >= 0", name="ck_team_total_matches_nonneg"),
        CheckConstraint("wins >= 0", name="ck_team_wins_nonneg"),
        CheckConstraint("losses >= 0", name="ck_team_losses_nonneg"),
        CheckConstraint("wins + losses <= total_matches", name="ck_team_wl_vs_total"),
        CheckConstraint("avg_score BETWEEN 0 AND 100", name="ck_team_avg_score_range"),
        CheckConstraint("avg_ai_score BETWEEN 0 AND 100", name="ck_team_ai_score_range"),
        CheckConstraint("freeze_integrity_score BETWEEN 0 AND 1", name="ck_team_integrity_range"),
        CheckConstraint("team_synergy_index >= 0", name="ck_team_synergy_nonneg"),
        Index("idx_team_stats_team_id", "team_id"),
        Index("idx_team_stats_rank_points", "rank_points"),
        Index("idx_team_stats_national_rank", "national_rank"),
        Index("idx_team_stats_institution_rank", "institution_rank"),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "team_id": self.team_id,
            "total_matches": self.total_matches,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": round(self.wins / self.total_matches * 100, 2) if self.total_matches > 0 else 0,
            "avg_score": float(self.avg_score),
            "avg_ai_score": float(self.avg_ai_score),
            "team_synergy_index": float(self.team_synergy_index),
            "comeback_index": float(self.comeback_index),
            "freeze_integrity_score": float(self.freeze_integrity_score),
            "rank_points": float(self.rank_points),
            "national_rank": self.national_rank,
            "institution_rank": self.institution_rank,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
        }


class JudgeBehaviorProfile(Base):
    """
    Behavioral analytics for judges.
    Tracks scoring patterns, bias, and alignment with AI evaluations.
    """
    __tablename__ = "judge_behavior_profile"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    judge_user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    
    # Scoring patterns
    total_matches_scored = Column(Integer, default=0, nullable=False)
    avg_score_given = Column(DECIMAL(5, 2), default=Decimal("0.00"), nullable=False)
    score_variance = Column(DECIMAL(6, 3), default=Decimal("0.000"), nullable=False)
    
    # AI alignment
    ai_deviation_index = Column(DECIMAL(6, 3), default=Decimal("0.000"), nullable=False)
    confidence_alignment_score = Column(DECIMAL(6, 3), default=Decimal("0.000"), nullable=False)
    
    # Bias detection
    bias_petitioner_ratio = Column(DECIMAL(6, 3), default=Decimal("0.000"), nullable=False)
    bias_respondent_ratio = Column(DECIMAL(6, 3), default=Decimal("0.000"), nullable=False)
    
    # Strictness
    strictness_index = Column(DECIMAL(6, 3), default=Decimal("0.000"), nullable=False)
    
    # Metadata
    last_updated = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    
    # Constraints
    __table_args__ = (
        UniqueConstraint("judge_user_id", name="uq_judge_profile_user_id"),
        CheckConstraint("total_matches_scored >= 0", name="ck_judge_total_scored_nonneg"),
        CheckConstraint("avg_score_given BETWEEN 0 AND 100", name="ck_judge_avg_given_range"),
        CheckConstraint("score_variance >= 0", name="ck_judge_variance_nonneg"),
        CheckConstraint("ai_deviation_index >= 0", name="ck_judge_ai_dev_nonneg"),
        CheckConstraint("bias_petitioner_ratio BETWEEN 0 AND 1", name="ck_judge_bias_pet_range"),
        CheckConstraint("bias_respondent_ratio BETWEEN 0 AND 1", name="ck_judge_bias_resp_range"),
        CheckConstraint("confidence_alignment_score BETWEEN 0 AND 1", name="ck_judge_conf_align_range"),
        Index("idx_judge_profile_user_id", "judge_user_id"),
        Index("idx_judge_profile_matches_scored", "total_matches_scored"),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "judge_user_id": self.judge_user_id,
            "total_matches_scored": self.total_matches_scored,
            "avg_score_given": float(self.avg_score_given),
            "score_variance": float(self.score_variance),
            "ai_deviation_index": float(self.ai_deviation_index),
            "confidence_alignment_score": float(self.confidence_alignment_score),
            "bias_petitioner_ratio": float(self.bias_petitioner_ratio),
            "bias_respondent_ratio": float(self.bias_respondent_ratio),
            "strictness_index": float(self.strictness_index),
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
        }


class NationalRankings(Base):
    """
    National rankings using ELO and deterministic sorting.
    """
    __tablename__ = "national_rankings"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Entity identification
    entity_type = Column(SQLEnum(EntityType), nullable=False, index=True)
    entity_id = Column(String(36), nullable=False, index=True)
    
    # Ranking metrics
    rating_score = Column(Float, default=1500.0, nullable=False)
    elo_rating = Column(Float, default=1500.0, nullable=False)
    volatility = Column(Float, default=0.06, nullable=False)
    confidence_score = Column(Float, default=0.0, nullable=False)
    
    # Tier assignment
    tier = Column(SQLEnum(RankingTier), default=RankingTier.C, nullable=False, index=True)
    
    # Rank position
    rank_position = Column(Integer, default=0, nullable=False, index=True)
    previous_rank = Column(Integer, default=0, nullable=False)
    rank_movement = Column(Integer, default=0, nullable=False)
    
    # Season
    season = Column(String(10), default="2026", nullable=False)
    
    # Metadata
    last_calculated = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    
    # Constraints
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "season", name="uq_rankings_entity_season"),
        CheckConstraint("rating_score >= 0", name="ck_rankings_rating_nonneg"),
        CheckConstraint("elo_rating >= 0", name="ck_rankings_elo_nonneg"),
        CheckConstraint("volatility >= 0", name="ck_rankings_volatility_nonneg"),
        CheckConstraint("confidence_score BETWEEN 0 AND 1", name="ck_rankings_conf_range"),
        CheckConstraint("rank_position >= 0", name="ck_rankings_pos_nonneg"),
        Index("idx_rankings_entity", "entity_type", "entity_id"),
        Index("idx_rankings_season", "season"),
        Index("idx_rankings_tier", "tier"),
        Index("idx_rankings_rating_desc", "rating_score"),
        Index("idx_rankings_position", "rank_position"),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "entity_type": self.entity_type.value if self.entity_type else None,
            "entity_id": self.entity_id,
            "rating_score": self.rating_score,
            "elo_rating": self.elo_rating,
            "volatility": self.volatility,
            "confidence_score": self.confidence_score,
            "tier": self.tier.value if self.tier else None,
            "rank_position": self.rank_position,
            "previous_rank": self.previous_rank,
            "rank_movement": self.rank_movement,
            "season": self.season,
            "last_calculated": self.last_calculated.isoformat() if self.last_calculated else None,
        }


class PerformanceTrends(Base):
    """
    Performance trends and momentum metrics.
    """
    __tablename__ = "performance_trends"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Entity identification
    entity_type = Column(SQLEnum(EntityType), nullable=False)
    entity_id = Column(String(36), nullable=False)
    
    # Moving averages
    last_5_avg = Column(DECIMAL(5, 2), default=Decimal("0.00"), nullable=False)
    last_10_avg = Column(DECIMAL(5, 2), default=Decimal("0.00"), nullable=False)
    
    # Velocity and volatility
    improvement_velocity = Column(DECIMAL(6, 3), default=Decimal("0.000"), nullable=False)
    volatility_index = Column(DECIMAL(6, 3), default=Decimal("0.000"), nullable=False)
    
    # Streak tracking
    streak_type = Column(SQLEnum(StreakType), default=StreakType.NONE, nullable=False)
    streak_count = Column(Integer, default=0, nullable=False)
    
    # Momentum
    momentum_score = Column(DECIMAL(6, 3), default=Decimal("0.000"), nullable=False)
    risk_index = Column(DECIMAL(6, 3), default=Decimal("0.000"), nullable=False)
    
    # Metadata
    last_updated = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    
    # Constraints
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", name="uq_trends_entity"),
        CheckConstraint("last_5_avg BETWEEN 0 AND 100", name="ck_trends_last5_range"),
        CheckConstraint("last_10_avg BETWEEN 0 AND 100", name="ck_trends_last10_range"),
        CheckConstraint("volatility_index >= 0", name="ck_trends_volatility_nonneg"),
        CheckConstraint("streak_count >= 0", name="ck_trends_streak_nonneg"),
        CheckConstraint("risk_index BETWEEN 0 AND 1", name="ck_trends_risk_range"),
        Index("idx_trends_entity", "entity_type", "entity_id"),
        Index("idx_trends_momentum", "momentum_score"),
        Index("idx_trends_streak", "streak_type", "streak_count"),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "entity_type": self.entity_type.value if self.entity_type else None,
            "entity_id": self.entity_id,
            "last_5_avg": float(self.last_5_avg),
            "last_10_avg": float(self.last_10_avg),
            "improvement_velocity": float(self.improvement_velocity),
            "volatility_index": float(self.volatility_index),
            "streak_type": self.streak_type.value if self.streak_type else None,
            "streak_count": self.streak_count,
            "momentum_score": float(self.momentum_score),
            "risk_index": float(self.risk_index),
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
        }
