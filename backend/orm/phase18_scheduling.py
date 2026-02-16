"""
Phase 18 — Scheduling & Court Allocation Engine.

ORM models for deterministic court scheduling without modifying Phase 14-17 tables.
"""
from enum import Enum
from datetime import datetime, date, time
from sqlalchemy import (
    Column, String, Integer, Boolean, ForeignKey, Date, DateTime, Text,
    UniqueConstraint, CheckConstraint, Index, text
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from backend.orm.base import Base


class ScheduleStatus(str, Enum):
    """Schedule day status state machine."""
    DRAFT = "draft"
    LOCKED = "locked"
    FROZEN = "frozen"


class AssignmentStatus(str, Enum):
    """Match schedule assignment status."""
    ASSIGNED = "assigned"
    CONFIRMED = "confirmed"


class Courtroom(Base):
    """
    Physical/virtual courtroom for tournament matches.
    
    Attributes:
        id: UUID primary key
        tournament_id: FK to tournament
        name: Courtroom name (e.g., "Courtroom A", "Virtual Room 1")
        capacity: Maximum capacity (nullable)
        is_active: Whether courtroom is available
    """
    __tablename__ = "courtrooms"
    
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()")
    )
    tournament_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tournaments.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    name = Column(String(100), nullable=False)
    capacity = Column(Integer, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    assignments = relationship(
        "MatchScheduleAssignment",
        back_populates="courtroom",
        cascade="all, delete-orphan"
    )
    
    __table_args__ = (
        UniqueConstraint(
            "tournament_id", "name",
            name="uq_tournament_court_name"
        ),
        Index("idx_court_tournament", "tournament_id"),
    )
    
    def to_dict(self):
        return {
            "id": str(self.id),
            "tournament_id": str(self.tournament_id),
            "name": self.name,
            "capacity": self.capacity,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ScheduleDay(Base):
    """
    A scheduled day in a tournament.
    
    Status flow: DRAFT → LOCKED → FROZEN
    FROZEN schedules are immutable with integrity_hash verification.
    
    Attributes:
        id: UUID primary key
        tournament_id: FK to tournament
        day_number: Sequential day number (> 0)
        date: Calendar date
        status: DRAFT/LOCKED/FROZEN
        integrity_hash: SHA256 hash for frozen schedules
    """
    __tablename__ = "schedule_days"
    
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()")
    )
    tournament_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tournaments.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    day_number = Column(Integer, nullable=False)
    date = Column(Date, nullable=False)
    status = Column(
        String(20),
        nullable=False,
        default=ScheduleStatus.DRAFT
    )
    integrity_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    time_slots = relationship(
        "TimeSlot",
        back_populates="schedule_day",
        cascade="all, delete-orphan",
        order_by="TimeSlot.slot_order"
    )
    
    __table_args__ = (
        UniqueConstraint(
            "tournament_id", "day_number",
            name="uq_tournament_day"
        ),
        CheckConstraint(
            "day_number > 0",
            name="ck_day_number_positive"
        ),
        CheckConstraint(
            f"status IN ('{ScheduleStatus.DRAFT}', '{ScheduleStatus.LOCKED}', '{ScheduleStatus.FROZEN}')",
            name="ck_status_valid"
        ),
        Index("idx_schedule_day_tournament", "tournament_id"),
        Index("idx_schedule_day_status", "status"),
    )
    
    def to_dict(self):
        return {
            "id": str(self.id),
            "tournament_id": str(self.tournament_id),
            "day_number": self.day_number,
            "date": self.date.isoformat() if self.date else None,
            "status": self.status,
            "integrity_hash": self.integrity_hash,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class TimeSlot(Base):
    """
    A time slot within a scheduled day.
    
    Attributes:
        id: UUID primary key
        schedule_day_id: FK to schedule_day
        start_time: Slot start datetime
        end_time: Slot end datetime
        slot_order: Display order within day (> 0)
    """
    __tablename__ = "time_slots"
    
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()")
    )
    schedule_day_id = Column(
        UUID(as_uuid=True),
        ForeignKey("schedule_days.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    slot_order = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    schedule_day = relationship("ScheduleDay", back_populates="time_slots")
    assignments = relationship(
        "MatchScheduleAssignment",
        back_populates="time_slot",
        cascade="all, delete-orphan"
    )
    
    __table_args__ = (
        UniqueConstraint(
            "schedule_day_id", "slot_order",
            name="uq_day_slot_order"
        ),
        CheckConstraint(
            "start_time < end_time",
            name="ck_start_before_end"
        ),
        CheckConstraint(
            "slot_order > 0",
            name="ck_slot_order_positive"
        ),
        Index("idx_time_slot_day", "schedule_day_id"),
    )
    
    def to_dict(self):
        return {
            "id": str(self.id),
            "schedule_day_id": str(self.schedule_day_id),
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "slot_order": self.slot_order,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class MatchScheduleAssignment(Base):
    """
    Assignment of a match to a courtroom, time slot, and judge.
    
    This is an operational orchestration record - it never modifies
    Phase 14 match tables or any frozen scores.
    
    Attributes:
        id: UUID primary key
        match_id: FK to tournament_matches
        courtroom_id: FK to courtrooms
        time_slot_id: FK to time_slots
        judge_user_id: FK to users (judge)
        status: ASSIGNED/CONFIRMED
    """
    __tablename__ = "match_schedule_assignments"
    
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()")
    )
    match_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tournament_matches.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    courtroom_id = Column(
        UUID(as_uuid=True),
        ForeignKey("courtrooms.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    time_slot_id = Column(
        UUID(as_uuid=True),
        ForeignKey("time_slots.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    judge_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    status = Column(
        String(20),
        nullable=False,
        default=AssignmentStatus.ASSIGNED
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    courtroom = relationship("Courtroom", back_populates="assignments")
    time_slot = relationship("TimeSlot", back_populates="assignments")
    
    __table_args__ = (
        # One match can only be scheduled once
        UniqueConstraint(
            "match_id",
            name="uq_match_once"
        ),
        # One courtroom per slot
        UniqueConstraint(
            "courtroom_id", "time_slot_id",
            name="uq_court_slot"
        ),
        # One judge per slot
        UniqueConstraint(
            "judge_user_id", "time_slot_id",
            name="uq_judge_slot"
        ),
        CheckConstraint(
            f"status IN ('{AssignmentStatus.ASSIGNED}', '{AssignmentStatus.CONFIRMED}')",
            name="ck_assignment_status_valid"
        ),
        # Performance indexes
        Index("idx_assignment_match", "match_id"),
        Index("idx_assignment_court", "courtroom_id"),
        Index("idx_assignment_judge", "judge_user_id"),
        Index("idx_assignment_slot", "time_slot_id"),
    )
    
    def to_dict(self):
        return {
            "id": str(self.id),
            "match_id": str(self.match_id),
            "courtroom_id": str(self.courtroom_id),
            "time_slot_id": str(self.time_slot_id),
            "judge_user_id": str(self.judge_user_id) if self.judge_user_id else None,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
