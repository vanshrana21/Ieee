"""
backend/schemas/practice_schemas.py
Phase 9B: Adaptive practice API schemas
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime


class GeneratePracticeRequest(BaseModel):
    """Request to generate adaptive practice questions"""
    subject_id: int = Field(..., gt=0, description="Subject ID")
    count: int = Field(5, ge=1, le=10, description="Number of questions to generate")
    difficulty: Literal["adaptive", "easy", "medium", "hard"] = Field(
        "adaptive",
        description="Difficulty level or 'adaptive' for automatic selection"
    )
    topic_tags: Optional[List[str]] = Field(
        None,
        description="Specific topics to focus on (ignored if difficulty=adaptive)"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "subject_id": 5,
                "count": 5,
                "difficulty": "adaptive"
            }
        }


class QuestionRubric(BaseModel):
    """Grading rubric for a question"""
    required_keywords: List[str] = Field(..., description="Keywords that must be present")
    optional_keywords: List[str] = Field(default_factory=list, description="Bonus keywords")
    keyword_score: float = Field(..., description="Points per required keyword")
    max_score: float = Field(..., description="Maximum score")
    
    class Config:
        json_schema_extra = {
            "example": {
                "required_keywords": ["right to life", "personal liberty", "due process"],
                "optional_keywords": ["fundamental right", "Article 21"],
                "keyword_score": 1.5,
                "max_score": 5.0
            }
        }


class GeneratedQuestion(BaseModel):
    """A generated practice question"""
    question_id: str = Field(..., description="Temporary ID for this generated question")
    question: str = Field(..., description="Question text")
    question_type: Literal["short_answer", "long_answer"] = Field(..., description="Question type")
    marks: float = Field(..., description="Total marks")
    difficulty: str = Field(..., description="Difficulty level")
    topic_tags: List[str] = Field(..., description="Associated topic tags")
    model_answer: str = Field(..., description="Model answer for reference")
    rubric: QuestionRubric = Field(..., description="Grading rubric")
    source_doc_ids: List[int] = Field(default_factory=list, description="Source document IDs")


class GeneratePracticeResponse(BaseModel):
    """Response with generated questions"""
    questions: List[GeneratedQuestion]
    difficulty_distribution: Dict[str, int] = Field(
        ...,
        description="Count of questions per difficulty"
    )
    weak_topics_targeted: List[str] = Field(
        default_factory=list,
        description="Topics targeted (if adaptive)"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "questions": [
                    {
                        "question_id": "gen-abc123",
                        "question": "Explain Article 21 in 200 words",
                        "question_type": "short_answer",
                        "marks": 5.0,
                        "difficulty": "medium",
                        "topic_tags": ["article-21", "fundamental-rights"],
                        "model_answer": "Article 21 guarantees...",
                        "rubric": {
                            "required_keywords": ["right to life", "personal liberty"],
                            "keyword_score": 2.5,
                            "max_score": 5.0
                        },
                        "source_doc_ids": [15, 8]
                    }
                ],
                "difficulty_distribution": {"easy": 1, "medium": 3, "hard": 1},
                "weak_topics_targeted": ["article-21", "contract-law"]
            }
        }


class AssessAnswerRequest(BaseModel):
    """Request to grade a student's answer"""
    question_id: str = Field(..., description="Question ID from generated questions")
    student_answer: str = Field(..., min_length=1, description="Student's answer text")
    rubric: QuestionRubric = Field(..., description="Grading rubric")
    model_answer: Optional[str] = Field(None, description="Optional model answer for comparison")
    
    class Config:
        json_schema_extra = {
            "example": {
                "question_id": "gen-abc123",
                "student_answer": "Article 21 protects the right to life and liberty...",
                "rubric": {
                    "required_keywords": ["right to life", "personal liberty"],
                    "keyword_score": 2.5,
                    "max_score": 5.0
                }
            }
        }


class AssessAnswerResponse(BaseModel):
    """Response with grading results"""
    score: float = Field(..., description="Awarded score")
    max_score: float = Field(..., description="Maximum possible score")
    percentage: float = Field(..., description="Score as percentage")
    matched_keywords: List[str] = Field(default_factory=list, description="Keywords found")
    missing_keywords: List[str] = Field(default_factory=list, description="Keywords not found")
    feedback: str = Field(..., description="Detailed feedback")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Grading confidence")
    improvement_areas: List[str] = Field(default_factory=list, description="Suggestions")
    
    class Config:
        json_schema_extra = {
            "example": {
                "score": 4.5,
                "max_score": 5.0,
                "percentage": 90.0,
                "matched_keywords": ["right to life", "personal liberty"],
                "missing_keywords": ["due process"],
                "feedback": "Good explanation of fundamental concepts. Consider adding procedural safeguards.",
                "confidence_score": 0.88,
                "improvement_areas": ["Elaborate on due process requirements"]
            }
        }


class MasteryStatus(BaseModel):
    """User's mastery status for a subject"""
    subject_id: int
    topic_mastery: List[Dict[str, Any]]
    overall_mastery: float
    weak_topics: List[str]
    strong_topics: List[str]
