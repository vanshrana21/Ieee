# backend/routes/case_simplifier.py
"""
Phase 5: Unified Case Simplifier API.
Orchestrates Phase 1-4 into a single endpoint.
"""
import logging
from fastapi import APIRouter, HTTPException, Path
from typing import Dict, Any

from backend.services.case_summarizer import get_case_simplification

router = APIRouter(prefix="/api/case-simplifier", tags=["Case Simplifier"])
logger = logging.getLogger(__name__)

@router.get("/{case_identifier}")
async def get_case_simplifier(
    case_identifier: str = Path(..., description="The unique identifier for the case (e.g., JKHC01-003375-2023)")
) -> Dict[str, Any]:
    """
    Exposes a SINGLE endpoint to fetch a case and generate an AI-powered structured summary.
    
    Flow:
    1. Fetch raw case data (Phase 1)
    2. Extract readable full case detail (Phase 2)
    3. Prepare canonical AI input structure (Phase 3)
    4. Generate AI structured summary (Phase 4)
    5. Return combined response
    """
    logger.info(f"Case Simplifier request received for: {case_identifier}")
    
    try:
        # Orchestrate all phases
        # get_case_simplification now returns exactly the required contract:
        # { "raw_case": {...}, "ai_structured_summary": {...} }
        response = await get_case_simplification(case_identifier)
        
        logger.info(f"Successfully processed case simplifier for: {case_identifier}")
        return response

    except ValueError as e:
        logger.error(f"Validation or not found error for {case_identifier}: {str(e)}")
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        logger.error(f"Kannon API error for {case_identifier}: {str(e)}")
        raise HTTPException(status_code=502, detail="External legal data service error")
    except Exception as e:
        logger.error(f"Unexpected error in Case Simplifier for {case_identifier}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred during case simplification")
