"""
backend/routes/evaluation.py
Evaluation endpoints - Trigger and fetch AI evaluations

PHASE 5: AI Evaluation & Feedback Engine

Endpoints:
- POST /api/practice/attempts/{attempt_id}/evaluate - Trigger evaluation
- GET /api/practice/attempts/{attempt_id}/evaluation - Get evaluation status/result

NOTE: This module must be imported in main.py:
app.include_router(evaluation.router, prefix="/api")
"""
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from backend.database import get_db
from backend.orm.user import User
from backend.orm.practice_attempt import PracticeAttempt
from backend.orm.practice_question import PracticeQuestion
from backend.orm.practice_evaluation import PracticeEvaluation, EvaluationType
from backend.schemas.evaluation import (
    EvaluationResponse,
    EvaluationTriggerResponse,
    EvaluationStatusResponse
)
from backend.routes.auth import get_current_user
from backend.services.ai_evaluator import AIEvaluator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/practice/attempts", tags=["Evaluation"])


# ================= BACKGROUND TASK =================

async def run_evaluation_task(
    attempt_id: int,
    evaluation_id: int,
    db_url: str
):
    """
    Background task to run AI evaluation.
    
    This runs asynchronously after the API response is sent.
    Uses a fresh database session to avoid connection issues.
    
    Args:
        attempt_id: Practice attempt ID
        evaluation_id: Evaluation record ID
        db_url: Database URL for creating new session
    """
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    
    logger.info(f"Starting background evaluation: attempt_id={attempt_id}")
    
    # Create fresh database session for background task
    engine = create_async_engine(db_url, echo=False)
    AsyncSessionLocal = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    async with AsyncSessionLocal() as db:
        try:
            # Fetch evaluation record
            eval_stmt = select(PracticeEvaluation).where(
                PracticeEvaluation.id == evaluation_id
            )
            eval_result = await db.execute(eval_stmt)
            evaluation = eval_result.scalar_one_or_none()
            
            if not evaluation:
                logger.error(f"Evaluation {evaluation_id} not found in background task")
                return
            
            # Mark as processing
            evaluation.mark_processing()
            await db.commit()
            
            # Fetch attempt and question
            attempt_stmt = (
                select(PracticeAttempt)
                .options(joinedload(PracticeAttempt.practice_question))
                .where(PracticeAttempt.id == attempt_id)
            )
            attempt_result = await db.execute(attempt_stmt)
            attempt = attempt_result.scalar_one_or_none()
            
            if not attempt or not attempt.practice_question:
                raise Exception("Attempt or question not found")
            
            question = attempt.practice_question
            
            # Run AI evaluation
            result = await AIEvaluator.evaluate_attempt(db, attempt, question)
            
            # Update evaluation with results
            evaluation.mark_completed(
                score=result.get("score"),
                feedback=result.get("feedback_text"),
                strengths=result.get("strengths", []),
                improvements=result.get("improvements", []),
                rubric=result.get("rubric_breakdown"),
                confidence=result.get("confidence_score")
            )
            
            await db.commit()
            
            logger.info(
                f"Evaluation completed successfully: "
                f"attempt_id={attempt_id}, evaluation_id={evaluation_id}"
            )
            
        except Exception as e:
            logger.error(
                f"Evaluation failed: attempt_id={attempt_id}, error={str(e)}",
                exc_info=True
            )
            
            # Mark evaluation as failed
            try:
                eval_stmt = select(PracticeEvaluation).where(
                    PracticeEvaluation.id == evaluation_id
                )
                eval_result = await db.execute(eval_stmt)
                evaluation = eval_result.scalar_one_or_none()
                
                if evaluation:
                    evaluation.mark_failed(str(e))
                    await db.commit()
            except Exception as commit_error:
                logger.error(f"Failed to mark evaluation as failed: {commit_error}")
        
        finally:
            await engine.dispose()


# ================= API ROUTES =================

@router.post("/{attempt_id}/evaluate", response_model=EvaluationTriggerResponse)
async def trigger_evaluation(
    attempt_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Trigger AI evaluation for a practice attempt.
    
    PHASE 5: Non-blocking evaluation trigger
    
    Business Logic:
    - Verify user owns the attempt
    - If evaluation exists and completed → return it
    - If evaluation exists and pending → return pending status
    - If evaluation exists and failed → re-run evaluation
    - If no evaluation → create and queue evaluation
    - Evaluation runs in background (does not block response)
    
    Args:
        attempt_id: Practice attempt ID
    
    Returns:
        {
            "message": "Evaluation started",
            "evaluation_id": 1,
            "status": "processing",
            "practice_attempt_id": 42
        }
    
    Raises:
        403: User does not own attempt
        404: Attempt not found
    """
    logger.info(f"Evaluation trigger: attempt_id={attempt_id}, user={current_user.email}")
    
    # ========== FETCH ATTEMPT ==========
    
    attempt_stmt = (
        select(PracticeAttempt)
        .options(joinedload(PracticeAttempt.practice_question))
        .where(PracticeAttempt.id == attempt_id)
    )
    attempt_result = await db.execute(attempt_stmt)
    attempt = attempt_result.scalar_one_or_none()
    
    if not attempt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Practice attempt not found"
        )
    
    # ========== VERIFY OWNERSHIP ==========
    
    if attempt.user_id != current_user.id:
        logger.warning(
            f"User {current_user.id} attempted to evaluate attempt {attempt_id} "
            f"owned by user {attempt.user_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only evaluate your own attempts"
        )
    
    # ========== CHECK EXISTING EVALUATION ==========
    
    eval_stmt = select(PracticeEvaluation).where(
        PracticeEvaluation.practice_attempt_id == attempt_id
    )
    eval_result = await db.execute(eval_stmt)
    existing_evaluation = eval_result.scalar_one_or_none()
    
    if existing_evaluation:
        # Evaluation already exists
        if existing_evaluation.is_completed():
            # Already completed - return existing evaluation
            logger.info(f"Evaluation already completed for attempt {attempt_id}")
            return EvaluationTriggerResponse(
                message="Evaluation already completed",
                evaluation_id=existing_evaluation.id,
                status=existing_evaluation.status,
                practice_attempt_id=attempt_id
            )
        
        elif existing_evaluation.is_pending():
            # Already in progress - return status
            logger.info(f"Evaluation already in progress for attempt {attempt_id}")
            return EvaluationTriggerResponse(
                message="Evaluation already in progress",
                evaluation_id=existing_evaluation.id,
                status=existing_evaluation.status,
                practice_attempt_id=attempt_id
            )
        
        elif existing_evaluation.is_failed():
            # Failed previously - re-run evaluation
            logger.info(f"Re-running failed evaluation for attempt {attempt_id}")
            existing_evaluation.status = "pending"
            existing_evaluation.error_message = None
            await db.commit()
            
            # Queue background task
            from backend.database import DATABASE_URL
            background_tasks.add_task(
                run_evaluation_task,
                attempt_id,
                existing_evaluation.id,
                DATABASE_URL
            )
            
            return EvaluationTriggerResponse(
                message="Evaluation re-started",
                evaluation_id=existing_evaluation.id,
                status="processing",
                practice_attempt_id=attempt_id
            )
    
    # ========== CREATE NEW EVALUATION ==========
    
    # Determine evaluation type
    question = attempt.practice_question
    if not question:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Question data missing"
        )
    
    from backend.orm.practice_question import QuestionType
    
    evaluation_type = (
        EvaluationType.AUTO_MCQ 
        if question.question_type == QuestionType.MCQ 
        else EvaluationType.AI_DESCRIPTIVE
    )
    
    # Create evaluation record
    evaluation = PracticeEvaluation(
        practice_attempt_id=attempt_id,
        evaluation_type=evaluation_type.value,
        status="pending",
        evaluated_by="ai",
        model_version="gemini-1.5-pro"
    )
    
    db.add(evaluation)
    await db.commit()
    await db.refresh(evaluation)
    
    logger.info(
        f"Created evaluation: id={evaluation.id}, type={evaluation_type.value}, "
        f"attempt_id={attempt_id}"
    )
    
    # ========== QUEUE BACKGROUND TASK ==========
    
    from backend.database import DATABASE_URL
    background_tasks.add_task(
        run_evaluation_task,
        attempt_id,
        evaluation.id,
        DATABASE_URL
    )
    
    logger.info(f"Queued background evaluation task for attempt {attempt_id}")
    
    return EvaluationTriggerResponse(
        message="Evaluation started",
        evaluation_id=evaluation.id,
        status="processing",
        practice_attempt_id=attempt_id
    )


@router.get("/{attempt_id}/evaluation", response_model=EvaluationStatusResponse)
async def get_evaluation(
    attempt_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get evaluation status and results for an attempt.
    
    PHASE 5: Non-blocking evaluation retrieval
    
    Response States:
    - pending: Evaluation queued but not started
    - processing: AI is currently evaluating
    - completed: Evaluation finished (includes full results)
    - failed: Evaluation failed (includes error message)
    - not_found: No evaluation exists for this attempt
    
    Args:
        attempt_id: Practice attempt ID
    
    Returns:
        {
            "status": "completed",
            "evaluation": {...},
            "message": null
        }
    
    Raises:
        403: User does not own attempt
        404: Attempt not found
    """
    logger.info(f"Get evaluation: attempt_id={attempt_id}, user={current_user.email}")
    
    # ========== FETCH ATTEMPT ==========
    
    attempt_stmt = select(PracticeAttempt).where(PracticeAttempt.id == attempt_id)
    attempt_result = await db.execute(attempt_stmt)
    attempt = attempt_result.scalar_one_or_none()
    
    if not attempt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Practice attempt not found"
        )
    
    # ========== VERIFY OWNERSHIP ==========
    
    if attempt.user_id != current_user.id:
        logger.warning(
            f"User {current_user.id} attempted to view evaluation for attempt {attempt_id} "
            f"owned by user {attempt.user_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view evaluations for your own attempts"
        )
    
    # ========== FETCH EVALUATION ==========
    
    eval_stmt = select(PracticeEvaluation).where(
        PracticeEvaluation.practice_attempt_id == attempt_id
    )
    eval_result = await db.execute(eval_stmt)
    evaluation = eval_result.scalar_one_or_none()
    
    if not evaluation:
        # No evaluation exists yet
        return EvaluationStatusResponse(
            status="not_found",
            evaluation=None,
            message="No evaluation found. Trigger evaluation first."
        )
    
    # ========== RETURN STATUS ==========
    
    if evaluation.is_completed():
        # Return full evaluation data
        return EvaluationStatusResponse(
            status="completed",
            evaluation=EvaluationResponse(**evaluation.to_dict()),
            message=None
        )
    
    elif evaluation.status == "pending":
        return EvaluationStatusResponse(
            status="pending",
            evaluation=None,
            message="Evaluation queued. Check back shortly."
        )
    
    elif evaluation.status == "processing":
        return EvaluationStatusResponse(
            status="processing",
            evaluation=None,
            message="AI is currently evaluating your answer. This may take 10-30 seconds."
        )
    
    elif evaluation.is_failed():
        # Return error details
        return EvaluationStatusResponse(
            status="failed",
            evaluation=EvaluationResponse(**evaluation.to_dict()),
            message=f"Evaluation failed: {evaluation.error_message}"
        )
    
    else:
        # Unknown status
        return EvaluationStatusResponse(
            status="unknown",
            evaluation=None,
            message="Evaluation in unknown state. Please contact support."
        )