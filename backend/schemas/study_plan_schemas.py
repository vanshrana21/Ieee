"""
backend/schemas/study_plan_schemas.py
Phase 9C: Study plan API schemas
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class GeneratePlanRequest(BaseModel):
    """Request to generate a study plan"""
    duration_weeks: int = Field(..., ge=1, le=12, description="Plan duration in weeks")
    focus_subject_ids: Optional[List[int]] = Field(
        None,
        description="Optional: specific subjects to focus on"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "duration_weeks": 4,
                "focus_subject_ids": [1, 3]
            }
        }


class WeeklyTopicItem(BaseModel):
    """A single topic within a week"""
    subject_name: str = Field(..., description="Subject name")
    subject_code: str = Field(..., description="Subject code")
    topic_tag: str = Field(..., description="Topic tag")
    priority: str = Field(..., description="Priority: high, medium, low")
    estimated_hours: int = Field(..., description="Estimated study hours")
    recommended_actions: List[str] = Field(..., description="Specific actions to take")
    rationale: str = Field(..., description="Why this topic is included")
    mastery_score: Optional[float] = Field(None, description="Current mastery score")


class WeeklyPlan(BaseModel):
    """Plan for one week"""
    week_number: int = Field(..., description="Week number")
    total_hours: int = Field(..., description="Total study hours for this week")
    topics: List[WeeklyTopicItem] = Field(..., description="Topics to study this week")


class GeneratePlanResponse(BaseModel):
    """Response with generated study plan"""
    plan_id: int = Field(..., description="Database ID of created plan")
    summary: str = Field(..., description="High-level plan summary")
    duration_weeks: int = Field(..., description="Plan duration")
    weeks: List[WeeklyPlan] = Field(..., description="Weekly breakdown")
    created_at: str = Field(..., description="ISO timestamp")
    
    class Config:
        json_schema_extra = {
            "example": {
                "plan_id": 12,
                "summary": "4-week focused study plan targeting weak areas in Constitutional Law and Contract Law",
                "duration_weeks": 4,
                "weeks": [
                    {
                        "week_number": 1,
                        "total_hours": 6,
                        "topics": [
                            {
                                "subject_name": "Constitutional Law",
                                "subject_code": "LAW101",
                                "topic_tag": "article-21",
                                "priority": "high",
                                "estimated_hours": 3,
                                "recommended_actions": [
                                    "Revise fundamental concepts",
                                    "Review landmark cases",
                                    "Attempt 2 practice questions"
                                ],
                                "rationale": "Low mastery (42%) and 5 tutor queries in past week",
                                "mastery_score": 0.42
                            }
                        ]
                    }
                ],
                "created_at": "2026-01-13T18:40:00Z"
            }
        }


class GetActivePlanResponse(BaseModel):
    """Response with user's active study plan"""
    has_active_plan: bool
    plan: Optional[GeneratePlanResponse]
