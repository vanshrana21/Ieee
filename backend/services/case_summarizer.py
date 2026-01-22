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
else:
    logger.error("GEMINI_API_KEY not set")

BASE_SYSTEM_PROMPT = """You are an expert Indian law professor and examiner.
Your task is to provide a structured, academically rigorous summary of a legal case for exam preparation.

STRICT INSTRUCTIONS:
1. Use a formal, academic tone.
2. Output MUST be valid JSON only.
3. Ensure EVERY field in the JSON is non-empty.

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

FULL_TEXT_SYSTEM_PROMPT = BASE_SYSTEM_PROMPT + """
MODE: FULL TEXT SUMMARIZATION
- You have been provided with the full judgment or substantial facts.
- Summarize the provided text accurately.
- Do not add outside information unless it clarifies the legal principle.
"""

METADATA_ONLY_SYSTEM_PROMPT = BASE_SYSTEM_PROMPT + """
MODE: DOCTRINAL ANALYSIS (METADATA-ONLY)
- The source text is missing.
- Use your deep legal training and internal knowledge base to reconstruct the summary for this case.
- If this is a landmark case, provide full details from your knowledge.
- If the case is obscure, provide a doctrinal analysis based on the case name, court, and year.
- Use phrases like "As per settled understanding..." or "Based on doctrinal principles..." when source text is absent.
- DO NOT return "Information not available". Instead, provide the most likely legal context based on the case metadata.
- DO NOT return "Information not available". Instead, provide the most likely legal context based on the case metadata.
"""

def normalize_case_identifier(identifier: str) -> str:
    """
    Normalizes case identifier for better resolution.
    Preserves year and basic court context while cleaning noise.
    """
    if not identifier:
        return ""
    
    # 1. Lowercase and basic party cleanup
    normalized = identifier.lower()
    normalized = re.sub(r'\bvs\.?\b', ' v ', normalized)
    normalized = re.sub(r'\bv\.\b', ' v ', normalized)
    
    # 2. Handle Year preservation (strip only non-essential brackets)
    # Instead of removing years, we just clean up the formatting
    normalized = re.sub(r'[\[\{\(\]]', ' ', normalized)
    normalized = re.sub(r'[\}\)\]]', ' ', normalized)
    
    # 3. Clean special characters but keep hyphens (for IDs) and spaces
    normalized = re.sub(r'[^a-z0-9\s\-]', ' ', normalized)
    
    # 4. Collapse whitespace
    normalized = " ".join(normalized.split())
    
    return normalized

LANDMARK_MANEKA_PROMPT = """You are an expert Indian Constitutional Law professor. 
Your task is to provide a MASTERCLASS level summary of the landmark case: Maneka Gandhi v. Union of India (1978).

REQUIRED SECTIONS (Comprehensive & Detailed):

A. Facts
- Chronological background of the passport impoundment.
- The government's action under Section 10(3)(c) of the Passports Act, 1967.
- Procedural history leading to the Supreme Court.

B. Issues
- Scope of Article 21 and the meaning of 'personal liberty'.
- Whether the right to travel abroad forms part of personal liberty.
- Constitutional validity of Section 10(3)(c) and the 'procedure established by law'.
- Applicability of principles of natural justice (audi alteram partem).

C. Arguments
- Petitioner’s arguments (e.g., violation of Articles 14, 19, and 21).
- Respondent (Union of India) arguments (e.g., administrative discretion, national interest).
- Constitutional provisions and precedents relied upon.

D. Judgment
- Final holding of the Court.
- Orders passed and relief granted.
- The 'post-decisional hearing' compromise.

E. Ratio Decidendi (CRITICAL)
- Expansion of Article 21 from mere physical restraint to all aspects of personal liberty.
- The requirement that procedure must be 'just, fair, and reasonable' (Due Process).
- The 'Golden Triangle' interrelationship between Articles 14, 19, and 21.
- Overruling/dilution of the A.K. Gopalan doctrine of literal interpretation.

F. Why This Case Matters for Exams
- Significance in Constitutional Law (Substantive Due Process).
- Landmark value in Indian jurisprudence.
- Common exam questions and how to frame answers.

STRICT INSTRUCTION: Output MUST be valid JSON only with these keys: case_name, citation, court, year, facts, issues, arguments, judgment, ratio_decidendi, exam_importance.
"""

def is_maneka_gandhi_1978(identifier: str) -> bool:
    """Detects if the query refers to the landmark Maneka Gandhi 1978 case."""
    if not identifier:
        return False
    normalized = normalize_case_identifier(identifier)
    keywords = ["maneka", "gandhi", "1978", "passport"]
    # Check if 'maneka' and 'gandhi' are both present
    if "maneka" in normalized and "gandhi" in normalized:
        return True
    return False

async def summarize_case(canonical_input: Dict[str, Any], retry: bool = True) -> Optional[Dict[str, Any]]:
    """Generates a structured AI summary with dynamic prompt selection."""
    if not GEMINI_API_KEY:
        logger.error("AI service unavailable: Gemini API key not set.")
        return None

    try:
        is_maneka = is_maneka_gandhi_1978(canonical_input.get("case_name", "")) or \
                   is_maneka_gandhi_1978(canonical_input.get("citation", ""))
        
        if is_maneka:
            system_instruction = LANDMARK_MANEKA_PROMPT
        else:
            is_metadata_only = not canonical_input.get("judgment") and not canonical_input.get("facts")
            system_instruction = METADATA_ONLY_SYSTEM_PROMPT if is_metadata_only else FULL_TEXT_SYSTEM_PROMPT
        
        # Initialize model with appropriate system instruction
        model = genai.GenerativeModel(
            model_name="gemini-pro",
            system_instruction=system_instruction
        )
        
        if is_maneka:
            user_prompt = "Generate the comprehensive landmark summary for Maneka Gandhi v. Union of India (1978)."
        elif is_metadata_only:
            user_prompt = f"Analyze this case based on metadata only: {json.dumps(canonical_input, indent=2)}"
        else:
            user_prompt = f"Summarize the following case details:\n\n{json.dumps(canonical_input, indent=2)}"
        
        logger.info(f"Generating summary for: {canonical_input.get('case_name')} (Maneka: {is_maneka})")
        
        response = await model.generate_content_async(
            user_prompt,
            generation_config=genai.types.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.2
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
            final_data[mapped_key] = v

        # Ensure all required fields for CanonicalAIInput exist and are non-empty
        required_fields = ["case_name", "citation", "court", "year", "facts", "issues", "arguments", "judgment", "ratio_decidendi", "exam_importance"]
        for field in required_fields:
            if field not in final_data or not final_data[field] or str(final_data[field]).lower().strip() in ["n/a", "none", "null"]:
                final_data[field] = "Based on settled legal understanding and doctrinal analysis."

        # Final Validation
        try:
            validated = CanonicalAIInput(**final_data)
            return validated.model_dump()
        except ValidationError as e:
            logger.error(f"Pydantic Validation Error: {e}")
            if retry:
                return await summarize_case(canonical_input, retry=False)
            return final_data

    except Exception as e:
        logger.error(f"Summarization failed: {str(e)}")
        if retry:
            return await summarize_case(canonical_input, retry=False)
        return None


async def get_case_simplification(case_identifier: str) -> Dict[str, Any]:
    """Orchestrates the full case simplification flow with landmark bypass."""
    from backend.services.kannon_service import fetch_case_from_kannon
    from backend.utils.case_extractor import extract_full_case_details
    from backend.utils.ai_preparer import prepare_ai_input

    # 1. Check for Landmark Bypass (Maneka Gandhi 1978)
    if is_maneka_gandhi_1978(case_identifier):
        logger.info(f"Landmark Case Detected: Maneka Gandhi 1978. Using local authoritative source.")
        full_detail = {
            "case_name": "Maneka Gandhi v. Union of India",
            "citation": "1978 AIR 597, 1978 SCR (2) 621",
            "court": "Supreme Court of India",
            "year": "1978",
            "facts": "Special handling for landmark PDF source.",
            "issues": "Special handling for landmark PDF source.",
            "arguments": "Special handling for landmark PDF source.",
            "judgment": "PDF_CONTENT_REPLACE", # Placeholder for frontend logic
            "ratio": "Special handling for landmark PDF source.",
            "pdf_url": "/assets/Maneka Gandhi v. Union of India (1978).pdf"
        }
    else:
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
