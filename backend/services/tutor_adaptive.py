import logging
import json
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.services.tutor_context_service import assemble_context
from backend.services.ai_service import call_gemini_deterministic
from backend.services.tutor_session_service import build_session_context, append_message
from backend.orm.topic_mastery import TopicMastery

logger = logging.getLogger(__name__)

async def determine_depth(user_id: int, question: str, context: Dict[str, Any], db: AsyncSession) -> str:
    """
    Determine response depth based on topic mastery.
    - mastery >= 75% -> concise
    - 50% <= mastery < 75% -> standard
    - mastery < 50% -> scaffolded
    - No data -> standard
    """
    question_lower = question.lower()
    matched_mastery = None
    
    for t in context.get("weak_topics", []):
        if t["topic_tag"].lower().replace("-", " ") in question_lower:
            matched_mastery = t["mastery_percent"]
            break
            
    if matched_mastery is None:
        for t in context.get("strong_topics", []):
            if t["topic_tag"].lower().replace("-", " ") in question_lower:
                matched_mastery = t["mastery_percent"]
                break
                
    if matched_mastery is None:
        stmt = select(TopicMastery).where(TopicMastery.user_id == user_id)
        result = await db.execute(stmt)
        masteries = result.scalars().all()
        for m in masteries:
            if m.topic_tag.lower().replace("-", " ") in question_lower:
                matched_mastery = m.mastery_score
                break
                
    if matched_mastery is None:
        return "standard"
        
    if matched_mastery >= 75:
        return "concise"
    elif matched_mastery >= 50:
        return "standard"
    else:
        return "scaffolded"

def build_adaptive_prompt(
    question: str, 
    context: Dict[str, Any], 
    depth: str,
    session_context: Optional[Dict[str, Any]] = None
) -> str:
    """Build the AI prompt for adaptive tutor with session memory."""
    student = context.get("student", {})
    subjects = [s["title"] for s in context.get("active_subjects", [])]
    weak_topics = [t["topic_tag"] for t in context.get("weak_topics", [])]
    
    subject_list = ", ".join(subjects) if subjects else "None specified"
    weak_topics_str = ", ".join(weak_topics) if weak_topics else "None identified yet"
    
    topic_mastery_str = json.dumps(context.get("weak_topics", []) + context.get("strong_topics", []), indent=2)
    
    # Build session section if available
    session_section = ""
    if session_context and session_context.get("session_available"):
        pinned_prefs = session_context.get("pinned_preferences", {})
        messages = session_context.get("messages", [])
        
        if pinned_prefs:
            session_section += f"\nPinned preferences:\n{json.dumps(pinned_prefs, indent=2)}\n"
            
        if messages:
            session_section += "\nSession messages (chronological):\n"
            for msg in messages:
                session_section += f"{msg}\n"
    
    prompt = f"""System: You are a curriculum-aware Indian law tutor. Use the following session history and pinned preferences to respond.
{session_section}
Context (from curriculum):
- Course: {student.get('course', 'N/A')}
- Semester: {student.get('semester', 'N/A')}
- Active subjects: {subject_list}
- Topic mastery: {topic_mastery_str}
- Weak topics: {weak_topics_str}
- Recent activity: {json.dumps(context.get('recent_activity', {}))}

Student new question: {question}

Constraints:
- Obey curriculum boundaries
- Respect pinned preferences
- Provide compact answer + optionally ask one clarifying question only if required

Response requirements:
1) Provide a single concise answer paragraph (<= 100 words) labeled 'answer'.
2) Provide 'depth' chosen: one of: 'concise'|'standard'|'scaffolded'. (Current determined depth: {depth})
3) If depth == 'scaffolded', include:
   - A 3-step mini-lesson with headings "Step 1 / Step 2 / Step 3".
   - Two worked examples (brief) with clear labels.
4) Always include 1-3 specific study actions (practice questions, modules to review, notes to read) that map to internal content IDs when possible (e.g., module_id:123).
5) Provide 'why_this_help' explaining why the chosen depth suits the student (based on mastery numbers).
6) Provide 'provenance' list: for each claim, include source doc_type and doc_id and a short match score. (Use mock IDs like 101, 102 if unknown).
7) Provide 'confidence_score' in [0.0, 1.0].
8) If question outside syllabus → refuse politely and provide 2 nearest syllabus topics.

Return strictly JSON object (no narrative outside JSON).
"""
    return prompt

async def process_adaptive_chat(
    user_id: int, 
    question: str, 
    mode: str, 
    db: AsyncSession,
    session_id: Optional[str] = None
) -> Dict[str, Any]:
    """Main entry point for adaptive chat processing with session support."""
    # 1. Fetch tutor context
    context = await assemble_context(user_id, db)
    
    # 2. Build session context if session_id provided
    session_context = None
    session_warning = None
    if session_id:
        session_context = await build_session_context(session_id, user_id, db)
        if not session_context.get("session_available"):
            session_warning = session_context.get("warning", "Session history not available")
            session_context = None
    
    # 3. Determine depth
    if mode == "adaptive":
        depth = await determine_depth(user_id, question, context, db)
    else:
        depth = mode if mode in ["concise", "standard", "scaffolded"] else "standard"
        
    # 4. Build prompt with session context
    prompt = build_adaptive_prompt(question, context, depth, session_context)
    
    # 5. Call AI service
    ai_result = await call_gemini_deterministic(prompt, user_id)
    
    if not ai_result.get("success"):
        return {
            "answer": None,
            "error": ai_result.get("error", "AI service unavailable"),
            "fallback": "I'm having trouble connecting. Please review your active modules for guidance.",
            "session_warning": session_warning
        }
        
    try:
        response_json = json.loads(ai_result["text"])
        
        # Add metadata
        response_json["provenance_metadata"] = {
            "prompt_hash": ai_result["prompt_hash"],
            "response_hash": ai_result["response_hash"],
            "latency": ai_result["latency"],
            "model": ai_result["model"]
        }
        
        if session_warning:
            response_json["session_warning"] = session_warning
            
        # Store messages in session if session_id provided
        if session_id and session_context:
            await append_message(session_id, user_id, "student", question, db)
            await append_message(
                session_id, user_id, "assistant", 
                response_json.get("answer", ""),
                db,
                provenance=response_json.get("provenance"),
                confidence_score=response_json.get("confidence_score")
            )
        
        return response_json
    except Exception as e:
        logger.error(f"Failed to parse AI response: {str(e)}")
        return {
            "answer": "Error parsing response",
            "error": "Invalid JSON from AI",
            "fallback": ai_result["text"],
            "session_warning": session_warning
        }

async def get_remediation_pack(user_id: int, topic_tag: str, db: AsyncSession) -> Dict[str, Any]:
    """Get remediation pack for a specific topic."""
    context = await assemble_context(user_id, db)
    question = f"Provide a full remediation pack for the topic: {topic_tag}"
    return await process_adaptive_chat(user_id, question, "scaffolded", db)
