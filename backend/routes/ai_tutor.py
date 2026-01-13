"""
backend/routes/ai_tutor.py
API Routes for AI Tutor and Analytics

PHASE 8: Intelligent Learning Engine - API Layer
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.orm.user import User
from backend.routes.auth import get_current_user
from backend.services.ai_tutor import AITutor
from backend.services.analytics import LearningAnalytics
from backend.services.guardrails import GuardrailViolation
from backend.schemas.ai_tutor import (
    AITutorRequest,
    AITutorResponse,
    ClarificationRequest,
    OverallProgressResponse,
    SubjectInsightsResponse,
    PerformanceTrendsResponse,
    SubjectComparisonResponse,
    ErrorResponse
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["AI Tutor & Analytics"])


# ========== AI TUTOR ENDPOINTS ==========

@router.post("/tutor/ask", response_model=AITutorResponse)
async def ask_ai_tutor(
    request: AITutorRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Ask AI tutor a legal question.
    
    PHASE 8 ENDPOINT - Context-Aware AI Responses
    
    Features:
    - Adapts to user role (student/lawyer/general)
    - Adjusts explanation level (simple/moderate/detailed)
    - Injects verified database content (RAG)
    - Maintains conversation context
    - Applies academic guardrails
    
    Request:
        {
            "question": "Explain Article 21 in simple words",
            "explanation_level": "simple",
            "session_id": "optional-session-id"
        }
    
    Response:
        {
            "success": true,
            "message": "Response generated successfully",
            "data": {
                "answer": "...",
                "related_content": [...],
                "follow_up_prompts": [...],
                "session_id": "..."
            }
        }
    """
    logger.info(
        f"[AI TUTOR] Question from {current_user.email}: '{request.question[:50]}...'"
    )
    
    try:
        # Generate response using AI Tutor service
        response_data = await AITutor.generate_response(
            user=current_user,
            query=request.question,
            explanation_level=request.explanation_level,
            session_id=request.session_id,
            db=db
        )
        
        logger.info(
            f"[AI TUTOR] Response generated for {current_user.email}, "
            f"session={response_data['session_id']}"
        )
        
        return {
            "success": True,
            "message": "Response generated successfully",
            "data": response_data
        }
    
    except GuardrailViolation as e:
        logger.error(f"[AI TUTOR] Guardrail violation: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Response failed safety checks: {str(e)}"
        )
    
    except Exception as e:
        logger.error(f"[AI TUTOR] Error generating response: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AI service temporarily unavailable. Please try again."
        )


@router.post("/tutor/clarify", response_model=AITutorResponse)
async def clarify_with_ai_tutor(
    request: ClarificationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Ask follow-up question using conversation context.
    
    Uses conversation history to understand context without
    requiring user to repeat the topic.
    
    Example:
        User: "Explain Article 21"
        AI: "Article 21 guarantees..."
        User: "Give me an example"  <- Uses context
    
    Request:
        {
            "session_id": "user_123_session_abc",
            "follow_up": "Give me an example",
            "explanation_level": "moderate"
        }
    """
    logger.info(
        f"[AI TUTOR] Clarification from {current_user.email}, "
        f"session={request.session_id}"
    )
    
    try:
        # Treat follow-up as regular question with session context
        response_data = await AITutor.generate_response(
            user=current_user,
            query=request.follow_up,
            explanation_level=request.explanation_level,
            session_id=request.session_id,
            db=db
        )
        
        return {
            "success": True,
            "message": "Clarification provided",
            "data": response_data
        }
    
    except GuardrailViolation as e:
        logger.error(f"[AI TUTOR] Guardrail violation: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Response failed safety checks: {str(e)}"
        )
    
    except Exception as e:
        logger.error(f"[AI TUTOR] Error in clarification: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AI service temporarily unavailable. Please try again."
        )


# ========== ANALYTICS ENDPOINTS ==========

@router.get("/analytics/overview", response_model=OverallProgressResponse)
async def get_analytics_overview(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get overall learning analytics summary.
    
    PHASE 8 ENDPOINT - Learning Analytics
    
    Returns:
        - Overall completion percentage
        - Practice accuracy
        - Time spent
        - Subject counts (completed/in progress/not started)
        - Total practice attempts
    
    Response:
        {
            "success": true,
            "message": "Progress calculated",
            "data": {
                "completion_percentage": 67.5,
                "practice_accuracy": 78.2,
                "total_time_spent_hours": 42.5,
                "subjects_completed": 3,
                "subjects_in_progress": 5,
                "subjects_not_started": 2,
                "total_practice_attempts": 156,
                "total_items_completed": 234
            }
        }
    """
    logger.info(f"[ANALYTICS] Overview request from {current_user.email}")
    
    try:
        data = await LearningAnalytics.get_overall_progress(current_user, db)
        
        logger.info(
            f"[ANALYTICS] Overview calculated: "
            f"completion={data['completion_percentage']:.1f}%, "
            f"accuracy={data['practice_accuracy']}"
        )
        
        return {
            "success": True,
            "message": "Progress calculated successfully",
            "data": data
        }
    
    except Exception as e:
        logger.error(f"[ANALYTICS] Error calculating overview: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to calculate analytics"
        )


@router.get("/analytics/subject/{subject_id}", response_model=SubjectInsightsResponse)
async def get_subject_analytics(
    subject_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed analytics for a specific subject.
    
    PHASE 8 ENDPOINT - Subject-Level Insights
    
    Returns:
        - Completion percentage
        - Practice accuracy
        - Time spent
        - Status (strong/moderate/weak/not_started)
        - Weak topics
        - Strong topics
        - Module breakdown
    
    Response:
        {
            "success": true,
            "message": "Subject insights calculated",
            "data": {
                "subject_id": 5,
                "subject_name": "Contract Law",
                "status": "moderate",
                "completion": 67.5,
                "accuracy": 72.3,
                "time_spent_minutes": 340,
                "last_activity": "2026-01-12T10:30:00Z",
                "weak_topics": ["Consideration"],
                "strong_topics": ["Offer & Acceptance"],
                "module_breakdown": {...}
            }
        }
    """
    logger.info(
        f"[ANALYTICS] Subject insights: subject_id={subject_id}, "
        f"user={current_user.email}"
    )
    
    try:
        data = await LearningAnalytics.get_subject_insights(
            current_user, subject_id, db
        )
        
        logger.info(
            f"[ANALYTICS] Subject insights calculated: "
            f"status={data['status']}, completion={data['completion']:.1f}%"
        )
        
        return {
            "success": True,
            "message": "Subject insights calculated successfully",
            "data": data
        }
    
    except ValueError as e:
        logger.warning(f"[ANALYTICS] Subject not found: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    
    except Exception as e:
        logger.error(f"[ANALYTICS] Error calculating subject insights: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to calculate subject analytics"
        )


@router.get("/analytics/trends", response_model=PerformanceTrendsResponse)
async def get_performance_trends(
    weeks: int = 4,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get performance trends over time.
    
    PHASE 8 ENDPOINT - Trend Analysis
    
    Args:
        weeks: Number of weeks to analyze (default: 4)
    
    Returns:
        - Weekly activity (hours, attempts, accuracy)
        - Accuracy trend (improving/declining/stable)
    
    Response:
        {
            "success": true,
            "message": "Trends calculated",
            "data": {
                "weekly_activity": [
                    {
                        "week": "2026-W01",
                        "hours": 8.5,
                        "questions_attempted": 45,
                        "accuracy": 75.5
                    },
                    ...
                ],
                "accuracy_trend": {
                    "current_week": 78.5,
                    "last_week": 72.3,
                    "direction": "improving"
                }
            }
        }
    """
    logger.info(f"[ANALYTICS] Trends request from {current_user.email}, weeks={weeks}")
    
    try:
        data = await LearningAnalytics.get_performance_trends(current_user, db, weeks)
        
        logger.info(
            f"[ANALYTICS] Trends calculated: "
            f"direction={data['accuracy_trend']['direction']}"
        )
        
        return {
            "success": True,
            "message": "Trends calculated successfully",
            "data": data
        }
    
    except Exception as e:
        logger.error(f"[ANALYTICS] Error calculating trends: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to calculate performance trends"
        )


@router.get("/analytics/subject-comparison", response_model=SubjectComparisonResponse)
async def get_subject_comparison(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Compare performance across all subjects.
    
    PHASE 8 ENDPOINT - Subject Comparison
    
    Returns subjects ranked by composite score (completion + accuracy).
    
    Response:
        {
            "success": true,
            "message": "Subjects compared",
            "data": [
                {
                    "subject_id": 3,
                    "subject_name": "Contract Law",
                    "score": 85.5,
                    "completion": 90.0,
                    "accuracy": 78.0
                },
                {
                    "subject_id": 7,
                    "subject_name": "Criminal Law",
                    "score": 72.3,
                    "completion": 75.0,
                    "accuracy": 68.0
                },
                ...
            ]
        }
    """
    logger.info(f"[ANALYTICS] Subject comparison from {current_user.email}")
    
    try:
        data = await LearningAnalytics.get_subject_comparison(current_user, db)
        
        logger.info(f"[ANALYTICS] Compared {len(data)} subjects")
        
        return {
            "success": True,
            "message": "Subjects compared successfully",
            "data": data
        }
    
    except Exception as e:
        logger.error(f"[ANALYTICS] Error comparing subjects: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to compare subjects"
        )