"""
backend/services/evaluation_service.py
Phase 5.2: AI Examiner & Feedback Engine

This service acts as a high-level wrapper for AI evaluation, 
orchestrating between different evaluation types and the AIEvaluator engine.
"""

import logging
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.orm.practice_attempt import PracticeAttempt
from backend.orm.practice_question import PracticeQuestion, QuestionType
from backend.orm.practice_evaluation import PracticeEvaluation, EvaluationType
from backend.services.ai_evaluator import AIEvaluator

logger = logging.getLogger(__name__)

class EvaluationService:
    @staticmethod
    async def evaluate_attempt(db: AsyncSession, attempt_id: int) -> PracticeEvaluation:
        """
        Orchestrates the evaluation of a practice attempt.
        
        Args:
            db: Async database session
            attempt_id: ID of the PracticeAttempt to evaluate
            
        Returns:
            PracticeEvaluation object with results (or processing state)
        """
        # 1. Fetch attempt and related data
        stmt = (
            select(PracticeAttempt)
            .where(PracticeAttempt.id == attempt_id)
        )
        result = await db.execute(stmt)
        attempt = result.scalar_one_or_none()
        
        if not attempt:
            raise ValueError(f"Attempt {attempt_id} not found")
        
        question = attempt.practice_question
        if not question:
            raise ValueError(f"Question for attempt {attempt_id} not found")
        
        # 2. Get or create evaluation record
        stmt = select(PracticeEvaluation).where(
            PracticeEvaluation.practice_attempt_id == attempt_id
        )
        result = await db.execute(stmt)
        evaluation = result.scalar_one_or_none()
        
        if not evaluation:
            evaluation_type = (
                EvaluationType.AUTO_MCQ 
                if question.question_type == QuestionType.MCQ 
                else EvaluationType.AI_DESCRIPTIVE
            )
            
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
        
        # 3. Skip if already completed/evaluated
        if evaluation.is_completed():
            return evaluation
        
        # 4. Mark as processing
        evaluation.mark_processing()
        await db.commit()
        
        try:
            # 5. Use AIEvaluator for the heavy lifting
            eval_result = await AIEvaluator.evaluate_attempt(db, attempt, question)
            
            # 6. Update evaluation with results
            evaluation.mark_completed(
                score=eval_result.get("score"),
                feedback=eval_result.get("feedback_text"),
                strengths=eval_result.get("strengths", []),
                improvements=eval_result.get("improvements", []),
                rubric=eval_result.get("rubric_breakdown"),
                confidence=eval_result.get("confidence_score")
            )
            await db.commit()
            return evaluation
            
        except Exception as e:
            logger.error(f"Evaluation failed for attempt {attempt_id}: {str(e)}")
            evaluation.mark_failed(str(e))
            await db.commit()
            return evaluation

    @staticmethod
    async def re_evaluate(db: AsyncSession, attempt_id: int) -> PracticeEvaluation:
        """
        Safely re-evaluates an attempt by clearing previous results.
        
        Args:
            db: Async database session
            attempt_id: ID of the PracticeAttempt to re-evaluate
        """
        stmt = select(PracticeEvaluation).where(
            PracticeEvaluation.practice_attempt_id == attempt_id
        )
        result = await db.execute(stmt)
        evaluation = result.scalar_one_or_none()
        
        if evaluation:
            # Re-evaluation safeguard: mark as pending to allow background task or service to pickup
            evaluation.status = "pending"
            evaluation.error_message = None
            await db.commit()
            
        return await EvaluationService.evaluate_attempt(db, attempt_id)
