"""
backend/schemas/evaluation.py
Pydantic schemas for evaluation API endpoints

PHASE 5: AI Evaluation & Feedback Engine
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class EvaluationResponse(BaseModel):
    """Response schema for evaluation data"""
    id: int
    practice_attempt_id: int
    evaluation_type: str
    status: str
    score: Optional[float] = None
    feedback_text: Optional[str] = None
    strengths: List[str] = Field(default_factory=list)
    improvements: List[str] = Field(default_factory=list)
    rubric_breakdown: Optional[Dict[str, Any]] = None
    evaluated_by: str
    model_version: Optional[str] = None
    confidence_score: Optional[float] = None
    error_message: Optional[str] = None
    created_at: str
    updated_at: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": 1,
                "practice_attempt_id": 42,
                "evaluation_type": "ai_descriptive",
                "status": "completed",
                "score": 7.5,
                "feedback_text": "Good understanding of contract formation...",
                "strengths": [
                    "Correctly identified offer and acceptance",
                    "Good use of legal terminology"
                ],
                "improvements": [
                    "Could elaborate on consideration",
                    "Add case law references"
                ],
                "rubric_breakdown": {
                    "conceptual_accuracy": 8,
                    "legal_reasoning": 7,
                    "structure": 8,
                    "completeness": 7
                },
                "evaluated_by": "ai",
                "model_version": "gemini-1.5-pro",
                "confidence_score": 0.85,
                "error_message": None,
                "created_at": "2025-01-13T10:30:00Z",
                "updated_at": "2025-01-13T10:30:05Z"
            }
        }


class EvaluationTriggerResponse(BaseModel):
    """Response when evaluation is triggered"""
    message: str
    evaluation_id: int
    status: str
    practice_attempt_id: int
    
    class Config:
        json_schema_extra = {
            "example": {
                "message": "Evaluation started",
                "evaluation_id": 1,
                "status": "processing",
                "practice_attempt_id": 42
            }
        }


class EvaluationStatusResponse(BaseModel):
    """Response for evaluation status check"""
    status: str
    evaluation: Optional[EvaluationResponse] = None
    message: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "completed",
                "evaluation": {
                    "id": 1,
                    "practice_attempt_id": 42,
                    "status": "completed",
                    "score": 7.5,
                    "feedback_text": "Good understanding..."
                },
                "message": None
            }
        }