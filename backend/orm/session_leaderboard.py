"""
Session Leaderboard Models — Phase 5 (Immutable Leaderboard Engine)

Production-grade leaderboard snapshotting for institutional-grade auditability.

Immutability guarantees:
- Snapshot rows are NEVER updated after creation
- Leaderboard entries are NEVER modified after freeze
- ON DELETE RESTRICT prevents accidental cascade deletion
- Checksum verification for tamper detection
"""
import enum
import hashlib
import json
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, 
    Text, Numeric, Index, UniqueConstraint, Enum, Boolean
)
from sqlalchemy.orm import relationship

from sqlalchemy import event

from backend.orm.base import Base


class LeaderboardSide(str, enum.Enum):
    """Side of the argument in moot court."""
    PETITIONER = "petitioner"
    RESPONDENT = "respondent"


class SessionLeaderboardSnapshot(Base):
    """
    Immutable snapshot of a session leaderboard at freeze time.
    
    One row per session freeze event. Contains metadata about the frozen
    leaderboard state including checksum for integrity verification.
    
    Rules:
    - NEVER update after creation
    - ON DELETE RESTRICT (cannot delete referenced records)
    - Checksum is SHA256 of ordered participant data
    """
    __tablename__ = "session_leaderboard_snapshots"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Foreign keys - all with RESTRICT delete
    session_id = Column(
        Integer, 
        ForeignKey("classroom_sessions.id", ondelete="RESTRICT"),
        nullable=False
    )
    frozen_by_faculty_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False
    )
    rubric_version_id = Column(
        Integer,
        ForeignKey("ai_rubric_versions.id", ondelete="RESTRICT"),
        nullable=False
    )
    
    # Freeze metadata
    frozen_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # AI model used for evaluations (for reproducibility)
    ai_model_version = Column(String(100), nullable=True)
    
    # Statistics
    total_participants = Column(Integer, nullable=False)
    
    # Integrity checksum
    checksum_hash = Column(String(64), nullable=False)  # SHA256 hex
    
    # COMPLIANCE MODE: Soft deletion via invalidation
    # Snapshots are NEVER physically deleted - only marked as invalidated
    is_invalidated = Column(Boolean, nullable=False, default=False)
    invalidated_reason = Column(Text, nullable=True)
    invalidated_at = Column(DateTime, nullable=True)
    invalidated_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    # PHASE 6: Governance Approval States
    # Tracks approval workflow before finalization
    is_pending_approval = Column(Boolean, nullable=False, default=False)
    is_finalized = Column(Boolean, nullable=False, default=False)
    finalized_at = Column(DateTime, nullable=True)
    
    # PHASE 6: Publication Control
    # Controls visibility and publication lifecycle
    publication_mode = Column(
        Enum("DRAFT", "SCHEDULED", "PUBLISHED", name="publication_mode_enum", create_constraint=True),
        nullable=False,
        default="DRAFT"
    )
    publication_date = Column(DateTime, nullable=True)  # For SCHEDULED mode
    is_published = Column(Boolean, nullable=False, default=False)
    published_at = Column(DateTime, nullable=True)
    published_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    session = relationship("ClassroomSession", back_populates="leaderboard_snapshots")
    frozen_by = relationship("User", foreign_keys=[frozen_by_faculty_id])
    rubric_version = relationship("AIRubricVersion")
    entries = relationship(
        "SessionLeaderboardEntry",
        back_populates="snapshot",
        order_by="SessionLeaderboardEntry.rank"
    )
    audit_entries = relationship(
        "SessionLeaderboardAudit",
        back_populates="snapshot"
    )
    
    __table_args__ = (
        UniqueConstraint("session_id", name="uq_session_snapshot"),
        Index("idx_snapshots_session", "session_id"),
        Index("idx_snapshots_faculty", "frozen_by_faculty_id"),
        Index("idx_snapshots_frozen_at", "frozen_at"),
        Index("idx_snapshots_finalized", "is_finalized"),  # PHASE 6
        Index("idx_snapshots_published", "is_published"),  # PHASE 6
        Index("idx_snapshots_pub_mode", "publication_mode"),  # PHASE 6
    )
    
    def __repr__(self) -> str:
        return f"<SessionLeaderboardSnapshot(id={self.id}, session_id={self.session_id}, frozen_at={self.frozen_at})>"
    
    def is_active(self) -> bool:
        """Check if snapshot is active (not invalidated)."""
        return not self.is_invalidated
    
    def is_visible_to_public(self) -> bool:
        """PHASE 6: Check if snapshot is publicly visible."""
        return self.is_published and not self.is_invalidated
    
    def is_visible_to_students(self) -> bool:
        """PHASE 6: Check if students can view this snapshot."""
        return self.is_published and not self.is_invalidated and self.publication_mode != "SCHEDULED"
    
    def can_be_published(self) -> bool:
        """PHASE 6: Check if snapshot meets requirements for publication."""
        return (
            self.is_finalized 
            and not self.is_invalidated 
            and not self.is_published
        )
    
    def verify_integrity(self, service_checksum_func=None) -> bool:
        """
        Verify leaderboard integrity against stored checksum.
        
        Requires service-level checksum function to be passed in.
        Returns True if data is unmodified.
        """
        if not self.checksum_hash or not self.entries:
            return True  # Nothing to verify
        
        if service_checksum_func is None:
            # Cannot verify without service function
            return True
        
        computed = service_checksum_func(self.entries)
        return computed == self.checksum_hash
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "frozen_at": self.frozen_at.isoformat() if self.frozen_at else None,
            "frozen_by_faculty_id": self.frozen_by_faculty_id,
            "rubric_version_id": self.rubric_version_id,
            "ai_model_version": self.ai_model_version,
            "total_participants": self.total_participants,
            "checksum_hash": self.checksum_hash,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "entries": [e.to_dict() for e in self.entries] if self.entries else [],
            # PHASE 6: Governance fields
            "is_pending_approval": self.is_pending_approval,
            "is_finalized": self.is_finalized,
            "finalized_at": self.finalized_at.isoformat() if self.finalized_at else None,
            # PHASE 6: Publication fields
            "publication_mode": self.publication_mode,
            "publication_date": self.publication_date.isoformat() if self.publication_date else None,
            "is_published": self.is_published,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            # Compliance fields
            "is_invalidated": self.is_invalidated,
            "invalidated_reason": self.invalidated_reason if self.is_invalidated else None,
        }


class SessionLeaderboardEntry(Base):
    """
    Single participant entry in a frozen leaderboard.
    
    Immutable record of a participant's final ranking and scores.
    Ties are broken deterministically using tie_breaker_score.
    
    Rules:
    - NEVER update after creation
    - ON DELETE RESTRICT on snapshot
    """
    __tablename__ = "session_leaderboard_entries"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Foreign keys
    snapshot_id = Column(
        Integer,
        ForeignKey("session_leaderboard_snapshots.id", ondelete="RESTRICT"),
        nullable=False
    )
    participant_id = Column(
        Integer,
        ForeignKey("classroom_participants.id", ondelete="RESTRICT"),
        nullable=False
    )
    
    # Participant metadata at freeze time
    side = Column(
        Enum(LeaderboardSide, name="leaderboard_side_enum", create_constraint=True),
        nullable=False
    )
    speaker_number = Column(Integer, nullable=True)
    
    # Scores
    total_score = Column(Numeric(10, 2), nullable=False)
    tie_breaker_score = Column(Numeric(10, 4), nullable=False, default=0)
    
    # Ranking
    rank = Column(Integer, nullable=False)
    
    # Detailed breakdown
    score_breakdown_json = Column(Text, nullable=True)  # JSON: {round_id: score}
    
    # Audit trail - which evaluations contributed to this score
    evaluation_ids_json = Column(Text, nullable=True)  # JSON: [evaluation_id, ...]
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    snapshot = relationship("SessionLeaderboardSnapshot", back_populates="entries")
    participant = relationship("ClassroomParticipant", back_populates="leaderboard_entries")
    
    __table_args__ = (
        # Prevent duplicate entries per snapshot
        UniqueConstraint("snapshot_id", "participant_id", name="uq_snapshot_participant"),
        
        # STEP 7: Extra rank integrity constraint
        # Ensures no duplicate ranks within same snapshot (ranking integrity)
        UniqueConstraint("snapshot_id", "rank", "participant_id", name="uq_snapshot_rank_participant"),
        
        # Index for common queries
        Index("idx_entries_snapshot", "snapshot_id"),
        Index("idx_entries_snapshot_rank", "snapshot_id", "rank"),
        Index("idx_entries_snapshot_score", "snapshot_id", "total_score"),
        Index("idx_entries_participant", "participant_id"),
    )
    
    def __repr__(self) -> str:
        return f"<SessionLeaderboardEntry(id={self.id}, snapshot_id={self.snapshot_id}, rank={self.rank}, participant_id={self.participant_id})>"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        import json
        from decimal import Decimal
        return {
            "id": self.id,
            "snapshot_id": self.snapshot_id,
            "participant_id": self.participant_id,
            "side": self.side.value if self.side else None,
            "speaker_number": self.speaker_number,
            "total_score": str(Decimal(self.total_score).quantize(Decimal("0.01"))) if self.total_score else "0.00",
            "tie_breaker_score": str(Decimal(self.tie_breaker_score).quantize(Decimal("0.0001"))) if self.tie_breaker_score else "0.0000",
            "rank": self.rank,
            "score_breakdown": json.loads(self.score_breakdown_json) if self.score_breakdown_json else {},
            "evaluation_ids": json.loads(self.evaluation_ids_json) if self.evaluation_ids_json else [],
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class SessionLeaderboardAudit(Base):
    """
    Audit trail for leaderboard operations.
    
    Tracks all leaderboard lifecycle events including:
    - LEADERBOARD_FROZEN
    - LEADERBOARD_DELETED (admin only)
    - Any future admin operations
    
    Immutable audit entries with proper foreign key relationships.
    """
    __tablename__ = "session_leaderboard_audit"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Foreign key with proper relationship
    snapshot_id = Column(
        Integer,
        ForeignKey("session_leaderboard_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )
    
    # Audit fields
    action = Column(String(50), nullable=False, index=True)
    actor_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    
    # Payload (JSON)
    payload_json = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    snapshot = relationship("SessionLeaderboardSnapshot", back_populates="audit_entries")
    actor = relationship("User", foreign_keys=[actor_user_id])
    
    __table_args__ = ()
    
    def __repr__(self) -> str:
        return f"<SessionLeaderboardAudit(id={self.id}, snapshot_id={self.snapshot_id}, action={self.action})>"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        import json
        return {
            "id": self.id,
            "snapshot_id": self.snapshot_id,
            "action": self.action,
            "actor_user_id": self.actor_user_id,
            "payload": json.loads(self.payload_json) if self.payload_json else {},
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


# =============================================================================
# ORM-Level Immutability Guards
# =============================================================================

@event.listens_for(SessionLeaderboardEntry, "before_update")
def prevent_entry_update(mapper, connection, target):
    """Prevent any updates to leaderboard entries after creation."""
    raise Exception("Leaderboard entries are immutable - updates are prohibited")


@event.listens_for(SessionLeaderboardSnapshot, "before_update")
def prevent_snapshot_update(mapper, connection, target):
    """
    Prevent updates to leaderboard snapshots except for invalidation fields.
    
    The only allowed updates are:
    - is_invalidated (compliance mode soft delete)
    - invalidated_reason
    - invalidated_at
    - invalidated_by
    """
    # Get the current state from database
    from sqlalchemy import select
    current = connection.execute(
        select(
            SessionLeaderboardSnapshot.is_invalidated,
            SessionLeaderboardSnapshot.invalidated_reason,
            SessionLeaderboardSnapshot.invalidated_at,
            SessionLeaderboardSnapshot.invalidated_by
        ).where(SessionLeaderboardSnapshot.id == target.id)
    ).fetchone()
    
    if current:
        # Allow only invalidation-related field changes
        is_invalidated_unchanged = target.is_invalidated == current.is_invalidated
        reason_unchanged = target.invalidated_reason == current.invalidated_reason
        at_unchanged = target.invalidated_at == current.invalidated_at
        by_unchanged = target.invalidated_by == current.invalidated_by
        
        # If any non-invalidation field changed, raise error
        if is_invalidated_unchanged and reason_unchanged and at_unchanged and by_unchanged:
            raise Exception("Leaderboard snapshots are immutable - only invalidation allowed")
