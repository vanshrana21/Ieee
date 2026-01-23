# backend/services/super_kanoon_service.py
"""
TEMPORARY TEST ADAPTER for SooperKanoon API.
Purpose: Verify whether Super Kanoon returns FULL judgment text.

⚠️  TEST ONLY - DO NOT:
    - Store responses in DB
    - Feed to AI
    - Show in UI
    - Replace existing Kanoon logic
"""
import os
import logging
import requests
from typing import Dict, Optional

logger = logging.getLogger(__name__)

SOOPER_KANOON_API_BASE = "https://sooperkanoon.com/api"
SOOPER_KANOON_GUID = os.getenv("SOOPER_KANOON_GUID", "")


def fetch_full_judgment(case_query: str) -> Dict:
    """
    Call Super Kanoon API to search for a case and verify if it returns full judgment text.
    
    Args:
        case_query: Case name/query (e.g. "Maneka Gandhi v Union of India 1978")
    
    Returns:
        dict with verification results including length, preview, and analysis
    """
    guid = os.getenv("SOOPER_KANOON_GUID", "")
    logger.info(f"[SuperKanoon Test] Starting search for: {case_query}")
    
    result = {
        "query": case_query,
        "api_called": False,
        "raw_response_keys": [],
        "length": 0,
        "has_full_text": False,
        "source": None,
        "preview_start": "",
        "preview_end": "",
        "verdict": "UNKNOWN",
        "error": None,
        "raw_data": None
    }
    
    if not guid:
        result["error"] = "SOOPER_KANOON_GUID not set in environment"
        logger.error(f"[SuperKanoon Test] {result['error']}")
        return result
    
    try:
        # Format query for search
        formatted_query = case_query.lower().replace(" ", "-")
        # According to some docs, the search endpoint might be directly under /api
        search_url = f"{SOOPER_KANOON_API_BASE}/search/name:{formatted_query}.json"
        
        headers = {
            "HTTP-GUID": guid,
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://sooperkanoon.com/api"
        }
        
        logger.info(f"[SuperKanoon Test] Calling URL: {search_url}")
        response = requests.get(search_url, headers=headers, timeout=30)
        result["api_called"] = True
        
        logger.info(f"[SuperKanoon Test] Response status: {response.status_code}")
        
        if response.status_code != 200:
            result["error"] = f"HTTP {response.status_code}: {response.text[:500]}"
            logger.error(f"[SuperKanoon Test] {result['error']}")
            return result
        
        data = response.json()
        result["raw_data"] = data
        
        if isinstance(data, dict):
            result["raw_response_keys"] = list(data.keys())
        elif isinstance(data, list) and len(data) > 0:
            result["raw_response_keys"] = list(data[0].keys()) if isinstance(data[0], dict) else ["list_items"]
        
        logger.info(f"[SuperKanoon Test] Response keys: {result['raw_response_keys']}")
        
        judgment_text = _extract_judgment_text(data)
        
        if judgment_text:
            text_length = len(judgment_text)
            result["length"] = text_length
            result["preview_start"] = judgment_text[:500]
            result["preview_end"] = judgment_text[-500:] if text_length > 500 else judgment_text
            
            logger.info(f"[SuperKanoon Test] Judgment length: {text_length} characters")
            logger.info(f"[SuperKanoon Test] First 500 chars: {result['preview_start']}")
            logger.info(f"[SuperKanoon Test] Last 500 chars: {result['preview_end']}")
            
            if text_length < 5000:
                result["verdict"] = "NOT_FULL_TEXT"
                result["has_full_text"] = False
                logger.warning(f"[SuperKanoon Test] Judgment length: {text_length} chars - likely NOT full text (< 5,000)")
            elif text_length < 15000:
                result["verdict"] = "PARTIAL"
                result["has_full_text"] = False
                logger.warning(f"[SuperKanoon Test] Judgment length: {text_length} chars - likely PARTIAL (5,000-15,000)")
            else:
                result["verdict"] = "LIKELY_FULL"
                result["has_full_text"] = True
                logger.info(f"[SuperKanoon Test] Judgment length: {text_length} chars - likely FULL text (20,000+)")
        else:
            result["verdict"] = "NO_TEXT_FOUND"
            logger.warning("[SuperKanoon Test] No judgment text field found in response")
        
        result["source"] = _extract_source(data)
        logger.info(f"[SuperKanoon Test] Source attribution: {result['source'] or 'NONE'}")
        
        return result
        
    except requests.exceptions.Timeout:
        result["error"] = "Request timed out after 30 seconds"
        logger.error(f"[SuperKanoon Test] {result['error']}")
        return result
    except requests.exceptions.RequestException as e:
        result["error"] = f"Request failed: {str(e)}"
        logger.error(f"[SuperKanoon Test] {result['error']}")
        return result
    except Exception as e:
        result["error"] = f"Unexpected error: {str(e)}"
        logger.error(f"[SuperKanoon Test] {result['error']}")
        return result


def _extract_judgment_text(data: Dict) -> Optional[str]:
    """
    Try to extract judgment text from various possible field names.
    """
    text_fields = [
        "full_text", "judgment_text", "judgement_text", "text", "content",
        "body", "judgment", "judgement", "doc_text", "document_text",
        "case_text", "decision_text", "ruling_text"
    ]
    
    if isinstance(data, dict):
        for field in text_fields:
            if field in data and data[field]:
                return str(data[field])
        
        for key in ["data", "result", "results", "case", "document"]:
            if key in data and isinstance(data[key], dict):
                for field in text_fields:
                    if field in data[key] and data[key][field]:
                        return str(data[key][field])
        
        if "results" in data and isinstance(data["results"], list) and len(data["results"]) > 0:
            first_result = data["results"][0]
            if isinstance(first_result, dict):
                for field in text_fields:
                    if field in first_result and first_result[field]:
                        return str(first_result[field])
    
    elif isinstance(data, list) and len(data) > 0:
        first_item = data[0]
        if isinstance(first_item, dict):
            for field in text_fields:
                if field in first_item and first_item[field]:
                    return str(first_item[field])
    
    return None


def _extract_source(data: Dict) -> Optional[str]:
    """
    Try to extract source/citation metadata.
    """
    source_fields = [
        "source", "citation", "cite", "court", "court_name",
        "case_citation", "reference", "source_url"
    ]
    
    if isinstance(data, dict):
        for field in source_fields:
            if field in data and data[field]:
                return str(data[field])
        
        for key in ["data", "result", "case", "meta", "metadata"]:
            if key in data and isinstance(data[key], dict):
                for field in source_fields:
                    if field in data[key] and data[key][field]:
                        return str(data[key][field])
    
    return None
