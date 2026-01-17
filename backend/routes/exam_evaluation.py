"""
backend/routes/exam_evaluation.py
Phase 7.3: Exam Evaluation API Routes

Provides endpoints for evaluating and retrieving exam results.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List

from backend.database import get_db
from backend.orm.user import User
from backend.orm.exam_session import ExamSession
from backend.routes.auth import get_current_user
from backend.services.exam_evaluation_service import (
    evaluate_exam_session,
    get_evaluation_results,
    get_rubric_template,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/exams", tags=["exam-evaluation"])


class RubricCriteriaResponse(BaseModel):
    criteria: str
    score: float
    max: float
    feedback: str
    performance_level: str


class AnswerEvaluationResponse(BaseModel):
    id: int
    exam_answer_id: int
    question_id: Optional[int]
    question_number: Optional[int]
    section_label: Optional[str]
    question_text: Optional[str]
    marks_awarded: Optional[float]
    max_marks: int
    rubric_breakdown: List[Dict[str, Any]]
    overall_feedback: Optional[str]
    strengths: List[str]
    improvements: List[str]
    examiner_tone: Optional[str]
    status: str


class SessionEvaluationResponse(BaseModel):
    id: int
    exam_session_id: int
    total_marks_awarded: Optional[float]
    total_marks_possible: int
    percentage: Optional[float]
    grade_band: Optional[str]
    section_breakdown: List[Dict[str, Any]]
    strength_areas: List[str]
    weak_areas: List[str]
    overall_feedback: Optional[str]
    performance_summary: Dict[str, Any]
    status: str
    evaluated_at: Optional[str]


class GradeInfoResponse(BaseModel):
    grade: Optional[str]
    percentage: Optional[float]
    marks: str


class EvaluationResultsResponse(BaseModel):
    session_id: int
    exam_type: Optional[str]
    subject_name: Optional[str]
    evaluation: Dict[str, Any]
    answer_evaluations: List[Dict[str, Any]]
    grade_info: GradeInfoResponse


@router.get("/{session_id}/evaluation")
async def get_exam_evaluation(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get evaluation results for an exam session.
    
    Returns:
    - Overall grade and percentage
    - Section-wise breakdown
    - Per-question rubric scores
    - Strengths and improvement areas
    
    Automatically triggers evaluation if not yet done.
    """
    from sqlalchemy import select
    
    try:
        session_stmt = select(ExamSession).where(ExamSession.id == session_id)
        session_result = await db.execute(session_stmt)
        session = session_result.scalar_one_or_none()
        
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Exam session not found"
            )
        
        if session.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        result = await evaluate_exam_session(session_id, db)
        
        if "error" in result:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["error"]
            )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Evaluation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get evaluation"
        )


@router.post("/{session_id}/evaluate")
async def trigger_evaluation(
    session_id: int,
    force: bool = Query(default=False, description="Force re-evaluation"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Trigger evaluation for an exam session.
    
    - force=true: Re-evaluates even if already evaluated
    - Returns evaluation results
    """
    from sqlalchemy import select
    
    try:
        session_stmt = select(ExamSession).where(ExamSession.id == session_id)
        session_result = await db.execute(session_stmt)
        session = session_result.scalar_one_or_none()
        
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Exam session not found"
            )
        
        if session.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        result = await evaluate_exam_session(session_id, db, force_reevaluate=force)
        
        if "error" in result:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["error"]
            )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Evaluation trigger error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to trigger evaluation"
        )


@router.get("/{session_id}/answer/{answer_id}/evaluation")
async def get_answer_evaluation(
    session_id: int,
    answer_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed evaluation for a specific answer.
    
    Returns:
    - Rubric breakdown for each criterion
    - Score per criterion with feedback
    - Strengths and improvements
    """
    from sqlalchemy import select, and_
    from backend.orm.exam_evaluation import ExamAnswerEvaluation
    from backend.orm.exam_answer import ExamAnswer
    
    try:
        session_stmt = select(ExamSession).where(ExamSession.id == session_id)
        session_result = await db.execute(session_stmt)
        session = session_result.scalar_one_or_none()
        
        if not session or session.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        eval_stmt = select(ExamAnswerEvaluation).where(
            and_(
                ExamAnswerEvaluation.exam_session_id == session_id,
                ExamAnswerEvaluation.exam_answer_id == answer_id
            )
        )
        eval_result = await db.execute(eval_stmt)
        evaluation = eval_result.scalar_one_or_none()
        
        if not evaluation:
            await evaluate_exam_session(session_id, db)
            eval_result = await db.execute(eval_stmt)
            evaluation = eval_result.scalar_one_or_none()
        
        if not evaluation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Evaluation not found"
            )
        
        answer_stmt = select(ExamAnswer).where(ExamAnswer.id == answer_id)
        answer_result = await db.execute(answer_stmt)
        answer = answer_result.scalar_one_or_none()
        
        response = evaluation.to_dict()
        
        if answer:
            response["question_number"] = answer.question_number
            response["section_label"] = answer.section_label
            response["answer_text"] = answer.answer_text
            response["word_count"] = answer.word_count
            response["time_taken_seconds"] = answer.time_taken_seconds
            
            if answer.question:
                response["question"] = {
                    "id": answer.question.id,
                    "question_text": answer.question.question,
                    "question_type": answer.question.question_type.value if answer.question.question_type else None,
                    "marks": answer.question.marks,
                }
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Answer evaluation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get answer evaluation"
        )


@router.get("/rubric/template")
async def get_rubric_template_endpoint(
    question_type: str = Query(default="short_answer", description="Question type"),
    marks: int = Query(default=10, ge=1, le=100, description="Total marks")
):
    """
    Get the rubric template for a question type and marks.
    
    Shows:
    - Criteria names and weights
    - Marks allocation per criterion
    - Scoring guide for each level
    
    Useful for understanding how answers are evaluated.
    """
    try:
        template = await get_rubric_template(question_type, marks)
        return template
        
    except Exception as e:
        logger.error(f"Rubric template error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get rubric template"
        )


@router.get("/grade-bands")
async def get_grade_bands():
    """
    Get all grade band definitions.
    
    Returns:
    - Grade name (Distinction, First Class, etc.)
    - Percentage range
    - Description
    """
    from backend.services.exam_evaluation_service import GRADE_BANDS
    
    return {
        "grade_bands": [
            {
                "grade": band["grade"],
                "min_percentage": band["min"],
                "max_percentage": band["max"],
                "description": band["description"]
            }
            for band in GRADE_BANDS
        ]
    }


@router.get("/{session_id}/evaluation/summary")
async def get_evaluation_summary(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get a condensed summary of exam evaluation.
    
    Lighter response for dashboard/overview display.
    """
    from sqlalchemy import select
    from backend.orm.exam_evaluation import ExamSessionEvaluation
    
    try:
        session_stmt = select(ExamSession).where(ExamSession.id == session_id)
        session_result = await db.execute(session_stmt)
        session = session_result.scalar_one_or_none()
        
        if not session or session.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        eval_stmt = select(ExamSessionEvaluation).where(
            ExamSessionEvaluation.exam_session_id == session_id
        )
        eval_result = await db.execute(eval_stmt)
        evaluation = eval_result.scalar_one_or_none()
        
        if not evaluation:
            return {
                "session_id": session_id,
                "status": "pending",
                "message": "Evaluation not yet completed"
            }
        
        return {
            "session_id": session_id,
            "exam_type": session.exam_type,
            "subject_name": session.subject.title if session.subject else None,
            "status": evaluation.status,
            "grade": evaluation.grade_band,
            "percentage": evaluation.percentage,
            "marks": f"{evaluation.total_marks_awarded}/{evaluation.total_marks_possible}",
            "section_count": len(evaluation.section_breakdown or []),
            "strength_count": len(evaluation.strength_areas or []),
            "weak_count": len(evaluation.weak_areas or []),
            "evaluated_at": evaluation.evaluated_at.isoformat() if evaluation.evaluated_at else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Evaluation summary error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get evaluation summary"
        )
