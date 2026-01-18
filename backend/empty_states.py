"""
backend/empty_states.py
Phase 11.2: Empty State & Graceful Degradation

CORE PRINCIPLE:
Empty state != Error state

Empty = "You haven't done this yet - here's what to do."
Error = "Something went wrong."

These must NEVER be confused.
"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel


class EmptyStateMetadata(BaseModel):
    """Metadata about empty state conditions"""
    is_empty: bool
    reason: str
    guidance: str
    action_label: Optional[str] = None
    action_href: Optional[str] = None
    min_required: Optional[int] = None
    current_count: Optional[int] = None


class DataWithEmptyState(BaseModel):
    """Wrapper for data that may be empty"""
    has_data: bool
    data: Optional[Any] = None
    empty_state: Optional[EmptyStateMetadata] = None
    data_quality: Optional[str] = None  # 'full', 'partial', 'insufficient', 'empty'


EMPTY_STATE_CONFIGS = {
    "subjects": {
        "reason": "No subjects in your curriculum",
        "guidance": "Complete your course enrollment to see subjects.",
        "action_label": "Complete Enrollment",
        "action_href": "onboarding.html"
    },
    "progress": {
        "reason": "No learning progress recorded",
        "guidance": "Start learning to track your progress.",
        "action_label": "Start Learning",
        "action_href": "start-studying.html"
    },
    "activity": {
        "reason": "No recent activity",
        "guidance": "Your learning history will appear here as you study.",
        "action_label": "Begin Studying",
        "action_href": "start-studying.html"
    },
    "practice": {
        "reason": "No practice attempts recorded",
        "guidance": "Practice questions to see your performance here.",
        "action_label": "Start Practice",
        "action_href": "practice-content.html"
    },
    "analytics": {
        "reason": "Insufficient data for analytics",
        "guidance": "Complete more practice questions to unlock detailed analytics.",
        "action_label": None,
        "action_href": None,
        "min_required": 5
    },
    "focus": {
        "reason": "No focus recommendations available",
        "guidance": "Practice more to receive personalized study recommendations.",
        "action_label": "Start Practice",
        "action_href": "practice-content.html",
        "min_required": 10
    },
    "mastery": {
        "reason": "Mastery data unavailable",
        "guidance": "Complete more practice to calculate mastery levels.",
        "action_label": "Practice Now",
        "action_href": "practice-content.html",
        "min_required": 3
    },
    "tutor_history": {
        "reason": "No tutor interactions yet",
        "guidance": "Use 'Explain' buttons while learning to get AI assistance.",
        "action_label": None,
        "action_href": None
    },
    "notes": {
        "reason": "No notes saved",
        "guidance": "Create notes while learning to see them here.",
        "action_label": "Start Learning",
        "action_href": "start-studying.html"
    },
    "modules": {
        "reason": "No modules available",
        "guidance": "Modules for this subject are being prepared.",
        "action_label": None,
        "action_href": None
    },
    "content": {
        "reason": "No content available",
        "guidance": "Content for this module is coming soon.",
        "action_label": None,
        "action_href": None
    }
}


def get_empty_state_metadata(
    state_type: str,
    current_count: int = 0,
    custom_reason: Optional[str] = None,
    custom_guidance: Optional[str] = None
) -> EmptyStateMetadata:
    """Generate empty state metadata for a given type"""
    config = EMPTY_STATE_CONFIGS.get(state_type, {
        "reason": "No data available",
        "guidance": "Data will appear here as you use this feature.",
        "action_label": None,
        "action_href": None
    })
    
    return EmptyStateMetadata(
        is_empty=True,
        reason=custom_reason or config["reason"],
        guidance=custom_guidance or config["guidance"],
        action_label=config.get("action_label"),
        action_href=config.get("action_href"),
        min_required=config.get("min_required"),
        current_count=current_count
    )


def determine_data_quality(
    data: Any,
    min_for_partial: int = 1,
    min_for_full: int = 5
) -> str:
    """Determine quality level of available data"""
    if data is None:
        return "empty"
    
    if isinstance(data, list):
        count = len(data)
    elif isinstance(data, dict):
        count = len(data)
    elif isinstance(data, (int, float)):
        count = int(data)
    else:
        count = 1 if data else 0
    
    if count == 0:
        return "empty"
    elif count < min_for_partial:
        return "insufficient"
    elif count < min_for_full:
        return "partial"
    else:
        return "full"


def wrap_with_empty_state(
    data: Any,
    state_type: str,
    min_for_partial: int = 1,
    min_for_full: int = 5,
    custom_reason: Optional[str] = None,
    custom_guidance: Optional[str] = None
) -> Dict[str, Any]:
    """Wrap data with empty state metadata"""
    quality = determine_data_quality(data, min_for_partial, min_for_full)
    
    if isinstance(data, list):
        count = len(data)
    elif isinstance(data, dict):
        count = len(data)
    elif isinstance(data, (int, float)):
        count = int(data)
    else:
        count = 1 if data else 0
    
    result = {
        "has_data": quality != "empty",
        "data_quality": quality,
        "data": data
    }
    
    if quality == "empty":
        result["empty_state"] = get_empty_state_metadata(
            state_type, 
            count,
            custom_reason,
            custom_guidance
        ).dict()
    elif quality == "insufficient":
        config = EMPTY_STATE_CONFIGS.get(state_type, {})
        min_required = config.get("min_required", min_for_partial)
        result["insufficient_data_warning"] = {
            "message": f"Limited data available ({count}/{min_required} minimum for accurate results)",
            "guidance": custom_guidance or config.get("guidance", "Continue to add more data for better insights.")
        }
    
    return result


def safe_percentage(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Safely calculate percentage without division by zero"""
    if denominator == 0 or denominator is None:
        return default
    result = (numerator / denominator) * 100
    if result != result:  # NaN check
        return default
    return max(0.0, min(100.0, result))


def safe_average(values: List[float], default: float = 0.0) -> float:
    """Safely calculate average of a list"""
    if not values:
        return default
    valid_values = [v for v in values if v is not None and v == v]  # Filter None and NaN
    if not valid_values:
        return default
    return sum(valid_values) / len(valid_values)


def safe_int(value: Any, default: int = 0) -> int:
    """Safely convert to int"""
    if value is None:
        return default
    try:
        result = int(value)
        if result != result:  # NaN check
            return default
        return result
    except (ValueError, TypeError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    """Safely convert to float"""
    if value is None:
        return default
    try:
        result = float(value)
        if result != result:  # NaN check
            return default
        return result
    except (ValueError, TypeError):
        return default


def get_first_time_user_guidance() -> Dict[str, Any]:
    """Get guidance for first-time users with no data"""
    return {
        "is_first_time": True,
        "welcome_message": "Welcome to Juris AI! Let's get you started on your legal education journey.",
        "next_steps": [
            {
                "step": 1,
                "title": "Complete Your Profile",
                "description": "Tell us about your course and semester",
                "href": "onboarding.html",
                "completed": False
            },
            {
                "step": 2,
                "title": "Explore Your Subjects",
                "description": "Browse through your curriculum",
                "href": "start-studying.html",
                "completed": False
            },
            {
                "step": 3,
                "title": "Start Learning",
                "description": "Begin with your first lesson",
                "href": "start-studying.html",
                "completed": False
            }
        ],
        "tips": [
            "Start with any subject that interests you",
            "Practice questions help reinforce learning",
            "Use the AI tutor when you need explanations"
        ]
    }


def get_partial_progress_guidance(
    subjects_started: int,
    content_completed: int,
    practice_attempted: int
) -> Dict[str, Any]:
    """Get guidance for users with partial progress"""
    suggestions = []
    
    if subjects_started == 0:
        suggestions.append({
            "type": "start_subject",
            "message": "Pick a subject to begin your learning journey",
            "priority": "high"
        })
    elif content_completed == 0:
        suggestions.append({
            "type": "complete_content",
            "message": "Complete your first lesson to track progress",
            "priority": "high"
        })
    elif practice_attempted == 0:
        suggestions.append({
            "type": "try_practice",
            "message": "Test your knowledge with practice questions",
            "priority": "medium"
        })
    elif practice_attempted < 5:
        suggestions.append({
            "type": "more_practice",
            "message": f"Complete {5 - practice_attempted} more practice questions to unlock analytics",
            "priority": "medium"
        })
    
    return {
        "has_partial_progress": True,
        "progress_summary": {
            "subjects_started": subjects_started,
            "content_completed": content_completed,
            "practice_attempted": practice_attempted
        },
        "suggestions": suggestions
    }
