"""
backend/orm/faculty_note.py
Phase 7: Faculty Note ORM Model

Private advisory notes for faculty to mentor students without authorship.
Notes are non-evaluative and do not affect student submissions.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime

from backend.orm.base import Base


class FacultyNote(Base):
    """
    Phase 7: Private faculty mentoring notes.
    
    These notes are advisory only and do not:
    - Modify student work
    - Influence submissions
    - Affect scoring or evaluation
    - Appear in student view (unless explicitly shared by faculty)
    
    Each note belongs to:
    - A faculty member (author)
    - A specific project (context)
    - An institution (for scoping)
    """
    __tablename__ = "faculty_notes"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Institution scoping - CRITICAL for multi-tenancy
    institution_id = Column(
        Integer,
        ForeignKey("institutions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Faculty member who authored the note
    faculty_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Project context (which moot project the note is about)
    project_id = Column(
        Integer,
        ForeignKey("moot_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # The note content
    note_text = Column(Text, nullable=False)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Optional: visibility setting for future sharing features
    # For now, notes are private to faculty only
    is_private = Column(Integer, default=1)  # 1 = private, 0 = shared with team
    
    # Relationships
    institution = relationship("Institution", lazy="selectin")
    faculty = relationship("User", lazy="selectin")
    project = relationship("MootProject", lazy="selectin")
    
    def __repr__(self):
        return f"<FacultyNote(id={self.id}, faculty={self.faculty_id}, project={self.project_id})>"
    
    def to_dict(self, include_faculty=False):
        """Convert to dictionary for API responses"""
        data = {
            "id": self.id,
            "institution_id": self.institution_id,
            "project_id": self.project_id,
            "note_text": self.note_text,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "is_private": bool(self.is_private),
        }
        
        if include_faculty and self.faculty:
            data["faculty"] = {
                "id": self.faculty.id,
                "full_name": self.faculty.full_name if hasattr(self.faculty, 'full_name') else None,
                "email": self.faculty.email if hasattr(self.faculty, 'email') else None,
            }
        else:
            data["faculty_id"] = self.faculty_id
        
        return data
