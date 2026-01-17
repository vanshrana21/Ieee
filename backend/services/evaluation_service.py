"""
backend/services/evaluation_service.py
Phase 5.2: AI Examiner & Feedback Engine

This service handles the AI-powered evaluation of student answers using 
deterministic rubrics generated in Phase 5.1.
"""

import logging
import json
import re
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select

from backend.orm.practice_attempt import PracticeAttempt
from backend.orm.practice_question import PracticeQuestion, QuestionType
from backend.orm.practice_evaluation import PracticeEvaluation, EvaluationStatus, EvaluationType
from backend.services.rubric_engine import generate_rubric, rubric_to_prompt_format
from backend.services.gemini_service import model

logger = logging.getLogger(__name__)

EVALUATION_PROMPT_TEMPLATE = """You are an expert Indian Law Examiner. Your task is to evaluate a student's answer to a legal question strictly based on the provided marking rubric and model answer guidelines.

### QUESTION
{question_text}

### MODEL ANSWER / GUIDELINES
{model_answer}

### STUDENT ANSWER
{student_answer}

### MARKING RUBRIC
{rubric_text}

### EVALUATION INSTRUCTIONS
1. Evaluate each component of the rubric separately.
2. Assign marks strictly within the maximum limit for each component.
3. Total marks awarded MUST be the sum of component scores.
4. Provide specific, constructive feedback for each component.
5. Identify overall strengths and specific areas where the answer is missing key points.
6. Suggest concrete improvements for the student.
7. Maintain a formal, academic tone consistent with Indian law examinations.
8. DO NOT hallucinate legal principles not present in the model answer or standard legal knowledge.
9. If the answer is irrelevant or empty, award 0 marks.

### OUTPUT FORMAT
You MUST return ONLY a valid JSON object with the following structure:
{{
  "component_scores": [
    {{
      "component": "Name of Component",
      "awarded": 1.5,
      "max": 2.0,
      "feedback": "Feedback for this component."
    }}
  ],
  "total_marks_awarded": 6.5,
  "strengths": ["List of strengths"],
  "missing_points": ["List of missing key points"],
  "improvement_suggestions": ["Concrete steps to improve"],
  "confidence_score": 0.95
}}
"""

class EvaluationService:
    @staticmethod
    async def evaluate_attempt(db: Session, attempt_id: int) -> PracticeEvaluation:
        """
        Triggers AI evaluation for a practice attempt.
        
        Args:
            db: Database session
            attempt_id: ID of the PracticeAttempt to evaluate
            
        Returns:
            PracticeEvaluation object with results
        """
        # 1. Fetch attempt and related data
        attempt = db.query(PracticeAttempt).filter(PracticeAttempt.id == attempt_id).first()
        if not attempt:
            raise ValueError(f"Attempt {attempt_id} not found")
        
        question = attempt.practice_question
        if not question:
            raise ValueError(f"Question for attempt {attempt_id} not found")
        
        # 2. Get or create evaluation record
        evaluation = db.query(PracticeEvaluation).filter(
            PracticeEvaluation.practice_attempt_id == attempt_id
        ).first()
        
        if not evaluation:
            evaluation = PracticeEvaluation(
                practice_attempt_id=attempt_id,
                evaluation_type=EvaluationType.AI_DESCRIPTIVE if question.question_type != QuestionType.MCQ else EvaluationType.AUTO_MCQ,
                status=EvaluationStatus.PENDING
            )
            db.add(evaluation)
            db.commit()
            db.refresh(evaluation)
        
        # Skip if already completed (unless we want to allow re-evaluation, which we do but maybe not automatically)
        if evaluation.status == EvaluationStatus.COMPLETED:
            return evaluation
        
        # 3. Mark as processing
        evaluation.status = EvaluationStatus.PROCESSING
        db.commit()
        
        try:
            # 4. Handle MCQ vs Descriptive
            if question.question_type == QuestionType.MCQ:
                return await EvaluationService._evaluate_mcq(db, attempt, question, evaluation)
            else:
                return await EvaluationService._evaluate_descriptive(db, attempt, question, evaluation)
                
        except Exception as e:
            logger.error(f"Evaluation failed for attempt {attempt_id}: {str(e)}")
            evaluation.status = EvaluationStatus.FAILED
            evaluation.error_message = str(e)
            db.commit()
            return evaluation

    @staticmethod
    async def _evaluate_mcq(db: Session, attempt: PracticeAttempt, question: PracticeQuestion, evaluation: PracticeEvaluation) -> PracticeEvaluation:
        """Auto-grade MCQ and add optional AI reasoning feedback"""
        is_correct = attempt.selected_option.upper() == question.correct_answer.upper()
        score = float(question.marks) if is_correct else 0.0
        
        # Simple breakdown
        rubric_breakdown = {
            "max_marks": question.marks,
            "components": [
                {
                    "name": "Accuracy",
                    "awarded": score,
                    "max": question.marks,
                    "feedback": "Correct option selected." if is_correct else f"Incorrect. The correct option was {question.correct_answer}."
                }
            ]
        }
        
        evaluation.mark_completed(
            score=score,
            feedback=question.explanation or ("Correct" if is_correct else "Incorrect"),
            strengths=["Correct answer"] if is_correct else [],
            improvements=["Review the topic"] if not is_correct else [],
            rubric=rubric_breakdown,
            confidence=1.0
        )
        db.commit()
        return evaluation

    @staticmethod
    async def _evaluate_descriptive(db: Session, attempt: PracticeAttempt, question: PracticeQuestion, evaluation: PracticeEvaluation) -> PracticeEvaluation:
        """Use AI to evaluate descriptive answers against rubric"""
        # 1. Generate/Retrieve Rubric
        rubric = evaluation.rubric_breakdown
        if not rubric:
            rubric = generate_rubric(question.marks, question.question_type.value)
            evaluation.rubric_breakdown = rubric
            db.commit()
        
        rubric_text = rubric_to_prompt_format(rubric)
        
        # 2. Construct Prompt
        prompt = EVALUATION_PROMPT_TEMPLATE.format(
            question_text=question.question,
            model_answer=question.correct_answer,
            student_answer=attempt.selected_option,
            rubric_text=rubric_text
        )
        
        # 3. Call Gemini
        try:
            response = await model.generate_content_async(prompt)
            raw_text = response.text
            
            # 4. Parse JSON Response
            # Clean up potential markdown formatting
            json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
            if not json_match:
                raise ValueError("AI failed to return valid JSON")
                
            result = json.loads(json_match.group())
            
            # 5. Update Evaluation
            evaluation.mark_completed(
                score=result.get("total_marks_awarded", 0.0),
                feedback="Evaluation completed successfully.",
                strengths=result.get("strengths", []),
                improvements=result.get("improvement_suggestions", []),
                rubric=result,
                confidence=result.get("confidence_score", 0.0)
            )
            evaluation.model_version = "gemini-1.5-flash"
            db.commit()
            
            return evaluation
            
        except Exception as e:
            logger.error(f"AI Evaluation failed: {str(e)}")
            raise

    @staticmethod
    async def re_evaluate(db: Session, attempt_id: int) -> PracticeEvaluation:
        """Force re-evaluation of an attempt"""
        evaluation = db.query(PracticeEvaluation).filter(
            PracticeEvaluation.practice_attempt_id == attempt_id
        ).first()
        
        if evaluation:
            evaluation.status = EvaluationStatus.PENDING
            db.commit()
            
        return await EvaluationService.evaluate_attempt(db, attempt_id)
