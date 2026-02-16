from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum as SQLEnum, Boolean, func
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from backend.orm.base import Base

class CompetitionStatus(str, enum.Enum):
    DRAFT = "draft"
    LIVE = "live"
    COMPLETED = "completed"
    ARCHIVED = "archived"

class Competition(Base):
    __tablename__ = "competitions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    problem_id = Column(Integer, ForeignKey("moot_projects.id"), nullable=False)
    institution_id = Column(Integer, ForeignKey("institutions.id"), nullable=True)
    start_date = Column(DateTime, nullable=False)
    memorial_deadline = Column(DateTime, nullable=False)
    oral_start_date = Column(DateTime, nullable=False)
    oral_end_date = Column(DateTime, nullable=False)
    max_team_size = Column(Integer, default=4, nullable=False)
    status = Column(SQLEnum(CompetitionStatus), default=CompetitionStatus.DRAFT, nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=func.now())
    
    teams = relationship("Team", back_populates="competition", cascade="all, delete-orphan")
    rounds = relationship("OralRound", back_populates="competition", cascade="all, delete-orphan")
    problem = relationship("MootProject", foreign_keys=[problem_id])
    creator = relationship("User", foreign_keys=[created_by_id])
    institution = relationship("Institution", back_populates="competitions")


# ============================================================================
# PHASE 3 PLACEHOLDER - Minimal class to satisfy ranking service import
# This will be fully implemented in Phase 3: Human Oral Rounds
# DO NOT USE IN PHASE 2 - Competition infrastructure only uses Competition
# ============================================================================

class CompetitionRound(Base):
    """Placeholder for Phase 3 - Competition rounds (quarterfinals, semifinals, etc.)"""
    __tablename__ = "competition_rounds"
    id = Column(Integer, primary_key=True, autoincrement=True)
    # TODO: Add columns in Phase 3 (competition_id, round_number, round_type, etc.)
