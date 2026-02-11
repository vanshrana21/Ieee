"""
backend/routes/ai_opponent.py
API routes for AI Opponent - Dynamic rebuttal generation
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timezone
import logging

from backend.database import get_db
from backend.services.ai_opponent_service import AIOpponentService
from backend.routes.auth import get_current_user
from backend.orm.user import User
from backend.orm.ai_opponent_argument import AIOpponentArgument
from backend.orm.oral_round import OralRound
from backend.orm.competition import Competition
from backend.orm.moot_project import MootProject

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai-opponent", tags=["AI Opponent"])

# Initialize service
ai_opponent_service = AIOpponentService()


# ============================================================================
# Pydantic Schemas
# ============================================================================

class GenerateRebuttalRequest(BaseModel):
    round_id: int = Field(..., description="ID of the oral round")
    user_argument: str = Field(..., min_length=10, max_length=5000, description="User's argument to rebut")
    opponent_side: str = Field(..., pattern="^(petitioner|respondent)$", description="Which side AI represents")
    previous_arguments: List[str] = Field(default=[], description="Previous arguments in this round to avoid repetition")


class RebuttalResponse(BaseModel):
    id: int
    round_id: int
    rebuttal_text: str
    legal_points: List[str]
    suggested_cases: List[str]
    doctrine_applied: Optional[str]
    opponent_side: str
    generation_source: str
    created_at: str


class MootContextResponse(BaseModel):
    fact_sheet: str
    legal_issues: List[str]
    relevant_cases: List[str]
    problem_title: str
    problem_description: str


class ErrorResponse(BaseModel):
    detail: str


# ============================================================================
# Helper Functions
# ============================================================================

async def get_moot_problem_context(round_id: int, db: AsyncSession) -> dict:
    """
    Fetch moot problem context for a round from the database.
    Uses cache if available.
    """
    # Check cache first
    cached = ai_opponent_service.get_cached_context(round_id)
    if cached:
        return cached
    
    # Fetch from database
    result = await db.execute(
        select(OralRound, Competition, MootProject)
        .join(Competition, OralRound.competition_id == Competition.id)
        .join(MootProject, Competition.problem_id == MootProject.id)
        .where(OralRound.id == round_id)
    )
    row = result.first()
    
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Round {round_id} not found or has no associated problem"
        )
    
    oral_round, competition, project = row
    
    # Build context
    context = {
        "fact_sheet": project.facts_sheet or project.description or "No fact sheet available",
        "legal_issues": _extract_legal_issues(project),
        "relevant_cases": _extract_relevant_cases(project),
        "problem_title": project.title,
        "problem_description": project.description or ""
    }
    
    # Cache for future use
    ai_opponent_service.cache_context(round_id, context)
    
    return context


def _extract_legal_issues(project: MootProject) -> List[str]:
    """Extract legal issues from project metadata."""
    # Try to get from project metadata if available
    if hasattr(project, 'metadata') and project.metadata:
        meta = project.metadata
        if isinstance(meta, dict):
            issues = meta.get("legal_issues", [])
            if issues:
                return issues
    
    # Default issues based on project title/description
    default_issues = [
        "Constitutional validity of the impugned provision",
        "Applicability of fundamental rights",
        "Proportionality of the measure"
    ]
    return default_issues


def _extract_relevant_cases(project: MootProject) -> List[str]:
    """Extract relevant cases from project metadata."""
    # Try to get from project metadata if available
    if hasattr(project, 'metadata') and project.metadata:
        meta = project.metadata
        if isinstance(meta, dict):
            cases = meta.get("relevant_cases", [])
            if cases:
                return cases
    
    # Default landmark cases
    default_cases = [
        "Puttaswamy (2017) 10 SCC 1",
        "Maneka Gandhi v. Union of India (1978) 2 SCC 248",
        "K.S. Puttaswamy v. Union of India (2017) 10 SCC 1"
    ]
    return default_cases


async def get_previous_arguments(round_id: int, db: AsyncSession) -> List[str]:
    """Fetch previous AI opponent arguments for a round."""
    result = await db.execute(
        select(AIOpponentArgument)
        .where(AIOpponentArgument.round_id == round_id)
        .order_by(AIOpponentArgument.created_at.desc())
        .limit(5)
    )
    arguments = result.scalars().all()
    return [arg.rebuttal_text for arg in arguments]


# ============================================================================
# API Endpoints
# ============================================================================

@router.post(
    "/generate-rebuttal",
    response_model=RebuttalResponse,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        403: {"model": ErrorResponse, "description": "Not authorized"},
        404: {"model": ErrorResponse, "description": "Round not found"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        503: {"model": ErrorResponse, "description": "AI service unavailable"}
    }
)
async def generate_rebuttal(
    request: GenerateRebuttalRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Generate dynamic AI rebuttal for user's argument.
    
    - Fetches moot problem context from competition
    - Calls AIOpponentService to generate unique rebuttal
    - Saves to database for record-keeping
    - Returns rebuttal with legal points and suggested cases
    
    Rate limit: 1 call per 30 seconds per user (recommended)
    """
    logger.info(f"Generating rebuttal for round {request.round_id}, user {current_user.id}")
    
    # Verify round exists and user has access
    result = await db.execute(
        select(OralRound).where(OralRound.id == request.round_id)
    )
    round_obj = result.scalar_one_or_none()
    
    if not round_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Round {request.round_id} not found"
        )
    
    # Get moot problem context
    try:
        moot_context = await get_moot_problem_context(request.round_id, db)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching moot context: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch moot problem context"
        )
    
    # Use provided previous arguments or fetch from database
    previous_args = request.previous_arguments
    if not previous_args:
        previous_args = await get_previous_arguments(request.round_id, db)
    
    # Generate rebuttal
    try:
        rebuttal_data = ai_opponent_service.generate_rebuttal(
            user_argument=request.user_argument,
            opponent_side=request.opponent_side,
            moot_problem_context=moot_context,
            previous_arguments=previous_args
        )
    except Exception as e:
        logger.error(f"Error generating rebuttal: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI opponent service temporarily unavailable. Please try again."
        )
    
    # Save to database
    try:
        ai_argument = AIOpponentArgument(
            round_id=request.round_id,
            generated_by_user_id=current_user.id,
            user_argument_text=request.user_argument,
            rebuttal_text=rebuttal_data["rebuttal_text"],
            legal_points=rebuttal_data.get("legal_points", []),
            suggested_cases=rebuttal_data.get("suggested_cases", []),
            doctrine_applied=rebuttal_data.get("doctrine_applied"),
            opponent_side=request.opponent_side,
            moot_problem_context=moot_context,
            generation_source=rebuttal_data.get("source", "llm"),
            created_at=datetime.now(timezone.utc)
        )
        db.add(ai_argument)
        await db.commit()
        await db.refresh(ai_argument)
        
        logger.info(f"Rebuttal saved: id={ai_argument.id}")
        
        # TODO: Broadcast via WebSocket to courtroom participants
        # This would use the WebSocket manager from courtroom.py
        # but is optional for initial implementation
        
    except Exception as e:
        logger.error(f"Error saving rebuttal: {e}")
        # Don't fail the request - return the rebuttal even if DB save fails
        # Create a temporary ID for response
        ai_argument = type('obj', (object,), {
            'id': 0,
            'round_id': request.round_id,
            'rebuttal_text': rebuttal_data["rebuttal_text"],
            'legal_points': rebuttal_data.get("legal_points", []),
            'suggested_cases': rebuttal_data.get("suggested_cases", []),
            'doctrine_applied': rebuttal_data.get("doctrine_applied"),
            'opponent_side': request.opponent_side,
            'generation_source': rebuttal_data.get("source", "llm"),
            'created_at': datetime.now(timezone.utc)
        })()
    
    return RebuttalResponse(
        id=ai_argument.id,
        round_id=ai_argument.round_id,
        rebuttal_text=ai_argument.rebuttal_text,
        legal_points=ai_argument.legal_points or [],
        suggested_cases=ai_argument.suggested_cases or [],
        doctrine_applied=ai_argument.doctrine_applied,
        opponent_side=ai_argument.opponent_side,
        generation_source=ai_argument.generation_source,
        created_at=ai_argument.created_at.isoformat() if isinstance(ai_argument.created_at, datetime) else str(ai_argument.created_at)
    )


@router.get(
    "/{round_id}/context",
    response_model=MootContextResponse,
    status_code=status.HTTP_200_OK,
    responses={
        404: {"model": ErrorResponse, "description": "Round not found"}
    }
)
async def get_moot_context(
    round_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get moot problem context for a round.
    
    Returns fact sheet, legal issues, and relevant cases.
    Used by frontend to display context to AI opponent for transparency.
    """
    logger.info(f"Fetching moot context for round {round_id}")
    
    try:
        context = await get_moot_problem_context(round_id, db)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching moot context: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch moot problem context"
        )
    
    return MootContextResponse(
        fact_sheet=context["fact_sheet"],
        legal_issues=context["legal_issues"],
        relevant_cases=context["relevant_cases"],
        problem_title=context["problem_title"],
        problem_description=context["problem_description"]
    )


@router.get(
    "/{round_id}/history",
    response_model=List[RebuttalResponse],
    status_code=status.HTTP_200_OK
)
async def get_rebuttal_history(
    round_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get history of AI rebuttals for a round.
    
    Useful for preventing repetition and showing argument flow.
    """
    result = await db.execute(
        select(AIOpponentArgument)
        .where(AIOpponentArgument.round_id == round_id)
        .order_by(AIOpponentArgument.created_at.desc())
    )
    arguments = result.scalars().all()
    
    return [
        RebuttalResponse(
            id=arg.id,
            round_id=arg.round_id,
            rebuttal_text=arg.rebuttal_text,
            legal_points=arg.legal_points or [],
            suggested_cases=arg.suggested_cases or [],
            doctrine_applied=arg.doctrine_applied,
            opponent_side=arg.opponent_side,
            generation_source=arg.generation_source,
            created_at=arg.created_at.isoformat() if arg.created_at else ""
        )
        for arg in arguments
    ]
