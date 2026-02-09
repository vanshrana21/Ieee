"""
backend/orm/submission_slot.py
Phase 5C: Oral round slot picker with calendar/availability system
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Enum as SQLEnum, Float
from sqlalchemy.orm import relationship
from datetime import datetime, timedelta
from enum import Enum as PyEnum
from backend.orm.base import Base


class SlotStatus(str, PyEnum):
    """Slot availability status"""
    AVAILABLE = "available"      # Open for booking
    RESERVED = "reserved"        # Tentatively held (payment pending, etc.)
    BOOKED = "booked"            # Confirmed booking
    BLOCKED = "blocked"          # Blocked by admin (break, etc.)
    COMPLETED = "completed"      # Oral round completed
    CANCELLED = "cancelled"      # Cancelled booking


class SlotType(str, PyEnum):
    """Type of oral round slot"""
    PRELIMINARY = "preliminary"
    QUARTERFINAL = "quarterfinal"
    SEMIFINAL = "semifinal"
    FINAL = "final"
    PRACTICE = "practice"


class SubmissionSlot(Base):
    """
    Oral round time slot with calendar/availability system.
    Teams can view available slots and book their oral round time.
    """
    __tablename__ = "submission_slots"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Institution and Competition scoping (Phase 5B)
    institution_id = Column(
        Integer,
        ForeignKey("institutions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    competition_id = Column(
        Integer,
        ForeignKey("competitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    round_id = Column(
        Integer,
        ForeignKey("competition_rounds.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    
    # Slot details
    slot_type = Column(SQLEnum(SlotType), default=SlotType.PRELIMINARY, nullable=False)
    status = Column(SQLEnum(SlotStatus), default=SlotStatus.AVAILABLE, nullable=False)
    
    # Time (UTC, displayed in competition timezone)
    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime, nullable=False)
    duration_minutes = Column(Integer, nullable=False, default=30)
    
    # Venue/Room
    venue = Column(String(255), nullable=True)  # "Courtroom A", "Zoom Room 1"
    room_url = Column(String(500), nullable=True)  # For virtual hearings
    
    # Booking details
    booked_by_team_id = Column(Integer, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True, index=True)
    booked_at = Column(DateTime, nullable=True)
    
    # Judges assigned to this slot
    presiding_judge_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    wing_judge_1_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    wing_judge_2_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Team side assignment (which side argues when)
    petitioner_team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)
    respondent_team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)
    
    # Scoring
    petitioner_score = Column(Float, nullable=True)
    respondent_score = Column(Float, nullable=True)
    
    # Notes
    admin_notes = Column(Text, nullable=True)
    judge_notes = Column(Text, nullable=True)
    
    # Conflict resolution
    is_conflict = Column(Boolean, default=False)  # Double-booking detected
    conflict_resolved_at = Column(DateTime, nullable=True)
    
    # Metadata
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<SubmissionSlot(id={self.id}, start={self.start_time}, status={self.status})>"
    
    def to_dict(self, timezone="UTC"):
        now = datetime.utcnow()
        
        return {
            "id": self.id,
            "institution_id": self.institution_id,
            "competition_id": self.competition_id,
            "round_id": self.round_id,
            "slot_type": self.slot_type.value if self.slot_type else None,
            "status": self.status.value if self.status else None,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_minutes": self.duration_minutes,
            "venue": self.venue,
            "room_url": self.room_url,
            "booked_by_team_id": self.booked_by_team_id,
            "booked_at": self.booked_at.isoformat() if self.booked_at else None,
            "presiding_judge_id": self.presiding_judge_id,
            "wing_judge_1_id": self.wing_judge_1_id,
            "wing_judge_2_id": self.wing_judge_2_id,
            "petitioner_team_id": self.petitioner_team_id,
            "respondent_team_id": self.respondent_team_id,
            "petitioner_score": self.petitioner_score,
            "respondent_score": self.respondent_score,
            "admin_notes": self.admin_notes,
            "is_past": self.start_time < now if self.start_time else False,
            "is_bookable": self.status == SlotStatus.AVAILABLE and self.start_time > now if self.start_time else False,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


class SlotBookingLog(Base):
    """
    Audit log for slot bookings, changes, and cancellations
    """
    __tablename__ = "slot_booking_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    slot_id = Column(Integer, ForeignKey("submission_slots.id", ondelete="CASCADE"), nullable=False, index=True)
    
    action = Column(String(50), nullable=False)  # book, cancel, change, block, etc.
    performed_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    performed_at = Column(DateTime, default=datetime.utcnow)
    
    old_value = Column(Text, nullable=True)  # JSON of previous state
    new_value = Column(Text, nullable=True)  # JSON of new state
    reason = Column(Text, nullable=True)  # Reason for change
    
    def to_dict(self):
        return {
            "id": self.id,
            "slot_id": self.slot_id,
            "action": self.action,
            "performed_by": self.performed_by,
            "performed_at": self.performed_at.isoformat() if self.performed_at else None,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "reason": self.reason
        }


class TeamSlotPreference(Base):
    """
    Team preferences for slot booking (for auto-scheduling)
    """
    __tablename__ = "team_slot_preferences"
    
    id = Column(Integer, primary_key=True, index=True)
    institution_id = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False)
    competition_id = Column(Integer, ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Preferred time ranges (comma-separated hours, e.g., "9,10,14,15")
    preferred_hours = Column(String(100), nullable=True)
    
    # Avoid these times
    blocked_dates = Column(Text, nullable=True)  # JSON array of dates
    
    # Special requests
    special_requests = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            "id": self.id,
            "team_id": self.team_id,
            "preferred_hours": self.preferred_hours,
            "blocked_dates": self.blocked_dates,
            "special_requests": self.special_requests
        }
