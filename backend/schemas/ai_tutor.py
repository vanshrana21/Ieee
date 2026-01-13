"""
backend/schemas/ai_tutor.py
Request/Response Schemas for Phase 8 Intelligence Features

Pydantic models for:
- AI Tutor
- Recommendations
- Analytics
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# ========== AI TUTOR SCHEMAS ==========

class AITutorRequest(BaseModel):
    """Request schema for AI tutor question"""
    question: str = Field(..., min_length=5, max_length=1000, description="User's legal question")
    explanation_level: str = Field(
        default="moderate",
        pattern="^(simple|moderate|detailed)$",
        description="Desired explanation depth"
    )
    session_id: Optional[str] = Field(None, description="Conversation session ID for context")


class RelatedContent(BaseModel):
    """Related content item"""
    type: str = Field(..., description="Content type: learn/case/practice")
    id: int = Field(..., description="Content ID")
    title: str = Field(..., description="Content title")


class AITutorResponse(BaseModel):
    """Response schema for AI tutor"""
    success: bool = True
    message: str = "Response generated successfully"
    data: Dict[str, Any] = Field(..., description="Response data")
    
    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "message": "Response generated successfully",
                "data": {
                    "answer": "Article 21 of the Indian Constitution guarantees...",
                    "related_content": [
                        {"type": "learn", "id": 42, "title": "Right to Life and Personal Liberty"},
                        {"type": "case", "id": 15, "case_name": "Maneka Gandhi v. Union of India"}
                    ],
                    "follow_up_prompts": [
                        "Can you explain this with an example?",
                        "What are the key points I should remember?"
                    ],
                    "session_id": "user_123_session_1234567890.5"
                }
            }
        }


class ClarificationRequest(BaseModel):
    """Request schema for follow-up questions"""
    session_id: str = Field(..., description="Active conversation session ID")
    follow_up: str = Field(..., min_length=2, max_length=500, description="Follow-up question")
    explanation_level: str = Field(
        default="moderate",
        pattern="^(simple|moderate|detailed)$"
    )


# ========== RECOMMENDATION SCHEMAS ==========

class RecommendationItem(BaseModel):
    """Single recommendation"""
    priority: str = Field(..., description="urgent/important/suggested")
    type: str = Field(..., description="Action type")
    subject_id: int
    subject_name: str
    reason: str = Field(..., description="Why this is recommended")
    action: str = Field(..., description="What user should do")


class RecommendationsResponse(BaseModel):
    """Response schema for recommendations"""
    success: bool = True
    message: str = "Recommendations generated"
    data: Dict[str, List[RecommendationItem]]
    
    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "message": "Recommendations generated",
                "data": {
                    "urgent": [
                        {
                            "priority": "urgent",
                            "type": "practice",
                            "subject_id": 5,
                            "subject_name": "Contract Law",
                            "reason": "Low accuracy (45%) indicates gaps",
                            "action": "Attempt 5 MCQs on Consideration"
                        }
                    ],
                    "important": [],
                    "suggested": []
                }
            }
        }


class NextActionResponse(BaseModel):
    """Response for single next action"""
    success: bool = True
    message: str = "Next action determined"
    data: Optional[RecommendationItem]


# ========== ANALYTICS SCHEMAS ==========

class OverallProgressData(BaseModel):
    """Overall progress metrics"""
    completion_percentage: float
    practice_accuracy: Optional[float]
    total_time_spent_hours: float
    subjects_completed: int
    subjects_in_progress: int
    subjects_not_started: int
    total_practice_attempts: int
    total_items_completed: int


class OverallProgressResponse(BaseModel):
    """Response for overall progress"""
    success: bool = True
    message: str = "Progress calculated"
    data: OverallProgressData


class SubjectInsightsData(BaseModel):
    """Subject-level insights"""
    subject_id: int
    subject_name: str
    status: str = Field(..., description="strong/moderate/weak/not_started")
    completion: float
    accuracy: Optional[float]
    time_spent_minutes: int
    last_activity: Optional[str]
    weak_topics: List[str]
    strong_topics: List[str]
    module_breakdown: Dict[str, Any]


class SubjectInsightsResponse(BaseModel):
    """Response for subject insights"""
    success: bool = True
    message: str = "Subject insights calculated"
    data: SubjectInsightsData


class WeeklyActivity(BaseModel):
    """Weekly activity data"""
    week: str = Field(..., description="Week identifier (YYYY-Www)")
    hours: float = Field(..., description="Hours spent learning")
    questions_attempted: int
    accuracy: Optional[float]


class AccuracyTrend(BaseModel):
    """Accuracy trend data"""
    current_week: Optional[float]
    last_week: Optional[float]
    direction: str = Field(..., description="improving/declining/stable/insufficient_data")


class PerformanceTrendsData(BaseModel):
    """Performance trends over time"""
    weekly_activity: List[WeeklyActivity]
    accuracy_trend: AccuracyTrend


class PerformanceTrendsResponse(BaseModel):
    """Response for performance trends"""
    success: bool = True
    message: str = "Trends calculated"
    data: PerformanceTrendsData


class SubjectComparison(BaseModel):
    """Subject comparison data"""
    subject_id: int
    subject_name: str
    score: float = Field(..., description="Composite score (0-100)")
    completion: float
    accuracy: Optional[float]


class SubjectComparisonResponse(BaseModel):
    """Response for subject comparison"""
    success: bool = True
    message: str = "Subjects compared"
    data: List[SubjectComparison]


# ========== GENERIC ERROR RESPONSE ==========

class ErrorResponse(BaseModel):
    """Standard error response"""
    success: bool = False
    message: str = Field(..., description="Error message")
    error: Optional[str] = Field(None, description="Detailed error info")