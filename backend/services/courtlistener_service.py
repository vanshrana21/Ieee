# backend/services/courtlistener_service.py
"""
CourtListener API integration for fetching real legal case data.
Enhanced with detailed case retrieval for case detail views.
"""
import os
import logging
from typing import List, Dict, Optional
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

COURTLISTENER_API_BASE = "https://www.courtlistener.com/api/rest/v4"
COURTLISTENER_API_KEY = os.getenv("COURTLISTENER_API_KEY")


def fetch_cases_from_courtlistener(
    query: str,
    court: Optional[str] = None,
    year: Optional[int] = None,
    max_results: int = 10
) -> List[Dict]:
    """
    Fetch real legal cases from CourtListener API v4.
    
    Args:
        query: Search query string (case name, legal topic, etc.)
        court: Optional court filter (e.g., "scotus", "ca9")
        year: Optional year filter
        max_results: Maximum number of results to return (default: 10)
    
    Returns:
        List of case dictionaries with structured data
    """
    if not COURTLISTENER_API_KEY:
        logger.error("COURTLISTENER_API_KEY not set in environment")
        raise ValueError("CourtListener API key not configured")
    
    headers = {
        "Authorization": f"Token {COURTLISTENER_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Build search parameters for v4 API
    params = {
        "q": query,
        "type": "o",  # Opinions
        "order_by": "score desc",
    }
    
    if court:
        params["court"] = court
    
    if year:
        params["filed_after"] = f"{year}-01-01"
        params["filed_before"] = f"{year}-12-31"
    
    try:
        logger.info(f"Searching CourtListener v4: query='{query}', court={court}, year={year}")
        
        response = requests.get(
            f"{COURTLISTENER_API_BASE}/search/",
            headers=headers,
            params=params,
            timeout=30
        )
        
        response.raise_for_status()
        data = response.json()
        
        if not data.get("results"):
            logger.warning(f"No results found for query: {query}")
            return []
        
        # Process and structure the results
        cases = []
        for result in data["results"][:max_results]:
            case_data = _extract_case_data(result)
            if case_data:
                cases.append(case_data)
        
        logger.info(f"Retrieved {len(cases)} cases from CourtListener")
        return cases
    
    except requests.exceptions.RequestException as e:
        logger.error(f"CourtListener API request failed: {str(e)}")
        raise RuntimeError(f"Failed to fetch cases from CourtListener: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error fetching cases: {str(e)}", exc_info=True)
        raise RuntimeError(f"Error processing CourtListener data: {str(e)}")


def _extract_case_data(result: Dict) -> Optional[Dict]:
    """
    Extract and structure relevant case data from CourtListener v4 result.
    
    Args:
        result: Raw result dictionary from CourtListener API v4
    
    Returns:
        Structured case dictionary or None if data is insufficient
    """
    try:
        case_name = result.get("caseName", "")
        court_id = result.get("court_id", "")
        court_name = result.get("court", court_id)
        
        # Parse date
        date_filed = result.get("dateFiled", "")
        year = None
        if date_filed:
            try:
                year = int(date_filed[:4])
            except (ValueError, TypeError):
                year = None
        
        # Extract text
        snippet = result.get("snippet", "")
        text = result.get("text", "")
        opinion_text = text if text else snippet
        
        # Get other fields
        docket_number = result.get("docketNumber", "")
        citation = result.get("citation", [])
        if isinstance(citation, list):
            citation = ", ".join(str(c) for c in citation) if citation else ""
        
        opinion_id = result.get("id", "")
        
        if not case_name:
            logger.warning(f"Skipping case with no case_name: {opinion_id}")
            return None
        
        return {
            "id": opinion_id,
            "case_name": case_name,
            "court": court_name or "Unknown Court",
            "year": year,
            "date_filed": date_filed,
            "docket_number": docket_number,
            "citation": citation,
            "opinion_text": opinion_text[:5000],
            "snippet": snippet,
            "url": result.get("absolute_url", "")
        }
    
    except Exception as e:
        logger.error(f"Error extracting case data: {str(e)}")
        return None


def get_case_details(case_id: int) -> Optional[Dict]:
    """
    Fetch detailed information for a specific case by opinion ID.
    
    Args:
        case_id: CourtListener opinion ID
    
    Returns:
        Detailed case dictionary or None if not found
    """
    if not COURTLISTENER_API_KEY:
        raise ValueError("CourtListener API key not configured")
    
    headers = {
        "Authorization": f"Token {COURTLISTENER_API_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        logger.info(f"Fetching case details for opinion ID: {case_id}")
        
        # Fetch opinion details
        response = requests.get(
            f"{COURTLISTENER_API_BASE}/opinions/{case_id}/",
            headers=headers,
            timeout=30
        )
        
        response.raise_for_status()
        opinion_data = response.json()
        
        # Extract cluster ID to get additional metadata
        cluster_id = opinion_data.get("cluster")
        cluster_data = {}
        
        if cluster_id:
            try:
                # Extract cluster ID from URL if it's a URL string
                if isinstance(cluster_id, str) and "/" in cluster_id:
                    cluster_id = cluster_id.rstrip("/").split("/")[-1]
                
                cluster_response = requests.get(
                    f"{COURTLISTENER_API_BASE}/clusters/{cluster_id}/",
                    headers=headers,
                    timeout=30
                )
                cluster_response.raise_for_status()
                cluster_data = cluster_response.json()
            except Exception as e:
                logger.warning(f"Could not fetch cluster data: {str(e)}")
        
        # Build comprehensive case details
        case_details = {
            "id": opinion_data.get("id"),
            "case_name": cluster_data.get("case_name", opinion_data.get("case_name", "")),
            "court": cluster_data.get("court", ""),
            "court_full_name": cluster_data.get("court_full", ""),
            "date_filed": cluster_data.get("date_filed", ""),
            "docket_number": cluster_data.get("docket", {}).get("docket_number", "") if isinstance(cluster_data.get("docket"), dict) else "",
            "judges": cluster_data.get("judges", ""),
            "nature_of_suit": cluster_data.get("nature_of_suit", ""),
            "citations": cluster_data.get("citation_count", 0),
            "opinion_type": opinion_data.get("type", ""),
            "author": opinion_data.get("author_str", ""),
            "plain_text": opinion_data.get("plain_text", ""),
            "html": opinion_data.get("html", ""),
            "html_with_citations": opinion_data.get("html_with_citations", ""),
            "source_url": f"https://www.courtlistener.com{cluster_data.get('absolute_url', '')}",
            "download_url": opinion_data.get("download_url", ""),
            "has_full_text": bool(opinion_data.get("plain_text") or opinion_data.get("html")),
        }
        
        logger.info(f"Successfully retrieved detailed case data for opinion {case_id}")
        return case_details
    
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch case details for ID {case_id}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching case details: {str(e)}", exc_info=True)
        return None


def get_cluster_details(cluster_id: int) -> Optional[Dict]:
    """
    Fetch detailed information for a specific case by cluster ID.
    Use this when only cluster ID is available (no opinion ID).
    
    Args:
        cluster_id: CourtListener cluster ID
    
    Returns:
        Detailed case dictionary or None if not found
    """
    if not COURTLISTENER_API_KEY:
        raise ValueError("CourtListener API key not configured")
    
    headers = {
        "Authorization": f"Token {COURTLISTENER_API_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        logger.info(f"Fetching case details for cluster ID: {cluster_id}")
        
        # Fetch cluster details
        response = requests.get(
            f"{COURTLISTENER_API_BASE}/clusters/{cluster_id}/",
            headers=headers,
            timeout=30
        )
        
        response.raise_for_status()
        cluster_data = response.json()
        
        # Try to get opinion text from sub_opinions
        plain_text = ""
        html = ""
        download_url = ""
        has_full_text = False
        
        sub_opinions = cluster_data.get("sub_opinions", [])
        if sub_opinions:
            # Fetch first opinion for text
            try:
                first_opinion_url = sub_opinions[0]
                if isinstance(first_opinion_url, str) and "/" in first_opinion_url:
                    opinion_id = first_opinion_url.rstrip("/").split("/")[-1]
                    opinion_response = requests.get(
                        f"{COURTLISTENER_API_BASE}/opinions/{opinion_id}/",
                        headers=headers,
                        timeout=30
                    )
                    if opinion_response.status_code == 200:
                        opinion_data = opinion_response.json()
                        plain_text = opinion_data.get("plain_text", "")
                        html = opinion_data.get("html", "")
                        download_url = opinion_data.get("download_url", "")
                        has_full_text = bool(plain_text or html)
            except Exception as e:
                logger.warning(f"Could not fetch opinion text from cluster: {str(e)}")
        
        # Build case details
        case_details = {
            "id": cluster_data.get("id"),
            "case_name": cluster_data.get("case_name", ""),
            "court": cluster_data.get("court", ""),
            "court_full_name": "",  # Cluster doesn't have this
            "date_filed": cluster_data.get("date_filed", ""),
            "docket_number": cluster_data.get("docket", {}).get("docket_number", "") if isinstance(cluster_data.get("docket"), dict) else "",
            "judges": cluster_data.get("judges", ""),
            "nature_of_suit": cluster_data.get("nature_of_suit", ""),
            "citations": cluster_data.get("citation_count", 0),
            "opinion_type": "",
            "author": "",
            "plain_text": plain_text,
            "html": html,
            "html_with_citations": "",
            "source_url": f"https://www.courtlistener.com{cluster_data.get('absolute_url', '')}",
            "download_url": download_url,
            "has_full_text": has_full_text,
        }
        
        logger.info(f"Successfully retrieved cluster data for cluster {cluster_id}")
        return case_details
    
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch cluster details for ID {cluster_id}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching cluster details: {str(e)}", exc_info=True)
        return None


def get_jurisdiction_from_court(court_id: str) -> str:
    """
    Map court ID to jurisdiction name.
    
    Args:
        court_id: CourtListener court identifier
    
    Returns:
        Human-readable jurisdiction name
    """
    jurisdiction_map = {
        "scotus": "Federal - Supreme Court",
        "ca1": "Federal - First Circuit",
        "ca2": "Federal - Second Circuit",
        "ca3": "Federal - Third Circuit",
        "ca4": "Federal - Fourth Circuit",
        "ca5": "Federal - Fifth Circuit",
        "ca6": "Federal - Sixth Circuit",
        "ca7": "Federal - Seventh Circuit",
        "ca8": "Federal - Eighth Circuit",
        "ca9": "Federal - Ninth Circuit",
        "ca10": "Federal - Tenth Circuit",
        "ca11": "Federal - Eleventh Circuit",
        "cadc": "Federal - D.C. Circuit",
        "cafc": "Federal - Federal Circuit",
    }
    
    return jurisdiction_map.get(court_id, "Unknown Jurisdiction")