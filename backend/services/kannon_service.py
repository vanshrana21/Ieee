# backend/services/kannon_service.py
"""
Kannon (Kanoon.dev) API integration for fetching case law data.
Phase 1: Raw ingestion only.
"""
import os
import logging
from typing import Dict, Optional
import requests

logger = logging.getLogger(__name__)

KANOON_API_BASE = "https://api.kanoon.dev/v1"
KANOON_API_KEY = os.getenv("KANOON_API_KEY")

def search_case_in_kannon(query_text: str) -> Optional[str]:
    """
    Search for a case by text and return the ID of the first match.
    """
    if not KANOON_API_KEY:
        logger.error("KANOON_API_KEY not set for search")
        return None
        
    headers = {
        "Authorization": f"Bearer {KANOON_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # We use 'text' parameter for fuzzy search on names/parties
    # Note: query is required, so we use 'object:case' as a broad base
    params = {
        "query": "object:case", 
        "text": query_text,
        "limit": 1
    }
    
    try:
        url = f"{KANOON_API_BASE}/search/cases"
        logger.info(f"Searching Kannon for: {query_text}")
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if data.get("data") and len(data["data"]) > 0:
            case_id = data["data"][0]["id"]
            logger.info(f"Found case ID via search: {case_id}")
            return case_id
            
        return None
    except Exception as e:
        logger.error(f"Search failed in Kannon for '{query_text}': {str(e)}")
        return None

def fetch_case_from_kannon(case_identifier: str) -> Dict:
    """
    Fetch raw case data from Kanoon (Kannon) API.
    Attempts direct fetch first, then search-based resolution.
    
    Args:
        case_identifier: The identifier or name for the case.
    
    Returns:
        Raw Python dictionary containing the API response.
    """
    if not KANOON_API_KEY:
        logger.error("KANOON_API_KEY not set in environment")
        raise ValueError("Kanoon API key not configured")

    headers = {
        "Authorization": f"Bearer {KANOON_API_KEY}",
        "Content-Type": "application/json"
    }

    # Helper for direct fetching
    def _do_fetch(cid: str) -> Optional[Dict]:
        court_id = cid.split('-')[0] if '-' in cid else None
        if not court_id:
            return None
        
        url = f"{KANOON_API_BASE}/courts/{court_id}/cases/{cid}"
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            if resp.status_code == 200:
                return resp.json()
            return None
        except:
            return None

    # Step 1: Try direct fetch if it looks like an ID
    if '-' in case_identifier:
        logger.info(f"Attempting direct fetch for: {case_identifier}")
        direct_data = _do_fetch(case_identifier)
        if direct_data:
            return direct_data

    # Step 2: Resolve via search
    resolved_id = search_case_in_kannon(case_identifier)
    if resolved_id:
        logger.info(f"Attempting fetch with resolved ID: {resolved_id}")
        resolved_data = _do_fetch(resolved_id)
        if resolved_data:
            return resolved_data

    # Step 3: Failure
    logger.error(f"Could not resolve or fetch case: {case_identifier}")
    raise ValueError(f"Case not found or could not be resolved: {case_identifier}")
