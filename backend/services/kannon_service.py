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

def search_case_in_kannon(query_text: str) -> Optional[Dict]:
    """
    Search for a case by text and return the first match result.
    Uses fuzzy matching on names/parties.
    """
    if not KANOON_API_KEY:
        logger.error("KANOON_API_KEY not set for search")
        return None
        
    # Kannon search works best with the query parameter for free-text search.
    # We use the token parameter for authentication as verified.
    params = {
        "query": query_text,
        "token": KANOON_API_KEY,
        "limit": 5
    }
    
    try:
        url = f"{KANOON_API_BASE}/search/cases"
        logger.info(f"Searching Kannon for: {query_text}")
        response = requests.get(url, params=params, timeout=30)
        
        if response.status_code != 200:
            logger.error(f"Kannon search returned status {response.status_code}: {response.text}")
            return None
            
        data = response.json()
        results = data.get("data", [])
        
        if results and len(results) > 0:
            # We take the first result as the most relevant
            result = results[0]
            logger.info(f"Found case via search: {result.get('id')}")
            return result
            
        return None
    except Exception as e:
        logger.error(f"Search failed in Kannon for '{query_text}': {str(e)}")
        return None

def fetch_case_from_kannon(case_identifier: str) -> Dict:
    """
    Fetch raw case data from Kanoon (Kannon) API.
    Attempts direct fetch first, then search-based resolution.
    
    CRITICAL: Search results are treated as authoritative raw data.
    Direct fetch-by-ID is OPTIONAL.
    
    Args:
        case_identifier: The identifier or name for the case.
    
    Returns:
        Raw Python dictionary containing the API response.
    """
    if not KANOON_API_KEY:
        logger.error("KANOON_API_KEY not set in environment")
        raise ValueError("Kanoon API key not configured")

    # Helper for direct fetching
    def _do_fetch(cid: str) -> Optional[Dict]:
        # Kannon IDs are usually COURT-NUMBER-YEAR or just NUMBER
        # Extract court_id from prefix (e.g., SC-123 -> SC, PHHC01-123 -> PHHC01)
        if '-' in cid:
            parts = cid.split('-')
            court_id = parts[0]
        else:
            court_id = "SC" # Default fallback
            
        url = f"{KANOON_API_BASE}/courts/{court_id}/cases/{cid}"
        params = {"token": KANOON_API_KEY}
        
        try:
            resp = requests.get(url, params=params, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                # Ensure it's the expected data structure
                if "data" in data:
                    return data["data"]
                return data
            
            # Fallback: if CID has no hyphen but failed with SC, try common courts
            if '-' not in cid:
                for alt_court in ["JKHC", "DLHC", "PHHC", "KLHC"]:
                    alt_url = f"{KANOON_API_BASE}/courts/{alt_court}/cases/{cid}"
                    alt_resp = requests.get(alt_url, params=params, timeout=10)
                    if alt_resp.status_code == 200:
                        alt_data = alt_resp.json()
                        return alt_data.get("data", alt_data)
            
            return None
        except:
            return None

    # Step 1: Try direct fetch if it looks like an ID
    court_prefixes = ["SC", "JKHC", "DLHC", "PHHC", "KLHC", "BHC", "MHC"]
    is_potential_id = '-' in case_identifier or any(case_identifier.upper().startswith(p) for p in court_prefixes)
    
    if is_potential_id:
        logger.info(f"Attempting direct fetch for potential ID: {case_identifier}")
        direct_data = _do_fetch(case_identifier)
        if direct_data:
            return {"data": direct_data} # Wrap to maintain consistency with API response expectations

    # Step 2: Resolve via search
    search_result = search_case_in_kannon(case_identifier)
    if search_result:
        resolved_id = search_result.get("id")
        logger.info(f"Resolved via search. Attempting deep fetch for ID: {resolved_id}")
        
        # Try deep fetch, but it is NOT mandatory
        deep_data = _do_fetch(resolved_id) if resolved_id else None
        
        if deep_data:
            logger.info(f"Deep fetch successful for {resolved_id}")
            return {"data": deep_data}
        
        # FALLBACK: Use search result itself as the authoritative data
        logger.warning(f"Deep fetch failed for {resolved_id}. Falling back to search result data.")
        return {"data": search_result}

    # Step 3: Failure
    logger.error(f"Could not resolve or fetch case: {case_identifier}")
    raise ValueError(f"Case not found: {case_identifier}")
