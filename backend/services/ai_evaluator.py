"""
backend/services/ai_evaluator.py
Phase 5.2: AI Examiner & Feedback Engine

This service handles the AI-powered evaluation of student answers using 
deterministic rubrics and strict examiner personas.
"""

import logging
import json
import re
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
import google.generativeai as genai

from backend.orm.practice_attempt import PracticeAttempt
from backend.orm.practice_question import PracticeQuestion, QuestionType
from backend.orm.practice_evaluation import PracticeEvaluation
from backend.services.rubric_engine import rubric_to_prompt_format

logger = logging.getLogger(__name__)

# System Prompt Template for AI Examiner
EXAMINER_PROMPT_TEMPLATE = """You are an expert Indian Law Examiner. Your task is to evaluate a student's answer to a legal question strictly based on the provided marking rubric and model answer guidelines.

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
7. Maintain a formal, academic tone consistent with Indian law examinations (IRAC focused).
8. DO NOT hallucinate legal principles not present in the model answer or standard legal knowledge.
9. If the answer is irrelevant or empty, award 0 marks.
10. Return your evaluation ONLY in the strict JSON format specified below.

### OUTPUT FORMAT (STRICT JSON)
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

class AIEvaluator:
    @staticmethod
    async def evaluate_attempt(
        db: AsyncSession, 
        attempt: PracticeAttempt, 
        question: PracticeQuestion
    ) -> Dict[str, Any]:
        """
        Evaluate a descriptive practice attempt using AI.
        
        Args:
            db: Async database session
            attempt: The PracticeAttempt object
            question: The PracticeQuestion object
            
        Returns:
            Dictionary containing evaluation results mapped to model fields
        """
        # 1. Prepare Rubric
        # If rubric_snapshot exists in evaluation, use it, otherwise generate
        # In this context, we assume the evaluation record already has it or we generate it now
        # Note: PracticeEvaluation.rubric_breakdown is the column name for the snapshot
        
        # We need to find the evaluation record for this attempt to get the rubric
        from sqlalchemy import select
        stmt = select(PracticeEvaluation).where(PracticeEvaluation.practice_attempt_id == attempt.id)
        result = await db.execute(stmt)
        evaluation = result.scalar_one_or_none()
        
        rubric = None
        if evaluation and evaluation.rubric_breakdown:
            rubric = evaluation.rubric_breakdown
        else:
            from backend.services.rubric_engine import generate_rubric
            rubric = generate_rubric(question.marks, question.question_type.value)
            # We don't save it here as the calling function should handle persistence
            
        rubric_text = rubric_to_prompt_format(rubric)
        
        # 2. Call AI
        try:
            # Initialize model (gemini-1.5-pro for better legal reasoning)
            # We use flash as fallback if pro is not available or for speed, 
            # but user requested pro for this phase.
            model_name = "gemini-1.5-pro"
            model = genai.GenerativeModel(model_name)
            
            prompt = EXAMINER_PROMPT_TEMPLATE.format(
                question_text=question.question,
                model_answer=question.correct_answer,
                student_answer=attempt.selected_option,
                rubric_text=rubric_text
            )
            
            logger.info(f"Calling {model_name} for evaluation of attempt {attempt.id}")
            response = await model.generate_content_async(prompt)
            raw_text = response.text
            
            # 3. Parse and Clean Response
            json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
            if not json_match:
                logger.error(f"AI response did not contain valid JSON: {raw_text}")
                raise ValueError("AI failed to return valid JSON format")
                
            result = json.loads(json_match.group())
            
            # 4. Map results to our DB fields
            # User wants: total_marks_awarded -> marks_awarded (score in our model)
            # status = "evaluated" (completed in our model, but we will use the string)
            
            evaluation_result = {
                "score": float(result.get("total_marks_awarded", 0.0)),
                "feedback_text": "Evaluation completed successfully by AI Examiner.",
                "strengths": result.get("strengths", []),
                "improvements": result.get("improvement_suggestions", []),
                "rubric_breakdown": result, # Store full AI JSON here
                "confidence_score": float(result.get("confidence_score", 0.0)),
                "model_version": model_name
            }
            
            # Special check: Total marks awarded should not exceed question marks
            if evaluation_result["score"] > question.marks:
                logger.warning(f"AI awarded {evaluation_result['score']} which exceeds max {question.marks}. Capping.")
                evaluation_result["score"] = float(question.marks)
                
            return evaluation_result
            
        except Exception as e:
            logger.error(f"Error in AIEvaluator: {str(e)}")
            raise
    
    @staticmethod
    def get_deterministic_id(attempt_id: int) -> str:
        """Helper to ensure same attempt gets same evaluation seed if needed"""
        import hashlib
        return hashlib.md5(str(attempt_id).encode()).hexdigest()
