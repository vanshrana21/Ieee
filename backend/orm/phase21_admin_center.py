"""
Phase 21 — Admin Command Center ORM.

Operational control layer for governance, monitoring, and audit.
Strictly on top of Phases 14–20.

Deterministic action logging with integrity hashes.
"""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    Column, String, DateTime, ForeignKey, Index, CheckConstraint, text, JSON
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from backend.database import Base


class AdminActionLog(Base):
    """
    Deterministic action logging for admin operations.
    
    Every administrative action is logged with an integrity hash
    for audit verification. Hash covers actor, action type, target,
    and payload snapshot.
    """
    __tablename__ = "admin_action_logs"
    
    id = Column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid4
    )
    
    tournament_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tournaments.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    action_type = Column(
        String(50),
        nullable=False
    )
    
    actor_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    
    target_id = Column(
        UUID(as_uuid=True),
        nullable=True
    )
    
    payload_snapshot = Column(
        JSON,
        nullable=False,
        default=dict
    )
    
    integrity_hash = Column(
        String(64),
        nullable=False
    )
    
    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    
    # Relationships
    tournament = relationship("Tournament", back_populates="admin_action_logs")
    actor = relationship("User", foreign_keys=[actor_user_id])
    
    # Table constraints
    __table_args__ = (
        CheckConstraint(
            "action_type <> ''",
            name="ck_action_type_not_empty"
        ),
        CheckConstraint(
            "LENGTH(integrity_hash) = 64",
            name="ck_hash_length_64"
        ),
        Index(
            "idx_admin_logs_tournament_created",
            "tournament_id",
            "created_at"
        ),
    )
    
    def __repr__(self) -> str:
        return (
            f"<AdminActionLog(id={self.id}, "
            f"action_type='{self.action_type}', "
            f"tournament_id={self.tournament_id})>"
        )
