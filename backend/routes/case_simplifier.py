# backend/routes/case_simplifier.py
"""
Unified Case Simplifier API.
Phase 5: Orchestrates raw ingestion, extraction, and AI summarization.
"""
import logging
from fastapi import APIRouter, HTTPException
from backend.services.case_summarizer import get_case_simplification

router = APIRouter(prefix="/case-simplifier", tags=["Case Simplifier"])
logger = logging.getLogger(__name__)

@router.get("/{case_identifier}")
async def get_case_simplifier_endpoint(case_identifier: str):
    """
    Unified Case Simplifier API.
    Orchestrates:
    1. Fetch raw case data (Phase 1)
    2. Extract full case detail (Phase 2)
    3. Prepare canonical AI input (Phase 3)
    4. Generate AI structured summary (Phase 4)
    5. Return combined response (Phase 5)
    """
    logger.info(f"Case request received: {case_identifier}")
    
    try:
        # get_case_simplification handles Phases 1-4 orchestration
        result = await get_case_simplification(case_identifier)
        
        # Phase 5: Locked Final Response Shape
        # raw_case contains: case_name, citation, court, year, facts, issues, arguments, judgment, ratio
        # ai_structured_summary contains: case_name, citation, court, year, facts, issues, judgment, ratio_decidendi
        response = {
            "raw_case": result["full_case_detail"],
            "ai_structured_summary": result["ai_summary"]
        }
        
        # Logging
        logger.info(f"Kannon success: {case_identifier}")
        
        if result.get("is_simplified"):
            logger.info(f"AI success: {case_identifier}")
        else:
            logger.warning(f"AI failure: {case_identifier}, returning raw data only.")
            
        return response

    except ValueError as e:
        # Graceful Degradation: If Kannon fails, return clear error
        logger.error(f"Kannon failure: {str(e)}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Case simplifier flow failed for {case_identifier}: {str(e)}")
        # If any unexpected error occurs in the pipeline
        raise HTTPException(
            status_code=500, 
            detail="An internal error occurred while orchestrating the case simplification."
        )
