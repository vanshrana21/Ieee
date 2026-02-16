"""
Phase 20 — Tournament Lifecycle Orchestrator.

ORM models for deterministic tournament state machine with cross-phase governance.
"""
from enum import Enum
from datetime import datetime
from sqlalchemy import (
    Column, String, DateTime, ForeignKey, UniqueConstraint, CheckConstraint, Index, text
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from backend.orm.base import Base


class TournamentStatus(str, Enum):
    """Tournament lifecycle status state machine."""
    DRAFT = "draft"
    REGISTRATION_OPEN = "registration_open"
    REGISTRATION_CLOSED = "registration_closed"
    SCHEDULING = "scheduling"
    ROUNDS_RUNNING = "rounds_running"
    SCORING_LOCKED = "scoring_locked"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class TournamentLifecycle(Base):
    """
    Global tournament lifecycle state machine.
    
    Governs tournament-wide state and enforces cross-phase invariants.
    ARCHIVED is terminal - no further modifications allowed.
    
    Attributes:
        id: UUID primary key
        tournament_id: FK to tournaments (unique)
        status: Current lifecycle status
        final_standings_hash: SHA256 of rankings at completion
        archived_at: When tournament was archived
        created_at, updated_at: Timestamps
    """
    __tablename__ = "tournament_lifecycle"
    
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()")
    )
    tournament_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tournaments.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True
    )
    status = Column(
        String(30),
        nullable=False,
        default=TournamentStatus.DRAFT
    )
    final_standings_hash = Column(String(64), nullable=True)
    archived_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        # Unique tournament constraint
        UniqueConstraint("tournament_id", name="uq_lifecycle_tournament"),
        
        # Valid status constraint
        CheckConstraint(
            f"status IN ('{TournamentStatus.DRAFT}', '{TournamentStatus.REGISTRATION_OPEN}', "
            f"'{TournamentStatus.REGISTRATION_CLOSED}', '{TournamentStatus.SCHEDULING}', "
            f"'{TournamentStatus.ROUNDS_RUNNING}', '{TournamentStatus.SCORING_LOCKED}', "
            f"'{TournamentStatus.COMPLETED}', '{TournamentStatus.ARCHIVED}')",
            name="ck_lifecycle_status_valid"
        ),
        
        # ARCHIVED status requires archived_at
        CheckConstraint(
            f"(status != '{TournamentStatus.ARCHIVED}') OR (archived_at IS NOT NULL)",
            name="ck_archived_has_timestamp"
        ),
        
        # Indexes
        Index("idx_lifecycle_tournament", "tournament_id"),
        Index("idx_lifecycle_status", "status"),
    )
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "tournament_id": str(self.tournament_id),
            "status": self.status,
            "final_standings_hash": self.final_standings_hash,
            "archived_at": self.archived_at.isoformat() if self.archived_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
