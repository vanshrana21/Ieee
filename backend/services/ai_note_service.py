"""
backend/services/ai_note_service.py
Phase 7: AI-powered note assistance

CRITICAL: Never modifies original notes
"""

import os
import google.generativeai as genai
from typing import Literal
from typing import List

# Configure Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-pro')


async def ai_assist_note(
    content: str,
    action: Literal["summarize", "exam_format", "revision_bullets"]
) -> str:
    """
    Generate AI assistance for a note.
    
    Args:
        content: Original note content
        action: Type of assistance needed
    
    Returns:
        Generated text (does NOT modify original)
    
    Raises:
        RuntimeError: If AI service fails
    """
    
    prompts = {
        "summarize": f"""You are a law student's study assistant. Summarize this legal note concisely (max 150 words):

{content}

Provide a clear, exam-focused summary.""",
        
        "exam_format": f"""You are a law exam preparation expert. Convert this note into a structured exam answer format:

{content}

Format as:
1. Issue
2. Rule
3. Application
4. Conclusion

Be concise and exam-ready.""",
        
        "revision_bullets": f"""You are a law student's revision assistant. Extract key revision points from this note as bullet points (max 5 points):

{content}

Focus on facts, principles, and exam-critical information."""
    }
    
    prompt = prompts.get(action)
    if not prompt:
        raise ValueError(f"Invalid action: {action}")
    
    try:
        response = model.generate_content(prompt)
        
        if not response or not response.text:
            raise RuntimeError("AI service returned empty response")
        
        return response.text.strip()
    
    except Exception as e:
        raise RuntimeError(f"AI assistance failed: {str(e)}")


async def smart_search_notes(query: str, notes_content: List[str]) -> List[int]:
    """
    AI-powered semantic search across notes.
    
    Args:
        query: Search query
        notes_content: List of note contents to search
    
    Returns:
        List of indices of relevant notes (sorted by relevance)
    
    Note: This is a simple implementation. Production should use embeddings.
    """
    # For now, simple keyword matching
    # TODO: Implement vector search with embeddings in Phase 8+
    results = []
    query_lower = query.lower()
    
    for idx, content in enumerate(notes_content):
        if query_lower in content.lower():
            results.append(idx)
    
    return results
