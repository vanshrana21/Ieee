# backend/services/case_summarizer.py
"""
AI Structured Summary Generation for Case Simplifier.
Phase 4: AI Structured Summary Generation.
"""
import json
import logging
import os
import re
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
1. Use the information provided in the input. 
2. If the judgment text is missing or minimal, use your extensive legal knowledge to summarize this landmark case based on known jurisprudence.
3. DO NOT hallucinate facts. If facts are uncertain or missing from the source, say "As per settled understanding..." or "Information not available from authoritative source".
4. Use concise, exam-ready language suitable for revision.
5. Maintain the exact JSON structure provided.
6. If a field lacks data and cannot be inferred from legal knowledge, return "Not available from authoritative source".
7. Rephrase and condense, but do not omit essential legal points.
8. Return ONLY valid JSON. No preamble, no postamble.

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

METADATA_ONLY_PROMPT = """The authoritative judgment text for this case is missing. 
Summarize this landmark Indian case based on known legal jurisprudence and your training data.
Focus on the core facts, legal issues, and the final decision/ratio as understood in Indian law.
If you are unsure of specific details, use phrases like 'Based on settled legal understanding...'
Do NOT invent citations or dates if not provided.

Case Metadata:
{metadata_json}
"""

def normalize_case_identifier(identifier: str) -> str:
    """
    Normalizes case identifier for better resolution.
    - Lowercases input
    - Normalizes 'vs', 'vs.', 'v.' -> 'v'
    - Removes year (1978)
    - Removes brackets, commas, extra symbols
    - Trims whitespace
    """
    if not identifier:
        return ""
    
    # Lowercase
    normalized = identifier.lower()
    
    # Normalize vs/v. to v
    normalized = re.sub(r'\bvs\.?\b', 'v', normalized)
    normalized = re.sub(r'\bv\.\b', 'v', normalized)
    
    # Remove year patterns like (1978), [1978], 1978
    normalized = re.sub(r'[\(\[\{]\d{4}[\)\]\}]', ' ', normalized)
    normalized = re.sub(r'\b\d{4}\b', ' ', normalized)
    
    # Remove brackets, commas, extra symbols
    # Keep alphanumeric, spaces, and hyphens (for IDs)
    normalized = re.sub(r'[\[\]\(\),]', ' ', normalized)
    normalized = re.sub(r'[^a-z0-9\s\-]', '', normalized)
    
    # Trim whitespace and normalize internal spaces
    normalized = " ".join(normalized.split())
    
    return normalized

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
        # Check if judgment/facts are missing to use special metadata-only prompt
        is_metadata_only = not canonical_input.get("judgment") and not canonical_input.get("facts")
        
        if is_metadata_only:
            user_prompt = METADATA_ONLY_PROMPT.format(metadata_json=json.dumps(canonical_input, indent=2))
        else:
            user_prompt = f"Summarize this case following the strict rules:\n\n{json.dumps(canonical_input, indent=2)}"
        
        logger.info(f"Requesting AI summary for case: {canonical_input.get('case_name')} (Metadata only: {is_metadata_only})")
        
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
            # Handle potential mismatch in key name: AI might return ratio instead of ratio_decidendi
            if "ratio" in summary_data and "ratio_decidendi" not in summary_data:
                summary_data["ratio_decidendi"] = summary_data.pop("ratio")
            
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

async def get_case_simplification(case_identifier: str) -> Dict[str, Any]:
    """
    Complete Case Simplification Flow:
    Returns format:
    {
      "raw_case": { ... },
      "ai_structured_summary": { ... }
    }
    """
    from backend.services.kannon_service import fetch_case_from_kannon
    from backend.utils.case_extractor import extract_full_case_details
    from backend.utils.ai_preparer import prepare_ai_input

    # Normalize input
    normalized_id = normalize_case_identifier(case_identifier)
    logger.info(f"Normalized identifier: {normalized_id}")

    # Phase 1: Fetch
    try:
        raw_data = fetch_case_from_kannon(normalized_id)
    except Exception as e:
        # If normalization was too aggressive, try original identifier as fallback
        logger.info(f"Normalization failed for {normalized_id}, trying original: {case_identifier}")
        try:
            raw_data = fetch_case_from_kannon(case_identifier)
        except Exception:
            raise ValueError(f"Case not found: {case_identifier}")
    
    # Phase 2: Extract
    # fetch_case_from_kannon returns {"data": {...}}
    inner_data = raw_data.get("data", raw_data)
    full_detail = extract_full_case_details(inner_data)
    
    # Phase 3: Prepare AI Input
    canonical_input = prepare_ai_input(full_detail)
    
    # Phase 4: Generate AI Summary
    # Always return a structured summary, even if it's a fallback
    ai_summary = None
    try:
        ai_summary = await summarize_case(canonical_input)
    except Exception as ai_err:
        logger.error(f"AI summarization failed: {str(ai_err)}")
    
    # Final Response Contract Enforcement (STRICT)
    if not ai_summary:
        ai_summary = {
            "case_name": full_detail.get("case_name", "Unknown Case"),
            "citation": full_detail.get("citation", ""),
            "court": full_detail.get("court", ""),
            "year": str(full_detail.get("year", "")),
            "facts": "Information not available from authoritative source.",
            "issues": "Information not available from authoritative source.",
            "judgment": "Information not available from authoritative source.",
            "ratio_decidendi": "Information not available from authoritative source."
        }
    
    return {
        "raw_case": full_detail,
        "ai_structured_summary": ai_summary
    }
