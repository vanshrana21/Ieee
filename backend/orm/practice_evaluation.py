"""
backend/orm/practice_evaluation.py

PracticeEvaluation - AI-powered feedback for practice attempts

PHASE 5: AI Evaluation & Feedback Engine

This model stores AI-generated evaluations for practice attempts.

Key points:
- Separate from PracticeAttempt (attempts are immutable)
- One-to-one relationship with PracticeAttempt
- Idempotent (re-evaluation replaces existing evaluation)
- Does NOT affect UserContentProgress or SubjectProgress
- Evaluation failure does not block submission flow
"""

from sqlalchemy import Column, Integer, String, Text, Float, ForeignKey, Index, UniqueConstraint, JSON
from sqlalchemy.orm import relationship
from enum import Enum
from backend.orm.base import BaseModel

class EvaluationType(str, Enum):
    """Type of evaluation performed"""
    AUTO_MCQ = "auto_mcq"  # MCQ already graded, optional AI feedback
    AI_DESCRIPTIVE = "ai_descriptive"  # AI evaluation of descriptive answer
    MANUAL = "manual"  # Manual grading (Phase 9+)

class EvaluationStatus(str, Enum):
    """Current status of evaluation"""
    PENDING = "pending"  # Evaluation queued but not started
    PROCESSING = "processing"  # AI is currently evaluating
    COMPLETED = "completed"  # Evaluation finished successfully
    FAILED = "failed"  # Evaluation failed (retryable)

class PracticeEvaluation(BaseModel):
    """
    AI-generated evaluation and feedback for practice attempts.

    Design Principles:
    - One evaluation per attempt (UNIQUE constraint)
    - Immutable attempts (evaluation is separate)
    - Idempotent (re-evaluation overwrites)
    - Non-blocking (async evaluation)
    - Progress-independent (does NOT affect completion)

    Examples:
    - MCQ attempt → Optional AI feedback on reasoning
    - Essay attempt → Comprehensive AI evaluation with rubric
    - Short answer → AI scoring + improvement suggestions

    Fields:
    - id: Primary key
    - practice_attempt_id: Link to attempt (UNIQUE, FK)
    - evaluation_type: Type of evaluation performed
    - status: Current evaluation state
    - score: Normalized score (0-100 or marks-based)
    - feedback_text: Main feedback narrative
    - strengths: What the student did well (JSON array)
    - improvements: Areas for improvement (JSON array)
    - rubric_breakdown: Detailed scoring breakdown (JSON)
    - evaluated_by: 'ai' or 'manual'
    - model_version: AI model used (e.g., "gemini-1.5-pro")
    - confidence_score: AI's confidence (0.0-1.0)
    - error_message: Error details if status=FAILED
    - created_at: When evaluation was created
    - updated_at: When evaluation was last updated

    Relationships:
    - practice_attempt: The attempt being evaluated

    Constraints:
    - UNIQUE: practice_attempt_id (one evaluation per attempt)

    Business Logic:
    - Evaluation triggered after attempt submission
    - Runs asynchronously (does not block response)
    - Failures are logged and retryable
    - MCQs: AI adds optional reasoning feedback
    - Descriptive: AI provides comprehensive evaluation
    - Re-evaluation: Replaces existing evaluation

    Usage:
    - POST /api/practice/attempts/{id}/evaluate → Trigger evaluation
    - GET /api/practice/attempts/{id}/evaluation → Get evaluation
    - Frontend polls for status → Shows feedback when completed
    """

    __tablename__ = "practice_evaluations"

    # Foreign Key (UNIQUE - one evaluation per attempt)
    practice_attempt_id = Column(
        Integer,
        ForeignKey("practice_attempts.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
        comment="Practice attempt being evaluated (one-to-one)"
    )

    # Evaluation Metadata
    evaluation_type = Column(
        String(50),
        nullable=False,
        index=True,
        comment="Type of evaluation: auto_mcq, ai_descriptive, manual"
    )

    status = Column(
        String(20),
        nullable=False,
        default="pending",
        index=True,
        comment="Current status: pending, processing, completed, failed"
    )

    # Scoring
    score = Column(
        Float,
        nullable=True,
        comment="Normalized score (0-100 or marks-based, NULL if not scored)"
    )

    # Feedback Content
    feedback_text = Column(
        Text,
        nullable=True,
        comment="Main AI-generated feedback narrative"
    )

    strengths = Column(
        JSON,
        nullable=True,
        comment="Array of strengths identified by AI"
    )

    improvements = Column(
        JSON,
        nullable=True,
        comment="Array of suggested improvements"
    )

    rubric_breakdown = Column(
        JSON,
        nullable=True,
        comment="Detailed scoring breakdown by criteria (optional)"
    )

    # AI Metadata
    evaluated_by = Column(
        String(20),
        nullable=False,
        default="ai",
        comment="Evaluator: 'ai' or 'manual'"
    )

    model_version = Column(
        String(100),
        nullable=True,
        comment="AI model version used (e.g., 'gemini-1.5-pro')"
    )

    confidence_score = Column(
        Float,
        nullable=True,
        comment="AI confidence level (0.0-1.0)"
    )

    # Error Handling
    error_message = Column(
        Text,
        nullable=True,
        comment="Error details if evaluation failed"
    )

    # Relationships
    practice_attempt = relationship(
        "PracticeAttempt",
        back_populates="evaluation",
        lazy="joined"
    )

    # Database Constraints
    __table_args__ = (
        # Index for fetching by status (admin dashboard)
        Index(
            "ix_evaluation_status",
            "status",
            "created_at"
        ),
        # Index for AI model analytics
        Index(
            "ix_evaluation_model_confidence",
            "model_version",
            "confidence_score"
        ),
    )

    def __repr__(self):
        return (
            f"<PracticeEvaluation(id={self.id}, attempt_id={self.practice_attempt_id}, "
            f"status={self.status}, score={self.score})>"
        )

    def to_dict(self, include_attempt_data: bool = False):
        """
        Convert evaluation to dictionary for API responses.

        Args:
            include_attempt_data: If True, includes basic attempt info
        """
        data = {
            "id": self.id,
            "practice_attempt_id": self.practice_attempt_id,
            "evaluation_type": self.evaluation_type,
            "status": self.status,
            "score": self.score,
            "feedback_text": self.feedback_text,
            "strengths": self.strengths or [],
            "improvements": self.improvements or [],
            "rubric_breakdown": self.rubric_breakdown,
            "evaluated_by": self.evaluated_by,
            "model_version": self.model_version,
            "confidence_score": self.confidence_score,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

        if include_attempt_data and self.practice_attempt:
            data["attempt"] = {
                "id": self.practice_attempt.id,
                "attempt_number": self.practice_attempt.attempt_number,
                "attempted_at": self.practice_attempt.attempted_at.isoformat() if self.practice_attempt.attempted_at else None,
            }

        return data

    def mark_processing(self):
        """Mark evaluation as currently being processed"""
        self.status = "processing"

    def mark_completed(
        self,
        score: float = None,
        feedback: str = None,
        strengths: list = None,
        improvements: list = None,
        rubric: dict = None,
        confidence: float = None
    ):
        """
        Mark evaluation as completed with results.

        Args:
            score: Normalized score
            feedback: Main feedback text
            strengths: List of strengths
            improvements: List of improvements
            rubric: Rubric breakdown dict
            confidence: AI confidence score
        """
        self.status = "completed"
        self.score = score
        self.feedback_text = feedback
        self.strengths = strengths
        self.improvements = improvements
        self.rubric_breakdown = rubric
        self.confidence_score = confidence
        self.error_message = None  # Clear any previous errors

    def mark_failed(self, error_message: str):
        """
        Mark evaluation as failed with error details.

        Args:
            error_message: Description of the failure
        """
        self.status = "failed"
        self.error_message = error_message

    def is_pending(self) -> bool:
        """Check if evaluation is pending"""
        return self.status in ["pending", "processing"]

    def is_completed(self) -> bool:
        """Check if evaluation is completed"""
        return self.status == "completed"

    def is_failed(self) -> bool:
        """Check if evaluation failed"""
        return self.status == "failed"
