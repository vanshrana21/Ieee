"""
backend/services/ai_evaluator.py
AI-powered evaluation service for practice attempts

PHASE 5: AI Evaluation & Feedback Engine

This service handles:
- Descriptive answer evaluation using Gemini
- MCQ feedback generation (optional enhancement)
- Rubric-based scoring
- Confidence estimation
"""
import os
import logging
import json
from typing import Dict, List, Optional, Tuple
import google.generativeai as genai
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.orm.practice_attempt import PracticeAttempt
from backend.orm.practice_question import PracticeQuestion, QuestionType

logger = logging.getLogger(__name__)

# Configure Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-1.5-pro')


class AIEvaluator:
    """
    AI-powered evaluation service.
    
    Responsibilities:
    - Generate comprehensive feedback for descriptive answers
    - Score based on rubric criteria
    - Identify strengths and improvements
    - Estimate confidence level
    """
    
    # ========== EVALUATION PROMPTS ==========
    
    DESCRIPTIVE_EVALUATION_PROMPT = """You are an expert legal education evaluator for Indian law students.

TASK: Evaluate the student's answer to a legal question.

QUESTION:
{question}

EXPECTED ANSWER / KEY POINTS:
{correct_answer}

STUDENT'S ANSWER:
{student_answer}

MARKS ALLOCATED: {marks}

EVALUATION CRITERIA:
1. Conceptual Accuracy (30%): Are legal concepts correctly understood?
2. Legal Reasoning (30%): Is the reasoning logical and legally sound?
3. Structure & Clarity (20%): Is the answer well-organized and clear?
4. Completeness (20%): Are all key points covered?

INSTRUCTIONS:
1. Evaluate the answer based on the criteria above
2. Assign a score out of {marks} marks (can be decimal)
3. Identify 2-4 specific strengths
4. Identify 2-4 specific areas for improvement
5. Provide overall constructive feedback (2-3 sentences)
6. Rate your confidence in this evaluation (0.0-1.0)

RESPOND ONLY WITH THIS EXACT JSON FORMAT (no markdown, no extra text):
{{
  "score": 7.5,
  "feedback_text": "Your answer demonstrates a good understanding...",
  "strengths": [
    "Correctly identified the key legal principle",
    "Good use of legal terminology"
  ],
  "improvements": [
    "Could elaborate on the application of the principle",
    "Add relevant case law references"
  ],
  "rubric_breakdown": {{
    "conceptual_accuracy": 8.0,
    "legal_reasoning": 7.0,
    "structure": 8.0,
    "completeness": 7.0
  }},
  "confidence_score": 0.85
}}

IMPORTANT:
- Be constructive and encouraging
- Be specific in feedback (avoid generic statements)
- Score fairly but not harshly
- If student answer is very brief or off-topic, score accordingly
- Confidence should reflect clarity of evaluation criteria
"""

    MCQ_FEEDBACK_PROMPT = """You are a legal education assistant providing feedback on MCQ answers.

QUESTION:
{question}

OPTIONS:
A) {option_a}
B) {option_b}
C) {option_c}
D) {option_d}

CORRECT ANSWER: {correct_answer}
STUDENT SELECTED: {student_answer}
RESULT: {"CORRECT" if student_answer == correct_answer else "INCORRECT"}

EXPLANATION:
{explanation}

TASK: Provide brief, encouraging feedback (1-2 sentences) explaining why the answer is correct/incorrect.

RESPOND ONLY WITH THIS JSON FORMAT:
{{
  "feedback_text": "Your explanation here...",
  "confidence_score": 0.95
}}
"""

    # ========== MAIN EVALUATION METHODS ==========
    
    @staticmethod
    async def evaluate_descriptive_answer(
        db: AsyncSession,
        attempt: PracticeAttempt,
        question: PracticeQuestion
    ) -> Dict:
        """
        Evaluate a descriptive answer using AI.
        
        Args:
            db: Database session (unused in this phase, for future RAG)
            attempt: Practice attempt to evaluate
            question: Associated question
        
        Returns:
            Dict with score, feedback, strengths, improvements, rubric, confidence
        
        Raises:
            Exception if AI call fails
        """
        logger.info(
            f"Evaluating descriptive answer: attempt_id={attempt.id}, "
            f"question_id={question.id}"
        )
        
        # Prepare prompt
        prompt = AIEvaluator.DESCRIPTIVE_EVALUATION_PROMPT.format(
            question=question.question,
            correct_answer=question.correct_answer or "No model answer provided",
            student_answer=attempt.selected_option,  # Contains full answer text
            marks=question.marks
        )
        
        try:
            # Call Gemini API
            response = model.generate_content(prompt)
            raw_response = response.text.strip()
            
            logger.info(f"Gemini response received for attempt {attempt.id}")
            
            # Parse JSON response
            # Remove markdown code blocks if present
            if raw_response.startswith("```json"):
                raw_response = raw_response[7:]
            if raw_response.startswith("```"):
                raw_response = raw_response[3:]
            if raw_response.endswith("```"):
                raw_response = raw_response[:-3]
            
            result = json.loads(raw_response.strip())
            
            # Validate required fields
            required_fields = ["score", "feedback_text", "strengths", "improvements", "confidence_score"]
            for field in required_fields:
                if field not in result:
                    raise ValueError(f"Missing required field: {field}")
            
            # Normalize score to marks range
            max_score = question.marks
            if result["score"] > max_score:
                logger.warning(
                    f"AI score {result['score']} exceeds max {max_score}, capping"
                )
                result["score"] = float(max_score)
            
            # Ensure lists
            if not isinstance(result["strengths"], list):
                result["strengths"] = []
            if not isinstance(result["improvements"], list):
                result["improvements"] = []
            
            # Validate confidence score
            confidence = result.get("confidence_score", 0.5)
            if not (0.0 <= confidence <= 1.0):
                logger.warning(f"Invalid confidence {confidence}, defaulting to 0.5")
                result["confidence_score"] = 0.5
            
            logger.info(
                f"Evaluation completed: attempt_id={attempt.id}, "
                f"score={result['score']}/{max_score}, "
                f"confidence={result['confidence_score']}"
            )
            
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini response as JSON: {e}")
            logger.error(f"Raw response: {raw_response}")
            raise Exception("AI returned invalid response format")
        
        except Exception as e:
            logger.error(f"AI evaluation failed for attempt {attempt.id}: {str(e)}")
            raise
    
    @staticmethod
    async def evaluate_mcq_feedback(
        db: AsyncSession,
        attempt: PracticeAttempt,
        question: PracticeQuestion
    ) -> Dict:
        """
        Generate optional feedback for MCQ attempts.
        
        MCQs are already auto-graded, but AI can provide reasoning feedback.
        
        Args:
            db: Database session
            attempt: Practice attempt
            question: Associated question
        
        Returns:
            Dict with feedback_text and confidence_score
        """
        logger.info(
            f"Generating MCQ feedback: attempt_id={attempt.id}, "
            f"question_id={question.id}"
        )
        
        prompt = AIEvaluator.MCQ_FEEDBACK_PROMPT.format(
            question=question.question,
            option_a=question.option_a or "",
            option_b=question.option_b or "",
            option_c=question.option_c or "",
            option_d=question.option_d or "",
            correct_answer=question.correct_answer,
            student_answer=attempt.selected_option,
            explanation=question.explanation or "No explanation provided"
        )
        
        try:
            response = model.generate_content(prompt)
            raw_response = response.text.strip()
            
            # Parse JSON
            if raw_response.startswith("```json"):
                raw_response = raw_response[7:]
            if raw_response.startswith("```"):
                raw_response = raw_response[3:]
            if raw_response.endswith("```"):
                raw_response = raw_response[:-3]
            
            result = json.loads(raw_response.strip())
            
            # MCQ feedback doesn't include scoring (already done)
            # Just return feedback text
            return {
                "score": None,  # Already scored in auto-grading
                "feedback_text": result.get("feedback_text", "Good attempt!"),
                "strengths": [],
                "improvements": [],
                "rubric_breakdown": None,
                "confidence_score": result.get("confidence_score", 0.9)
            }
            
        except Exception as e:
            logger.error(f"MCQ feedback generation failed: {str(e)}")
            # Return minimal feedback on failure
            return {
                "score": None,
                "feedback_text": "Review the explanation above for detailed feedback.",
                "strengths": [],
                "improvements": [],
                "rubric_breakdown": None,
                "confidence_score": 0.5
            }
    
    @staticmethod
    async def evaluate_attempt(
        db: AsyncSession,
        attempt: PracticeAttempt,
        question: PracticeQuestion
    ) -> Dict:
        """
        Main evaluation dispatcher.
        
        Routes to appropriate evaluation method based on question type.
        
        Args:
            db: Database session
            attempt: Practice attempt to evaluate
            question: Associated question
        
        Returns:
            Evaluation result dict
        """
        if question.question_type == QuestionType.MCQ:
            # MCQs: Optional feedback enhancement
            return await AIEvaluator.evaluate_mcq_feedback(db, attempt, question)
        else:
            # Descriptive: Full AI evaluation
            return await AIEvaluator.evaluate_descriptive_answer(db, attempt, question)