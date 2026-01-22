# backend/utils/case_extractor.py
"""
Utility for extracting readable content from raw Kannon API responses.
Phase 2: Readable Full Case Extraction.
"""
import re
from typing import Dict, Any, Optional

def clean_html(text: Optional[str]) -> str:
    """Removes HTML tags and cleans up technical noise while preserving breaks."""
    if not text:
        return ""
    
    # Replace block-level tags (opening and closing) with newlines to preserve structure
    text = re.sub(r'</?(p|div|br|h[1-6]|li|tr|blockquote)[^>]*>', '\n', text, flags=re.IGNORECASE)
    
    # Remove all other remaining HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    
    # Decode common HTML entities (if any)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    
    # Normalize multiple newlines to exactly two for paragraph separation
    text = re.sub(r'\n\s*\n+', '\n\n', text)
    
    return text.strip()

def extract_full_case_details(raw_data: Dict[str, Any]) -> Dict[str, str]:
    """
    Extracts and formats legal sections from raw Kannon response.
    
    Args:
        raw_data: The raw dictionary from Kannon API.
        
    Returns:
        A dictionary with clean, readable legal sections.
    """
    # Extract basic metadata
    case_name = raw_data.get("case_name") or raw_data.get("title") or "Unknown Case Name"
    citation = raw_data.get("citation") or raw_data.get("id") or "N/A"
    court = raw_data.get("court") or raw_data.get("court_name") or raw_data.get("court_id") or "N/A"
    
    # Extract year/date
    filed_at = raw_data.get("filed_at") or raw_data.get("judgment_date") or ""
    year = filed_at[:4] if filed_at else "N/A"

    # Extract legal content sections
    # Kannon often provides these in 'judgment_text' or separate fields
    # We prioritize specific fields if they exist, otherwise try to extract from full text
    
    facts = clean_html(raw_data.get("facts") or "")
    issues = clean_html(raw_data.get("issues") or "")
    arguments = clean_html(raw_data.get("arguments") or raw_data.get("submissions") or "")
    judgment = clean_html(raw_data.get("judgment") or raw_data.get("judgment_text") or raw_data.get("content") or "")
    ratio = clean_html(raw_data.get("ratio") or raw_data.get("ratio_decidendi") or raw_data.get("observations") or "")

    # If the response is a simple one-blob judgment, and sections are empty,
    # we might need to handle it, but per requirements we don't normalize beyond safety yet.
    # We just return what's there.

    return {
        "case_name": case_name,
        "citation": citation,
        "court": court,
        "year": year,
        "facts": facts,
        "issues": issues,
        "arguments": arguments,
        "judgment": judgment,
        "ratio": ratio
    }
