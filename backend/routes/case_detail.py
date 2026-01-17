# backend/routes/case_detail.py
"""
Case detail endpoint for comprehensive case information with AI analysis.
Supports both opinion and cluster IDs with proper fallback handling.
"""
import logging
from fastapi import APIRouter, HTTPException, status, Query, Depends
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any
import json

from backend.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.orm.case_content import CaseContent

from backend.services.courtlistener_service import (
    get_case_details, 
    get_cluster_details,
    get_jurisdiction_from_court
)
from backend.services.ai_analysis_service import generate_case_brief, generate_indian_case_summary

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


class FullCaseResponse(BaseModel):
    """Simplified case response for Indian students"""
    case: Dict[str, Any]
    full_text: str
    summary: Dict[str, str]
    is_curriculum_case: bool = False


@router.get("/{case_id}/full", response_model=FullCaseResponse)
async def get_full_case_view(
    case_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get full judgment and structured summary for a case.
    Prioritizes curriculum cases from database, fallbacks to CourtListener.
    Caches AI-generated summaries in the database for curriculum cases.
    """
    logger.info(f"Full case view requested for ID: {case_id}")
    
    # 1. Check if it's a curriculum case (Integer ID)
    try:
        case_id_int = int(case_id)
        stmt = select(CaseContent).where(CaseContent.id == case_id_int)
        result = await db.execute(stmt)
        case_record = result.scalar_one_or_none()
        
        if case_record:
            logger.info(f"Found curriculum case: {case_record.case_name}")
            
            # Use 'judgment' field for full text as per plan
            full_text = case_record.judgment
            
            # Check if summary is already cached in 'facts' field
            # We assume it's cached if 'facts' starts with '{' (JSON)
            summary_data = None
            if case_record.facts and case_record.facts.strip().startswith('{'):
                try:
                    summary_data = json.loads(case_record.facts)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse cached summary for case {case_id}")
            
            # If no cached summary, generate and save it
            if not summary_data:
                logger.info(f"Generating summary for curriculum case: {case_record.case_name}")
                summary_data = await generate_indian_case_summary(
                    case_record.case_name,
                    full_text
                )
                
                # Cache it in the database (facts field)
                case_record.facts = json.dumps(summary_data)
                await db.commit()
                logger.info(f"Cached summary for case {case_id}")
            
            return FullCaseResponse(
                case={
                    "title": case_record.case_name,
                    "court": case_record.court or "Unknown Court",
                    "year": str(case_record.year),
                    "citation": case_record.citation
                },
                full_text=full_text,
                summary=summary_data,
                is_curriculum_case=True
            )
    except (ValueError, TypeError):
        # Not an integer ID, continue to CourtListener
        pass

    # 2. Fallback to CourtListener (already implemented in original get_case_detail but we need structured view)
    logger.info(f"Falling back to CourtListener for case ID: {case_id}")
    try:
        case_id_int = int(case_id)
        # Try cluster first
        case_data = get_cluster_details(case_id_int)
        if not case_data:
            case_data = get_case_details(case_id_int)
            
        if not case_data or not case_data.get('has_full_text'):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Case full text not available"
            )
            
        full_text = case_data.get('plain_text') or case_data.get('html', '')
        
        # Generate summary (not caching for CourtListener cases to avoid data proliferation)
        summary_data = await generate_indian_case_summary(
            case_data.get('case_name', 'Unknown'),
            full_text
        )
        
        return FullCaseResponse(
            case={
                "title": case_data.get('case_name', 'Unknown'),
                "court": case_data.get('court', 'Unknown'),
                "year": str(case_data.get('date_filed', ''))[:4],
                "citation": case_data.get('docket_number', '')
            },
            full_text=full_text,
            summary=summary_data,
            is_curriculum_case=False
        )
        
    except Exception as e:
        logger.error(f"Failed to fetch/summarize CourtListener case: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case details not available: {str(e)}"
        )


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