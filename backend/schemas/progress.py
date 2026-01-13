"""
backend/schemas/progress.py
PHASE 9: Pydantic schemas for user learning actions

All Phase 9 endpoints use standardized response format:
{
    "success": bool,
    "message": str,
    "data": dict
}
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator


# ================= REQUEST SCHEMAS =================

class PracticeAttemptRequest(BaseModel):
    """
    Request schema for submitting practice question answer.
    
    Used by: POST /api/progress/submit-answer
    """
    question_id: int = Field(..., gt=0, description="ID of the practice question")
    selected_option: str = Field(..., min_length=1, description="For MCQ: A/B/C/D, For others: full answer text")
    time_taken_seconds: Optional[int] = Field(None, ge=0, le=3600, description="Time spent answering (0-3600 seconds)")
    
    @field_validator('selected_option')
    @classmethod
    def validate_selected_option(cls, v: str) -> str:
        """Ensure selected_option is not empty after stripping"""
        if not v.strip():
            raise ValueError("selected_option cannot be empty")
        return v.strip()
    
    class Config:
        json_schema_extra = {
            "example": {
                "question_id": 42,
                "selected_option": "B",
                "time_taken_seconds": 45
            }
        }


class ContentCompleteRequest(BaseModel):
    """
    Request schema for marking content as completed.
    
    Used by: POST /api/progress/complete-content
    """
    content_type: str = Field(..., description="Type of content: learn | case | practice")
    content_id: int = Field(..., gt=0, description="ID of the content item")
    time_spent_seconds: Optional[int] = Field(None, ge=0, description="Time spent on content")
    
    @field_validator('content_type')
    @classmethod
    def validate_content_type(cls, v: str) -> str:
        """Validate content type is one of allowed values"""
        allowed = ['learn', 'case', 'practice']
        if v.lower() not in allowed:
            raise ValueError(f"content_type must be one of: {', '.join(allowed)}")
        return v.lower()
    
    class Config:
        json_schema_extra = {
            "example": {
                "content_type": "learn",
                "content_id": 42,
                "time_spent_seconds": 180
            }
        }


# ================= RESPONSE SCHEMAS =================

class StandardResponse(BaseModel):
    """
    Standardized response format for all Phase 9 endpoints.
    
    Structure:
    {
        "success": true/false,
        "message": "Human-readable message",
        "data": {...}  // Endpoint-specific data
    }
    """
    success: bool = Field(..., description="Whether the operation succeeded")
    message: str = Field(..., description="Human-readable status message")
    data: Dict[str, Any] = Field(..., description="Endpoint-specific response data")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Operation completed successfully",
                "data": {}
            }
        }


class AnswerSubmissionResponse(BaseModel):
    """
    Response data for practice answer submission.
    
    Nested inside StandardResponse.data
    """
    is_correct: Optional[bool] = Field(None, description="True if correct (MCQ only), None for essays")
    attempt_number: int = Field(..., description="Which attempt this is (1st, 2nd, etc.)")
    correct_answer: str = Field(..., description="The correct answer")
    explanation: Optional[str] = Field(None, description="Explanation of correct answer")
    current_accuracy: Optional[float] = Field(None, ge=0, le=100, description="Current practice accuracy % for subject")
    completion_percentage: float = Field(..., ge=0, le=100, description="Subject completion %")
    
    class Config:
        json_schema_extra = {
            "example": {
                "is_correct": True,
                "attempt_number": 2,
                "correct_answer": "B",
                "explanation": "Option B is correct because...",
                "current_accuracy": 78.5,
                "completion_percentage": 45.5
            }
        }


class ContentCompletionResponse(BaseModel):
    """
    Response data for content completion.
    
    Nested inside StandardResponse.data
    """
    completion_percentage: float = Field(..., ge=0, le=100, description="Subject completion %")
    total_items: int = Field(..., ge=0, description="Total items in subject")
    completed_items: int = Field(..., ge=0, description="Items completed by user")
    
    class Config:
        json_schema_extra = {
            "example": {
                "completion_percentage": 45.5,
                "total_items": 50,
                "completed_items": 23
            }
        }


class UserProgressSummary(BaseModel):
    """
    Response data for overall user progress.
    
    Nested inside StandardResponse.data
    """
    total_subjects: int = Field(..., ge=0, description="Total subjects user is enrolled in")
    overall_completion: float = Field(..., ge=0, le=100, description="Average completion across all subjects")
    practice_accuracy: Optional[float] = Field(None, ge=0, le=100, description="Overall MCQ accuracy %")
    total_attempts: int = Field(..., ge=0, description="Total practice attempts")
    recent_activity: List[Dict[str, Any]] = Field(default_factory=list, description="Recent content interactions")
    
    class Config:
        json_schema_extra = {
            "example": {
                "total_subjects": 8,
                "overall_completion": 37.5,
                "practice_accuracy": 76.0,
                "total_attempts": 50,
                "recent_activity": []
            }
        }


class SubjectProgressDetail(BaseModel):
    """
    Response data for subject-specific progress.
    
    Nested inside StandardResponse.data
    """
    subject_id: int = Field(..., description="Subject ID")
    subject_title: str = Field(..., description="Subject name")
    completion_percentage: float = Field(..., ge=0, le=100, description="Subject completion %")
    total_items: int = Field(..., ge=0, description="Total content items")
    completed_items: int = Field(..., ge=0, description="Completed items")
    practice_accuracy: Optional[float] = Field(None, ge=0, le=100, description="Practice accuracy for this subject")
    last_activity_at: str = Field(..., description="ISO timestamp of last activity")
    
    class Config:
        json_schema_extra = {
            "example": {
                "subject_id": 5,
                "subject_title": "Contract Law",
                "completion_percentage": 45.5,
                "total_items": 50,
                "completed_items": 23,
                "practice_accuracy": 82.0,
                "last_activity_at": "2026-01-12T14:30:00Z"
            }
        }


# ================= LEGACY SCHEMAS (Phase 8 Compatibility) =================

class ContentProgressResponse(BaseModel):
    """Legacy response for Phase 8 compatibility"""
    id: int
    user_id: int
    content_type: str
    content_id: int
    is_completed: bool
    completed_at: Optional[str] = None
    last_viewed_at: str
    view_count: int
    time_spent_seconds: Optional[int] = None
    
    class Config:
        from_attributes = True


class PracticeAttemptSummary(BaseModel):
    """Legacy response for Phase 8 compatibility"""
    id: int
    attempt_number: int
    is_correct: Optional[bool] = None
    time_taken_seconds: Optional[int] = None
    attempted_at: str


class PracticeAttemptResponse(BaseModel):
    """Legacy response for Phase 8 compatibility"""
    id: int
    user_id: int
    practice_question_id: int
    selected_option: str
    is_correct: Optional[bool] = None
    attempt_number: int
    time_taken_seconds: Optional[int] = None
    attempted_at: str
    question: dict = Field(..., description="Full question with correct answer")
    
    class Config:
        from_attributes = True


class SubjectProgressResponse(BaseModel):
    """Legacy response for Phase 8 compatibility"""
    id: int
    user_id: int
    subject_id: int
    completion_percentage: float = Field(..., ge=0, le=100)
    total_items: int
    completed_items: int
    last_activity_at: str
    status_label: str = Field(..., description="Not Started | In Progress | Completed")
    
    class Config:
        from_attributes = True


class ResumeItemResponse(BaseModel):
    """Legacy response for Phase 8 compatibility"""
    content_type: str = Field(..., description="learn | case | practice")
    content_id: int
    content_title: str
    subject_id: int
    subject_title: str
    module_id: int
    last_viewed_at: str
    is_completed: bool


class ResumeLearningResponse(BaseModel):
    """Legacy response for Phase 8 compatibility"""
    last_activity: Optional[ResumeItemResponse] = None
    recent_subjects: List[dict] = Field(default_factory=list)
    total_completion_percentage: float = Field(..., ge=0, le=100)


class UserStatisticsResponse(BaseModel):
    """Legacy response for Phase 8 compatibility"""
    total_subjects: int
    completed_subjects: int
    in_progress_subjects: int
    total_content_items: int
    completed_content_items: int
    overall_completion_percentage: float = Field(..., ge=0, le=100)
    total_practice_attempts: int
    correct_practice_attempts: int
    practice_accuracy_percentage: Optional[float] = Field(None, ge=0, le=100)
    total_time_spent_seconds: int
    total_time_spent_hours: float
    streak_days: int = Field(0, description="Learning streak (future feature)")
    last_active_date: Optional[str] = None