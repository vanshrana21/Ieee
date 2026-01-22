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
    judgment: str = Field("", description="The final operative judgment or decision")
    ratio_decidendi: str = Field("", description="The underlying legal principle or rationale")

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
    # This is conservative to avoid removing important legal references
    # Often found at the top or bottom of pages
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
    
    Args:
        extracted_details: Output from Phase 2 (extract_full_case_details).
        
    Returns:
        A validated dictionary conforming to the CanonicalAIInput schema.
    """
    # Mapping logic from Phase 2 fields to Canonical structure
    # Phase 2 keys: case_name, citation, court, year, facts, issues, arguments, judgment, ratio
    
    # Note: 'arguments' is explicitly OUT OF SCOPE for AI input per Phase 3 rules.
    
    canonical_data = {
        "case_name": extracted_details.get("case_name", ""),
        "citation": extracted_details.get("citation", ""),
        "court": extracted_details.get("court", ""),
        "year": str(extracted_details.get("year", "")),
        "facts": reduce_metadata(extracted_details.get("facts", "")),
        "issues": reduce_metadata(extracted_details.get("issues", "")),
        "judgment": reduce_metadata(extracted_details.get("judgment", "")),
        "ratio_decidendi": reduce_metadata(extracted_details.get("ratio", ""))
    }
    
    # Validation Layer
    try:
        validated_input = CanonicalAIInput(**canonical_data)
        return validated_input.model_dump()
    except ValidationError as e:
        # For Phase 3, we log and re-raise or return empty structure with keys if critical
        # But Pydantic should pass empty strings as valid per our Field defaults.
        raise ValueError(f"AI Input Validation Failed: {e.json()}")

if __name__ == "__main__":
    # Internal test example
    dummy_extracted = {
        "case_name": "Phase 2 Case Title",
        "citation": "2026 INSC 456",
        "court": "Supreme Court",
        "year": "2026",
        "facts": "Headnote: This should be removed.\n\nActual facts are here.",
        "issues": "Whether X is true.",
        "arguments": "This should NOT be in canonical output.",
        "judgment": "Digitally signed by clerk.\n\nThe appeal is dismissed.",
        "ratio": "The principle of X applies."
    }
    
    try:
        canonical = prepare_ai_input(dummy_extracted)
        print("Canonical Mapping Successful")
        print(f"Keys: {list(canonical.keys())}")
        if "arguments" in canonical:
            print("ERROR: Arguments field should not be present!")
        print(f"Sample Facts (Reduced): {canonical['facts']}")
    except Exception as e:
        print(f"Test Failed: {e}")
