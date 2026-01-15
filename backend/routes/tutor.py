"""
backend/routes/tutor.py
Phase 9A: AI Tutor chat endpoint
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.orm.user import User
from backend.routes.auth import get_current_user
from backend.schemas.tutor_schemas import ChatRequest, ChatResponse
from backend.services.tutor_engine import TutorEngine
from backend.services.rag_service import rag_retrieve_for_tutor

router = APIRouter(prefix="/api/tutor", tags=["tutor"])
logger = logging.getLogger(__name__)


@router.post("/chat", response_model=ChatResponse)
async def tutor_chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Chat with AI tutor using Retrieval-Augmented Generation.
    
    Phase 9A: Chat only - no practice generation or grading.
    
    Security:
    - JWT authentication required
    - Only retrieves content from user's course/semester
    - Only unlocked modules
    - User's own notes only
    
    Process:
    1. Retrieve relevant documents (RAG)
    2. Filter by curriculum access
    3. Generate response using Gemini
    4. Track provenance
    5. Store conversation
    
    Args:
        request: Chat request with user input and optional context
    
    Returns:
        ChatResponse with AI response, sources, and confidence
    
    Raises:
        400: Invalid input
        401: Not authenticated
        503: AI service unavailable
    """
    
    logger.info(f"Tutor chat request: user={current_user.email}, input_len={len(request.input)}")
    
    # Validate user enrollment
    if not current_user.course_id or not current_user.current_semester:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incomplete enrollment. Please complete your course setup."
        )
    
    try:
        # 1. Retrieve relevant documents with curriculum filtering
        retrieved_docs = await rag_retrieve_for_tutor(
            query=request.input,
            user=current_user,
            db=db,
            subject_id=request.context.subject_id if request.context else None,
            top_k=5
        )
        
        logger.info(f"Retrieved {len(retrieved_docs)} documents for tutor")
        
        # 2. Initialize tutor engine
        tutor = TutorEngine(db=db, user=current_user)
        
        # 3. Generate response
        response = await tutor.chat(
            user_input=request.input,
            session_id=request.session_id,
            retrieved_docs=retrieved_docs
        )
        
        return response
    
    except Exception as e:
        logger.error(f"Tutor chat error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI tutor service is temporarily unavailable. Please try again."
        )
