# backend/routes/debug_super_kanoon.py
"""
TEMPORARY DEBUG ENDPOINT for SooperKanoon API verification.

⚠️  TEST ONLY - DO NOT use in production.
"""
import os
import logging
import requests
from fastapi import APIRouter, Query
from backend.services.super_kanoon_service import fetch_case_from_sooperkanoon

router = APIRouter(prefix="/debug", tags=["Debug"])
logger = logging.getLogger(__name__)

SOOPER_KANOON_BASE = "https://sooperkanoon.com"


@router.get("/sooperkanoon-fulltext")
async def test_sooperkanoon_fulltext(
    query: str = Query(..., description="Case name query (e.g. 'kesavananda-bharati')")
):
    """
    End-to-end test of SooperKanoon API for full judgment text availability.
    
    Flow:
    1. Call search API: GET /cases/search/name:{query}.json
    2. Extract first jid from response
    3. Call case detail API: GET /case/{id}.json
    4. Check if judgment_text exists and length > 500
    
    Returns:
    - case_name: Case title
    - has_full_text: true if judgment_text > 500 chars
    - judgment_preview: First 2000 chars of judgment
    - source: "SooperKanoon"
    """
    guid = os.getenv("SOOPER_KANOON_GUID", "")
    if not guid:
        return {
            "case_name": None,
            "has_full_text": False,
            "judgment_preview": None,
            "source": "SooperKanoon",
            "error": "SOOPER_KANOON_GUID not set"
        }
    
    headers = {
        "HTTP-GUID": guid,
        "Accept": "application/json",
        "User-Agent": "JurisAI/1.0"
    }
    
    formatted_query = query.strip().replace(" ", "-").lower()
    search_url = f"{SOOPER_KANOON_BASE}/cases/search/name:{formatted_query}.json"
    
    logger.info(f"[SooperKanoon] STEP 1: Search - GET {search_url}")
    
    try:
        search_resp = requests.get(search_url, headers=headers, timeout=30)
        logger.info(f"[SooperKanoon] Search status: {search_resp.status_code}, length: {len(search_resp.text)}")
        
        if "cloudflare" in search_resp.text.lower() or "just a moment" in search_resp.text.lower():
            return {
                "case_name": None,
                "has_full_text": False,
                "judgment_preview": None,
                "source": "SooperKanoon",
                "error": "Blocked by Cloudflare",
                "_debug": {
                    "search_url": search_url,
                    "search_status": search_resp.status_code,
                    "response_preview": search_resp.text[:500]
                }
            }
        
        if search_resp.status_code != 200:
            return {
                "case_name": None,
                "has_full_text": False,
                "judgment_preview": None,
                "source": "SooperKanoon",
                "error": f"Search failed: HTTP {search_resp.status_code}",
                "_debug": {"search_url": search_url, "response_preview": search_resp.text[:500]}
            }
        
        search_data = search_resp.json()
        jids = search_data.get("jids", [])
        
        if not jids:
            return {
                "case_name": None,
                "has_full_text": False,
                "judgment_preview": None,
                "source": "SooperKanoon",
                "error": "No jids found in search response",
                "_debug": {"search_url": search_url, "response_keys": list(search_data.keys())}
            }
        
        first_jid = jids[0]
        logger.info(f"[SooperKanoon] STEP 2: Found jid: {first_jid}")
        
        if first_jid.endswith(".json"):
            detail_url = f"{SOOPER_KANOON_BASE}{first_jid}"
        else:
            detail_url = f"{SOOPER_KANOON_BASE}{first_jid}.json"
        
        logger.info(f"[SooperKanoon] STEP 3: Detail - GET {detail_url}")
        
        detail_resp = requests.get(detail_url, headers=headers, timeout=30)
        logger.info(f"[SooperKanoon] Detail status: {detail_resp.status_code}, length: {len(detail_resp.text)}")
        
        if "cloudflare" in detail_resp.text.lower() or "just a moment" in detail_resp.text.lower():
            return {
                "case_name": None,
                "has_full_text": False,
                "judgment_preview": None,
                "source": "SooperKanoon",
                "error": "Blocked by Cloudflare on detail fetch",
                "_debug": {"detail_url": detail_url, "detail_status": detail_resp.status_code}
            }
        
        if detail_resp.status_code != 200:
            return {
                "case_name": None,
                "has_full_text": False,
                "judgment_preview": None,
                "source": "SooperKanoon",
                "error": f"Detail fetch failed: HTTP {detail_resp.status_code}",
                "_debug": {"detail_url": detail_url, "response_preview": detail_resp.text[:500]}
            }
        
        detail_data = detail_resp.json()
        
        case_name = (
            detail_data.get("title") or 
            detail_data.get("case_name") or 
            detail_data.get("name") or 
            "Unknown"
        )
        
        judgment_text = (
            detail_data.get("judgment_text") or 
            detail_data.get("judgment") or 
            detail_data.get("content") or 
            detail_data.get("full_text") or 
            detail_data.get("text") or 
            ""
        )
        
        has_full_text = len(judgment_text) > 500
        judgment_preview = judgment_text[:2000] if judgment_text else None
        
        logger.info(f"[SooperKanoon] STEP 4: has_full_text={has_full_text}, text_length={len(judgment_text)}")
        
        return {
            "case_name": case_name,
            "has_full_text": has_full_text,
            "judgment_preview": judgment_preview,
            "source": "SooperKanoon",
            "_debug": {
                "search_url": search_url,
                "detail_url": detail_url,
                "jid": first_jid,
                "search_status": search_resp.status_code,
                "detail_status": detail_resp.status_code,
                "text_length": len(judgment_text),
                "response_keys": list(detail_data.keys())
            }
        }
        
    except requests.exceptions.Timeout:
        return {
            "case_name": None,
            "has_full_text": False,
            "judgment_preview": None,
            "source": "SooperKanoon",
            "error": "Request timed out"
        }
    except Exception as e:
        logger.error(f"[SooperKanoon] Error: {e}")
        return {
            "case_name": None,
            "has_full_text": False,
            "judgment_preview": None,
            "source": "SooperKanoon",
            "error": str(e)
        }


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
