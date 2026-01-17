"""
backend/routes/tutor_chat.py
Phase 6.1: Context-Aware AI Tutor Chat Routes

Provides API endpoints for the disciplined AI law tutor.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List

from backend.database import get_db
from backend.orm.user import User
from backend.routes.auth import get_current_user
from backend.services.context_aware_tutor import (
    generate_tutor_response,
    assemble_student_context,
    detect_query_intent,
    extract_topic_from_query,
    QueryIntent,
    MasteryLevel
)
from backend.services.tutor_session_service import (
    get_history,
    append_message,
    start_session,
    get_session
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tutor/chat", tags=["tutor-chat"])


class TutorChatRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=2000)
    session_id: Optional[str] = None


class TutorChatResponse(BaseModel):
    response: str
    intent: str
    topic: Optional[str]
    mastery_level: str
    suggestions: List[str]
    related_content: List[Dict[str, Any]]
    session_id: str
    meta: Dict[str, Any]


class StudentContextResponse(BaseModel):
    course: str
    semester: int
    allowed_subjects: List[Dict[str, Any]]
    weak_topics: List[str]
    strong_topics: List[str]
    total_attempts: int
    study_priorities: List[Dict[str, Any]]


class IntentDetectionResponse(BaseModel):
    query: str
    intent: str
    topic: Optional[str]
    is_in_syllabus: bool


@router.post("/ask", response_model=TutorChatResponse)
async def ask_tutor(
    request: TutorChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Send a query to the AI tutor.
    
    The tutor will:
    - Validate query against student's syllabus
    - Detect intent (explain/clarify/writing guidance/revision)
    - Adapt response based on topic mastery
    - Refuse out-of-scope queries
    
    Returns structured response with suggestions and related content.
    """
    logger.info(f"Tutor chat request: user={current_user.email}, query='{request.query[:50]}...'")
    
    session_id = request.session_id
    session_history = None
    
    if session_id:
        session = await get_session(session_id, current_user.id, db)
        if session:
            history = await get_history(session_id, current_user.id, db, limit=6)
            if history and "messages" in history:
                session_history = history["messages"]
        else:
            result = await start_session(
                user_id=current_user.id,
                db=db,
                session_name="Tutor Chat"
            )
            session_id = result["session_id"]
    else:
        result = await start_session(
            user_id=current_user.id,
            db=db,
            session_name="Tutor Chat"
        )
        session_id = result["session_id"]
    
    try:
        response = await generate_tutor_response(
            user_id=current_user.id,
            query=request.query,
            db=db,
            session_history=session_history
        )
        
        await append_message(
            session_id=session_id,
            user_id=current_user.id,
            role="student",
            text=request.query,
            db=db,
            metadata={"intent": response.get("intent")}
        )
        
        await append_message(
            session_id=session_id,
            user_id=current_user.id,
            role="assistant",
            text=response["response"],
            db=db,
            metadata={
                "topic": response.get("topic"),
                "mastery_level": response.get("mastery_level")
            }
        )
        
        return TutorChatResponse(
            response=response["response"],
            intent=response["intent"],
            topic=response.get("topic"),
            mastery_level=response["mastery_level"],
            suggestions=response["suggestions"],
            related_content=response["related_content"],
            session_id=session_id,
            meta=response["meta"]
        )
        
    except Exception as e:
        logger.error(f"Tutor chat error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate tutor response"
        )


@router.get("/context", response_model=StudentContextResponse)
async def get_student_context(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get the student's context used by the tutor.
    
    Returns:
    - Course and semester
    - Allowed subjects
    - Weak/strong topics
    - Study priorities
    """
    try:
        context = await assemble_student_context(current_user.id, db)
        
        return StudentContextResponse(
            course=context.course_name,
            semester=context.semester,
            allowed_subjects=context.allowed_subjects,
            weak_topics=context.weak_topics,
            strong_topics=context.strong_topics,
            total_attempts=context.total_attempts,
            study_priorities=context.study_priorities
        )
        
    except Exception as e:
        logger.error(f"Context fetch error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch student context"
        )


@router.post("/preview-intent", response_model=IntentDetectionResponse)
async def preview_query_intent(
    request: TutorChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Preview how the tutor will interpret a query without generating a response.
    
    Useful for understanding:
    - What intent will be detected
    - What topic will be extracted
    - Whether query is in syllabus
    """
    intent = detect_query_intent(request.query)
    topic = extract_topic_from_query(request.query)
    
    context = await assemble_student_context(current_user.id, db)
    is_in_syllabus = context.is_topic_in_syllabus(topic) if topic else True
    
    return IntentDetectionResponse(
        query=request.query,
        intent=intent.value,
        topic=topic,
        is_in_syllabus=is_in_syllabus
    )


@router.get("/suggested-queries")
async def get_suggested_queries(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get suggested queries based on student's context.
    
    Returns queries targeting:
    - Weak topics (for improvement)
    - Strong topics (for revision)
    - Study priorities
    """
    context = await assemble_student_context(current_user.id, db)
    
    suggestions = []
    
    for topic in context.weak_topics[:3]:
        topic_display = topic.replace("-", " ").replace("_", " ").title()
        suggestions.append({
            "query": f"Explain {topic_display}",
            "reason": "You are weak in this topic",
            "intent": QueryIntent.EXPLAIN_CONCEPT.value
        })
    
    for priority in context.study_priorities[:2]:
        if priority["priority"] == "High":
            suggestions.append({
                "query": f"Key points to revise in {priority['subject_title']}",
                "reason": f"High priority subject ({priority['completion']:.0f}% complete)",
                "intent": QueryIntent.REVISION_HELP.value
            })
    
    if context.allowed_subjects:
        subject = context.allowed_subjects[0]
        suggestions.append({
            "query": f"How to write a 10-mark answer on {subject['title']}",
            "reason": "Writing guidance for your subject",
            "intent": QueryIntent.WRITING_GUIDANCE.value
        })
    
    default_suggestions = [
        {
            "query": "Explain Article 21 and its scope",
            "reason": "Fundamental constitutional topic",
            "intent": QueryIntent.EXPLAIN_CONCEPT.value
        },
        {
            "query": "Difference between IPC and CrPC",
            "reason": "Common exam comparison",
            "intent": QueryIntent.CLARIFY_DOUBT.value
        },
        {
            "query": "How to structure a case analysis answer",
            "reason": "Exam writing technique",
            "intent": QueryIntent.WRITING_GUIDANCE.value
        }
    ]
    
    for default in default_suggestions:
        if len(suggestions) < 6:
            suggestions.append(default)
    
    return {
        "suggestions": suggestions[:6],
        "context": {
            "course": context.course_name,
            "semester": context.semester,
            "weak_topics_count": len(context.weak_topics),
            "total_attempts": context.total_attempts
        }
    }


@router.get("/history/{session_id}")
async def get_chat_history(
    session_id: str,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get chat history for a session.
    """
    history = await get_history(session_id, current_user.id, db, limit=limit)
    
    if "error" in history and not history.get("messages"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=history["error"]
        )
    
    return history
