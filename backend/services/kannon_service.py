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
    Search for a case by text and return the best matching result.
    Uses smart scoring based on title, year, and court match.
    """
    if not KANOON_API_KEY:
        logger.error("KANOON_API_KEY not set for search")
        return None
        
    # Kannon API 'text' param is for free-text search (petitioners, respondents, snippets).
    # 'query' param is for structured filters like court_id:SC.
    # We use both for maximum precision.
    params = {
        "text": query_text,
        "token": KANOON_API_KEY,
        "limit": 10  # Get more results to perform smart selection
    }
    
    # Try to extract court filter if present in query
    if "supreme court" in query_text.lower() or " sc " in query_text.lower():
        params["query"] = "court_id:SC"
    
    try:
        url = f"{KANOON_API_BASE}/search/cases"
        logger.info(f"Searching Kannon for: {query_text} (Params: {params})")
        response = requests.get(url, params=params, timeout=30)
        
        if response.status_code != 200:
            logger.error(f"Kannon search returned status {response.status_code}: {response.text}")
            return None
            
        data = response.json()
        results = data.get("data", [])
        
        if not results:
            logger.warning(f"No results found for query: {query_text}")
            return None

        # --- Smart Resolution Logic ---
        # Instead of taking results[0], we score them against the original query
        scored_results = []
        q_tokens = set(query_text.lower().split())
        
        for res in results:
            score = 0
            res_id = res.get("id", "").lower()
            res_title = (res.get("title") or "").lower()
            res_court = (res.get("court_id") or "").lower()
            res_year = (res.get("filed_at") or "")[:4]
            
            # 1. Title Match (Fuzzy)
            if res_title:
                t_tokens = set(res_title.split())
                overlap = len(q_tokens.intersection(t_tokens))
                score += (overlap / len(q_tokens)) * 50
            
            # 2. Year Match
            if res_year and res_year in query_text:
                score += 30
                
            # 3. Court Match
            if res_court and res_court in query_text.lower():
                score += 20
            elif "supreme court" in query_text.lower() and res_court == "sc":
                score += 20
            
            # 4. ID direct match (if user entered ID)
            if res_id in query_text.lower():
                score += 100

            scored_results.append((score, res))
        
        # Sort by score descending
        scored_results.sort(key=lambda x: x[0], reverse=True)
        
        best_score, best_result = scored_results[0]
        
        # If the best score is too low and we have a specific name, reject it
        # This prevents the "Default PHHC" bug when no match is found
        if best_score < 10 and len(q_tokens) > 2:
            logger.warning(f"Best match score {best_score} too low for '{query_text}'. Rejecting results.")
            return None

        logger.info(f"Resolved case: {best_result.get('id')} with score {best_score}")
        return best_result
        
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
