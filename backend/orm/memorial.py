from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Float, Enum as SQLEnum, func
from sqlalchemy.orm import relationship
import enum
from backend.orm.base import Base

class MemorialStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"

class MemorialSubmission(Base):
    __tablename__ = "memorial_submissions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    round_type = Column(String(50), default="written")
    file_path = Column(String(500), nullable=False)
    original_filename = Column(String(255), nullable=False)
    status = Column(SQLEnum(MemorialStatus), default=MemorialStatus.PENDING, nullable=False)
    
    ai_feedback = Column(Text, nullable=True)
    score_irac = Column(Integer, nullable=True)
    score_citation = Column(Integer, nullable=True)
    score_structure = Column(Integer, nullable=True)
    score_overall = Column(Float, nullable=True)
    badges_earned = Column(String(500), nullable=True)
    
    submitted_at = Column(DateTime, default=func.now())
    processed_at = Column(DateTime, nullable=True)
    
    team = relationship("Team", back_populates="memorials")
