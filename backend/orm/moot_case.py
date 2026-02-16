"""
MootCase ORM Model

Represents a legal case for moot court sessions.
Supports structured High Court cases with constitutional analysis.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON
from sqlalchemy.orm import relationship

from backend.orm.base import Base


class MootCase(Base):
    """Moot case for classroom sessions."""
    __tablename__ = "moot_cases"

    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # External case identifier for deterministic ingestion
    external_case_code = Column(String(50), unique=True, nullable=True, index=True)
    
    # Legacy fields (backward compatible)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    topic = Column(String(100), nullable=True)  # Case topic/category
    legal_domain = Column(String(100), nullable=True)
    difficulty_level = Column(String(50), default="intermediate")
    
    # New structured fields for High Court cases
    citation = Column(String(255), nullable=True)  # e.g., "AIR 2023 SC 1234"
    short_proposition = Column(Text, nullable=True)  # One-line case summary
    constitutional_articles = Column(JSON, nullable=True)  # ["Article 14", "Article 21"]
    key_issues = Column(JSON, nullable=True)  # ["Right to Privacy", "Equality"]
    landmark_cases_expected = Column(JSON, nullable=True)  # ["Puttaswamy", "Navtej Singh"]
    complexity_level = Column(Integer, nullable=False, default=3)  # 1-5 scale
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)

    sessions = relationship(
        "ClassroomSession",
        back_populates="case",
        cascade="all, delete-orphan",
        lazy="selectin"
    )

    def __repr__(self):
        return f"<MootCase(id={self.id}, title='{self.title}')>"
