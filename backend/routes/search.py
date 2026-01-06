import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.search import (
    SearchRequest,
    SearchResponse,
    SearchResult,
    CaseDetail,
    AISummaryRequest,
    AISummaryResponse,
)
from backend.orm.user import User
from backend.routes.auth import get_current_user
from backend.services.credit_service import check_credits, deduct_credits
from backend.services.courtlistener_service import fetch_cases_from_courtlistener
from backend.services.ai_analysis_service import generate_case_brief

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/search", response_model=SearchResponse)
async def search_legal_cases(
    search_request: SearchRequest
):
    """
    Search for legal cases using CourtListener API
    """
    logger.info(f"Search request: query='{search_request.query}'")
    
    try:
        # Extract filters
        court = None
        year = None
        if search_request.filters:
            court = search_request.filters.court
            year = int(search_request.filters.year) if search_request.filters.year else None
        
        # Fetch from CourtListener
        cases = fetch_cases_from_courtlistener(
            query=search_request.query,
            court=court,
            year=year,
            max_results=20
        )
        
        # Convert to SearchResult format
        results = []
        for case in cases:
            results.append(SearchResult(
                id=str(case.get("id", "")),
                title=case["case_name"],
                court=case["court"],
                year=case.get("year", 0) or 0,
                summary=case.get("snippet", "")[:500],
                citations=0,  # CourtListener doesn't provide citation count in search
                tags=[],
                relevance_score=None,
                source="CourtListener"
            ))
        
        logger.info(f"Search completed successfully: {len(results)} results")
        
        return SearchResponse(
            total_results=len(results),
            results=results,
            query=search_request.query,
            credits_used=0
        )
        
    except ValueError as e:
        logger.error(f"Configuration error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Service configuration error"
        )
    except RuntimeError as e:
        logger.error(f"Search operation failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Search service temporarily unavailable"
        )
    except Exception as e:
        logger.error(f"Unexpected error during search: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred"
        )

@router.get("/case/{case_id}/public")
async def get_case_details_public(case_id: str):
    """
    Retrieve detailed information about a specific case (public endpoint, no auth required).
    This is used by the case detail page.
    """
    logger.info(f"Public case detail request: case_id={case_id}")
    
    # Validate case_id is numeric
    if not case_id or not case_id.isdigit():
        logger.warning(f"Invalid case ID format: {case_id}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid case ID format"
        )
    
    try:
        from backend.services.courtlistener_service import get_case_details
        
        case = get_case_details(int(case_id))
        
        if not case:
            logger.warning(f"Case not found: {case_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Case not found"
            )
        
        # Return raw case data for frontend to format
        logger.info(f"Case details retrieved successfully: {case_id}")
        return {
            "success": True,
            "case": case
        }
        
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Configuration error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Service configuration error"
        )
    except Exception as e:
        logger.error(f"Failed to retrieve case {case_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve case details"
        )
    
@router.get("/case/{case_id}", response_model=CaseDetail)
async def get_case_details(
    case_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Retrieve detailed information about a specific case.
    """
    logger.info(f"Case detail request from user {current_user.id}: case_id={case_id}")
    
    try:
        from backend.services.courtlistener_service import get_case_details
        
        case = get_case_details(int(case_id))
        
        if not case:
            logger.warning(f"Case not found: {case_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Case not found"
            )
        
        # Convert to CaseDetail format
        case_detail = CaseDetail(
            id=str(case.get("id", "")),
            title=case.get("case_name", ""),
            court=case.get("court", ""),
            year=case.get("date_filed", "")[:4] if case.get("date_filed") else 0,
            date=case.get("date_filed"),
            docket_number=case.get("docket_number"),
            summary=case.get("plain_text", "")[:1000] if case.get("plain_text") else "",
            holdings=None,
            key_points=None,
            tags=[],
            citations=0,
            cited_by=None,
            cites=None,
            statutes=None,
            source="CourtListener"
        )
        
        logger.info(f"Case details retrieved successfully: {case_id}")
        return case_detail
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve case {case_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve case details"
        )


@router.post("/summary", response_model=AISummaryResponse)
async def get_ai_summary(
    summary_request: AISummaryRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Generate AI-powered summary for a legal case.
    """
    summary_cost = 5
    
    logger.info(f"AI summary request from user {current_user.id}: case_id={summary_request.case_id}")
    
    has_credits = await check_credits(
        user_id=current_user.id,
        required=summary_cost,
        db=db
    )
    
    if not has_credits:
        logger.warning(f"User {current_user.id} has insufficient credits for AI summary")
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Insufficient credits"
        )
    
    try:
        from backend.services.courtlistener_service import get_case_details
        
        case = get_case_details(int(summary_request.case_id))
        
        if not case:
            logger.warning(f"Case not found for AI summary: {summary_request.case_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Case not found"
            )
        
        # Generate AI brief
        brief = generate_case_brief(case)
        
        # Extract key points from brief (simple extraction)
        key_points = [
            line.strip() for line in brief.split('\n') 
            if line.strip() and (line.strip().startswith('-') or line.strip().startswith('•'))
        ][:5]
        
        if not key_points:
            key_points = [brief[:200] + "..."]
        
        credits_deducted = await deduct_credits(
            user_id=current_user.id,
            amount=summary_cost,
            db=db
        )
        
        if not credits_deducted:
            logger.error(f"Failed to deduct credits for user {current_user.id}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Credit deduction failed"
            )
        
        logger.info(f"AI summary generated successfully for case {summary_request.case_id}")
        
        return AISummaryResponse(
            case_id=summary_request.case_id,
            summary=brief,
            key_points=key_points,
            credits_used=summary_cost
        )
        
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Configuration error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AI service configuration error"
        )
    except RuntimeError as e:
        logger.error(f"AI summary generation failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service temporarily unavailable"
        )
    except Exception as e:
        logger.error(f"Unexpected error during AI summary: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred"
        )
    