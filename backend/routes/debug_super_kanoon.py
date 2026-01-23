# backend/routes/debug_super_kanoon.py
"""
TEMPORARY DEBUG ENDPOINT for Super Kanoon API verification.

⚠️  TEST ONLY - DO NOT use in production.
"""
from fastapi import APIRouter, Query
from backend.services.super_kanoon_service import fetch_full_judgment

router = APIRouter(prefix="/debug", tags=["Debug"])


@router.get("/super-kanoon-test")
async def test_super_kanoon(
    query: str = Query(..., description="Case query (e.g. 'Maneka Gandhi v Union of India 1978')")
):
    """
    Test Super Kanoon API to verify if it returns full judgment text.
    
    Returns verification results including:
    - length: Character count of judgment text
    - has_full_text: Boolean indicating if text appears to be full judgment
    - verdict: NOT_FULL_TEXT (<5k) | PARTIAL (5k-15k) | LIKELY_FULL (20k+)
    - source: Court/citation metadata if available
    - preview_start: First 500 characters
    - preview_end: Last 500 characters
    """
    result = fetch_full_judgment(query)
    
    safe_result = {
        "query": result["query"],
        "api_called": result["api_called"],
        "raw_response_keys": result["raw_response_keys"],
        "length": result["length"],
        "has_full_text": result["has_full_text"],
        "verdict": result["verdict"],
        "source": result["source"],
        "preview_start": result["preview_start"],
        "preview_end": result["preview_end"],
        "error": result["error"]
    }
    
    return safe_result
