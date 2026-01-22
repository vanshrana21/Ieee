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
    # Using gemini-1.5-flash as the primary model
    model = genai.GenerativeModel("gemini-1.5-flash")
else:
    logger.error("GEMINI_API_KEY not set")
    model = None

SYSTEM_PROMPT = """You are an expert Indian law professor and examiner.
Your task is to provide a structured, academically rigorous summary of a legal case for exam preparation.

STRICT INSTRUCTIONS:
1. If full judgment text is provided, summarize it accurately.
2. If only metadata (title, court, citation) is provided, use your deep legal training to reconstruct the summary for this landmark case.
3. Use a formal, academic tone.
4. DO NOT HALLUCINATE facts for unknown cases. If a case is not a well-known landmark and no text is provided, use "Information not available from authoritative source".
5. For landmark cases with missing text, use phrases like "As per settled understanding..." to provide the facts and ratio.
6. Ensure EVERY field in the JSON is non-empty. Use "Based on settled legal understanding" as a filler if necessary.
7. Output MUST be valid JSON only.

REQUIRED JSON STRUCTURE:
{
  "case_name": "Full authoritative name",
  "citation": "Official citation",
  "court": "Court name and bench",
  "year": "Year of judgment",
  "facts": "Concise factual background",
  "issues": "Core legal issues/questions of law",
  "arguments": "Key contentions from Petitioner and Respondent",
  "judgment": "Final decision and operative order",
  "ratio": "The underlying legal principle (Ratio Decidendi)",
  "exam_importance": "Why this case is a must-read for law exams"
}"""

METADATA_ONLY_PROMPT = """THE SOURCE TEXT IS MISSING.
Analyze this case based on your legal knowledge.

Case Metadata:
{metadata_json}

Provide a doctrinal analysis. If this is a landmark case (e.g., Kesavananda Bharati, Maneka Gandhi, etc.), provide full details from your knowledge base.
"""

def normalize_case_identifier(identifier: str) -> str:
    """Normalizes case identifier for better resolution."""
    if not identifier:
        return ""
    normalized = identifier.lower()
    normalized = re.sub(r'\bvs\.?\b', 'v', normalized)
    normalized = re.sub(r'\bv\.\b', 'v', normalized)
    normalized = re.sub(r'[\(\[\{]\d{4}[\)\]\}]', ' ', normalized)
    normalized = re.sub(r'\b\d{4}\b', ' ', normalized)
    normalized = re.sub(r'[\[\]\(\),]', ' ', normalized)
    normalized = re.sub(r'[^a-z0-9\s\-]', '', normalized)
    normalized = " ".join(normalized.split())
    return normalized

async def summarize_case(canonical_input: Dict[str, Any], retry: bool = True) -> Optional[Dict[str, Any]]:
    """Generates a structured AI summary with strict validation."""
    if not model:
        logger.error("AI service unavailable: Gemini API key not set.")
        return None

    try:
        is_metadata_only = not canonical_input.get("judgment") and not canonical_input.get("facts")
        
        if is_metadata_only:
            user_prompt = METADATA_ONLY_PROMPT.format(metadata_json=json.dumps(canonical_input, indent=2))
        else:
            user_prompt = f"Summarize the following case details:\n\n{json.dumps(canonical_input, indent=2)}"
        
        logger.info(f"Generating summary for: {canonical_input.get('case_name')} (Metadata only: {is_metadata_only})")
        
        response = await model.generate_content_async(
            contents=[
                {"role": "user", "parts": [SYSTEM_PROMPT]},
                {"role": "user", "parts": [user_prompt]}
            ],
            generation_config=genai.types.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.2 # Lower temperature for more factual legal output
            )
        )
        
        if not response or not response.text:
            raise ValueError("Empty response from Gemini")

        summary_data = json.loads(response.text.strip())
        
        # Map fields to match CanonicalAIInput if AI used different keys
        field_mapping = {
            "ratio": "ratio_decidendi",
            "ratio_decidendi": "ratio_decidendi",
            "importance": "exam_importance",
            "exam_importance": "exam_importance"
        }
        
        final_data = {}
        for k, v in summary_data.items():
            mapped_key = field_mapping.get(k, k)
            final_data[mapped_key] = v or "Information not available from authoritative source"

        # Ensure all required fields for CanonicalAIInput exist
        required_fields = ["case_name", "citation", "court", "year", "facts", "issues", "arguments", "judgment", "ratio_decidendi", "exam_importance"]
        for field in required_fields:
            if field not in final_data or not final_data[field]:
                final_data[field] = "Based on settled legal understanding"

        # Final Validation
        try:
            validated = CanonicalAIInput(**final_data)
            return validated.model_dump()
        except ValidationError as e:
            logger.error(f"Pydantic Validation Error: {e}")
            if retry:
                return await summarize_case(canonical_input, retry=False)
            return final_data # Return raw mapped data as last resort

    except Exception as e:
        logger.error(f"Summarization failed: {str(e)}")
        if retry:
            return await summarize_case(canonical_input, retry=False)
        return None

async def get_case_simplification(case_identifier: str) -> Dict[str, Any]:
    """Orchestrates the full case simplification flow."""
    from backend.services.kannon_service import fetch_case_from_kannon
    from backend.utils.case_extractor import extract_full_case_details
    from backend.utils.ai_preparer import prepare_ai_input

    # 1. Fetch
    normalized_id = normalize_case_identifier(case_identifier)
    try:
        raw_data = fetch_case_from_kannon(normalized_id)
    except Exception:
        try:
            raw_data = fetch_case_from_kannon(case_identifier)
        except Exception:
            # Create a minimal skeleton if fetch fails entirely
            raw_data = {"case_name": case_identifier, "title": case_identifier}

    # 2. Extract
    inner_data = raw_data.get("data", raw_data)
    full_detail = extract_full_case_details(inner_data)
    
    # 3. Prepare
    canonical_input = prepare_ai_input(full_detail)
    
    # 4. Summarize
    ai_summary = await summarize_case(canonical_input)
    
    # 5. Strict Fallback if AI fails
    if not ai_summary:
        ai_summary = {
            "case_name": full_detail.get("case_name", "Unknown Case"),
            "citation": full_detail.get("citation", "N/A"),
            "court": full_detail.get("court", "N/A"),
            "year": full_detail.get("year", "N/A"),
            "facts": "Information not available from authoritative source.",
            "issues": "Information not available from authoritative source.",
            "arguments": "Information not available from authoritative source.",
            "judgment": "Information not available from authoritative source.",
            "ratio_decidendi": "Information not available from authoritative source.",
            "exam_importance": "Information not available from authoritative source."
        }
    
    return {
        "raw_case": full_detail,
        "ai_structured_summary": ai_summary
    }
