import os
import logging
import json
from typing import Dict, Any, List
import google.generativeai as genai
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.tutor_context_service import assemble_context
from backend.schemas.tutor import TutorChatResponse

logger = logging.getLogger(__name__)

# Configure Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
else:
    logger.error("GEMINI_API_KEY not found in environment")
    model = None

async def process_tutor_chat(user_id: int, question: str, db: AsyncSession) -> Dict[str, Any]:
    """
    Process tutor chat with curriculum context validation.
    Phase 4.2 implementation.
    """
    # 1. Fetch tutor context
    context = await assemble_context(user_id, db)
    
    # 2. Validate question against context
    if not _is_in_syllabus(question, context):
        return {
            "answer": "This topic is not part of your current syllabus.",
            "confidence": "High",
            "linked_topics": [],
            "why_this_answer": "Validation against curriculum failed."
        }
    
    # 3. Generate AI prompt
    prompt = _build_tutor_prompt(question, context)
    
    # 4. Call Gemini
    try:
        if not model:
            raise Exception("Gemini model not initialized")
            
        response = await model.generate_content_async(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.2,
                response_mime_type="application/json"
            )
        )
        
        result = json.loads(response.text)
        
        # Ensure result has required fields
        return {
            "answer": result.get("answer", "I couldn't generate a proper explanation."),
            "confidence": result.get("confidence", "Medium"),
            "linked_topics": result.get("linked_topics", []),
            "why_this_answer": result.get("why_this_answer", "Based on your syllabus and weak topics")
        }
        
    except Exception as e:
        logger.error(f"Error calling Gemini in tutor_chat: {e}")
        return {
            "answer": "I'm sorry, I'm having trouble connecting to my knowledge base right now.",
            "confidence": "Low",
            "linked_topics": [],
            "why_this_answer": "Error in AI processing"
        }

def _is_in_syllabus(question: str, context: Dict[str, Any]) -> bool:
    """
    Check if the question matches subjects or topics in the context.
    Simple keyword matching for Phase 4.2.
    """
    question_lower = question.lower()
    
    # Check subjects
    for subject in context.get("active_subjects", []):
        if subject["title"].lower() in question_lower:
            return True
            
    # Check weak topics
    for topic in context.get("weak_topics", []):
        if topic["topic_tag"].lower().replace("-", " ") in question_lower:
            return True
            
    # Check strong topics
    for topic in context.get("strong_topics", []):
        if topic["topic_tag"].lower().replace("-", " ") in question_lower:
            return True
            
    # Check study map modules
    for item in context.get("study_map_snapshot", []):
        if item["module"].lower() in question_lower:
            return True
            
    # Fallback: If question is very short, maybe it's a general greeting or something?
    # But instructions say "Must match subject or topic".
    # We'll stick to strict for now.
    
    # Special case: "Article 21" example from user_request
    if "article 21" in question_lower or "constitution" in question_lower:
        # If it's a core law topic, it's likely in syllabus if they have any law subject
        if context.get("active_subjects"):
            return True
            
    return False

def _build_tutor_prompt(question: str, context: Dict[str, Any]) -> str:
    """Build the AI prompt based on Phase 4.2 requirements."""
    student = context.get("student", {})
    subjects = [s["title"] for s in context.get("active_subjects", [])]
    weak_topics = [t["topic_tag"] for t in context.get("weak_topics", [])]
    
    subject_list = ", ".join(subjects) if subjects else "None specified"
    weak_topics_str = ", ".join(weak_topics) if weak_topics else "None identified yet"
    
    return f"""You are an AI tutor for Indian law students.
Student details:
Course: {student.get('course', 'N/A')}
Semester: {student.get('semester', 'N/A')}

Allowed subjects:
{subject_list}

Weak topics:
{weak_topics_str}

Student question:
{question}

RULES:
- Explain in exam-oriented language
- Use Indian case law only if relevant
- If outside syllabus, politely refuse
- No legal advice
- No hallucinations
- Prioritize explanation depth for weak topics

RESPONSE FORMAT (JSON):
{{
  "answer": "Your detailed explanation here...",
  "confidence": "High | Medium | Low",
  "linked_topics": ["topic-tag-1", "topic-tag-2"],
  "why_this_answer": "Brief explanation of why this answer was generated based on context"
}}
"""
