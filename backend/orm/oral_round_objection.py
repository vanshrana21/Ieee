"""
Phase 0: Virtual Courtroom Infrastructure - Oral Round Objections ORM Model
Tracks objections raised during oral rounds with timing and ruling information.
"""
from sqlalchemy import Column, Integer, ForeignKey, DateTime, Enum as SQLEnum, func, String, Text, Boolean, Index
from sqlalchemy.orm import relationship
import enum
from backend.orm.base import Base


class ObjectionType(str, enum.Enum):
    """Types of legal objections allowed during oral rounds."""
    HEARSAY = "hearsay"
    LEADING = "leading"
    RELEVANCE = "relevance"
    SPECULATION = "speculation"
    ARGUMENTATIVE = "argumentative"
    OTHER = "other"


class ObjectionRuling(str, enum.Enum):
    """Possible rulings on an objection."""
    SUSTAINED = "sustained"
    OVERRULED = "overruled"
    RESERVED = "reserved"


class SpeakerRole(str, enum.Enum):
    """Role of the interrupted speaker."""
    PETITIONER = "petitioner"
    RESPONDENT = "respondent"
    JUDGE = "judge"


class OralRoundObjection(Base):
    """
    Objections table for tracking courtroom objections.
    
    Records when objections are raised, by whom, the type of objection,
    timer state at the moment of interruption, and the judge's ruling.
    """
    __tablename__ = "oral_round_objections"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Core fields - Round and team identification
    round_id = Column(Integer, ForeignKey("oral_rounds.id"), nullable=False)
    raised_by_team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    raised_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Timing
    raised_at = Column(DateTime, nullable=False, default=func.now())
    
    # Objection details
    objection_type = Column(SQLEnum(ObjectionType), nullable=False)
    objection_text = Column(Text, nullable=True)  # Custom reason if type is "other"
    
    # Judge ruling
    judge_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    ruling = Column(SQLEnum(ObjectionRuling), nullable=True)
    ruling_at = Column(DateTime, nullable=True)
    ruling_notes = Column(Text, nullable=True)
    is_resolved = Column(Boolean, default=False)
    
    # Timer state tracking (critical for resuming after objection)
    interrupted_speaker = Column(SQLEnum(SpeakerRole), nullable=False)
    time_remaining_before = Column(Integer, nullable=False)  # Timer value before interruption
    time_remaining_after = Column(Integer, nullable=True)  # Timer value after ruling (may differ)
    
    # Metadata
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    round = relationship("OralRound", back_populates="objections")
    raised_by_team = relationship("Team", foreign_keys=[raised_by_team_id])
    raised_by_user = relationship("User", foreign_keys=[raised_by_user_id])
    judge = relationship("User", foreign_keys=[judge_id])
    
    # Table indexes for common queries
    __table_args__ = (
        Index('idx_objections_round', 'round_id'),
        Index('idx_objections_raised_by', 'raised_by_team_id'),
        Index('idx_objections_resolved', 'is_resolved'),
    )
    
    def to_dict(self):
        """Convert objection to dictionary for API responses."""
        return {
            "id": self.id,
            "round_id": self.round_id,
            "raised_by": {
                "team_id": self.raised_by_team_id,
                "user_id": self.raised_by_user_id
            },
            "raised_at": self.raised_at.isoformat() if self.raised_at else None,
            "objection": {
                "type": self.objection_type.value if self.objection_type else None,
                "text": self.objection_text
            },
            "ruling": {
                "judge_id": self.judge_id,
                "ruling": self.ruling.value if self.ruling else None,
                "ruling_at": self.ruling_at.isoformat() if self.ruling_at else None,
                "notes": self.ruling_notes,
                "is_resolved": self.is_resolved
            },
            "timer_state": {
                "interrupted_speaker": self.interrupted_speaker.value if self.interrupted_speaker else None,
                "time_remaining_before": self.time_remaining_before,
                "time_remaining_after": self.time_remaining_after
            },
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
    
    def resolve(self, judge_id, ruling, notes=None, time_after=None):
        """Mark objection as resolved with judge's ruling."""
        self.judge_id = judge_id
        self.ruling = ruling
        self.ruling_at = func.now()
        self.ruling_notes = notes
        self.time_remaining_after = time_after
        self.is_resolved = True
