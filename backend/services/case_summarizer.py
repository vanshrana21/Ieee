# backend/services/case_summarizer.py
"""
AI Structured Summary Generation for Case Simplifier.
Phase 4: AI Structured Summary Generation.
"""
import json
import logging
import os
from typing import Dict, Any, Optional

import google.generativeai as genai
from pydantic import ValidationError

from backend.utils.ai_preparer import CanonicalAIInput

logger = logging.getLogger(__name__)

# Configure Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-1.5-flash")
else:
    logger.error("GEMINI_API_KEY not set")
    model = None

SYSTEM_PROMPT = """You are an expert law student assistant specializing in legal case summarization for exams.
Your task is to summarize the provided legal case into a strict structured format.

STRICT RULES:
1. Use ONLY the information provided in the input. DO NOT add external legal knowledge or facts.
2. DO NOT reinterpret or speculate on the judgment.
3. Use concise, exam-ready language suitable for revision.
4. Maintain the exact JSON structure provided.
5. If a field lacks data in the input, return an empty string (""), do not make assumptions.
6. Rephrase and condense, but do not omit essential legal points.
7. Return ONLY valid JSON. No preamble, no postamble.

LOCKED OUTPUT FORMAT:
{
  "case_name": "...",
  "citation": "...",
  "court": "...",
  "year": "...",
  "facts": "...",
  "issues": "...",
  "judgment": "...",
  "ratio_decidendi": "..."
}"""

async def summarize_case(canonical_input: Dict[str, Any], retry: bool = True) -> Optional[Dict[str, Any]]:
    """
    Generates a structured AI summary of a legal case using the canonical input.
    
    Args:
        canonical_input: The validated canonical structure from Phase 3.
        retry: Whether to retry once on failure.
        
    Returns:
        A validated dictionary conforming to the CanonicalAIInput schema, or None if failed.
    """
    if not model:
        logger.error("AI service unavailable: Gemini API key not set.")
        return None

    try:
        user_prompt = f"Summarize this case following the strict rules:\n\n{json.dumps(canonical_input, indent=2)}"
        
        logger.info(f"Requesting AI summary for case: {canonical_input.get('case_name')}")
        
        response = await model.generate_content_async(
            contents=[
                {"role": "user", "parts": [SYSTEM_PROMPT]},
                {"role": "user", "parts": [user_prompt]}
            ],
            generation_config=genai.types.GenerationConfig(
                response_mime_type="application/json",
            )
        )
        
        if not response or not response.text:
            raise ValueError("Empty response from AI service")

        # Clean response text in case AI added markdown blocks
        clean_text = response.text.strip()
        if clean_text.startswith("```json"):
            clean_text = clean_text[7:]
        if clean_text.endswith("```"):
            clean_text = clean_text[:-3]
        clean_text = clean_text.strip()

        summary_data = json.loads(clean_text)
        
        # Validation Layer
        try:
            validated_summary = CanonicalAIInput(**summary_data)
            logger.info("AI summary validated successfully.")
            return validated_summary.model_dump()
        except ValidationError as e:
            logger.error(f"AI summary validation failed: {e}")
            if retry:
                logger.info("Retrying AI summary generation...")
                return await summarize_case(canonical_input, retry=False)
            return None

    except Exception as e:
        logger.error(f"Error in summarize_case: {str(e)}")
        if retry:
            logger.info("Retrying AI summary generation...")
            return await summarize_case(canonical_input, retry=False)
        return None

async def get_case_simplification(case_id: str) -> Dict[str, Any]:
    """
    Complete Case Simplification Flow:
    Phase 1: Fetch raw data
    Phase 2: Extract full case detail
    Phase 3: Prepare canonical AI input
    Phase 4: Generate AI structured summary
    
    Failure Safety: Returns full case detail if AI fails.
    """
    from backend.services.kannon_service import fetch_case_from_kannon
    from backend.utils.case_extractor import extract_full_case_details
    from backend.utils.ai_preparer import prepare_ai_input

    try:
        # Phase 1: Fetch
        raw_data = fetch_case_from_kannon(case_id)
        
        # Phase 2: Extract
        full_detail = extract_full_case_details(raw_data)
        
        # Phase 3: Prepare AI Input
        canonical_input = prepare_ai_input(full_detail)
        
        # Phase 4: Generate AI Summary
        ai_summary = await summarize_case(canonical_input)
        
        return {
            "success": True,
            "full_case_detail": full_detail,
            "ai_summary": ai_summary,
            "is_simplified": ai_summary is not None
        }

    except Exception as e:
        logger.error(f"Failed to simplify case {case_id}: {str(e)}")
        raise
