"""
Phase 3: Score Finalization Routes

Handles explicit finalization of evaluations with hybrid scoring.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from backend.database import get_db
from backend.orm.user import User
from backend.routes.auth import get_current_user
from backend.security.rbac import require_teacher
from backend.services.score_integrity_service import finalize_evaluation, ScoreIntegrityError

router = APIRouter()


class FinalizeRequest(BaseModel):
    """Request to finalize an evaluation."""
    evaluation_id: int


@router.post("/evaluations/finalize")
async def finalize_score(
    request: FinalizeRequest,
    current_user: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db)
):
    """
    Finalize an evaluation with hybrid scoring.
    
    This endpoint:
    - Computes final_score based on session mode (AI_ONLY, TEACHER_ONLY, HYBRID)
    - Locks the score permanently
    - Sets is_draft=False
    - Prevents any further modifications
    
    Teacher only.
    """
    try:
        result = await finalize_evaluation(
            evaluation_id=request.evaluation_id,
            db=db,
            current_user=current_user
        )
        return result
        
    except ScoreIntegrityError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to finalize evaluation"
        )
