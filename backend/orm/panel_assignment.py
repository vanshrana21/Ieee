"""
Phase 4 — Hardened Judge Panel Assignment Engine ORM Models

Conflict Detection + Immutability with:
- Deterministic SHA256 hashing
- Immutable freeze records
- Judge assignment history for conflict detection
- Panel member role tracking
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
from sqlalchemy import event

from backend.database import Base
from backend.core.db_types import UniversalJSON


# =============================================================================
# Enums
# =============================================================================

class PanelMemberRole(PyEnum):
    PRESIDING = "presiding"
    MEMBER = "member"


# =============================================================================
# Model 1: JudgePanel
# =============================================================================

class JudgePanel(Base):
    __tablename__ = "judge_panels"
    
    id = Column(Integer, primary_key=True, index=True)
    round_id = Column(
        Integer,
        ForeignKey("tournament_rounds.id", ondelete="RESTRICT"),
        nullable=False
    )
    table_number = Column(Integer, nullable=False)
    panel_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    round = relationship("TournamentRound", back_populates="judge_panels")
    members = relationship("PanelMember", back_populates="panel", cascade="all, delete-orphan")
    
    __table_args__ = (
        UniqueConstraint('round_id', 'table_number', name='uq_panel_round_table'),
        Index('idx_panel_round', 'round_id'),
    )
    
    def compute_panel_hash(self) -> str:
        """
        Compute deterministic SHA256 hash of panel data.
        
        Hash formula:
        SHA256(f"{panel_id}|{sorted_judge_ids}|{table_number}")
        """
        # Get sorted member judge IDs
        member_ids = sorted([m.judge_id for m in self.members]) if self.members else []
        member_ids_str = ",".join(str(id) for id in member_ids)
        
        combined = (
            f"{self.id or 0}|"
            f"[{member_ids_str}]|"
            f"{self.table_number}"
        )
        
        return hashlib.sha256(combined.encode()).hexdigest()
    
    def update_hash(self):
        """Update the panel_hash after members are set."""
        self.panel_hash = self.compute_panel_hash()
    
    def verify_hash(self) -> bool:
        """Verify stored hash matches computed hash."""
        if not self.panel_hash:
            return False
        return self.panel_hash == self.compute_panel_hash()
    
    def to_dict(self, include_members: bool = False) -> Dict[str, Any]:
        """Serialize to dictionary."""
        result = {
            "id": self.id,
            "round_id": self.round_id,
            "table_number": self.table_number,
            "panel_hash": self.panel_hash,
            "hash_valid": self.verify_hash(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        
        if include_members:
            # Sort members deterministically by role then judge_id
            sorted_members = sorted(
                self.members,
                key=lambda m: (0 if m.role == PanelMemberRole.PRESIDING else 1, m.judge_id)
            )
            result["members"] = [m.to_dict() for m in sorted_members]
            result["member_count"] = len(self.members)
        
        return result


# =============================================================================
# Model 2: PanelMember
# =============================================================================

class PanelMember(Base):
    __tablename__ = "panel_members"
    
    id = Column(Integer, primary_key=True, index=True)
    panel_id = Column(
        Integer,
        ForeignKey("judge_panels.id", ondelete="RESTRICT"),
        nullable=False
    )
    judge_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False
    )
    role = Column(
        Enum(PanelMemberRole, create_constraint=True),
        nullable=False,
        default=PanelMemberRole.MEMBER
    )
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    panel = relationship("JudgePanel", back_populates="members")
    judge = relationship("User")
    
    __table_args__ = (
        UniqueConstraint('panel_id', 'judge_id', name='uq_panel_member'),
        Index('idx_panel_members_panel', 'panel_id'),
        Index('idx_panel_members_judge', 'judge_id'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "panel_id": self.panel_id,
            "judge_id": self.judge_id,
            "role": self.role.value if self.role else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# =============================================================================
# Model 3: JudgeAssignmentHistory (Conflict Detection)
# =============================================================================

class JudgeAssignmentHistory(Base):
    __tablename__ = "judge_assignment_history"
    
    id = Column(Integer, primary_key=True, index=True)
    tournament_id = Column(
        Integer,
        ForeignKey("national_tournaments.id", ondelete="RESTRICT"),
        nullable=False
    )
    judge_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False
    )
    team_id = Column(
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
    judge = relationship("User")
    team = relationship("TournamentTeam")
    round = relationship("TournamentRound")
    
    __table_args__ = (
        UniqueConstraint('tournament_id', 'judge_id', 'team_id', name='uq_assignment_judge_team'),
        Index('idx_assignment_history_tournament', 'tournament_id'),
        Index('idx_assignment_history_judge', 'judge_id'),
        Index('idx_assignment_history_team', 'team_id'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "tournament_id": self.tournament_id,
            "judge_id": self.judge_id,
            "team_id": self.team_id,
            "round_id": self.round_id,
        }


# =============================================================================
# Model 4: PanelFreeze
# =============================================================================

class PanelFreeze(Base):
    __tablename__ = "panel_freeze"
    
    id = Column(Integer, primary_key=True, index=True)
    round_id = Column(
        Integer,
        ForeignKey("tournament_rounds.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True
    )
    panel_snapshot_json = Column(UniversalJSON, nullable=False, default=list)
    panel_checksum = Column(String(64), nullable=False)
    frozen_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False
    )
    frozen_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    round = relationship("TournamentRound", back_populates="panel_freeze")
    frozen_by_user = relationship("User")
    
    __table_args__ = (
        Index('idx_panel_freeze_round', 'round_id'),
    )
    
    def compute_panel_checksum(self, panel_hashes: List[str]) -> str:
        """
        Compute deterministic SHA256 checksum from all panel hashes.
        
        Formula:
        SHA256(sorted_hashes joined by "|")
        """
        # Sort hashes alphabetically for determinism
        sorted_hashes = sorted(panel_hashes)
        combined = "|".join(sorted_hashes)
        
        return hashlib.sha256(combined.encode()).hexdigest()
    
    def verify_checksum(self, current_panel_hashes: List[str]) -> bool:
        """Verify stored checksum matches current panels."""
        computed = self.compute_panel_checksum(current_panel_hashes)
        return self.panel_checksum == computed
    
    def to_dict(self, include_snapshot: bool = False) -> Dict[str, Any]:
        """Serialize to dictionary."""
        result = {
            "id": self.id,
            "round_id": self.round_id,
            "panel_checksum": self.panel_checksum,
            "frozen_by": self.frozen_by,
            "frozen_at": self.frozen_at.isoformat() if self.frozen_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "total_panels": len(self.panel_snapshot_json) if self.panel_snapshot_json else 0,
        }
        
        if include_snapshot:
            result["panel_snapshot_json"] = self.panel_snapshot_json
        
        return result


# =============================================================================
# ORM Event Listeners (Additional Immutability Guards)
# =============================================================================

@event.listens_for(JudgePanel, 'before_insert')
def validate_panel_before_insert(mapper, connection, target):
    """Validate panel data before insertion."""
    if target.table_number is None or target.table_number < 1:
        raise ValueError("table_number must be a positive integer")


@event.listens_for(PanelMember, 'before_insert')
def validate_member_before_insert(mapper, connection, target):
    """Validate panel member data before insertion."""
    if target.role is None:
        target.role = PanelMemberRole.MEMBER


@event.listens_for(PanelFreeze, 'before_insert')
def validate_freeze_data(mapper, connection, target):
    """Validate freeze data before insertion."""
    if not target.panel_checksum:
        raise ValueError("panel_checksum is required")
    if not target.panel_snapshot_json:
        raise ValueError("panel_snapshot_json is required")
