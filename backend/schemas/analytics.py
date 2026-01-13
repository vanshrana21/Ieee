"""
backend/schemas/analytics.py
Pydantic schemas for Learning Analytics API

PHASE 10: Clean response schemas for intelligence data

All schemas are read-only (no input validation needed).
No UI formatting logic - pure data structures.
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


# ================= OVERVIEW SCHEMAS =================

class LearningSnapshotResponse(BaseModel):
    """
    High-level overview of user's learning progress.
    
    Used by: GET /api/analytics/overview
    """
    total_subjects: int = Field(..., ge=0, description="Total subjects enrolled")
    overall_completion: float = Field(..., ge=0, le=100, description="Average completion %")
    overall_accuracy: Optional[float] = Field(None, ge=0, le=100, description="Overall practice accuracy %")
    study_consistency: str = Field(..., description="excellent | good | irregular | inactive")
    weak_subjects_count: int = Field(..., ge=0, description="Number of weak subjects")
    strong_subjects_count: int = Field(..., ge=0, description="Number of strong subjects")
    needs_revision_count: int = Field(..., ge=0, description="Subjects needing high-priority revision")
    last_activity: Optional[str] = Field(None, description="ISO timestamp of last activity")
    
    class Config:
        json_schema_extra = {
            "example": {
                "total_subjects": 8,
                "overall_completion": 37.5,
                "overall_accuracy": 76.0,
                "study_consistency": "good",
                "weak_subjects_count": 2,
                "strong_subjects_count": 3,
                "needs_revision_count": 2,
                "last_activity": "2026-01-12T14:30:00Z"
            }
        }


# ================= SUBJECT STRENGTH SCHEMAS =================

class SubjectStrengthItem(BaseModel):
    """Individual subject strength classification"""
    subject_id: int = Field(..., description="Subject ID")
    subject_title: str = Field(..., description="Subject name")
    completion_percentage: float = Field(..., ge=0, le=100, description="Completion %")
    accuracy: Optional[float] = Field(None, ge=0, le=100, description="Practice accuracy %")
    strength: str = Field(..., description="weak | average | strong | unstarted")
    total_items: int = Field(..., ge=0, description="Total content items")
    completed_items: int = Field(..., ge=0, description="Completed items")
    
    class Config:
        json_schema_extra = {
            "example": {
                "subject_id": 5,
                "subject_title": "Contract Law",
                "completion_percentage": 45.5,
                "accuracy": 78.0,
                "strength": "strong",
                "total_items": 50,
                "completed_items": 23
            }
        }


class SubjectStrengthMapResponse(BaseModel):
    """
    Complete subject strength analysis.
    
    Used by: GET /api/analytics/subjects
    """
    subjects: List[SubjectStrengthItem] = Field(..., description="All subjects with strength classification")
    weak_subjects: List[SubjectStrengthItem] = Field(..., description="Subjects classified as weak")
    strong_subjects: List[SubjectStrengthItem] = Field(..., description="Subjects classified as strong")
    total_subjects: int = Field(..., ge=0, description="Total subjects analyzed")
    
    class Config:
        json_schema_extra = {
            "example": {
                "subjects": [],
                "weak_subjects": [],
                "strong_subjects": [],
                "total_subjects": 8
            }
        }


# ================= PRACTICE ACCURACY SCHEMAS =================

class PracticeAccuracyResponse(BaseModel):
    """
    Detailed practice accuracy breakdown.
    
    Used by: GET /api/analytics/practice
    """
    overall_accuracy: Optional[float] = Field(None, ge=0, le=100, description="Overall accuracy %")
    total_attempts: int = Field(..., ge=0, description="Total MCQ attempts")
    correct_attempts: int = Field(..., ge=0, description="Correct attempts")
    by_difficulty: Dict[str, float] = Field(default_factory=dict, description="Accuracy by difficulty level")
    recent_accuracy: Optional[float] = Field(None, ge=0, le=100, description="Accuracy in last 7 days")
    trend: str = Field(..., description="improving | declining | stable | insufficient_data")
    
    class Config:
        json_schema_extra = {
            "example": {
                "overall_accuracy": 76.0,
                "total_attempts": 50,
                "correct_attempts": 38,
                "by_difficulty": {
                    "easy": 90.0,
                    "medium": 75.0,
                    "hard": 60.0
                },
                "recent_accuracy": 82.0,
                "trend": "improving"
            }
        }


# ================= REVISION RECOMMENDATION SCHEMAS =================

class RevisionItem(BaseModel):
    """Individual revision recommendation"""
    subject_id: int = Field(..., description="Subject ID")
    subject_title: str = Field(..., description="Subject name")
    priority: str = Field(..., description="high | medium | low | none")
    reason: str = Field(..., description="Human-readable reason for priority")
    completion_percentage: float = Field(..., ge=0, le=100, description="Current completion %")
    accuracy: Optional[float] = Field(None, ge=0, le=100, description="Current accuracy %")
    strength: str = Field(..., description="weak | average | strong | unstarted")
    time_spent_seconds: int = Field(..., ge=0, description="Total time spent (seconds)")
    has_conceptual_gap: bool = Field(..., description="True if high time + low accuracy")
    
    class Config:
        json_schema_extra = {
            "example": {
                "subject_id": 7,
                "subject_title": "Criminal Law",
                "priority": "high",
                "reason": "Low accuracy and incomplete",
                "completion_percentage": 35.0,
                "accuracy": 45.0,
                "strength": "weak",
                "time_spent_seconds": 1800,
                "has_conceptual_gap": True
            }
        }


class RevisionRecommendationsResponse(BaseModel):
    """
    Prioritized revision recommendations.
    
    Used by: GET /api/analytics/recommendations
    """
    recommendations: List[RevisionItem] = Field(..., description="All subjects with revision priority")
    high_priority: List[RevisionItem] = Field(..., description="High-priority subjects")
    medium_priority: List[RevisionItem] = Field(..., description="Medium-priority subjects")
    low_priority: List[RevisionItem] = Field(..., description="Low-priority subjects")
    total_recommendations: int = Field(..., ge=0, description="Total subjects analyzed")
    
    class Config:
        json_schema_extra = {
            "example": {
                "recommendations": [],
                "high_priority": [],
                "medium_priority": [],
                "low_priority": [],
                "total_recommendations": 8
            }
        }


# ================= STUDY CONSISTENCY SCHEMAS =================

class StudyConsistencyResponse(BaseModel):
    """
    Study pattern and consistency metrics.
    
    Used in overview endpoint.
    """
    consistency_level: str = Field(..., description="excellent | good | irregular | inactive")
    days_active_last_30: int = Field(..., ge=0, le=30, description="Days active in last 30 days")
    current_streak: int = Field(..., ge=0, description="Current learning streak (consecutive days)")
    average_session_time_minutes: float = Field(..., ge=0, description="Average session duration")
    total_time_spent_hours: float = Field(..., ge=0, description="Total time spent learning")
    last_activity_date: Optional[str] = Field(None, description="ISO timestamp of last activity")
    
    class Config:
        json_schema_extra = {
            "example": {
                "consistency_level": "good",
                "days_active_last_30": 15,
                "current_streak": 3,
                "average_session_time_minutes": 12.5,
                "total_time_spent_hours": 18.5,
                "last_activity_date": "2026-01-12T14:30:00Z"
            }
        }


# ================= COMBINED ANALYTICS SCHEMAS =================

class ComprehensiveAnalyticsResponse(BaseModel):
    """
    Complete analytics package (all data in one response).
    
    Optional: Can be used for dashboard summary.
    """
    snapshot: LearningSnapshotResponse = Field(..., description="High-level overview")
    consistency: StudyConsistencyResponse = Field(..., description="Study consistency metrics")
    top_weak_subjects: List[SubjectStrengthItem] = Field(..., max_items=5, description="Top 5 weak subjects")
    top_recommendations: List[RevisionItem] = Field(..., max_items=5, description="Top 5 revision priorities")
    
    class Config:
        json_schema_extra = {
            "example": {
                "snapshot": {},
                "consistency": {},
                "top_weak_subjects": [],
                "top_recommendations": []
            }
        }


# ================= STANDARDIZED API RESPONSE =================

class AnalyticsAPIResponse(BaseModel):
    """
    Standardized response wrapper for all analytics endpoints.
    
    Consistent with Phase 9 response format.
    """
    success: bool = Field(..., description="Whether operation succeeded")
    message: str = Field(..., description="Human-readable message")
    data: Dict[str, Any] = Field(..., description="Analytics data")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Analytics retrieved successfully",
                "data": {}
            }
        }