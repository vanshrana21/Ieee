# backend/services/super_kanoon_service.py
"""
SooperKanoon API Integration Service.

Purpose: Verify whether SooperKanoon returns FULL judgment text.

Status: API BLOCKED by Cloudflare JS Challenge (403)
"""
import os
import logging
import requests
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

SOOPER_KANOON_BASE = "https://sooperkanoon.com"


def _get_headers() -> Dict[str, str]:
    """Standard headers for all SooperKanoon requests."""
    guid = os.getenv("SOOPER_KANOON_GUID", "")
    return {
        "HTTP-GUID": guid,
        "Accept": "application/json",
        "User-Agent": "JurisAI/1.0 (IEEE Academic Project)"
    }


def _is_cloudflare_blocked(response: requests.Response) -> bool:
    """Check if response is blocked by Cloudflare."""
    content_type = response.headers.get("Content-Type", "")
    if "text/html" in content_type:
        body_lower = response.text[:1000].lower()
        if "cloudflare" in body_lower or "just a moment" in body_lower or "enable javascript" in body_lower:
            return True
    return response.status_code == 403


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
                val = data[field]
                if isinstance(val, str) and len(val) > 100:
                    return val
        for key in ["data", "result", "case", "document"]:
            if key in data and isinstance(data[key], dict):
                for field in text_fields:
                    if field in data[key] and data[key][field]:
                        val = data[key][field]
                        if isinstance(val, str) and len(val) > 100:
                            return val
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
        case_query: Case name/query (e.g. "kesavananda-bharati")
    
    Returns:
        Normalized response object with case data or error info
    """
    print(f"[SooperKanoon] === Starting fetch for: {case_query} ===")
    
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
        "search_response_preview": None,
        "jids_found": []
    }
    
    guid = os.getenv("SOOPER_KANOON_GUID", "")
    if not guid:
        result["error"] = "SOOPER_KANOON_GUID not set in environment"
        print(f"[SooperKanoon] ERROR: {result['error']}")
        return result
    
    headers = _get_headers()
    
    try:
        formatted_query = case_query.strip().replace(" ", "-").lower()
        search_url = f"{SOOPER_KANOON_BASE}/cases/search/name:{formatted_query}.json"
        result["search_url"] = search_url
        
        print(f"[SooperKanoon] STEP 1: GET {search_url}")
        print(f"[SooperKanoon] Headers: HTTP-GUID={guid[:8]}...")
        
        search_response = requests.get(search_url, headers=headers, timeout=30)
        result["search_status"] = search_response.status_code
        result["search_content_type"] = search_response.headers.get('Content-Type', 'N/A')
        result["search_response_preview"] = search_response.text[:500]
        
        print(f"[SooperKanoon] Search Status: {search_response.status_code}")
        print(f"[SooperKanoon] Search Content-Type: {result['search_content_type']}")
        print(f"[SooperKanoon] Search Response (500 chars): {result['search_response_preview']}")
        
        if _is_cloudflare_blocked(search_response):
            result["error"] = "Blocked by Cloudflare or authorization layer"
            result["has_full_text"] = False
            print(f"[SooperKanoon] BLOCKED: {result['error']}")
            return result
        
        if search_response.status_code != 200:
            result["error"] = f"Search failed with HTTP {search_response.status_code}"
            print(f"[SooperKanoon] ERROR: {result['error']}")
            return result
        
        try:
            search_data = search_response.json()
        except Exception as e:
            result["error"] = f"Failed to parse search JSON: {str(e)}"
            print(f"[SooperKanoon] ERROR: {result['error']}")
            return result
        
        if isinstance(search_data, dict):
            result["raw_keys"] = list(search_data.keys())
        print(f"[SooperKanoon] Search response keys: {result['raw_keys']}")
        
        jids = search_data.get("jids", [])
        if not jids:
            result["error"] = "No jids found in search response"
            print(f"[SooperKanoon] WARNING: {result['error']}")
            return result
        
        result["jids_found"] = jids[:5]
        print(f"[SooperKanoon] STEP 2: Found {len(jids)} jids, first 5: {result['jids_found']}")
        
        for idx, jid in enumerate(jids[:5]):
            print(f"[SooperKanoon] STEP 3.{idx+1}: Fetching jid {jid}")
            
            if jid.endswith(".json"):
                detail_url = f"{SOOPER_KANOON_BASE}{jid}"
            else:
                detail_url = f"{SOOPER_KANOON_BASE}{jid}.json"
            
            result["detail_url"] = detail_url
            print(f"[SooperKanoon] Detail URL: {detail_url}")
            
            detail_response = requests.get(detail_url, headers=headers, timeout=30)
            result["detail_status"] = detail_response.status_code
            
            print(f"[SooperKanoon] Detail Status: {detail_response.status_code}")
            print(f"[SooperKanoon] Detail Content-Type: {detail_response.headers.get('Content-Type', 'N/A')}")
            print(f"[SooperKanoon] Detail Response (500 chars): {detail_response.text[:500]}")
            
            if _is_cloudflare_blocked(detail_response):
                print(f"[SooperKanoon] Detail BLOCKED by Cloudflare")
                continue
            
            if detail_response.status_code != 200:
                print(f"[SooperKanoon] Detail failed: HTTP {detail_response.status_code}")
                continue
            
            try:
                detail_data = detail_response.json()
            except Exception as e:
                print(f"[SooperKanoon] Failed to parse detail JSON: {e}")
                continue
            
            if isinstance(detail_data, dict):
                result["raw_keys"] = list(detail_data.keys())
            print(f"[SooperKanoon] Detail response keys: {result['raw_keys']}")
            
            result["case_name"] = _extract_metadata(detail_data, ["title", "case_name", "name", "case_title"]) or "UNKNOWN"
            result["court"] = _extract_metadata(detail_data, ["court", "court_name", "bench"])
            result["year"] = _extract_metadata(detail_data, ["year", "date", "judgment_date", "decision_date"])
            
            full_text = _extract_text_field(detail_data)
            
            if full_text and len(full_text) > 500:
                result["has_full_text"] = True
                result["full_text_length"] = len(full_text)
                result["preview_start"] = full_text[:500]
                print(f"[SooperKanoon] SUCCESS: Found full text with {result['full_text_length']} characters")
                print(f"[SooperKanoon] Preview: {result['preview_start'][:200]}...")
                return result
            else:
                print(f"[SooperKanoon] No full text in this jid, trying next...")
        
        result["error"] = "No case with full judgment text found in first 5 results"
        result["has_full_text"] = False
        print(f"[SooperKanoon] CONCLUSION: {result['error']}")
        return result
        
    except requests.exceptions.Timeout:
        result["error"] = "Request timed out after 30 seconds"
        print(f"[SooperKanoon] ERROR: {result['error']}")
        return result
    except requests.exceptions.RequestException as e:
        result["error"] = f"Request failed: {str(e)}"
        print(f"[SooperKanoon] ERROR: {result['error']}")
        return result
    except Exception as e:
        result["error"] = f"Unexpected error: {str(e)}"
        print(f"[SooperKanoon] ERROR: {result['error']}")
        return result


def test_sooperkanoon_comprehensive() -> Dict:
    """
    Run comprehensive test of SooperKanoon API.
    Tests search + detail fetch for kesavananda-bharati case.
    
    Returns full diagnostic report.
    """
    return fetch_case_from_sooperkanoon("kesavananda-bharati")
