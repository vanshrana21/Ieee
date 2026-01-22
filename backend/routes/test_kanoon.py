from fastapi import APIRouter, HTTPException, Depends
from backend.services.kannon_service import fetch_case_from_kannon
from backend.utils.case_extractor import extract_full_case_details
from backend.services.case_summarizer import get_case_simplification
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/test-kanoon", tags=["Internal-Test"])

@router.get("/fetch/{case_id}")
async def test_fetch_case(case_id: str):
    """
    Internal test endpoint to verify Kanoon API fetch logic.
    NOT FOR FRONTEND USE.
    """
    try:
        logger.info(f"Test endpoint triggered for case: {case_id}")
        data = fetch_case_from_kannon(case_id)
        return {
            "success": True,
            "message": "Raw data fetched successfully",
            "data_preview": {
                "id": data.get("id"),
                "court_id": data.get("court_id"),
                "status": data.get("status"),
                "party_count": len(data.get("petitioners", [])) + len(data.get("respondents", []))
            }
        }
    except ValueError as e:
        logger.error(f"Test fetch validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Test fetch error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/extract/{case_id}")
async def test_extract_case(case_id: str):
    """
    Internal test endpoint to verify Kanoon extraction logic.
    Converts raw response to readable full case details.
    """
    try:
        logger.info(f"Extraction test triggered for case: {case_id}")
        raw_data = fetch_case_from_kannon(case_id)
        extracted_data = extract_full_case_details(raw_data)
        return {
            "success": True,
            "message": "Case data extracted successfully",
            "full_case_detail": extracted_data
        }
    except ValueError as e:
        logger.error(f"Extraction test validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Extraction test error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/search")
async def test_search_case(q: str):
    """
    Internal test endpoint to verify Kanoon search logic.
    """
    try:
        from backend.services.kannon_service import search_case_in_kannon
        logger.info(f"Search test triggered for: {q}")
        case_id = search_case_in_kannon(q)
        return {
            "success": True,
            "query": q,
            "resolved_id": case_id
        }
    except Exception as e:
        logger.error(f"Search test error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/simplify/{case_id}")
async def test_simplify_case(case_id: str):
    """
    Internal test endpoint to verify Phase 4: AI Structured Summary Generation.
    Returns both full case detail and AI-generated summary.
    """
    try:
        logger.info(f"Simplification test triggered for case: {case_id}")
        result = await get_case_simplification(case_id)
        return result
    except ValueError as e:
        logger.error(f"Simplification test validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Simplification test error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
