"""
Phase 0: Virtual Courtroom Infrastructure - Oral Rounds ORM Model
Database-first schema for moot court oral rounds with complete timer and state management.
"""
from sqlalchemy import Column, Integer, ForeignKey, DateTime, Enum as SQLEnum, func, String, Text, Boolean, Index, JSON
from sqlalchemy.orm import relationship
import enum
from backend.orm.base import Base


class OralRoundStatus(str, enum.Enum):
    """Oral round lifecycle states."""
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FORFEITED = "forfeited"
    POSTPONED = "postponed"


class SpeakerRole(str, enum.Enum):
    """Current speaker in the courtroom."""
    NONE = "none"
    PETITIONER = "petitioner"
    RESPONDENT = "respondent"
    JUDGE = "judge"


class RoundType(str, enum.Enum):
    """Type of oral round segment."""
    ORAL = "oral"
    REBUTTAL = "rebuttal"
    Q_AND_A = "q_and_a"


class OralRound(Base):
    """
    Oral rounds table for virtual courtroom moot court competitions.
    
    Tracks round scheduling, team assignments, judge assignments, timer configuration,
    and current courtroom state for real-time sync via WebSocket.
    """
    __tablename__ = "oral_rounds"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Foreign key to MootProject (required for relationship)
    moot_project_id = Column(Integer, ForeignKey("moot_projects.id"), nullable=False, index=True)
    
    # Core fields - Competition and round identification
    competition_id = Column(Integer, ForeignKey("competitions.id"), nullable=False)
    round_number = Column(Integer, nullable=False)  # 1=quarterfinal, 2=semifinal, 3=final
    round_type = Column(SQLEnum(RoundType), default=RoundType.ORAL, nullable=False)
    
    # Team assignments
    petitioner_team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    respondent_team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    
    # Judge assignments
    presiding_judge_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    co_judges_ids = Column(String(200), nullable=True)  # JSON array of judge user IDs
    
    # Scheduling
    scheduled_start = Column(DateTime, nullable=False)
    scheduled_end = Column(DateTime, nullable=False)
    actual_start = Column(DateTime, nullable=True)
    actual_end = Column(DateTime, nullable=True)
    
    # Timer configuration (seconds)
    petitioner_time = Column(Integer, default=900)  # 15 minutes default
    respondent_time = Column(Integer, default=900)
    rebuttal_time = Column(Integer, default=180)  # 3 minutes per side
    q_and_a_time = Column(Integer, default=300)  # 5 minutes per side
    
    # Current courtroom state
    current_speaker = Column(SQLEnum(SpeakerRole), default=SpeakerRole.NONE)
    time_remaining = Column(Integer, nullable=True)  # Seconds remaining for current speaker
    is_paused = Column(Boolean, default=False)
    is_completed = Column(Boolean, default=False)
    status = Column(SQLEnum(OralRoundStatus), default=OralRoundStatus.SCHEDULED, nullable=False)
    
    # Metadata
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    moot_project = relationship("MootProject", back_populates="oral_rounds")
    competition = relationship("Competition", back_populates="rounds")
    petitioner_team = relationship("Team", foreign_keys=[petitioner_team_id])
    respondent_team = relationship("Team", foreign_keys=[respondent_team_id])
    presiding_judge = relationship("User", foreign_keys=[presiding_judge_id])
    
    # Related entities (defined in separate ORM files)
    objections = relationship("OralRoundObjection", back_populates="round", cascade="all, delete-orphan")
    scores = relationship("OralRoundScore", back_populates="round", cascade="all, delete-orphan")
    
    # Table indexes for common queries
    __table_args__ = (
        Index('idx_oral_rounds_competition', 'competition_id'),
        Index('idx_oral_rounds_status', 'status'),
        Index('idx_oral_rounds_scheduled', 'scheduled_start'),
    )
    
    def to_dict(self):
        """Convert round to dictionary for API responses."""
        return {
            "id": self.id,
            "competition_id": self.competition_id,
            "round_number": self.round_number,
            "round_type": self.round_type.value if self.round_type else None,
            "petitioner_team_id": self.petitioner_team_id,
            "respondent_team_id": self.respondent_team_id,
            "presiding_judge_id": self.presiding_judge_id,
            "co_judges_ids": self.co_judges_ids,
            "scheduled_start": self.scheduled_start.isoformat() if self.scheduled_start else None,
            "scheduled_end": self.scheduled_end.isoformat() if self.scheduled_end else None,
            "actual_start": self.actual_start.isoformat() if self.actual_start else None,
            "actual_end": self.actual_end.isoformat() if self.actual_end else None,
            "timer_config": {
                "petitioner_time": self.petitioner_time,
                "respondent_time": self.respondent_time,
                "rebuttal_time": self.rebuttal_time,
                "q_and_a_time": self.q_and_a_time
            },
            "current_state": {
                "current_speaker": self.current_speaker.value if self.current_speaker else None,
                "time_remaining": self.time_remaining,
                "is_paused": self.is_paused,
                "is_completed": self.is_completed,
                "status": self.status.value if self.status else None
            },
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
    
    def get_co_judges_list(self):
        """Parse co_judges_ids JSON string to list of integers."""
        if self.co_judges_ids:
            import json
            try:
                return json.loads(self.co_judges_ids)
            except json.JSONDecodeError:
                return []
        return []
    
    def set_co_judges_list(self, judge_ids):
        """Serialize list of judge IDs to JSON string."""
        import json
        self.co_judges_ids = json.dumps(judge_ids) if judge_ids else None


# Aliases for backward compatibility
RoundStatus = OralRoundStatus
OralRoundStatusEnum = OralRoundStatus


# ================= LEGACY COMPATIBILITY MODELS =================
# These models are restored to maintain backward compatibility
# with faculty monitoring and progress calculation modules.
# Do NOT remove unless full oral round refactor is completed.

from sqlalchemy import JSON


class OralResponse(Base):
    __tablename__ = "oral_responses"

    id = Column(Integer, primary_key=True)
    round_id = Column(Integer, ForeignKey("oral_rounds.id"), nullable=False)
    content = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "round_id": self.round_id,
            "content": self.content,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class RoundTranscript(Base):
    __tablename__ = "round_transcripts"

    id = Column(Integer, primary_key=True)
    round_id = Column(Integer, ForeignKey("oral_rounds.id"), nullable=False)
    transcript_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "round_id": self.round_id,
            "transcript_data": self.transcript_data,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# === RELATIONSHIP BINDING (post-definition to avoid registry issues) ===

OralRound.transcripts = relationship(
    "OralRoundTranscript",
    back_populates="round",
    cascade="all, delete-orphan"
)
