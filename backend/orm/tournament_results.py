"""
Phase 9 — Tournament Results & Ranking Engine
ORM Models for tournament_team_results, tournament_speaker_results, tournament_results_freeze

Deterministic ranking, immutable after freeze, SHA256 verification.
"""
import hashlib
import json
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Dict, Any
from datetime import datetime

from sqlalchemy import (
    Column, Integer, Numeric, String, ForeignKey, DateTime,
    UniqueConstraint, CheckConstraint
)
from sqlalchemy.orm import relationship

from backend.database import Base
from backend.core.db_types import UniversalJSON


# =============================================================================
# Quantizers for Decimal precision
# =============================================================================

QUANTIZER_2DP = Decimal("0.01")      # For scores
QUANTIZER_3DP = Decimal("0.001")     # For percentile
QUANTIZER_4DP = Decimal("0.0001")   # For SOS


class TournamentTeamResult(Base):
    """
    Final tournament results for a team.
    
    Immutable after freeze (enforced by PostgreSQL trigger).
    Deterministic ranking with tie-breakers.
    """
    __tablename__ = 'tournament_team_results'
    
    id = Column(Integer, primary_key=True, index=True)
    tournament_id = Column(
        Integer,
        ForeignKey('national_tournaments.id', ondelete='RESTRICT'),
        nullable=False,
        index=True
    )
    team_id = Column(
        Integer,
        ForeignKey('tournament_teams.id', ondelete='RESTRICT'),
        nullable=False,
        index=True
    )
    
    # Scores
    memorial_total = Column(Numeric(12, 2), nullable=False, default=0)
    oral_total = Column(Numeric(12, 2), nullable=False, default=0)
    total_score = Column(Numeric(14, 2), nullable=False, default=0)
    
    # Strength of schedule
    strength_of_schedule = Column(Numeric(12, 4), nullable=False, default=0)
    opponent_wins_total = Column(Integer, nullable=False, default=0)
    
    # Rankings
    final_rank = Column(Integer, nullable=True)
    percentile = Column(Numeric(6, 3), nullable=True)
    
    # Integrity
    result_hash = Column(String(64), nullable=False)
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('tournament_id', 'team_id', name='uq_team_result'),
        CheckConstraint(
            'total_score = memorial_total + oral_total',
            name='chk_total_score'
        ),
    )
    
    # Relationships
    tournament = relationship("NationalTournament")
    team = relationship("TournamentTeam")
    
    def compute_hash(self) -> str:
        """
        Compute SHA256 hash of result data for tamper detection.
        
        Formula:
        SHA256(f"{team_id}|{total_score:.2f}|{sos:.4f}|{rank}|{percentile:.3f}")
        
        Returns:
            Hex digest of SHA256 hash
        """
        # Convert Decimals to quantize for consistent string representation
        total_score_q = Decimal(str(self.total_score)).quantize(QUANTIZER_2DP)
        sos_q = Decimal(str(self.strength_of_schedule)).quantize(QUANTIZER_4DP)
        
        if self.percentile is not None:
            percentile_q = Decimal(str(self.percentile)).quantize(QUANTIZER_3DP)
            percentile_str = f"{percentile_q:.3f}"
        else:
            percentile_str = ""
        
        combined = (
            f"{self.team_id}|"
            f"{total_score_q:.2f}|"
            f"{sos_q:.4f}|"
            f"{self.final_rank or ''}|"
            f"{percentile_str}"
        )
        
        return hashlib.sha256(combined.encode()).hexdigest()
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize to dictionary with deterministic ordering.
        
        Returns:
            Sorted dict representation
        """
        return {
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "final_rank": self.final_rank,
            "id": self.id,
            "memorial_total": float(self.memorial_total) if self.memorial_total else 0,
            "opponent_wins_total": self.opponent_wins_total,
            "oral_total": float(self.oral_total) if self.oral_total else 0,
            "percentile": float(self.percentile) if self.percentile else None,
            "result_hash": self.result_hash,
            "strength_of_schedule": float(self.strength_of_schedule) if self.strength_of_schedule else 0,
            "team_id": self.team_id,
            "total_score": float(self.total_score) if self.total_score else 0,
            "tournament_id": self.tournament_id
        }


class TournamentSpeakerResult(Base):
    """
    Final tournament results for a speaker.
    
    Immutable after freeze (enforced by PostgreSQL trigger).
    """
    __tablename__ = 'tournament_speaker_results'
    
    id = Column(Integer, primary_key=True, index=True)
    tournament_id = Column(
        Integer,
        ForeignKey('national_tournaments.id', ondelete='RESTRICT'),
        nullable=False,
        index=True
    )
    speaker_id = Column(
        Integer,
        ForeignKey('users.id', ondelete='RESTRICT'),
        nullable=False,
        index=True
    )
    
    # Scores
    total_speaker_score = Column(Numeric(12, 2), nullable=False, default=0)
    average_score = Column(Numeric(12, 4), nullable=False, default=0)
    rounds_participated = Column(Integer, nullable=False, default=0)
    
    # Rankings
    final_rank = Column(Integer, nullable=True)
    percentile = Column(Numeric(6, 3), nullable=True)
    
    # Integrity
    speaker_hash = Column(String(64), nullable=False)
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('tournament_id', 'speaker_id', name='uq_speaker_result'),
    )
    
    # Relationships
    tournament = relationship("NationalTournament")
    speaker = relationship("User")
    
    def compute_hash(self) -> str:
        """
        Compute SHA256 hash of speaker result data.
        
        Returns:
            Hex digest of SHA256 hash
        """
        total_q = Decimal(str(self.total_speaker_score)).quantize(QUANTIZER_2DP)
        avg_q = Decimal(str(self.average_score)).quantize(QUANTIZER_4DP)
        
        if self.percentile is not None:
            percentile_q = Decimal(str(self.percentile)).quantize(QUANTIZER_3DP)
            percentile_str = f"{percentile_q:.3f}"
        else:
            percentile_str = ""
        
        combined = (
            f"{self.speaker_id}|"
            f"{total_q:.2f}|"
            f"{avg_q:.4f}|"
            f"{self.rounds_participated}|"
            f"{self.final_rank or ''}|"
            f"{percentile_str}"
        )
        
        return hashlib.sha256(combined.encode()).hexdigest()
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize to dictionary with deterministic ordering.
        
        Returns:
            Sorted dict representation
        """
        return {
            "average_score": float(self.average_score) if self.average_score else 0,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "final_rank": self.final_rank,
            "id": self.id,
            "percentile": float(self.percentile) if self.percentile else None,
            "rounds_participated": self.rounds_participated,
            "speaker_hash": self.speaker_hash,
            "speaker_id": self.speaker_id,
            "total_speaker_score": float(self.total_speaker_score) if self.total_speaker_score else 0,
            "tournament_id": self.tournament_id
        }


class TournamentResultsFreeze(Base):
    """
    Immutable snapshot of tournament results at finalization.
    
    Once created, cannot be modified or deleted (enforced by PostgreSQL trigger).
    """
    __tablename__ = 'tournament_results_freeze'
    
    id = Column(Integer, primary_key=True, index=True)
    tournament_id = Column(
        Integer,
        ForeignKey('national_tournaments.id', ondelete='RESTRICT'),
        nullable=False,
        unique=True,
        index=True
    )
    
    # Snapshots (immutable JSON)
    team_snapshot_json = Column(UniversalJSON, nullable=False)
    speaker_snapshot_json = Column(UniversalJSON, nullable=False)
    
    # Global integrity checksum
    results_checksum = Column(String(64), nullable=False)
    
    # Audit trail
    frozen_by = Column(
        Integer,
        ForeignKey('users.id', ondelete='RESTRICT'),
        nullable=False
    )
    frozen_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    tournament = relationship("NationalTournament")
    frozen_by_user = relationship("User")
    
    def compute_global_checksum(self, team_hashes: list, speaker_hashes: list) -> str:
        """
        Compute global checksum from all individual result hashes.
        
        Args:
            team_hashes: List of team result SHA256 hashes
            speaker_hashes: List of speaker result SHA256 hashes
        
        Returns:
            Global SHA256 checksum
        """
        # Sort for determinism
        all_hashes = sorted(team_hashes + speaker_hashes)
        combined = "|".join(all_hashes)
        
        return hashlib.sha256(combined.encode()).hexdigest()
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize to dictionary.
        
        Returns:
            Dict representation
        """
        return {
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "frozen_at": self.frozen_at.isoformat() if self.frozen_at else None,
            "frozen_by": self.frozen_by,
            "id": self.id,
            "results_checksum": self.results_checksum,
            "speaker_snapshot_json": self.speaker_snapshot_json,
            "team_snapshot_json": self.team_snapshot_json,
            "tournament_id": self.tournament_id
        }


# Update relationships on related models
# These would be added to the respective model files:
# NationalTournament.team_results = relationship("TournamentTeamResult", back_populates="tournament")
# NationalTournament.speaker_results = relationship("TournamentSpeakerResult", back_populates="tournament")
# NationalTournament.results_freeze = relationship("TournamentResultsFreeze", back_populates="tournament", uselist=False)
# NationalTournament.audit_snapshot = relationship("TournamentAuditSnapshot", back_populates="tournament", uselist=False)
# TournamentTeam.results = relationship("TournamentTeamResult", back_populates="team", uselist=False)
# User.tournament_results = relationship("TournamentSpeakerResult", back_populates="speaker")


# =============================================================================
# Phase 12 — Tournament Audit Snapshot
# =============================================================================

class TournamentAuditSnapshot(Base):
    """
    Immutable audit snapshot with Merkle root integrity.
    
    Once created, tournament is frozen and no modifications allowed.
    Cryptographically tamper-evident using HMAC-SHA256 signature.
    """
    __tablename__ = 'tournament_audit_snapshots'
    
    id = Column(Integer, primary_key=True, index=True)
    tournament_id = Column(
        Integer,
        ForeignKey('national_tournaments.id', ondelete='RESTRICT'),
        nullable=False,
        unique=True,
        index=True
    )
    institution_id = Column(
        Integer,
        ForeignKey('institutions.id', ondelete='RESTRICT'),
        nullable=False,
        index=True
    )
    
    # Merkle root and integrity
    audit_root_hash = Column(String(64), nullable=False, unique=True)
    snapshot_json = Column(UniversalJSON, nullable=False)
    signature_hmac = Column(String(64), nullable=False)
    
    # Audit trail
    generated_by = Column(
        Integer,
        ForeignKey('users.id', ondelete='RESTRICT'),
        nullable=False
    )
    generated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    tournament = relationship("NationalTournament")
    institution = relationship("Institution")
    generated_by_user = relationship("User")
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize to dictionary with deterministic ordering.
        
        Returns:
            Sorted dict representation
        """
        return {
            "audit_root_hash": self.audit_root_hash,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "generated_at": self.generated_at.isoformat() if self.generated_at else None,
            "generated_by": self.generated_by,
            "id": self.id,
            "institution_id": self.institution_id,
            "signature_hmac": self.signature_hmac,
            "snapshot_json": self.snapshot_json,
            "tournament_id": self.tournament_id
        }
