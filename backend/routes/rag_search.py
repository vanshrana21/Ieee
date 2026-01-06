# backend/routes/rag_search.py
"""
RAG-powered legal search endpoint.
Implements proper Retrieval-Augmented Generation pattern.
"""
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from backend.services.courtlistener_service import fetch_cases_from_courtlistener
from backend.services.ai_analysis_service import analyze_cases_with_ai

router = APIRouter(prefix="/rag", tags=["RAG Search"])
logger = logging.getLogger(__name__)


class RAGSearchRequest(BaseModel):
    """Request model for RAG-powered search."""
    query: str = Field(..., min_length=3, description="Legal search query")
    court: Optional[str] = Field(None, description="Filter by court (e.g., 'scotus', 'ca9')")
    year: Optional[int] = Field(None, ge=1700, le=2025, description="Filter by year")
    max_results: int = Field(10, ge=1, le=50, description="Maximum cases to retrieve")
    analysis_type: str = Field(
        "summary",
        description="Type of AI analysis: 'summary', 'comparison', or 'legal_issue'"
    )


class RAGSearchResponse(BaseModel):
    """Response model for RAG-powered search."""
    query: str
    case_count: int
    analysis: str
    cases: list
    success: bool = True


@router.post("/search", response_model=RAGSearchResponse)
async def rag_search(request: RAGSearchRequest):
    """
    RAG-powered legal case search and analysis.
    
    Pipeline:
    1. Retrieve real cases from CourtListener API
    2. Pass ONLY retrieved case data to AI
    3. AI analyzes and answers based on retrieved data
    4. Return structured results
    
    This ensures AI responses are grounded in real data, not hallucinated.
    """
    try:
        logger.info(f"RAG search initiated: query='{request.query}'")
        
        # STEP 1: RETRIEVAL - Fetch real cases from CourtListener
        logger.info("Step 1: Retrieving cases from CourtListener...")
        cases = fetch_cases_from_courtlistener(
            query=request.query,
            court=request.court,
            year=request.year,
            max_results=request.max_results
        )
        
        if not cases:
            logger.warning(f"No cases found for query: {request.query}")
            return RAGSearchResponse(
                query=request.query,
                case_count=0,
                analysis="No cases found matching your search criteria. Try broader search terms or different filters.",
                cases=[]
            )
        
        logger.info(f"Retrieved {len(cases)} cases from CourtListener")
        
        # STEP 2: AUGMENTATION - Prepare case data for AI
        logger.info("Step 2: Preparing case data for AI analysis...")
        
        # STEP 3: GENERATION - AI analyzes ONLY the retrieved cases
        logger.info("Step 3: Analyzing cases with AI...")
        analysis_result = analyze_cases_with_ai(
            cases=cases,
            user_query=request.query,
            analysis_type=request.analysis_type
        )
        
        # Format cases for response
        formatted_cases = [
            {
                "id": case.get("id"),
                "case_name": case["case_name"],
                "court": case["court"],
                "year": case.get("year"),
                "citation": case.get("citation"),
                "docket_number": case.get("docket_number"),
                "date_filed": case.get("date_filed"),
                "snippet": case.get("snippet", "")[:500],
                "url": case.get("url")
            }
            for case in cases
        ]
        
        logger.info(f"RAG search completed successfully: {len(cases)} cases analyzed")
        
        return RAGSearchResponse(
            query=request.query,
            case_count=len(cases),
            analysis=analysis_result["analysis"],
            cases=formatted_cases
        )
    
    except ValueError as e:
        logger.error(f"Configuration error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Service configuration error: {str(e)}"
        )
    
    except RuntimeError as e:
        logger.error(f"Service error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"External service error: {str(e)}"
        )
    
    except Exception as e:
        logger.error(f"Unexpected error in RAG search: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during search"
        )


@router.get("/case/{case_id}")
async def get_case_with_brief(case_id: int):
    """
    Get detailed case information with AI-generated brief.
    
    Args:
        case_id: CourtListener case/opinion ID
    
    Returns:
        Case details with AI-generated brief
    """
    from backend.services.courtlistener_service import get_case_details
    from backend.services.ai_analysis_service import generate_case_brief
    
    try:
        logger.info(f"Fetching case details: case_id={case_id}")
        
        # Fetch case from CourtListener
        case = get_case_details(case_id)
        
        if not case:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Case {case_id} not found"
            )
        
        # Generate AI brief based on retrieved case
        logger.info(f"Generating AI brief for case {case_id}")
        brief = generate_case_brief(case)
        
        return {
            "case": case,
            "ai_brief": brief,
            "success": True
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching case {case_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve case details"
        )
    