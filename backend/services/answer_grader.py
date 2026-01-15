"""
backend/services/answer_grader.py
Phase 9B: AI-powered answer grading with explainable feedback
"""

import os
import logging
from typing import Optional, List
import google.generativeai as genai

from backend.schemas.practice_schemas import QuestionRubric, AssessAnswerResponse

logger = logging.getLogger(__name__)

# Configure Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


async def grade_answer(
    student_answer: str,
    rubric: QuestionRubric,
    model_answer: Optional[str] = None
) -> AssessAnswerResponse:
    """
    Grade a student's answer using keyword matching + AI feedback.
    
    Grading process:
    1. Keyword matching (deterministic scoring)
    2. AI comparison with model answer (qualitative feedback)
    3. Generate improvement suggestions
    
    Args:
        student_answer: Student's submitted answer
        rubric: Grading rubric with keywords and scoring
        model_answer: Optional model answer for comparison
    
    Returns:
        AssessAnswerResponse with score, feedback, and suggestions
    
    CRITICAL: Does NOT modify student answer or store in DB
    """
    
    logger.info(f"Grading answer: length={len(student_answer)}, rubric_keywords={len(rubric.required_keywords)}")
    
    # 1. Keyword-based scoring (deterministic)
    matched_keywords, missing_keywords, keyword_score = _score_by_keywords(
        student_answer, rubric
    )
    
    # 2. Calculate base score
    base_score = min(keyword_score, rubric.max_score)
    
    # 3. Generate AI feedback (if model answer provided)
    if model_answer:
        ai_feedback, improvement_areas, confidence = await _generate_ai_feedback(
            student_answer=student_answer,
            model_answer=model_answer,
            matched_keywords=matched_keywords,
            missing_keywords=missing_keywords
        )
    else:
        ai_feedback = _generate_keyword_feedback(matched_keywords, missing_keywords)
        improvement_areas = [f"Include: {kw}" for kw in missing_keywords[:3]]
        confidence = 0.7  # Lower confidence without model answer
    
    # 4. Build response
    percentage = round((base_score / rubric.max_score) * 100, 1)
    
    response = AssessAnswerResponse(
        score=round(base_score, 2),
        max_score=rubric.max_score,
        percentage=percentage,
        matched_keywords=matched_keywords,
        missing_keywords=missing_keywords,
        feedback=ai_feedback,
        confidence_score=round(confidence, 3),
        improvement_areas=improvement_areas
    )
    
    logger.info(f"Grading complete: score={response.score}/{response.max_score}, confidence={confidence}")
    
    return response


def _score_by_keywords(
    student_answer: str,
    rubric: QuestionRubric
) -> tuple[List[str], List[str], float]:
    """
    Score answer by keyword matching.
    
    Returns:
        (matched_keywords, missing_keywords, total_score)
    """
    
    answer_lower = student_answer.lower()
    
    # Check required keywords
    matched = []
    missing = []
    
    for keyword in rubric.required_keywords:
        if keyword.lower() in answer_lower:
            matched.append(keyword)
        else:
            missing.append(keyword)
    
    # Check optional keywords (bonus points)
    optional_matched = []
    for keyword in rubric.optional_keywords:
        if keyword.lower() in answer_lower:
            optional_matched.append(keyword)
    
    # Calculate score
    required_score = len(matched) * rubric.keyword_score
    optional_score = len(optional_matched) * (rubric.keyword_score * 0.5)  # 50% bonus
    
    total_score = required_score + optional_score
    
    logger.debug(f"Keyword scoring: matched={len(matched)}, missing={len(missing)}, score={total_score}")
    
    return matched, missing, total_score


async def _generate_ai_feedback(
    student_answer: str,
    model_answer: str,
    matched_keywords: List[str],
    missing_keywords: List[str]
) -> tuple[str, List[str], float]:
    """
    Generate qualitative feedback using AI comparison.
    
    Returns:
        (feedback_text, improvement_areas, confidence_score)
    """
    
    prompt = f"""You are grading a law student's answer. Compare it to the model answer and provide constructive feedback.

MODEL ANSWER:
{model_answer}

STUDENT ANSWER:
{student_answer}

KEYWORD ANALYSIS:
- Matched: {', '.join(matched_keywords)}
- Missing: {', '.join(missing_keywords)}

TASK:
1. Provide 2-3 sentence feedback on content quality
2. List 2-3 specific improvement areas
3. Be encouraging but honest

FORMAT YOUR RESPONSE AS:
FEEDBACK: [your feedback]
IMPROVEMENTS: [improvement 1] | [improvement 2] | [improvement 3]
"""
    
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.4,
                max_output_tokens=300
            )
        )
        
        # Parse response
        response_text = response.text.strip()
        
        # Extract feedback and improvements
        feedback = ""
        improvements = []
        
        for line in response_text.split('\n'):
            if line.startswith('FEEDBACK:'):
                feedback = line.replace('FEEDBACK:', '').strip()
            elif line.startswith('IMPROVEMENTS:'):
                improvements = [
                    imp.strip() 
                    for imp in line.replace('IMPROVEMENTS:', '').split('|')
                ]
        
        # Default if parsing failed
        if not feedback:
            feedback = response_text[:200]
        
        if not improvements:
            improvements = [f"Address: {kw}" for kw in missing_keywords[:3]]
        
        # Confidence based on keyword coverage
        confidence = len(matched_keywords) / (len(matched_keywords) + len(missing_keywords)) if (matched_keywords or missing_keywords) else 0.5
        
        return feedback, improvements[:3], confidence
    
    except Exception as e:
        logger.error(f"AI feedback generation failed: {e}")
        
        # Fallback to keyword-based feedback
        feedback = _generate_keyword_feedback(matched_keywords, missing_keywords)
        improvements = [f"Include: {kw}" for kw in missing_keywords[:3]]
        
        return feedback, improvements, 0.6


def _generate_keyword_feedback(
    matched_keywords: List[str],
    missing_keywords: List[str]
) -> str:
    """Generate simple keyword-based feedback"""
    
    if not matched_keywords and not missing_keywords:
        return "Unable to assess answer quality. Please ensure your answer addresses the question."
    
    feedback_parts = []
    
    if matched_keywords:
        feedback_parts.append(f"Good coverage of: {', '.join(matched_keywords)}.")
    
    if missing_keywords:
        feedback_parts.append(f"Missing key concepts: {', '.join(missing_keywords)}.")
    
    return " ".join(feedback_parts)
