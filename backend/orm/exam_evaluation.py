"""
backend/orm/exam_evaluation.py
Phase 7.3: Exam Evaluation Model

Stores evaluation results for exam answers with rubric-based scoring.

Key Design:
- One ExamAnswerEvaluation per ExamAnswer (1:1)
- One ExamSessionEvaluation per ExamSession (1:1)
- Evaluations are immutable once published
- Rubric breakdown stored as JSON for explainability
"""

from sqlalchemy import Column, Integer, String, Text, Float, ForeignKey, Index, UniqueConstraint, JSON, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from enum import Enum
from backend.orm.base import BaseModel


class EvaluationStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    EVALUATED = "evaluated"
    FAILED = "failed"


class ExamAnswerEvaluation(BaseModel):
    """
    Evaluation of a single exam answer with rubric-based scoring.
    
    Rubric Dimensions (for Indian Law exams):
    1. Issue Identification
    2. Legal Principles / Authorities
    3. Application to Facts
    4. Structure & Clarity
    5. Conclusion / Holding
    """
    
    __tablename__ = "exam_answer_evaluations"
    
    exam_answer_id = Column(
        Integer,
        ForeignKey("exam_answers.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
        comment="The exam answer being evaluated"
    )
    
    exam_session_id = Column(
        Integer,
        ForeignKey("exam_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Parent exam session"
    )
    
    question_id = Column(
        Integer,
        ForeignKey("practice_questions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Question reference"
    )
    
    marks_awarded = Column(
        Float,
        nullable=True,
        comment="Total marks awarded for this answer"
    )
    
    max_marks = Column(
        Integer,
        nullable=False,
        comment="Maximum marks possible"
    )
    
    rubric_breakdown = Column(
        JSON,
        nullable=True,
        comment="Detailed rubric scoring breakdown"
    )
    
    overall_feedback = Column(
        Text,
        nullable=True,
        comment="Summary feedback for the answer"
    )
    
    strengths = Column(
        JSON,
        nullable=True,
        comment="List of identified strengths"
    )
    
    improvements = Column(
        JSON,
        nullable=True,
        comment="List of areas for improvement"
    )
    
    examiner_tone = Column(
        String(50),
        nullable=True,
        default="neutral-academic",
        comment="Tone of feedback"
    )
    
    status = Column(
        String(50),
        nullable=False,
        default="pending",
        index=True,
        comment="Evaluation status"
    )
    
    evaluated_at = Column(
        DateTime,
        nullable=True,
        comment="When evaluation was completed"
    )
    
    evaluation_method = Column(
        String(50),
        nullable=True,
        default="ai",
        comment="ai, rubric_fallback, manual"
    )
    
    confidence_score = Column(
        Float,
        nullable=True,
        comment="AI confidence in evaluation (0-1)"
    )
    
    error_message = Column(
        Text,
        nullable=True,
        comment="Error details if evaluation failed"
    )
    
    exam_answer = relationship(
        "ExamAnswer",
        lazy="joined"
    )
    
    __table_args__ = (
        UniqueConstraint('exam_answer_id', name='uq_exam_answer_evaluation'),
        Index('ix_eval_session_status', 'exam_session_id', 'status'),
    )
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "exam_answer_id": self.exam_answer_id,
            "question_id": self.question_id,
            "marks_awarded": self.marks_awarded,
            "max_marks": self.max_marks,
            "rubric_breakdown": self.rubric_breakdown or [],
            "overall_feedback": self.overall_feedback,
            "strengths": self.strengths or [],
            "improvements": self.improvements or [],
            "examiner_tone": self.examiner_tone,
            "status": self.status,
            "evaluated_at": self.evaluated_at.isoformat() if self.evaluated_at else None,
            "evaluation_method": self.evaluation_method,
            "confidence_score": self.confidence_score,
        }


class ExamSessionEvaluation(BaseModel):
    """
    Aggregated evaluation for an entire exam session.
    
    Provides:
    - Total marks and percentage
    - Grade band classification
    - Strength/weakness analysis
    - Section-wise breakdown
    """
    
    __tablename__ = "exam_session_evaluations"
    
    exam_session_id = Column(
        Integer,
        ForeignKey("exam_sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
        comment="The exam session being evaluated"
    )
    
    total_marks_awarded = Column(
        Float,
        nullable=True,
        comment="Sum of all marks awarded"
    )
    
    total_marks_possible = Column(
        Integer,
        nullable=False,
        comment="Maximum possible marks"
    )
    
    percentage = Column(
        Float,
        nullable=True,
        comment="Percentage score"
    )
    
    grade_band = Column(
        String(50),
        nullable=True,
        comment="Distinction/First/Second/Pass/Fail"
    )
    
    section_breakdown = Column(
        JSON,
        nullable=True,
        comment="Section-wise marks breakdown"
    )
    
    strength_areas = Column(
        JSON,
        nullable=True,
        comment="Topics/areas of strength"
    )
    
    weak_areas = Column(
        JSON,
        nullable=True,
        comment="Topics/areas needing improvement"
    )
    
    overall_feedback = Column(
        Text,
        nullable=True,
        comment="Overall exam feedback"
    )
    
    performance_summary = Column(
        JSON,
        nullable=True,
        comment="Detailed performance metrics"
    )
    
    status = Column(
        String(50),
        nullable=False,
        default="pending",
        index=True,
        comment="Evaluation status"
    )
    
    evaluated_at = Column(
        DateTime,
        nullable=True,
        comment="When evaluation was completed"
    )
    
    evaluation_method = Column(
        String(50),
        nullable=True,
        default="ai",
        comment="ai, rubric_fallback, manual"
    )
    
    exam_session = relationship(
        "ExamSession",
        lazy="joined"
    )
    
    __table_args__ = (
        UniqueConstraint('exam_session_id', name='uq_exam_session_evaluation'),
    )
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "exam_session_id": self.exam_session_id,
            "total_marks_awarded": self.total_marks_awarded,
            "total_marks_possible": self.total_marks_possible,
            "percentage": self.percentage,
            "grade_band": self.grade_band,
            "section_breakdown": self.section_breakdown or [],
            "strength_areas": self.strength_areas or [],
            "weak_areas": self.weak_areas or [],
            "overall_feedback": self.overall_feedback,
            "performance_summary": self.performance_summary or {},
            "status": self.status,
            "evaluated_at": self.evaluated_at.isoformat() if self.evaluated_at else None,
            "evaluation_method": self.evaluation_method,
        }
