# backend/utils/ai_preparer.py
"""
Utility for preparing a strict, canonical AI input structure.
Phase 3: Canonical AI Input Structure.
"""
import re
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, ValidationError

class CanonicalAIInput(BaseModel):
    """
    Strict canonical schema for AI input.
    Ensures a consistent structure for Phase 4 summarization.
    """
    case_name: str = Field("", description="The authoritative name of the case")
    citation: str = Field("", description="Legal citation for the case")
    court: str = Field("", description="The court or bench that delivered the judgment")
    year: str = Field("", description="The year of the judgment")
    facts: str = Field("", description="The authoritative full facts of the case")
    issues: str = Field("", description="The core legal issues identified in the case")
    arguments: str = Field("", description="Main contentions from both sides")
    judgment: str = Field("", description="The final operative judgment or decision")
    ratio_decidendi: str = Field("", description="The underlying legal principle or rationale")
    exam_importance: str = Field("", description="Why this case is important for exams/academics")

def reduce_metadata(text: str) -> str:
    """
    Removes headnotes, repeated citations, and procedural metadata from legal text.
    Does NOT paraphrase or reword legal content.
    """
    if not text:
        return ""
    
    # Remove common headnote markers (e.g., "Held:", "Cases Cited:", "Headnote:", etc.)
    # Note: We use multiline flag to handle these at start of lines
    text = re.sub(r'^(Headnote|Cases Cited|Held|Advocates|Appearances):.*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
    
    # Remove repeated citations in brackets (e.g., [2026] 1 SC 123)
    text = re.sub(r'\[\d{4}\]\s+[A-Z\s]+\d+', '', text)
    
    # Remove procedural metadata like "Page 1 of 50", "Digitally signed by...", "Order dated..."
    text = re.sub(r'Page \d+ of \d+', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Digitally signed( by)?.*', '', text, flags=re.IGNORECASE)
    
    # Normalize whitespace left by removals
    text = re.sub(r'\n\s*\n+', '\n\n', text)
    
    return text.strip()

def prepare_ai_input(extracted_details: Dict[str, str]) -> Dict[str, Any]:
    """
    Maps Phase 2 extracted details into the Phase 3 canonical AI input structure.
    """
    canonical_data = {
        "case_name": extracted_details.get("case_name", ""),
        "citation": extracted_details.get("citation", ""),
        "court": extracted_details.get("court", ""),
        "year": str(extracted_details.get("year", "")),
        "facts": reduce_metadata(extracted_details.get("facts", "")),
        "issues": reduce_metadata(extracted_details.get("issues", "")),
        "arguments": reduce_metadata(extracted_details.get("arguments", "")),
        "judgment": reduce_metadata(extracted_details.get("judgment", "")),
        "ratio_decidendi": reduce_metadata(extracted_details.get("ratio", "")),
        "exam_importance": ""  # Initially empty, to be filled by AI
    }
    
    # Validation Layer
    try:
        validated_input = CanonicalAIInput(**canonical_data)
        return validated_input.model_dump()
    except ValidationError as e:
        raise ValueError(f"AI Input Validation Failed: {e.json()}")
