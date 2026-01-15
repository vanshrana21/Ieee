"""
backend/routes/practice.py
Phase 9B: Adaptive practice generation and assessment
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from backend.database import get_db
from backend.orm.user import User
from backend.orm.subject import Subject
from backend.orm.curriculum import CourseCurriculum
from backend.routes.auth import get_current_user
from backend.schemas.practice_schemas import (
    GeneratePracticeRequest,
    GeneratePracticeResponse,
    AssessAnswerRequest,
    AssessAnswerResponse
)
from backend.services.adaptive_practice_gen import generate_adaptive_questions
from backend.services.answer_grader import grade_answer

router = APIRouter(prefix="/api/practice", tags=["adaptive-practice"])
logger = logging.getLogger(__name__)


@router.post("/generate", response_model=GeneratePracticeResponse)
async def generate_practice(
    request: GeneratePracticeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Generate adaptive practice questions based on user's mastery.
    
    Phase 9B: Adaptive question generation with AI.
    
    Security:
    - JWT authentication required
    - Subject must be in user's curriculum
    - Respects course and semester access
    
    Process:
    1. Validate subject access
    2. Compute weak topics (if adaptive)
    3. Retrieve relevant content
    4. Generate questions with rubrics
    
    Args:
        request: Generation parameters
    
    Returns:
        Generated questions with rubrics and difficulty distribution
    
    Raises:
        400: Invalid request or enrollment incomplete
        403: Subject not accessible
        404: Subject not found
        503: AI service unavailable
    """
    
    logger.info(f"Practice generation: user={current_user.email}, subject={request.subject_id}, difficulty={request.difficulty}")
    
    # Validate enrollment
    if not current_user.course_id or not current_user.current_semester:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incomplete enrollment. Please complete course setup."
        )
    
    # Verify subject access
    stmt = select(Subject).join(
        CourseCurriculum
    ).where(
        and_(
            Subject.id == request.subject_id,
            CourseCurriculum.course_id == current_user.course_id,
            CourseCurriculum.semester <= current_user.current_semester
        )
    )
    
    result = await db.execute(stmt)
    subject = result.scalar_one_or_none()
    
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subject not found or not accessible in your curriculum"
        )
    
    try:
        # Generate questions
        questions = await generate_adaptive_questions(
            user=current_user,
            subject_id=request.subject_id,
            count=request.count,
            difficulty=request.difficulty,
            db=db
        )
        
        # Calculate difficulty distribution
        difficulty_dist = {}
        for q in questions:
            difficulty_dist[q.difficulty] = difficulty_dist.get(q.difficulty, 0) + 1
        
        # Get weak topics if adaptive
        weak_topics = []
        if request.difficulty == "adaptive":
            from backend.services.mastery_calculator import get_weak_topics
            weak_topics = await get_weak_topics(
                current_user.id,
                request.subject_id,
                db,
                limit=3
            )
        
        return GeneratePracticeResponse(
            questions=questions,
            difficulty_distribution=difficulty_dist,
            weak_topics_targeted=weak_topics
        )
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
    except Exception as e:
        logger.error(f"Practice generation error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Practice generation service temporarily unavailable"
        )


@router.post("/assess", response_model=AssessAnswerResponse)
async def assess_answer(
    request: AssessAnswerRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Grade a student's answer with AI-powered feedback.
    
    Phase 9B: Auto-grading with explainable feedback.
    
    Security:
    - JWT authentication required
    - Does NOT modify student's answer
    - Does NOT store in database (stateless grading)
    
    Process:
    1. Keyword-based scoring (deterministic)
    2. AI comparison with model answer (qualitative)
    3. Generate improvement suggestions
    
    Args:
        request: Answer and rubric
    
    Returns:
        Score, feedback, and improvement areas
    
    Raises:
        400: Invalid input
        401: Not authenticated
        503: AI service unavailable
    """
    
    logger.info(f"Assessing answer: user={current_user.email}, question={request.question_id}")
    
    try:
        # Grade answer
        result = await grade_answer(
            student_answer=request.student_answer,
            rubric=request.rubric,
            model_answer=request.model_answer
        )
        
        logger.info(f"Assessment complete: score={result.score}/{result.max_score}")
        
        return result
    
    except Exception as e:
        logger.error(f"Assessment error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Assessment service temporarily unavailable"
        )
