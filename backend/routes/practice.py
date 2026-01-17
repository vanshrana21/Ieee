"""
backend/routes/practice.py
Practice Mode API - Phase 3.3 + Phase 3.5

Module-aware practice mode for Indian law students.
Serves MCQs and short answers from database, auto-grades MCQs,
and feeds mastery analytics engine.

Phase 3.5: Answer Writing Practice & Evaluation
"""
import logging
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload
from pydantic import BaseModel

from backend.database import get_db
from backend.orm.user import User
from backend.orm.content_module import ContentModule, ModuleType
from backend.orm.practice_question import PracticeQuestion, QuestionType, Difficulty
from backend.orm.practice_attempt import PracticeAttempt
from backend.orm.practice_evaluation import PracticeEvaluation
from backend.routes.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/practice", tags=["Practice Mode"])


class PracticeQuestionResponse(BaseModel):
    id: int
    type: str
    question: str
    options: Optional[List[str]] = None
    topic_tag: Optional[str] = None
    difficulty: str


class ModuleInfo(BaseModel):
    id: int
    title: str
    subject_id: int


class PracticeModuleResponse(BaseModel):
    module: ModuleInfo
    questions: List[PracticeQuestionResponse]
    total_count: int


@router.get("/module/{module_id}", response_model=PracticeModuleResponse)
async def get_practice_questions_for_module(
    module_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all practice questions for a module.
    
    Phase 3.3: Module-Aware Practice Mode
    
    Rules:
    - Returns ONLY active questions (all questions in DB are considered active)
    - Ordered by difficulty ASC (easy → medium → hard)
    - NO answers returned (use attempt endpoint for grading)
    - Returns empty list if no questions exist
    
    Returns:
        {
            "module": { "id", "title", "subject_id" },
            "questions": [...],
            "total_count": int
        }
    """
    logger.info(f"Practice fetch: module_id={module_id}, user={current_user.email}")
    
    stmt = (
        select(ContentModule)
        .options(joinedload(ContentModule.subject))
        .where(ContentModule.id == module_id)
    )
    result = await db.execute(stmt)
    module = result.scalar_one_or_none()
    
    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module not found"
        )
    
    if module.module_type != ModuleType.PRACTICE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This module does not contain practice questions"
        )
    
    difficulty_order = {
        Difficulty.EASY: 1,
        Difficulty.MEDIUM: 2,
        Difficulty.HARD: 3
    }
    
    questions_stmt = (
        select(PracticeQuestion)
        .where(PracticeQuestion.module_id == module_id)
        .order_by(PracticeQuestion.difficulty, PracticeQuestion.order_index)
    )
    questions_result = await db.execute(questions_stmt)
    questions = questions_result.scalars().all()
    
    sorted_questions = sorted(
        questions, 
        key=lambda q: (difficulty_order.get(q.difficulty, 2), q.order_index)
    )
    
    formatted_questions = []
    for q in sorted_questions:
        options = None
        if q.question_type == QuestionType.MCQ:
            options = [q.option_a, q.option_b, q.option_c, q.option_d]
            options = [opt for opt in options if opt]
        
        topic_tag = q.tags.split(",")[0].strip() if q.tags else None
        
        formatted_questions.append(PracticeQuestionResponse(
            id=q.id,
            type=q.question_type.value if q.question_type else "mcq",
            question=q.question,
            options=options,
            topic_tag=topic_tag,
            difficulty=q.difficulty.value if q.difficulty else "medium"
        ))
    
    logger.info(f"Practice fetch complete: {len(formatted_questions)} questions for module {module_id}")
    
    return PracticeModuleResponse(
        module=ModuleInfo(
            id=module.id,
            title=module.title,
            subject_id=module.subject_id
        ),
        questions=formatted_questions,
        total_count=len(formatted_questions)
    )


class AnswerWritingQuestion(BaseModel):
    id: int
    marks: int
    question: str
    topic_tag: Optional[str] = None
    guidelines: List[str] = []


class AnswerWritingResponse(BaseModel):
    module: ModuleInfo
    questions: List[AnswerWritingQuestion]
    total_count: int


class AnswerSubmitRequest(BaseModel):
    answer_text: str
    time_taken_minutes: Optional[int] = None


class EvaluationInfo(BaseModel):
    id: int
    status: str
    score: Optional[float] = None
    feedback_text: Optional[str] = None
    strengths: Optional[List[str]] = None
    improvements: Optional[List[str]] = None


class AttemptResponse(BaseModel):
    id: int
    attempt_number: int
    answer_preview: str
    time_taken_minutes: Optional[int] = None
    attempted_at: str
    evaluation: Optional[EvaluationInfo] = None


class AnswerSubmitResponse(BaseModel):
    message: str
    attempt: AttemptResponse


class PastAttemptsResponse(BaseModel):
    question_id: int
    question_text: str
    marks: int
    attempts: List[AttemptResponse]
    total_attempts: int


@router.get("/answer-writing/{module_id}", response_model=AnswerWritingResponse)
async def get_answer_writing_questions(
    module_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get answer writing questions for a module.
    
    Phase 3.5: Answer Writing Practice
    
    Returns essay-type questions (5/10/15 marks) with guidelines.
    Guidelines are parsed from the correct_answer field (stored as key points).
    """
    logger.info(f"Answer writing fetch: module_id={module_id}, user={current_user.email}")
    
    stmt = (
        select(ContentModule)
        .options(joinedload(ContentModule.subject))
        .where(ContentModule.id == module_id)
    )
    result = await db.execute(stmt)
    module = result.scalar_one_or_none()
    
    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module not found"
        )
    
    questions_stmt = (
        select(PracticeQuestion)
        .where(
            PracticeQuestion.module_id == module_id,
            PracticeQuestion.question_type.in_([
                QuestionType.ESSAY,
                QuestionType.CASE_ANALYSIS,
                QuestionType.SHORT_ANSWER
            ])
        )
        .order_by(PracticeQuestion.marks, PracticeQuestion.order_index)
    )
    questions_result = await db.execute(questions_stmt)
    questions = questions_result.scalars().all()
    
    formatted_questions = []
    for q in questions:
        guidelines = []
        if q.correct_answer:
            lines = q.correct_answer.strip().split('\n')
            guidelines = [line.strip().lstrip('•-*').strip() for line in lines if line.strip()]
        
        topic_tag = q.tags.split(",")[0].strip() if q.tags else None
        
        formatted_questions.append(AnswerWritingQuestion(
            id=q.id,
            marks=q.marks,
            question=q.question,
            topic_tag=topic_tag,
            guidelines=guidelines[:5]
        ))
    
    logger.info(f"Answer writing fetch complete: {len(formatted_questions)} questions for module {module_id}")
    
    return AnswerWritingResponse(
        module=ModuleInfo(
            id=module.id,
            title=module.title,
            subject_id=module.subject_id
        ),
        questions=formatted_questions,
        total_count=len(formatted_questions)
    )


@router.post("/answer/{question_id}/submit", response_model=AnswerSubmitResponse)
async def submit_answer(
    question_id: int,
    request: AnswerSubmitRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Submit an answer for evaluation.
    
    Phase 3.5: Answer Writing Practice
    
    Rules:
    - Saves answer in practice_attempts
    - is_correct = NULL (not auto-graded)
    - Creates pending evaluation placeholder
    - Multiple attempts allowed (does not overwrite)
    """
    logger.info(f"Answer submit: question_id={question_id}, user={current_user.email}")
    
    question_stmt = select(PracticeQuestion).where(PracticeQuestion.id == question_id)
    question_result = await db.execute(question_stmt)
    question = question_result.scalar_one_or_none()
    
    if not question:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question not found"
        )
    
    if question.question_type == QuestionType.MCQ:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This endpoint is for essay/descriptive answers only"
        )
    
    if not request.answer_text or len(request.answer_text.strip()) < 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Answer must be at least 10 characters"
        )
    
    attempt_count_stmt = (
        select(func.count(PracticeAttempt.id))
        .where(
            PracticeAttempt.user_id == current_user.id,
            PracticeAttempt.practice_question_id == question_id
        )
    )
    attempt_count_result = await db.execute(attempt_count_stmt)
    attempt_number = attempt_count_result.scalar() + 1
    
    time_taken_seconds = None
    if request.time_taken_minutes:
        time_taken_seconds = request.time_taken_minutes * 60
    
    attempt = PracticeAttempt(
        user_id=current_user.id,
        practice_question_id=question_id,
        selected_option=request.answer_text.strip(),
        is_correct=None,
        attempt_number=attempt_number,
        time_taken_seconds=time_taken_seconds,
        attempted_at=datetime.utcnow()
    )
    db.add(attempt)
    await db.flush()
    
    evaluation = PracticeEvaluation(
        practice_attempt_id=attempt.id,
        evaluation_type="ai_descriptive",
        status="pending",
        evaluated_by="ai",
        score=None,
        feedback_text=None,
        strengths=None,
        improvements=None
    )
    db.add(evaluation)
    await db.commit()
    await db.refresh(attempt)
    await db.refresh(evaluation)
    
    logger.info(f"Answer submitted: attempt_id={attempt.id}, evaluation_id={evaluation.id}")
    
    answer_preview = request.answer_text[:100] + "..." if len(request.answer_text) > 100 else request.answer_text
    
    return AnswerSubmitResponse(
        message="Your answer has been submitted for evaluation.",
        attempt=AttemptResponse(
            id=attempt.id,
            attempt_number=attempt.attempt_number,
            answer_preview=answer_preview,
            time_taken_minutes=request.time_taken_minutes,
            attempted_at=attempt.attempted_at.isoformat(),
            evaluation=EvaluationInfo(
                id=evaluation.id,
                status=evaluation.status,
                score=None,
                feedback_text=None,
                strengths=None,
                improvements=None
            )
        )
    )


@router.get("/answer/{question_id}/attempts", response_model=PastAttemptsResponse)
async def get_past_attempts(
    question_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get user's past attempts for a question.
    
    Phase 3.5: View attempt history with evaluation status.
    """
    question_stmt = select(PracticeQuestion).where(PracticeQuestion.id == question_id)
    question_result = await db.execute(question_stmt)
    question = question_result.scalar_one_or_none()
    
    if not question:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question not found"
        )
    
    attempts_stmt = (
        select(PracticeAttempt)
        .options(joinedload(PracticeAttempt.evaluation))
        .where(
            PracticeAttempt.user_id == current_user.id,
            PracticeAttempt.practice_question_id == question_id
        )
        .order_by(PracticeAttempt.attempted_at.desc())
    )
    attempts_result = await db.execute(attempts_stmt)
    attempts = attempts_result.scalars().unique().all()
    
    formatted_attempts = []
    for attempt in attempts:
        eval_info = None
        if attempt.evaluation:
            eval_info = EvaluationInfo(
                id=attempt.evaluation.id,
                status=attempt.evaluation.status,
                score=attempt.evaluation.score,
                feedback_text=attempt.evaluation.feedback_text,
                strengths=attempt.evaluation.strengths,
                improvements=attempt.evaluation.improvements
            )
        
        answer_preview = attempt.selected_option[:100] + "..." if len(attempt.selected_option) > 100 else attempt.selected_option
        time_minutes = attempt.time_taken_seconds // 60 if attempt.time_taken_seconds else None
        
        formatted_attempts.append(AttemptResponse(
            id=attempt.id,
            attempt_number=attempt.attempt_number,
            answer_preview=answer_preview,
            time_taken_minutes=time_minutes,
            attempted_at=attempt.attempted_at.isoformat(),
            evaluation=eval_info
        ))
    
    return PastAttemptsResponse(
        question_id=question.id,
        question_text=question.question,
        marks=question.marks,
        attempts=formatted_attempts,
        total_attempts=len(formatted_attempts)
    )
