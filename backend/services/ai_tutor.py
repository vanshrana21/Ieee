"""
backend/services/ai_tutor.py
Context-Aware AI Tutor with RAG and Conversation Memory

PHASE 8: Intelligent Learning Engine - Component 1

PURPOSE:
Provide intelligent, context-aware responses to legal queries:
- Adapts to user type (student/judge/faculty/admin/general)
- Maintains conversation context
- Injects verified database content (RAG)
- Applies academic guardrails

LOGIC FLOW:
User Query → Extract Context → Build Prompt → Inject DB Content → 
Call Gemini → Validate → Format → Return
"""
import os
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import google.generativeai as genai
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from backend.orm.user import User, UserRole
from backend.orm.learn_content import LearnContent
from backend.orm.case_content import CaseContent
from backend.services.guardrails import validate_and_format_response, GuardrailViolation

logger = logging.getLogger(__name__)

# Configure Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-pro')


class ConversationSession:
    """
    In-memory conversation storage.
    
    In production, use Redis with TTL for session management.
    """
    _sessions: Dict[str, Dict] = {}
    SESSION_TIMEOUT = timedelta(hours=2)
    
    @classmethod
    def create_session(cls, user_id: int) -> str:
        """Create new conversation session"""
        session_id = f"user_{user_id}_session_{datetime.utcnow().timestamp()}"
        cls._sessions[session_id] = {
            "user_id": user_id,
            "turns": [],
            "current_topic": None,
            "created_at": datetime.utcnow(),
            "last_updated": datetime.utcnow()
        }
        logger.info(f"Created session: {session_id}")
        return session_id
    
    @classmethod
    def get_session(cls, session_id: str) -> Optional[Dict]:
        """Get existing session"""
        session = cls._sessions.get(session_id)
        
        if not session:
            return None
        
        # Check if session expired
        if datetime.utcnow() - session["last_updated"] > cls.SESSION_TIMEOUT:
            cls.delete_session(session_id)
            logger.info(f"Session expired: {session_id}")
            return None
        
        return session
    
    @classmethod
    def add_turn(cls, session_id: str, role: str, content: str):
        """Add conversation turn"""
        session = cls.get_session(session_id)
        if session:
            session["turns"].append({
                "role": role,
                "content": content,
                "timestamp": datetime.utcnow()
            })
            session["last_updated"] = datetime.utcnow()
            
            # Keep only last 6 turns (3 exchanges)
            if len(session["turns"]) > 6:
                session["turns"] = session["turns"][-6:]
    
    @classmethod
    def update_topic(cls, session_id: str, topic: str):
        """Update current discussion topic"""
        session = cls.get_session(session_id)
        if session:
            session["current_topic"] = topic
    
    @classmethod
    def delete_session(cls, session_id: str):
        """Delete session"""
        if session_id in cls._sessions:
            del cls._sessions[session_id]


class AITutor:
    """
    Context-aware legal education AI tutor.
    
    Adapts responses based on:
    - User role (student/judge/faculty/admin)
    - Explanation level (simple/moderate/detailed)
    - Conversation history
    """
    
    # ========== SYSTEM PROMPTS ==========
    
    SYSTEM_PROMPTS = {
        UserRole.STUDENT: """You are a legal education assistant for LAW STUDENTS in India.

RESPONSE GUIDELINES:
- Use proper legal terminology
- Cite landmark judgments when relevant
- Explain ratio decidendi and obiter dicta
- Reference IPC/CrPC/Constitution sections with context
- Academic tone, not advisory
- Use examples from Indian legal system

CONSTRAINTS:
- NO legal advice (educational only)
- NO political commentary
- NO speculative interpretations
- ONLY cite cases from the provided database
- If case not in database, say "consult case law databases"

STRUCTURE:
1. Direct answer to question
2. Legal principle explanation
3. Example or case illustration (if available)
4. Key points summary
""",
        
        UserRole.JUDGE: """You are a legal reference assistant for LEGAL PROFESSIONALS in India.

RESPONSE GUIDELINES:
- Advanced legal analysis
- Statutory interpretation with precedent
- Procedural considerations
- Recent developments and amendments
- Academic rigor expected

CONSTRAINTS:
- NO personal legal advice
- NO political statements
- Verify with latest statutes (mention this)
- Reference case law from provided database only

STRUCTURE:
1. Principle statement
2. Statutory framework
3. Judicial interpretation (with cases)
4. Practical considerations
""",
        
        UserRole.FACULTY: """You are a legal reference assistant for LEGAL PROFESSIONALS in India.

RESPONSE GUIDELINES:
- Advanced legal analysis
- Statutory interpretation with precedent
- Procedural considerations
- Recent developments and amendments
- Academic rigor expected

CONSTRAINTS:
- NO personal legal advice
- NO political statements
- Verify with latest statutes (mention this)
- Reference case law from provided database only

STRUCTURE:
1. Principle statement
2. Statutory framework
3. Judicial interpretation (with cases)
4. Practical considerations
""",
        
        UserRole.ADMIN: """You are a legal information assistant for the GENERAL PUBLIC in India.

RESPONSE GUIDELINES:
- Simple language (avoid complex jargon)
- Explain concepts, not legal advice
- Use everyday examples
- Focus on rights and responsibilities
- Friendly, accessible tone

CONSTRAINTS:
- NO legal advice (informational only)
- NO jargon without explanation
- NO case law (unless very famous)
- Clear disclaimer needed

STRUCTURE:
1. Simple explanation in plain language
2. Real-world example
3. Why it matters to common people
4. When to consult a lawyer
"""
    }
    
    # ========== EXPLANATION LEVEL MODIFIERS ==========
    
    LEVEL_INSTRUCTIONS = {
        "simple": "Explain as if to a high school student. Use simple words.",
        "moderate": "Provide balanced explanation with key details.",
        "detailed": "Comprehensive explanation with all nuances and technicalities."
    }
    
    # ========== RAG: DATABASE CONTENT INJECTION ==========
    
    @staticmethod
    async def search_relevant_content(
        query: str,
        db: AsyncSession,
        user: User
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Search database for relevant learning content and cases.
        
        This is a simple keyword-based RAG. In production, use
        vector embeddings for semantic search.
        
        Args:
            query: User's question
            db: Database session
            user: Current user (for access control)
        
        Returns:
            (learn_items, case_items)
        """
        # Extract keywords from query
        keywords = query.lower().split()
        keywords = [k for k in keywords if len(k) > 3]  # Filter short words
        
        learn_items = []
        case_items = []
        
        if not keywords:
            return learn_items, case_items
        
        # Search LearnContent
        try:
            learn_stmt = select(LearnContent).where(
                or_(*[LearnContent.title.ilike(f"%{kw}%") for kw in keywords])
            ).limit(3)
            
            learn_result = await db.execute(learn_stmt)
            learn_matches = learn_result.scalars().all()
            
            for item in learn_matches:
                learn_items.append({
                    "id": item.id,
                    "title": item.title,
                    "summary": item.summary,
                    "body": item.body[:500]  # First 500 chars
                })
        except Exception as e:
            logger.error(f"Error searching learn content: {e}")
        
        # Search CaseContent (only for law students, judges, and faculty)
        if user.role in [UserRole.STUDENT, UserRole.JUDGE, UserRole.FACULTY]:
            try:
                case_stmt = select(CaseContent).where(
                    or_(*[CaseContent.case_name.ilike(f"%{kw}%") for kw in keywords])
                ).limit(2)
                
                case_result = await db.execute(case_stmt)
                case_matches = case_result.scalars().all()
                
                for case in case_matches:
                    case_items.append({
                        "id": case.id,
                        "case_name": case.case_name,
                        "year": case.year,
                        "ratio": case.ratio[:300]  # First 300 chars
                    })
            except Exception as e:
                logger.error(f"Error searching case content: {e}")
        
        logger.info(f"RAG: Found {len(learn_items)} learn items, {len(case_items)} cases")
        return learn_items, case_items
    
    # ========== PROMPT CONSTRUCTION ==========
    
    @staticmethod
    def build_prompt(
        user: User,
        query: str,
        explanation_level: str,
        session: Optional[Dict],
        learn_items: List[Dict],
        case_items: List[Dict]
    ) -> str:
        """
        Construct complete prompt for Gemini.
        
        Structure:
        1. System prompt (role-based)
        2. Explanation level instruction
        3. Database content (RAG)
        4. Conversation history
        5. Current query
        """
        # Base system prompt
        system_prompt = AITutor.SYSTEM_PROMPTS.get(
            user.role,
            AITutor.SYSTEM_PROMPTS[UserRole.ADMIN]
        )
        
        # Level instruction
        level_instruction = AITutor.LEVEL_INSTRUCTIONS.get(
            explanation_level,
            AITutor.LEVEL_INSTRUCTIONS["moderate"]
        )
        
        prompt_parts = [
            system_prompt,
            f"\nEXPLANATION LEVEL: {level_instruction}",
        ]
        
        # Inject database content (RAG)
        if learn_items:
            prompt_parts.append("\n\nVERIFIED LEARNING CONTENT FROM DATABASE:")
            for item in learn_items:
                prompt_parts.append(f"- {item['title']}: {item['body']}")
        
        if case_items:
            prompt_parts.append("\n\nVERIFIED CASE LAW FROM DATABASE:")
            for case in case_items:
                prompt_parts.append(
                    f"- {case['case_name']} ({case['year']}): {case['ratio']}"
                )
        
        # Conversation history
        if session and session.get("turns"):
            prompt_parts.append("\n\nCONVERSATION HISTORY:")
            for turn in session["turns"][-4:]:  # Last 2 exchanges
                role = "User" if turn["role"] == "user" else "Assistant"
                prompt_parts.append(f"{role}: {turn['content']}")
        
        # Current query
        prompt_parts.append(f"\n\nCURRENT QUESTION:\n{query}")
        
        prompt_parts.append("\n\nYour response:")
        
        return "\n".join(prompt_parts)
    
    # ========== MAIN METHODS ==========
    
    @staticmethod
    async def generate_response(
        user: User,
        query: str,
        explanation_level: str,
        session_id: Optional[str],
        db: AsyncSession
    ) -> Dict:
        """
        Generate AI response to user query.
        
        Args:
            user: Current user
            query: User's question
            explanation_level: simple/moderate/detailed
            session_id: Optional conversation session ID
            db: Database session
        
        Returns:
            {
                "answer": str,
                "related_content": List[Dict],
                "follow_up_prompts": List[str],
                "session_id": str
            }
        
        Raises:
            GuardrailViolation if response fails validation
        """
        logger.info(f"AI Tutor request: user={user.email}, query='{query[:50]}...'")
        
        # Get or create session
        if session_id:
            session = ConversationSession.get_session(session_id)
            if not session:
                logger.warning(f"Session not found: {session_id}, creating new")
                session_id = ConversationSession.create_session(user.id)
                session = ConversationSession.get_session(session_id)
        else:
            session_id = ConversationSession.create_session(user.id)
            session = ConversationSession.get_session(session_id)
        
        # RAG: Search database for relevant content
        learn_items, case_items = await AITutor.search_relevant_content(
            query, db, user
        )
        
        # Build prompt
        prompt = AITutor.build_prompt(
            user, query, explanation_level, session,
            learn_items, case_items
        )
        
        # Call Gemini API
        try:
            response = model.generate_content(prompt)
            raw_answer = response.text
            logger.info("Gemini API call successful")
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            raise Exception("AI service temporarily unavailable")
        
        # Validate with guardrails
        try:
            validated_answer = await validate_and_format_response(
                raw_answer,
                user.role.value,
                db,
                strict=True
            )
        except GuardrailViolation as e:
            logger.error(f"Guardrail violation: {e}")
            raise
        
        # Store conversation turn
        ConversationSession.add_turn(session_id, "user", query)
        ConversationSession.add_turn(session_id, "assistant", validated_answer)
        
        # Extract topic from query (simple keyword extraction)
        topic_keywords = [w for w in query.split() if len(w) > 4]
        if topic_keywords:
            ConversationSession.update_topic(session_id, " ".join(topic_keywords[:3]))
        
        # Prepare related content
        related_content = []
        for item in learn_items:
            related_content.append({
                "type": "learn",
                "id": item["id"],
                "title": item["title"]
            })
        for case in case_items:
            related_content.append({
                "type": "case",
                "id": case["id"],
                "title": case["case_name"]
            })
        
        # Generate follow-up prompts
        follow_up_prompts = AITutor.generate_follow_ups(query, user.role)
        
        return {
            "answer": validated_answer,
            "related_content": related_content,
            "follow_up_prompts": follow_up_prompts,
            "session_id": session_id
        }
    
    @staticmethod
    def generate_follow_ups(query: str, role: UserRole) -> List[str]:
        """Generate contextual follow-up prompts"""
        base_prompts = [
            "Can you explain this with an example?",
            "What are the key points I should remember?",
        ]
        
        if role == UserRole.STUDENT:
            base_prompts.extend([
                "Which cases illustrate this principle?",
                "How is this tested in exams?"
            ])
        elif role in [UserRole.JUDGE, UserRole.FACULTY]:
            base_prompts.extend([
                "What are the procedural considerations?",
                "Are there recent amendments?"
            ])
        else:
            base_prompts.extend([
                "When should I consult a lawyer?",
                "What are my rights here?"
            ])
        
        return base_prompts[:4]  # Return top 4