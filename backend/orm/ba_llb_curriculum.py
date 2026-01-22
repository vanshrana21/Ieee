"""
backend/orm/ba_llb_curriculum.py
BA LLB Curriculum Models - Data-driven curriculum structure

Models:
- BALLBSemester: 10 semesters for BA LLB course
- BALLBSubject: All subjects with optional/variable support
- BALLBModule: All modules (curriculum modules, not content types)

This implements the BCI-compliant BA LLB (5-Year Integrated) curriculum.
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import relationship
from backend.orm.base import BaseModel


class BALLBSemester(BaseModel):
    """
    Semester entity for BA LLB course.
    10 semesters total, each containing multiple subjects.
    """
    __tablename__ = "ballb_semesters"
    
    semester_number = Column(Integer, nullable=False, unique=True, index=True)
    name = Column(String(100), nullable=False)
    
    subjects = relationship(
        "BALLBSubject",
        back_populates="semester",
        cascade="all, delete-orphan",
        order_by="BALLBSubject.display_order"
    )
    
    def __repr__(self):
        return f"<BALLBSemester(id={self.id}, semester={self.semester_number})>"


class BALLBSubject(BaseModel):
    """
    Subject entity for BA LLB curriculum.
    
    Supports:
    - is_optional: Whether subject is optional/elective
    - option_group: Groups optional subjects (e.g., "Optional I", "Optional II")
    - is_variable: Major/Minor/Regular designation
    - subject_type: "major", "minor_i", "minor_ii", "core", "clinical", "optional"
    """
    __tablename__ = "ballb_subjects"
    
    semester_id = Column(
        Integer,
        ForeignKey("ballb_semesters.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    name = Column(String(300), nullable=False, index=True)
    code = Column(String(50), nullable=False, index=True)
    description = Column(Text, nullable=True)
    
    subject_type = Column(
        String(50),
        nullable=False,
        default="core",
        index=True
    )
    
    is_optional = Column(Boolean, default=False, nullable=False, index=True)
    is_foundation = Column(Boolean, default=False, nullable=False, index=True)
    option_group = Column(String(100), nullable=True, index=True)
    is_variable = Column(Boolean, default=False, nullable=False)
    
    display_order = Column(Integer, default=0, nullable=False)
    
    semester = relationship("BALLBSemester", back_populates="subjects")
    modules = relationship(
        "BALLBModule",
        back_populates="subject",
        cascade="all, delete-orphan",
        order_by="BALLBModule.sequence_order"
    )
    units_new = relationship(
        "Unit",
        back_populates="subject",
        cascade="all, delete-orphan",
        order_by="Unit.sequence_order"
    )
    
    __table_args__ = (
        UniqueConstraint("semester_id", "code", name="uq_ballb_semester_subject_code"),
        Index("ix_ballb_subject_semester_type", "semester_id", "subject_type"),
    )
    
    @property
    def module_count(self):
        """Dynamically computed module count - NEVER returns 0 if modules exist."""
        return len(self.modules) if self.modules else 0
    
    def __repr__(self):
        return f"<BALLBSubject(id={self.id}, name='{self.name[:30]}...')>"


class BALLBModule(BaseModel):
    """
    Module entity for BA LLB curriculum.
    Each subject has multiple modules (topics/units).
    Modules have sequence_order for correct display order.
    """
    __tablename__ = "ballb_modules"
    
    subject_id = Column(
        Integer,
        ForeignKey("ballb_subjects.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    title = Column(String(500), nullable=False)
    sequence_order = Column(Integer, nullable=False, index=True)
    description = Column(Text, nullable=True)
    
    subject = relationship("BALLBSubject", back_populates="modules")
    
    __table_args__ = (
        UniqueConstraint("subject_id", "sequence_order", name="uq_ballb_subject_module_order"),
        Index("ix_ballb_module_subject_order", "subject_id", "sequence_order"),
    )
    
    def __repr__(self):
        return f"<BALLBModule(id={self.id}, title='{self.title[:30]}...', order={self.sequence_order})>"
