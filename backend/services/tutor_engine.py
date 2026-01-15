"""
backend/services/tutor_engine.py
Phase 9A: AI Tutor conversation engine
"""

import os
import logging
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

import google.generativeai as genai

from backend.orm.user import User
from backend.orm.tutor_session import TutorSession
from backend.orm.tutor_message import TutorMessage
from backend.schemas.tutor_schemas import ChatResponse, ProvenanceItem

logger = logging.getLogger(__name__)

# Configure Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


class TutorEngine:
    """
    AI Tutor conversation engine with RAG and provenance tracking.
    
    Phase 9A: Chat only (no practice generation, grading, or planning)
    """
    
    def __init__(self, db: AsyncSession, user: User):
        self.db = db
        self.user = user
        self.model = genai.GenerativeModel('gemini-1.5-flash')
    
    async def chat(
        self,
        user_input: str,
        session_id: Optional[str],
        retrieved_docs: List[Dict[str, Any]]
    ) -> ChatResponse:
        """
        Process a chat turn with the AI tutor.
        
        Steps:
        1. Get or create session
        2. Store user message
        3. Build prompt from retrieved docs
        4. Call Gemini
        5. Calculate confidence
        6. Store assistant message
        7. Return response
        
        Args:
            user_input: User's question
            session_id: Existing session or None for new
            retrieved_docs: Documents from RAG
        
        Returns:
            ChatResponse with content, provenance, confidence
        """
        
        # 1. Get or create session
        if session_id:
            session = await self._get_session(session_id)
            if not session or session.user_id != self.user.id:
                # Invalid session - create new
                session = await self._create_session()
        else:
            session = await self._create_session()
        
        # 2. Store user message
        user_msg = TutorMessage(
            session_id=session.session_id,
            role="user",
            content=user_input
        )
        self.db.add(user_msg)
        session.increment_message_count()
        await self.db.flush()
        
        # 3. Build prompt
        system_prompt = self._build_system_prompt(retrieved_docs)
        user_prompt = self._build_user_prompt(user_input)
        
        # 4. Call Gemini
        try:
            response = self.model.generate_content(
                [system_prompt, user_prompt],
                generation_config=genai.types.GenerationConfig(
                    temperature=0.7,
                    max_output_tokens=500
                )
            )
            
            assistant_content = response.text.strip()
        
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            assistant_content = "I'm having trouble processing your question right now. Please try again."
            retrieved_docs = []
        
        # 5. Calculate confidence (average similarity of retrieved docs)
        confidence_score = self._calculate_confidence(retrieved_docs)
        
        # 6. Build provenance
        provenance = self._build_provenance(retrieved_docs)
        
        # 7. Store assistant message
        assistant_msg = TutorMessage(
            session_id=session.session_id,
            role="assistant",
            content=assistant_content,
            provenance=[p.dict() for p in provenance],
            confidence_score=confidence_score
        )
        self.db.add(assistant_msg)
        session.increment_message_count()
        
        await self.db.commit()
        await self.db.refresh(assistant_msg)
        
        logger.info(f"Tutor response generated: session={session.session_id}, confidence={confidence_score:.2f}")
        
        # 8. Return response
        return ChatResponse(
            message_id=assistant_msg.id,
            session_id=session.session_id,
            content=assistant_content,
            provenance=provenance,
            confidence_score=confidence_score,
            timestamp=assistant_msg.created_at.isoformat()
        )
    
    async def _get_session(self, session_id: str) -> Optional[TutorSession]:
        """Fetch existing session"""
        result = await self.db.execute(
            select(TutorSession).where(TutorSession.session_id == session_id)
        )
        return result.scalar_one_or_none()
    
    async def _create_session(self) -> TutorSession:
        """Create new session"""
        session = TutorSession(
            user_id=self.user.id,
            session_id=str(uuid.uuid4()),
            message_count=0,
            last_activity_at=datetime.utcnow()
        )
        self.db.add(session)
        await self.db.flush()
        return session
    
    def _build_system_prompt(self, retrieved_docs: List[Dict[str, Any]]) -> str:
        """
        Build system prompt with retrieved documents.
        
        CRITICAL: Only use provided documents - no external knowledge.
        """
        
        if not retrieved_docs:
            sources_section = "NO COURSE MATERIALS FOUND. You must tell the student that this topic is not covered in their current course materials."
        else:
            sources_list = []
            for i, doc in enumerate(retrieved_docs, 1):
                sources_list.append(
                    f"[{i}] {doc['doc_type'].upper()}:{doc['doc_id']} - {doc['title']}\n"
                    f"   {doc['snippet']}"
                )
            sources_section = "COURSE MATERIALS (use ONLY these):\n" + "\n\n".join(sources_list)
        
        return f"""You are an expert Indian law tutor helping a student prepare for exams.

PERSONA:
- Friendly, encouraging teaching style
- Use simple language
- Break down complex concepts
- Socratic method (ask guiding questions when helpful)

CRITICAL CONSTRAINTS:
- Answer ONLY from the provided course materials below
- NEVER use external knowledge or make assumptions
- If information is not in the materials, say: "This is not covered in your current course materials. Please consult your professor or textbook."
- Cite sources inline using format: [doc_type:doc_id]
- Keep responses under 400 words

{sources_section}

STUDENT CONTEXT:
- Course: {self.user.course_id or 'Not enrolled'}
- Semester: {self.user.current_semester or 'N/A'}

Your goal: Help the student understand the concept using ONLY the materials above."""
    
    def _build_user_prompt(self, user_input: str) -> str:
        """Build user prompt"""
        return f"""Student question: {user_input}

Respond as a tutor. Cite sources as [type:id]. If the question is outside the course materials, explain this clearly."""
    
    def _calculate_confidence(self, retrieved_docs: List[Dict[str, Any]]) -> float:
        """
        Calculate confidence score based on retrieval quality.
        
        Heuristic: Average similarity score of retrieved documents
        """
        if not retrieved_docs:
            return 0.0
        
        scores = [doc['score'] for doc in retrieved_docs]
        return round(sum(scores) / len(scores), 3)
    
    def _build_provenance(self, retrieved_docs: List[Dict[str, Any]]) -> List[ProvenanceItem]:
        """Convert retrieved docs to provenance items"""
        return [
            ProvenanceItem(
                doc_id=doc['doc_id'],
                doc_type=doc['doc_type'],
                score=doc['score'],
                snippet=doc['snippet'],
                title=doc.get('title', f"{doc['doc_type']}:{doc['doc_id']}")
            )
            for doc in retrieved_docs
        ]
