"""
AI Rubric Models — Phase 4

Rubric definitions and frozen versions for AI evaluation.
Ensures immutability by snapshotting rubric JSON when used.
"""
import enum
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON, Index, UniqueConstraint
from sqlalchemy.orm import relationship

from backend.orm.base import Base


class RubricType(str, enum.Enum):
    """Types of rubrics available."""
    ORAL_ARGUMENT = "oral_argument"
    MEMORIAL = "memorial"
    RESEARCH = "research"
    GENERAL = "general"


class AIRubric(Base):
    """
    Editable rubric definition.
    
    This is the mutable source. When used in an evaluation,
    a snapshot is created in ai_rubric_versions.
    """
    __tablename__ = "ai_rubrics"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    rubric_type = Column(String(32), nullable=False, default=RubricType.ORAL_ARGUMENT.value)
    
    # JSON definition - mutable until versioned
    definition_json = Column(Text, nullable=False)
    
    # Current version number (increments on edit)
    current_version = Column(Integer, nullable=False, default=1)
    
    # Ownership
    created_by_faculty_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    institution_id = Column(Integer, ForeignKey("institutions.id"), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True, onupdate=datetime.utcnow)
    is_active = Column(Integer, default=1)  # Soft delete
    
    # Relationships
    versions = relationship("AIRubricVersion", back_populates="rubric", cascade="all, delete-orphan")
    created_by = relationship("User", foreign_keys=[created_by_faculty_id])
    
    __table_args__ = (
        Index("idx_rubrics_faculty", "created_by_faculty_id"),
        Index("idx_rubrics_institution", "institution_id"),
        Index("idx_rubrics_type", "rubric_type"),
    )
    
    def __repr__(self) -> str:
        return f"<AIRubric(id={self.id}, name='{self.name}', version={self.current_version})>"


class AIRubricVersion(Base):
    """
    Frozen snapshot of a rubric at a specific version.
    
    Once created, this is immutable and referenced by evaluations.
    Ensures reproducibility - same rubric version always produces
    the same scoring criteria.
    """
    __tablename__ = "ai_rubric_versions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    rubric_id = Column(Integer, ForeignKey("ai_rubrics.id", ondelete="RESTRICT"), nullable=False)
    
    # Version metadata
    version_number = Column(Integer, nullable=False)
    name = Column(String(255), nullable=False)  # Snapshot of name at version time
    
    # Frozen JSON - NEVER changes after creation
    frozen_json = Column(Text, nullable=False)
    
    # Criteria extracted for indexing/search (optional)
    criteria_summary = Column(String(500), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Constraints
    __table_args__ = (
        UniqueConstraint("rubric_id", "version_number", name="uq_rubric_version"),
        Index("idx_rubric_versions_rubric", "rubric_id"),
    )
    
    # Relationships
    rubric = relationship("AIRubric", back_populates="versions")
    evaluations = relationship("AIEvaluation", back_populates="rubric_version")
    
    def __repr__(self) -> str:
        return f"<AIRubricVersion(id={self.id}, rubric_id={self.rubric_id}, version={self.version_number})>"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        import json
        return {
            "id": self.id,
            "rubric_id": self.rubric_id,
            "version_number": self.version_number,
            "name": self.name,
            "frozen_json": json.loads(self.frozen_json) if self.frozen_json else None,
            "criteria_summary": self.criteria_summary,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
