from fastapi import APIRouter, HTTPException, Depends
from backend.services.kannon_service import fetch_case_from_kannon
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
