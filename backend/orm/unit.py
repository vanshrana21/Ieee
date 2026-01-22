from sqlalchemy import Column, Integer, String, Text, ForeignKey, Index
from sqlalchemy.orm import relationship
from backend.orm.base import BaseModel

class Unit(BaseModel):
    """
    Unit entity for syllabus-accurate curriculum structure.
    Used as the official container for subjects.
    """
    __tablename__ = "units"
    
    subject_id = Column(
        Integer,
        ForeignKey("ballb_subjects.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    title = Column(String(500), nullable=False)
    sequence_order = Column(Integer, nullable=False, index=True)
    description = Column(Text, nullable=True)
    
    # Relationship to BALLBSubject
    subject = relationship("BALLBSubject", back_populates="units_new")
    
    def __repr__(self):
        return f"<Unit(id={self.id}, title='{self.title[:30]}...', order={self.sequence_order})>"
