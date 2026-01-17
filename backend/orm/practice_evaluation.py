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
    EVALUATED = "evaluated"  # Phase 5.2 requirement: marks as evaluated
    FAILED = "failed"  # Evaluation failed (retryable)

class PracticeEvaluation(BaseModel):
    """Model for storing AI evaluation results for practice attempts"""
    
    __tablename__ = "practice_evaluations"
    
    practice_attempt_id = Column(
        Integer,
        ForeignKey("practice_attempts.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True
    )
    
    evaluation_type = Column(String(50), default="ai_descriptive")
    status = Column(String(50), default="pending", index=True)
    
    score = Column(Float, nullable=True)
    feedback_text = Column(Text, nullable=True)
    strengths = Column(JSON, nullable=True)
    improvements = Column(JSON, nullable=True)
    rubric_breakdown = Column(JSON, nullable=True)
    
    confidence_score = Column(Float, nullable=True)
    model_version = Column(String(100), nullable=True)
    evaluated_by = Column(String(50), default="ai")
    error_message = Column(Text, nullable=True)
    
    practice_attempt = relationship(
        "PracticeAttempt",
        back_populates="evaluation",
        uselist=False
    )
    
    __table_args__ = (
        UniqueConstraint('practice_attempt_id', name='uq_evaluation_attempt'),
        Index('ix_evaluation_status', 'status'),
    )
    
    def mark_processing(self):
        """Mark evaluation as processing"""
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
        self.status = "evaluated"
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
        return self.status in ["completed", "evaluated"]


    def is_failed(self) -> bool:
        """Check if evaluation failed"""
        return self.status == "failed"
