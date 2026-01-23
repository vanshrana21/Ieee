# backend/routes/debug_super_kanoon.py
"""
TEMPORARY DEBUG ENDPOINT for SooperKanoon API verification.

⚠️  TEST ONLY - DO NOT use in production.
"""
from fastapi import APIRouter, Query
from backend.services.super_kanoon_service import fetch_case_from_sooperkanoon

router = APIRouter(prefix="/debug", tags=["Debug"])


@router.get("/sooperkanoon-test")
async def test_sooperkanoon(
    query: str = Query(..., description="Case query (e.g. 'Maneka Gandhi v Union of India 1978')")
):
    """
    Test SooperKanoon API to verify if it returns full judgment text.
    
    Returns normalized response:
    - case_name: Case title or UNKNOWN
    - court: Court name or null
    - year: Year or null
    - has_full_text: true/false
    - full_text_length: Character count
    - preview_start: First 500 characters
    - source: "sooperkanoon"
    - raw_keys: Top-level JSON keys from response
    - error: Error message if any
    """
    result = fetch_case_from_sooperkanoon(query)
    
    return {
        "case_name": result["case_name"],
        "court": result["court"],
        "year": result["year"],
        "has_full_text": result["has_full_text"],
        "full_text_length": result["full_text_length"],
        "preview_start": result["preview_start"],
        "source": result["source"],
        "raw_keys": result["raw_keys"],
        "error": result["error"],
        "_debug": {
            "search_url": result.get("search_url"),
            "detail_url": result.get("detail_url"),
            "search_status": result.get("search_status"),
            "detail_status": result.get("detail_status"),
            "search_content_type": result.get("search_content_type"),
            "search_response_preview": result.get("search_response_preview")
        }
    }
