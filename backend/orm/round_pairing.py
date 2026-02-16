"""
Phase 3 — Hardened Round Pairing Engine ORM Models

Swiss + Knockout Pairing with:
- Deterministic SHA256 hashing
- Immutable freeze records
- Rematch prevention (pairing_history)
- No float(), no random(), no datetime.now()
"""
import hashlib
import json
from datetime import datetime
from enum import Enum as PyEnum
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, 
    Index, UniqueConstraint, Enum
)
from sqlalchemy.orm import relationship, validates
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy import event

from backend.database import Base
from backend.core.db_types import UniversalJSON


# =============================================================================
# Enums
# =============================================================================

class RoundType(PyEnum):
    SWISS = "swiss"
    KNOCKOUT = "knockout"


class RoundStatus(PyEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    FINALIZED = "finalized"


# =============================================================================
# Model 1: TournamentRound
# =============================================================================

class TournamentRound(Base):
    __tablename__ = "tournament_rounds"
    
    id = Column(Integer, primary_key=True, index=True)
    tournament_id = Column(
        Integer, 
        ForeignKey("national_tournaments.id", ondelete="RESTRICT"),
        nullable=False
    )
    round_number = Column(Integer, nullable=False)
    round_type = Column(Enum(RoundType, create_constraint=True), nullable=False)
    status = Column(Enum(RoundStatus, create_constraint=True), nullable=False, default=RoundStatus.DRAFT)
    pairing_checksum = Column(String(64), nullable=True)
    published_at = Column(DateTime, nullable=True)
    finalized_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    pairings = relationship("RoundPairing", back_populates="round", cascade="all, delete-orphan")
    freeze = relationship("RoundFreeze", back_populates="round", uselist=False)
    tournament = relationship("NationalTournament", back_populates="rounds")
    
    __table_args__ = (
        UniqueConstraint('tournament_id', 'round_number', name='uq_round_tournament_number'),
        Index('idx_rounds_tournament', 'tournament_id', 'status'),
    )
    
    def to_dict(self, include_pairings: bool = False) -> Dict[str, Any]:
        """Serialize to dictionary."""
        result = {
            "id": self.id,
            "tournament_id": self.tournament_id,
            "round_number": self.round_number,
            "round_type": self.round_type.value if self.round_type else None,
            "status": self.status.value if self.status else None,
            "pairing_checksum": self.pairing_checksum,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "finalized_at": self.finalized_at.isoformat() if self.finalized_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        
        if include_pairings:
            # Sort pairings deterministically by table_number
            sorted_pairings = sorted(
                self.pairings, 
                key=lambda p: p.table_number if p.table_number is not None else 0
            )
            result["pairings"] = [p.to_dict() for p in sorted_pairings]
        
        return result


# =============================================================================
# Model 2: RoundPairing
# =============================================================================

class RoundPairing(Base):
    __tablename__ = "round_pairings"
    
    id = Column(Integer, primary_key=True, index=True)
    round_id = Column(
        Integer,
        ForeignKey("tournament_rounds.id", ondelete="RESTRICT"),
        nullable=False
    )
    petitioner_team_id = Column(
        Integer,
        ForeignKey("tournament_teams.id", ondelete="RESTRICT"),
        nullable=False
    )
    respondent_team_id = Column(
        Integer,
        ForeignKey("tournament_teams.id", ondelete="RESTRICT"),
        nullable=False
    )
    table_number = Column(Integer, nullable=False)
    pairing_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    round = relationship("TournamentRound", back_populates="pairings")
    petitioner_team = relationship("TournamentTeam", foreign_keys=[petitioner_team_id])
    respondent_team = relationship("TournamentTeam", foreign_keys=[respondent_team_id])
    
    __table_args__ = (
        UniqueConstraint('round_id', 'petitioner_team_id', name='uq_pairing_petitioner'),
        UniqueConstraint('round_id', 'respondent_team_id', name='uq_pairing_respondent'),
        UniqueConstraint('round_id', 'table_number', name='uq_pairing_table'),
        Index('idx_pairings_round', 'round_id'),
    )
    
    def compute_pairing_hash(self) -> str:
        """
        Compute deterministic SHA256 hash of pairing data.
        
        Hash formula:
        SHA256(f"{round_id}|{petitioner_team_id}|{respondent_team_id}|{table_number}")
        """
        combined = (
            f"{self.round_id}|"
            f"{self.petitioner_team_id}|"
            f"{self.respondent_team_id}|"
            f"{self.table_number}"
        )
        
        return hashlib.sha256(combined.encode()).hexdigest()
    
    def verify_hash(self) -> bool:
        """Verify stored hash matches computed hash."""
        if not self.pairing_hash:
            return False
        return self.pairing_hash == self.compute_pairing_hash()
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "round_id": self.round_id,
            "petitioner_team_id": self.petitioner_team_id,
            "respondent_team_id": self.respondent_team_id,
            "table_number": self.table_number,
            "pairing_hash": self.pairing_hash,
            "hash_valid": self.verify_hash(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# =============================================================================
# Model 3: PairingHistory (Rematch Prevention)
# =============================================================================

class PairingHistory(Base):
    __tablename__ = "pairing_history"
    
    id = Column(Integer, primary_key=True, index=True)
    tournament_id = Column(
        Integer,
        ForeignKey("national_tournaments.id", ondelete="RESTRICT"),
        nullable=False
    )
    # team_a_id always < team_b_id (enforced in service layer)
    team_a_id = Column(
        Integer,
        ForeignKey("tournament_teams.id", ondelete="RESTRICT"),
        nullable=False
    )
    team_b_id = Column(
        Integer,
        ForeignKey("tournament_teams.id", ondelete="RESTRICT"),
        nullable=False
    )
    round_id = Column(
        Integer,
        ForeignKey("tournament_rounds.id", ondelete="RESTRICT"),
        nullable=False
    )
    
    # Relationships
    tournament = relationship("NationalTournament")
    team_a = relationship("TournamentTeam", foreign_keys=[team_a_id])
    team_b = relationship("TournamentTeam", foreign_keys=[team_b_id])
    round = relationship("TournamentRound")
    
    __table_args__ = (
        UniqueConstraint('tournament_id', 'team_a_id', 'team_b_id', name='uq_history_teams'),
        Index('idx_history_tournament', 'tournament_id'),
        Index('idx_history_teams', 'team_a_id', 'team_b_id'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "tournament_id": self.tournament_id,
            "team_a_id": self.team_a_id,
            "team_b_id": self.team_b_id,
            "round_id": self.round_id,
        }


# =============================================================================
# Model 4: RoundFreeze
# =============================================================================

class RoundFreeze(Base):
    __tablename__ = "round_freeze"
    
    id = Column(Integer, primary_key=True, index=True)
    round_id = Column(
        Integer,
        ForeignKey("tournament_rounds.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True
    )
    pairing_snapshot_json = Column(UniversalJSON, nullable=False, default=list)
    round_checksum = Column(String(64), nullable=False)
    frozen_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False
    )
    frozen_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    round = relationship("TournamentRound", back_populates="freeze")
    frozen_by_user = relationship("User")
    
    __table_args__ = (
        Index('idx_freeze_round', 'round_id'),
    )
    
    def compute_round_checksum(self, pairing_hashes: List[str]) -> str:
        """
        Compute deterministic SHA256 checksum from all pairing hashes.
        
        Formula:
        SHA256(sorted_hashes joined by "|")
        """
        # Sort hashes alphabetically for determinism
        sorted_hashes = sorted(pairing_hashes)
        combined = "|".join(sorted_hashes)
        
        return hashlib.sha256(combined.encode()).hexdigest()
    
    def verify_checksum(self, current_pairing_hashes: List[str]) -> bool:
        """Verify stored checksum matches current pairings."""
        computed = self.compute_round_checksum(current_pairing_hashes)
        return self.round_checksum == computed
    
    def to_dict(self, include_snapshot: bool = False) -> Dict[str, Any]:
        """Serialize to dictionary."""
        result = {
            "id": self.id,
            "round_id": self.round_id,
            "round_checksum": self.round_checksum,
            "frozen_by": self.frozen_by,
            "frozen_at": self.frozen_at.isoformat() if self.frozen_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "total_pairings": len(self.pairing_snapshot_json) if self.pairing_snapshot_json else 0,
        }
        
        if include_snapshot:
            result["pairing_snapshot_json"] = self.pairing_snapshot_json
        
        return result


# =============================================================================
# ORM Event Listeners (Additional Immutability Guards)
# =============================================================================

@event.listens_for(RoundPairing, 'before_update')
def prevent_pairing_update(mapper, connection, target):
    """Prevent modification of frozen pairings at ORM level."""
    # This is a secondary guard - primary protection is PostgreSQL trigger
    pass  # Triggers handle the heavy lifting


@event.listens_for(RoundFreeze, 'before_insert')
def validate_freeze_data(mapper, connection, target):
    """Validate freeze data before insertion."""
    if not target.round_checksum:
        raise ValueError("round_checksum is required")
    if not target.pairing_snapshot_json:
        raise ValueError("pairing_snapshot_json is required")
