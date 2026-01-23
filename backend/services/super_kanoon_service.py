# backend/services/super_kanoon_service.py
"""
TEMPORARY TEST ADAPTER for SooperKanoon API.
Purpose: Verify whether SooperKanoon returns FULL judgment text.

⚠️  TEST ONLY - DO NOT:
    - Store responses in DB
    - Feed to AI
    - Show in UI
    - Replace existing Kanoon logic
"""
import os
import logging
import requests
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)
logging.getLogger(__name__).setLevel(logging.DEBUG)

SOOPER_KANOON_BASE = "https://sooperkanoon.com"


def _get_headers() -> Dict[str, str]:
    """Standard headers for all SooperKanoon requests."""
    guid = os.getenv("SOOPER_KANOON_GUID", "")
    return {
        "HTTP-GUID": guid,
        "Accept": "application/json",
        "User-Agent": "JurisAI/1.0 (IEEE Academic Project)"
    }


def _is_cloudflare_or_html(response: requests.Response) -> bool:
    """Check if response is blocked by Cloudflare or is HTML instead of JSON."""
    content_type = response.headers.get("Content-Type", "")
    if "text/html" in content_type:
        return True
    body_start = response.text[:500].lower()
    if "cloudflare" in body_start or "<!doctype html" in body_start or "<html" in body_start:
        return True
    return False


def _extract_text_field(data: Any) -> Optional[str]:
    """Try to extract judgment text from various possible field names."""
    text_fields = [
        "judgment", "judgement", "full_text", "judgment_text", "judgement_text",
        "text", "content", "body", "doc", "doc_text", "document_text",
        "case_text", "decision_text", "ruling_text"
    ]
    
    if isinstance(data, dict):
        for field in text_fields:
            if field in data and data[field]:
                return str(data[field])
        for key in ["data", "result", "case", "document"]:
            if key in data and isinstance(data[key], dict):
                for field in text_fields:
                    if field in data[key] and data[key][field]:
                        return str(data[key][field])
    return None


def _extract_metadata(data: Any, field_names: list) -> Optional[str]:
    """Extract metadata from response by trying multiple field names."""
    if isinstance(data, dict):
        for field in field_names:
            if field in data and data[field]:
                return str(data[field])
        for key in ["data", "result", "case", "meta"]:
            if key in data and isinstance(data[key], dict):
                for field in field_names:
                    if field in data[key] and data[key][field]:
                        return str(data[key][field])
    return None


def fetch_case_from_sooperkanoon(case_query: str) -> Dict:
    """
    Call SooperKanoon API to search for a case and fetch full judgment.
    
    Steps:
    1. Search: GET https://sooperkanoon.com/cases/search/name:<query>.json
    2. Extract first jid from json.jids[]
    3. Fetch detail: GET https://sooperkanoon.com<jid>
    
    Args:
        case_query: Case name/query (e.g. "Maneka Gandhi v Union of India 1978")
    
    Returns:
        Normalized response object with case data or error info
    """
    print(f"[SooperKanoon] === Starting fetch for: {case_query} ===")
    logger.info(f"[SooperKanoon] === Starting fetch for: {case_query} ===")
    
    result = {
        "case_name": "UNKNOWN",
        "court": None,
        "year": None,
        "has_full_text": False,
        "full_text_length": 0,
        "preview_start": "",
        "source": "sooperkanoon",
        "raw_keys": [],
        "error": None,
        "search_url": None,
        "detail_url": None,
        "search_status": None,
        "detail_status": None,
        "search_content_type": None,
        "search_response_preview": None
    }
    
    guid = os.getenv("SOOPER_KANOON_GUID", "")
    if not guid:
        result["error"] = "SOOPER_KANOON_GUID not set in environment"
        logger.error(f"[SooperKanoon] {result['error']}")
        return result
    
    headers = _get_headers()
    
    try:
        formatted_query = case_query.strip().replace(" ", "-")
        search_url = f"{SOOPER_KANOON_BASE}/cases/search/name:{formatted_query}.json"
        result["search_url"] = search_url
        
        print(f"[SooperKanoon] STEP 1: Calling search URL: {search_url}")
        logger.info(f"[SooperKanoon] STEP 1: Calling search URL: {search_url}")
        search_response = requests.get(search_url, headers=headers, timeout=30)
        result["search_status"] = search_response.status_code
        
        print(f"[SooperKanoon] Search response status: {search_response.status_code}")
        print(f"[SooperKanoon] Search Content-Type: {search_response.headers.get('Content-Type', 'N/A')}")
        print(f"[SooperKanoon] Search response first 500 chars: {search_response.text[:500]}")
        logger.info(f"[SooperKanoon] Search response status: {search_response.status_code}")
        logger.info(f"[SooperKanoon] Search Content-Type: {search_response.headers.get('Content-Type', 'N/A')}")
        logger.info(f"[SooperKanoon] Search response first 500 chars: {search_response.text[:500]}")
        
        result["search_content_type"] = search_response.headers.get('Content-Type', 'N/A')
        result["search_response_preview"] = search_response.text[:500]
        
        if search_response.status_code == 403 or _is_cloudflare_or_html(search_response):
            result["error"] = "Blocked by Cloudflare or authorization layer"
            result["has_full_text"] = False
            logger.warning(f"[SooperKanoon] {result['error']}")
            return result
        
        if search_response.status_code != 200:
            result["error"] = f"Search failed with HTTP {search_response.status_code}"
            logger.error(f"[SooperKanoon] {result['error']}")
            return result
        
        try:
            search_data = search_response.json()
        except Exception as e:
            result["error"] = f"Failed to parse search JSON: {str(e)}"
            logger.error(f"[SooperKanoon] {result['error']}")
            return result
        
        if isinstance(search_data, dict):
            result["raw_keys"] = list(search_data.keys())
        logger.info(f"[SooperKanoon] Search response keys: {result['raw_keys']}")
        
        jids = search_data.get("jids", [])
        if not jids or len(jids) == 0:
            result["error"] = "No jids found in search response"
            logger.warning(f"[SooperKanoon] {result['error']}")
            return result
        
        first_jid = jids[0]
        logger.info(f"[SooperKanoon] STEP 2: Extracted first jid: {first_jid}")
        
        if first_jid.endswith(".json"):
            detail_url = f"{SOOPER_KANOON_BASE}{first_jid}"
        else:
            detail_url = f"{SOOPER_KANOON_BASE}{first_jid}.json"
        result["detail_url"] = detail_url
        
        logger.info(f"[SooperKanoon] STEP 3: Calling detail URL: {detail_url}")
        detail_response = requests.get(detail_url, headers=headers, timeout=30)
        result["detail_status"] = detail_response.status_code
        
        logger.info(f"[SooperKanoon] Detail response status: {detail_response.status_code}")
        logger.info(f"[SooperKanoon] Detail Content-Type: {detail_response.headers.get('Content-Type', 'N/A')}")
        logger.info(f"[SooperKanoon] Detail response first 500 chars: {detail_response.text[:500]}")
        
        if detail_response.status_code == 403 or _is_cloudflare_or_html(detail_response):
            result["error"] = "Blocked by Cloudflare or authorization layer"
            result["has_full_text"] = False
            logger.warning(f"[SooperKanoon] {result['error']}")
            return result
        
        if detail_response.status_code != 200:
            result["error"] = f"Detail fetch failed with HTTP {detail_response.status_code}"
            logger.error(f"[SooperKanoon] {result['error']}")
            return result
        
        try:
            detail_data = detail_response.json()
        except Exception as e:
            result["error"] = f"Failed to parse detail JSON: {str(e)}"
            logger.error(f"[SooperKanoon] {result['error']}")
            return result
        
        if isinstance(detail_data, dict):
            result["raw_keys"] = list(detail_data.keys())
        logger.info(f"[SooperKanoon] Detail response keys: {result['raw_keys']}")
        
        result["case_name"] = _extract_metadata(detail_data, ["title", "case_name", "name", "case_title"]) or "UNKNOWN"
        result["court"] = _extract_metadata(detail_data, ["court", "court_name", "bench"])
        result["year"] = _extract_metadata(detail_data, ["year", "date", "judgment_date", "decision_date"])
        
        full_text = _extract_text_field(detail_data)
        
        if full_text:
            result["has_full_text"] = True
            result["full_text_length"] = len(full_text)
            result["preview_start"] = full_text[:500] if len(full_text) >= 500 else full_text
            logger.info(f"[SooperKanoon] SUCCESS: Found full text with {result['full_text_length']} characters")
            logger.info(f"[SooperKanoon] Preview start: {result['preview_start']}")
        else:
            result["has_full_text"] = False
            result["full_text_length"] = 0
            result["preview_start"] = ""
            logger.warning("[SooperKanoon] No judgment/full_text/doc/text/content field found in detail response")
        
        logger.info(f"[SooperKanoon] === Fetch complete. has_full_text={result['has_full_text']}, length={result['full_text_length']} ===")
        return result
        
    except requests.exceptions.Timeout:
        result["error"] = "Request timed out after 30 seconds"
        logger.error(f"[SooperKanoon] {result['error']}")
        return result
    except requests.exceptions.RequestException as e:
        result["error"] = f"Request failed: {str(e)}"
        logger.error(f"[SooperKanoon] {result['error']}")
        return result
    except Exception as e:
        result["error"] = f"Unexpected error: {str(e)}"
        logger.error(f"[SooperKanoon] {result['error']}")
        return result
