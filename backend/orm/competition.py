"""
backend/orm/competition.py
Phase 5B: Competition model for moot court competitions
Each competition belongs to exactly one institution.
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
from enum import Enum as PyEnum
from backend.orm.base import Base


class CompetitionType(str, PyEnum):
    """Types of moot court competitions"""
    MEMORIAL = "memorial"      # Written submissions only
    ORAL = "oral"              # Oral arguments only
    HYBRID = "hybrid"          # Both memorial and oral


class CompetitionStatus(str, PyEnum):
    """Competition lifecycle status - Phase 5D Extended"""
    DRAFT = "draft"                    # Being configured (admin only)
    REGISTRATION = "registration"        # Open for team registration
    ACTIVE = "active"                  # Teams can write + edit
    SUBMISSION_CLOSED = "submission_closed"  # ALL student edits locked
    EVALUATION = "evaluation"          # Judges only, read-only for students
    CLOSED = "closed"                  # Fully archived, read-only for everyone
    CANCELLED = "cancelled"            # Cancelled


class Competition(Base):
    """
    Competition model for moot court events.
    Scoped to a single institution - complete data isolation.
    """
    __tablename__ = "competitions"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Institution scoping - CRITICAL for multi-tenancy
    institution_id = Column(
        Integer,
        ForeignKey("institutions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Basic Info
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    moot_type = Column(SQLEnum(CompetitionType), default=CompetitionType.HYBRID, nullable=False)
    
    # Schedule - Phase 5D Extended
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    registration_deadline = Column(DateTime, nullable=True)
    memorial_submission_deadline = Column(DateTime, nullable=True)
    oral_round_start = Column(DateTime, nullable=True)
    oral_round_end = Column(DateTime, nullable=True)
    
    # Legacy field for backward compatibility
    submission_deadline = Column(DateTime, nullable=True)
    
    # Moot Proposition
    proposition_text = Column(Text, nullable=True)
    proposition_url = Column(String(500), nullable=True)  # External PDF link
    
    # Status
    status = Column(SQLEnum(CompetitionStatus), default=CompetitionStatus.DRAFT, nullable=False, index=True)
    is_published = Column(Boolean, default=False, nullable=False)
    
    # Metadata
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    teams = relationship("Team", backref="competition", lazy="selectin", cascade="all, delete-orphan")
    rounds = relationship("CompetitionRound", backref="competition", lazy="selectin", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Competition(id={self.id}, title='{self.title}', institution={self.institution_id})>"
    
    def to_dict(self, include_proposition=False):
        data = {
            "id": self.id,
            "institution_id": self.institution_id,
            "title": self.title,
            "description": self.description,
            "moot_type": self.moot_type.value if self.moot_type else None,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "registration_deadline": self.registration_deadline.isoformat() if self.registration_deadline else None,
            "memorial_submission_deadline": self.memorial_submission_deadline.isoformat() if self.memorial_submission_deadline else None,
            "oral_round_start": self.oral_round_start.isoformat() if self.oral_round_start else None,
            "oral_round_end": self.oral_round_end.isoformat() if self.oral_round_end else None,
            "submission_deadline": self.submission_deadline.isoformat() if self.submission_deadline else None,
            "status": self.status.value if self.status else None,
            "is_published": self.is_published,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "team_count": len(self.teams) if self.teams else 0
        }
        
        if include_proposition:
            data["proposition_text"] = self.proposition_text
            data["proposition_url"] = self.proposition_url
            
        return data


class CompetitionRound(Base):
    """
    Individual rounds within a competition (e.g., Preliminary, Quarterfinals)
    """
    __tablename__ = "competition_rounds"
    
    id = Column(Integer, primary_key=True, index=True)
    competition_id = Column(Integer, ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Round info
    name = Column(String(100), nullable=False)  # e.g., "Preliminary Round"
    sequence = Column(Integer, nullable=False)  # Order of rounds
    
    # Schedule
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    
    # Status
    status = Column(String(20), default="pending", nullable=False)  # pending / active / completed
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            "id": self.id,
            "competition_id": self.competition_id,
            "name": self.name,
            "sequence": self.sequence,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "status": self.status
        }
