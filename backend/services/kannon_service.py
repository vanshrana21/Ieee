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

KANNON_API_BASE = "https://api.kanoon.dev/v1"
KANNON_API_KEY = os.getenv("KANNON_API_KEY")

def fetch_case_from_kannon(case_identifier: str) -> Dict:
    """
    Fetch raw case data from Kannon API.
    
    Args:
        case_identifier: The identifier for the case (e.g., 'JKHC01-003375-2023')
    
    Returns:
        Raw Python dictionary containing the API response.
    """
    if not KANNON_API_KEY:
        logger.error("KANNON_API_KEY not set in environment")
        raise ValueError("Kannon API key not configured")

    # Extract court_id from case_identifier if possible
    # Kanoon.dev IDs often prefix the court ID (e.g., JKHC01-...)
    court_id = case_identifier.split('-')[0] if '-' in case_identifier else None
    
    if not court_id:
        logger.error(f"Could not extract court_id from identifier: {case_identifier}")
        raise ValueError(f"Invalid case identifier format: {case_identifier}")

    headers = {
        "Authorization": f"Bearer {KANNON_API_KEY}",
        "Content-Type": "application/json"
    }

    url = f"{KANNON_API_BASE}/courts/{court_id}/cases/{case_identifier}"
    
    try:
        logger.info(f"Fetching case from Kannon: {case_identifier} (Court: {court_id})")
        
        response = requests.get(
            url,
            headers=headers,
            timeout=30
        )
        
        # Log success or failure status
        if response.status_code == 200:
            logger.info(f"Successfully fetched case: {case_identifier}")
        else:
            logger.error(f"Failed to fetch case {case_identifier}: Status {response.status_code}")
            
        response.raise_for_status()
        raw_data = response.json()
        
        # Phase 1: Return raw data as is
        return raw_data

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            logger.error(f"Case not found: {case_identifier}")
            raise ValueError(f"Case not found in Kannon: {case_identifier}")
        logger.error(f"Kannon API HTTP error: {str(e)}")
        raise RuntimeError(f"Kannon API error: {str(e)}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Kannon API request failed: {str(e)}")
        raise RuntimeError(f"Failed to connect to Kannon API: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in fetch_case_from_kannon: {str(e)}", exc_info=True)
        raise RuntimeError(f"Unexpected error fetching case: {str(e)}")
