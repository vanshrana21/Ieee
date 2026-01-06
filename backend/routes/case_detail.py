# backend/routes/case_detail.py
"""
Case detail endpoint for comprehensive case information with AI analysis.
Supports both opinion and cluster IDs with proper fallback handling.
"""
import logging
from fastapi import APIRouter, HTTPException, status, Query
from pydantic import BaseModel, Field
from typing import Optional, Dict

from backend.services.courtlistener_service import (
    get_case_details, 
    get_cluster_details,
    get_jurisdiction_from_court
)
from backend.services.ai_analysis_service import generate_case_brief

router = APIRouter(prefix="/cases", tags=["Case Details"])
logger = logging.getLogger(__name__)


class CaseMetadata(BaseModel):
    """Case metadata section"""
    case_name: str
    court: str
    court_full_name: Optional[str] = None
    date_filed: Optional[str] = None
    judges: Optional[str] = None
    docket_number: Optional[str] = None
    jurisdiction: str
    citations: int = 0
    opinion_type: Optional[str] = None
    author: Optional[str] = None


class AIBrief(BaseModel):
    """AI-generated case brief"""
    case_summary: str
    legal_issues: str
    holding: str
    reasoning: str
    outcome: str
    full_brief: str


class FullJudgment(BaseModel):
    """Full judgment text and source"""
    plain_text: Optional[str] = None
    html: Optional[str] = None
    source_url: str
    download_url: Optional[str] = None
    has_text: bool = False


class CaseDetailResponse(BaseModel):
    """Complete case detail response"""
    case_id: str  # Changed to string to handle both opinion and cluster IDs
    metadata: CaseMetadata
    ai_brief: Optional[AIBrief] = None
    ai_brief_available: bool
    full_judgment: FullJudgment
    success: bool = True


@router.get("/{case_id}", response_model=CaseDetailResponse)
async def get_case_detail(
    case_id: str,
    id_type: Optional[str] = Query(None, description="Type of ID: 'opinion' or 'cluster'")
):
    """
    Get comprehensive case details with AI-generated brief.
    Automatically detects whether case_id is an opinion or cluster ID.
    
    Pipeline:
    1. Fetch full case details from CourtListener API
    2. Extract metadata (case name, court, judges, etc.)
    3. If opinion text exists, generate AI brief
    4. Return structured response
    
    Args:
        case_id: CourtListener opinion or cluster ID
        id_type: Optional hint for ID type ('opinion' or 'cluster')
    
    Returns:
        Structured case details with AI analysis
    """
    try:
        logger.info(f"Fetching case details for ID: {case_id}, type: {id_type}")
        
        # Convert to int if possible
        try:
            case_id_int = int(case_id)
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid case ID: {case_id}"
            )
        
        # STEP 1: Fetch case from CourtListener
        # Try opinion first, then cluster
        case = None
        fetch_type = None
        
        if id_type == "cluster" or id_type is None:
            case = get_cluster_details(case_id_int)
            if case:
                fetch_type = "cluster"
                logger.info(f"Retrieved case as cluster: {case.get('case_name', 'Unknown')}")
        
        if not case and (id_type == "opinion" or id_type is None):
            case = get_case_details(case_id_int)
            if case:
                fetch_type = "opinion"
                logger.info(f"Retrieved case as opinion: {case.get('case_name', 'Unknown')}")
        
        if not case:
            logger.warning(f"Case not found: case_id={case_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Case with ID {case_id} not found"
            )
        
        # STEP 2: Extract metadata
        jurisdiction = get_jurisdiction_from_court(case.get('court', ''))
        
        metadata = CaseMetadata(
            case_name=case.get('case_name', 'Unknown Case'),
            court=case.get('court', 'Unknown Court'),
            court_full_name=case.get('court_full_name'),
            date_filed=case.get('date_filed'),
            judges=case.get('judges'),
            docket_number=case.get('docket_number'),
            jurisdiction=jurisdiction,
            citations=case.get('citations', 0),
            opinion_type=case.get('opinion_type'),
            author=case.get('author')
        )
        
        # STEP 3: Generate AI brief if text is available
        ai_brief = None
        ai_brief_available = False
        
        if case.get('has_full_text', False):
            logger.info(f"Generating AI brief for case {case_id}")
            try:
                brief_data = generate_case_brief(case)
                if brief_data:
                    ai_brief = AIBrief(**brief_data)
                    ai_brief_available = True
                    logger.info(f"AI brief generated successfully for case {case_id}")
                else:
                    logger.info(f"AI brief generation skipped (insufficient text) for case {case_id}")
            except Exception as e:
                logger.error(f"AI brief generation failed for case {case_id}: {str(e)}")
                # Continue without AI brief rather than failing the entire request
        else:
            logger.info(f"No opinion text available for case {case_id}, skipping AI brief")
        
        # STEP 4: Prepare full judgment section
        full_judgment = FullJudgment(
            plain_text=case.get('plain_text'),
            html=case.get('html'),
            source_url=case.get('source_url', ''),
            download_url=case.get('download_url'),
            has_text=case.get('has_full_text', False)
        )
        
        logger.info(f"Successfully prepared case detail response for case {case_id}")
        
        return CaseDetailResponse(
            case_id=str(case_id),
            metadata=metadata,
            ai_brief=ai_brief,
            ai_brief_available=ai_brief_available,
            full_judgment=full_judgment
        )
    
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Configuration error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Service configuration error"
        )
    except Exception as e:
        logger.error(f"Unexpected error fetching case details: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve case details"
        )