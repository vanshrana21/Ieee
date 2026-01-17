"""
backend/orm/exam_answer.py
Phase 7.2: Exam Answer Model

Stores individual answers within an exam session.

Key Design:
- Links to exam_session (not standalone)
- Tracks time spent per question
- Supports draft saving before final submit
- Locked after session submission
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.orm.base import BaseModel


class ExamAnswer(BaseModel):
    """
    Individual answer within a mock exam session.
    
    Tracking:
    - answer_text: User's written answer
    - time_taken_seconds: Time spent on this question
    - word_count: For essay length tracking
    - is_submitted: Draft vs final answer
    """
    
    __tablename__ = "exam_answers"
    
    exam_session_id = Column(
        Integer,
        ForeignKey("exam_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Parent exam session"
    )
    
    question_id = Column(
        Integer,
        ForeignKey("practice_questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Question being answered"
    )
    
    section_label = Column(
        String(10),
        nullable=True,
        comment="Section this question belongs to (A, B, C)"
    )
    
    question_number = Column(
        Integer,
        nullable=False,
        comment="Question number within exam"
    )
    
    answer_text = Column(
        Text,
        nullable=True,
        comment="User's answer (NULL if not attempted)"
    )
    
    time_taken_seconds = Column(
        Integer,
        nullable=True,
        default=0,
        comment="Time spent on this question"
    )
    
    word_count = Column(
        Integer,
        nullable=True,
        default=0,
        comment="Word count of answer"
    )
    
    marks_allocated = Column(
        Integer,
        nullable=False,
        comment="Marks this question carries"
    )
    
    is_flagged = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="User flagged for review"
    )
    
    first_viewed_at = Column(
        DateTime,
        nullable=True,
        comment="When user first viewed this question"
    )
    
    last_updated_at = Column(
        DateTime,
        nullable=True,
        onupdate=datetime.utcnow,
        comment="Last time answer was modified"
    )
    
    exam_session = relationship(
        "ExamSession",
        back_populates="answers",
        lazy="joined"
    )
    
    question = relationship(
        "PracticeQuestion",
        lazy="joined"
    )
    
    __table_args__ = (
        Index("ix_exam_answer_session_question", "exam_session_id", "question_id", unique=True),
        Index("ix_exam_answer_section", "exam_session_id", "section_label"),
    )
    
    def __repr__(self):
        return f"<ExamAnswer(id={self.id}, session={self.exam_session_id}, q_num={self.question_number})>"
    
    def is_attempted(self) -> bool:
        """Check if question has been answered."""
        return bool(self.answer_text and self.answer_text.strip())
    
    def to_dict(self, include_answer: bool = True) -> dict:
        """Convert to dictionary for API responses."""
        data = {
            "id": self.id,
            "exam_session_id": self.exam_session_id,
            "question_id": self.question_id,
            "section_label": self.section_label,
            "question_number": self.question_number,
            "marks_allocated": self.marks_allocated,
            "is_flagged": self.is_flagged,
            "is_attempted": self.is_attempted(),
            "time_taken_seconds": self.time_taken_seconds,
            "word_count": self.word_count,
            "first_viewed_at": self.first_viewed_at.isoformat() if self.first_viewed_at else None,
            "last_updated_at": self.last_updated_at.isoformat() if self.last_updated_at else None,
        }
        
        if include_answer:
            data["answer_text"] = self.answer_text
        
        return data
    
    def to_dict_with_question(self) -> dict:
        """Return answer with question details."""
        data = self.to_dict()
        
        if self.question:
            data["question"] = {
                "id": self.question.id,
                "question_text": self.question.question,
                "question_type": self.question.question_type.value if self.question.question_type else None,
                "marks": self.question.marks,
                "guidelines": self.question.guidelines,
            }
        
        return data
