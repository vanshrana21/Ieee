"""
backend/orm/practice_question.py
PracticeQuestion model - Practice questions for assessments

PHASE 8 UPDATE: Added attempts relationship
"""
from sqlalchemy import Column, Integer, String, Text, ForeignKey, Index, Enum as SQLEnum
from sqlalchemy.orm import relationship
from enum import Enum
from backend.orm.base import BaseModel


class QuestionType(str, Enum):
    """Types of practice questions"""
    MCQ = "mcq"
    SHORT_ANSWER = "short_answer"
    ESSAY = "essay"
    CASE_ANALYSIS = "case_analysis"


class Difficulty(str, Enum):
    """Question difficulty level"""
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class PracticeQuestion(BaseModel):
    """
    PracticeQuestion represents a single practice item in PRACTICE module.
    
    PHASE 8: Added attempts relationship to track user submissions.
    """
    __tablename__ = "practice_questions"
    
    # Foreign Keys
    module_id = Column(
        Integer,
        ForeignKey("content_modules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Reference to content_modules table"
    )
    
    # Question Type
    question_type = Column(
        SQLEnum(QuestionType),
        nullable=False,
        index=True,
        comment="Type of question"
    )
    
    # Question Content
    question = Column(
        Text,
        nullable=False,
        comment="The question text"
    )
    
    # MCQ Options (NULL for non-MCQ questions)
    option_a = Column(Text, nullable=True, comment="MCQ option A")
    option_b = Column(Text, nullable=True, comment="MCQ option B")
    option_c = Column(Text, nullable=True, comment="MCQ option C")
    option_d = Column(Text, nullable=True, comment="MCQ option D")
    
    # Answer
    correct_answer = Column(
        Text,
        nullable=False,
        comment="For MCQ: A/B/C/D, For others: model answer/key points"
    )
    
    explanation = Column(
        Text,
        nullable=True,
        comment="Detailed explanation of correct answer"
    )
    
    # Metadata
    marks = Column(Integer, nullable=False, default=1, comment="Marks allocated to question")
    
    difficulty = Column(
        SQLEnum(Difficulty),
        nullable=False,
        default=Difficulty.MEDIUM,
        index=True,
        comment="Question difficulty level"
    )
    
    order_index = Column(
        Integer,
        default=0,
        nullable=False,
        index=True,
        comment="Display order within module"
    )
    
    tags = Column(
        String(500),
        nullable=True,
        comment="Comma-separated topics (e.g., 'offer,acceptance,consideration')"
    )
    
    # Relationships
    module = relationship(
        "ContentModule",
        back_populates="practice_items",
        lazy="joined"
    )
    
    # PHASE 8: Track user attempts
    attempts = relationship(
        "PracticeAttempt",
        back_populates="practice_question",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    
    # Database Constraints
    __table_args__ = (
        Index("ix_module_type_difficulty", "module_id", "question_type", "difficulty"),
        Index("ix_module_order", "module_id", "order_index"),
    )
    
    def __repr__(self):
        return (
            f"<PracticeQuestion("
            f"id={self.id}, "
            f"type={self.question_type}, "
            f"difficulty={self.difficulty})>"
        )
    
    def to_dict(self, include_answer: bool = False):
        """Convert model to dictionary for API responses"""
        data = {
            "id": self.id,
            "module_id": self.module_id,
            "question_type": self.question_type.value if self.question_type else None,
            "question": self.question,
            "marks": self.marks,
            "difficulty": self.difficulty.value if self.difficulty else None,
            "order_index": self.order_index,
            "tags": self.tags.split(",") if self.tags else [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        
        # Include options for MCQs
        if self.question_type == QuestionType.MCQ:
            data.update({
                "option_a": self.option_a,
                "option_b": self.option_b,
                "option_c": self.option_c,
                "option_d": self.option_d,
            })
        
        # Include answer only when requested
        if include_answer:
            data.update({
                "correct_answer": self.correct_answer,
                "explanation": self.explanation,
            })
        
        return data
    
    def check_mcq_answer(self, user_answer: str) -> bool:
        """Check if user's MCQ answer is correct"""
        if self.question_type != QuestionType.MCQ:
            raise ValueError("This method is only for MCQ questions")
        
        return user_answer.upper() == self.correct_answer.upper()