from fastapi import APIRouter, HTTPException, Depends
from backend.services.kannon_service import fetch_case_from_kannon
from backend.utils.case_extractor import extract_full_case_details
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
