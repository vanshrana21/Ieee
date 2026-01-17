"""
backend/orm/practice_attempt.py

PracticeAttempt - Tracks user answers to practice questions

PHASE 8: Practice Question Attempts

This model records EVERY attempt a user makes on practice questions:
- Multiple attempts allowed per question
- Stores selected option/answer
- Auto-grades MCQs
- Tracks attempt history

Key Design Decisions:
- Separate from UserContentProgress (attempts vs completion are different)
- MCQs auto-graded on submission
- Essays/short answers stored for future manual review
- Attempt number tracks retry behavior
- No soft deletes (audit trail is permanent)
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Index, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
from enum import Enum
from backend.orm.base import BaseModel
from backend.orm.practice_evaluation import PracticeEvaluation


class PracticeAttempt(BaseModel):
    """
    Records individual practice question attempts.

    Examples:
    - User answers MCQ "What are elements of contract?" → Attempt created
    - User submits essay answer → Attempt created (grading=NULL)
    - User retries MCQ → New attempt created (attempt_number increments)

    Fields:
    - id: Primary key
    - user_id: Who made the attempt (FK)
    - practice_question_id: Which question (FK)
    - selected_option: For MCQ: "A"/"B"/"C"/"D", For others: full answer text
    - is_correct: Auto-graded for MCQs, NULL for essays
    - attempt_number: 1st attempt, 2nd attempt, etc.
    - time_taken_seconds: How long user took (optional)
    - attempted_at: When attempt was submitted
    - created_at: When record was created

    Relationships:
    - user: The user who attempted
    - practice_question: The question attempted

    Constraints:
    - No unique constraint (multiple attempts allowed)

    Business Logic:
    - MCQs: Auto-grade on submission by comparing with correct_answer
    - Essays/Short answers: is_correct=NULL (manual grading in Phase 9+)
    - Attempt number auto-increments per user per question
    - First attempt = 1, second = 2, etc.

    Grading Rules:
    - MCQ: Compare selected_option.upper() with question.correct_answer.upper()
    - is_correct=True → Correct answer
    - is_correct=False → Wrong answer
    - is_correct=NULL → Not auto-gradable (essay/short answer)

    Usage:
    - POST /api/progress/practice/{id}/attempt → Submit answer
    - GET /api/progress/practice/{id}/attempts → View attempt history
    - Answers revealed ONLY after submission
    """

    __tablename__ = "practice_attempts"

    # Foreign Keys
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User who made this attempt"
    )

    practice_question_id = Column(
        Integer,
        ForeignKey("practice_questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Question that was attempted"
    )

    # Attempt Data
    selected_option = Column(
        Text,
        nullable=False,
        comment="For MCQ: A/B/C/D, For others: full answer text"
    )

    is_correct = Column(
        Boolean,
        nullable=True,
        index=True,
        comment="Auto-graded for MCQs, NULL for essays/short answers"
    )

    attempt_number = Column(
        Integer,
        nullable=False,
        default=1,
        index=True,
        comment="1st attempt, 2nd attempt, etc. per user per question"
    )

    # Timing
    time_taken_seconds = Column(
        Integer,
        nullable=True,
        comment="Time taken to answer (optional, for analytics)"
    )

    attempted_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        index=True,
        comment="When attempt was submitted"
    )

    # Relationships
    user = relationship(
        "User",
        back_populates="practice_attempts",
        lazy="joined"
    )

    practice_question = relationship(
        "PracticeQuestion",
        back_populates="attempts",
        lazy="joined"
    )

    evaluation = relationship(
        "PracticeEvaluation",
        back_populates="practice_attempt",
        uselist=False,
        cascade="all, delete-orphan"
    )

    practice_evaluation = relationship(
        "PracticeEvaluation",
        back_populates="practice_attempt",
        uselist=False,
        viewonly=True,
        overlaps="evaluation"
    )

    # Database Constraints
    __table_args__ = (
        # Composite index for user's attempt history
        Index(
            "ix_user_question_attempt",
            "user_id",
            "practice_question_id",
            "attempted_at"
        ),
        # Index for recent attempts
        Index(
            "ix_user_recent_attempts",
            "user_id",
            "attempted_at"
        ),
        # Index for correctness analytics
        Index(
            "ix_question_correctness",
            "practice_question_id",
            "is_correct"
        ),
    )

    def __repr__(self):
        return (
            f"<PracticeAttempt(id={self.id}, user_id={self.user_id}, "
            f"question_id={self.practice_question_id}, attempt={self.attempt_number}, "
            f"correct={self.is_correct})>"
        )

    def to_dict(self, include_answer: bool = False):
        """
        Convert model to dictionary for API responses.

        Args:
            include_answer: If True, includes selected_option and is_correct
            (should be False when showing attempt history without revealing answers)
        """
        data = {
            "id": self.id,
            "user_id": self.user_id,
            "practice_question_id": self.practice_question_id,
            "attempt_number": self.attempt_number,
            "time_taken_seconds": self.time_taken_seconds,
            "attempted_at": self.attempted_at.isoformat() if self.attempted_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

        if include_answer:
            data.update({
                "selected_option": self.selected_option,
                "is_correct": self.is_correct,
            })

        return data

    def to_dict_with_question(self):
        """
        Return attempt with question details (for feedback).

        Used after submission to show:
        - What user answered
        - Whether it was correct
        - Correct answer and explanation
        """
        data = self.to_dict(include_answer=True)

        if self.practice_question:
            data["question"] = self.practice_question.to_dict(include_answer=True)

        return data
