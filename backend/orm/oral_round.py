"""
backend/orm/oral_round.py
Phase 5C: Oral round persistence models
Replaces client-side oral round storage
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
from enum import Enum as PyEnum
from backend.orm.base import Base


class RoundStage(str, PyEnum):
    """Oral round stage"""
    PETITIONER = "petitioner"
    RESPONDENT = "respondent"
    REBUTTAL = "rebuttal"
    SURREBUTTAL = "surrebuttal"


class RoundStatus(str, PyEnum):
    """Oral round status"""
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class OralRound(Base):
    """
    Phase 5C: Oral round session
    Immutable after completion
    """
    __tablename__ = "oral_rounds"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Scoping
    institution_id = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("moot_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Round details
    stage = Column(SQLEnum(RoundStage), nullable=False)
    status = Column(SQLEnum(RoundStatus), default=RoundStatus.SCHEDULED, nullable=False)
    
    # Timing
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    
    # Metadata
    notes = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Immutability flag
    is_locked = Column(Boolean, default=False, nullable=False)
    locked_at = Column(DateTime, nullable=True)
    
    # Relationships
    responses = relationship("OralResponse", backref="round", lazy="selectin", cascade="all, delete-orphan")
    bench_questions = relationship("BenchQuestion", backref="round", lazy="selectin", cascade="all, delete-orphan")
    transcript = relationship("RoundTranscript", backref="round", lazy="selectin", uselist=False, cascade="all, delete-orphan")
    
    def to_dict(self, include_content=False):
        data = {
            "id": self.id,
            "institution_id": self.institution_id,
            "project_id": self.project_id,
            "stage": self.stage.value if self.stage else None,
            "status": self.status.value if self.status else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_seconds": self.duration_seconds,
            "notes": self.notes,
            "is_locked": self.is_locked,
            "locked_at": self.locked_at.isoformat() if self.locked_at else None,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
        
        if include_content:
            data["responses"] = [r.to_dict() for r in self.responses] if self.responses else []
            data["bench_questions"] = [q.to_dict() for q in self.bench_questions] if self.bench_questions else []
        
        return data


class OralResponse(Base):
    """
    Phase 5C: Oral arguments/responses given by speakers
    """
    __tablename__ = "oral_responses"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Scoping
    institution_id = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False, index=True)
    round_id = Column(Integer, ForeignKey("oral_rounds.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("moot_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Response details
    issue_id = Column(Integer, ForeignKey("moot_issues.id", ondelete="SET NULL"), nullable=True)
    speaker_role = Column(String(50), nullable=False)  # 'petitioner_counsel', 'respondent_counsel', etc.
    text = Column(Text, nullable=False)
    
    # Timing
    timestamp = Column(DateTime, default=datetime.utcnow)
    elapsed_seconds = Column(Integer, nullable=True)  # Time into the round
    
    # Metadata
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    def to_dict(self):
        return {
            "id": self.id,
            "round_id": self.round_id,
            "project_id": self.project_id,
            "issue_id": self.issue_id,
            "speaker_role": self.speaker_role,
            "text": self.text,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "elapsed_seconds": self.elapsed_seconds,
            "created_by": self.created_by
        }


class BenchQuestion(Base):
    """
    Phase 5C: Questions asked by judges/bench
    """
    __tablename__ = "bench_questions"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Scoping
    institution_id = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False, index=True)
    round_id = Column(Integer, ForeignKey("oral_rounds.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("moot_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Question details
    judge_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # If known
    judge_name = Column(String(100), nullable=True)  # Display name
    question_text = Column(Text, nullable=False)
    
    # Context
    issue_id = Column(Integer, ForeignKey("moot_issues.id", ondelete="SET NULL"), nullable=True)
    
    # Timing
    timestamp = Column(DateTime, default=datetime.utcnow)
    elapsed_seconds = Column(Integer, nullable=True)
    
    # Response tracking
    was_answered = Column(Boolean, default=False)
    answer_response_id = Column(Integer, ForeignKey("oral_responses.id"), nullable=True)
    
    def to_dict(self):
        return {
            "id": self.id,
            "round_id": self.round_id,
            "project_id": self.project_id,
            "judge_id": self.judge_id,
            "judge_name": self.judge_name,
            "question_text": self.question_text,
            "issue_id": self.issue_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "elapsed_seconds": self.elapsed_seconds,
            "was_answered": self.was_answered,
            "answer_response_id": self.answer_response_id
        }


class RoundTranscript(Base):
    """
    Phase 5C: Auto-generated transcript from oral responses and bench questions
    Immutable once generated
    """
    __tablename__ = "round_transcripts"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Scoping
    institution_id = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False, index=True)
    round_id = Column(Integer, ForeignKey("oral_rounds.id", ondelete="CASCADE"), nullable=False, index=True, unique=True)
    project_id = Column(Integer, ForeignKey("moot_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Transcript content (chronological sequence)
    transcript_items = Column(Text, nullable=False)  # JSON array of {type, speaker, text, timestamp}
    full_text = Column(Text, nullable=False)  # Plain text version
    
    # Metadata
    generated_at = Column(DateTime, default=datetime.utcnow)
    generated_by = Column(Integer, ForeignKey("users.id"), nullable=True)  # System or user
    
    # Immutability
    is_final = Column(Boolean, default=True, nullable=False)
    
    def to_dict(self):
        return {
            "id": self.id,
            "round_id": self.round_id,
            "project_id": self.project_id,
            "transcript_items": self.transcript_items,
            "full_text": self.full_text,
            "generated_at": self.generated_at.isoformat() if self.generated_at else None,
            "is_final": self.is_final
        }
