"""
Phase 3: Score Integrity & Locking Service

Enforces score immutability after finalization.
Handles hybrid scoring with atomic finalization.
"""
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import joinedload

from backend.orm.classroom_session import ClassroomScore, ClassroomSession
from backend.orm.ai_evaluations import AIEvaluation
from backend.orm.user import User
from backend.errors import ErrorCode, APIError

logger = logging.getLogger(__name__)


class ScoreIntegrityError(APIError):
    """Raised when attempting to modify a locked score."""
    def __init__(self, message: str = "Score is locked and cannot be modified"):
        super().__init__(ErrorCode.SCORE_LOCKED, message)


async def finalize_evaluation(
    evaluation_id: int,
    db: AsyncSession,
    current_user: User
) -> Dict[str, Any]:
    """
    Atomically finalize an evaluation with hybrid scoring.
    
    Process:
    1. Fetch AI score and teacher score
    2. Compute final_score based on session mode
    3. Lock the score permanently
    4. Set is_draft=False
    
    Args:
        evaluation_id: AI evaluation ID
        db: Database session
        current_user: User performing finalization
        
    Returns:
        Dict with final_score and status
        
    Raises:
        ScoreIntegrityError: If already locked or invalid state
    """
    try:
        # Fetch AI evaluation
        ai_eval_result = await db.execute(
            select(AIEvaluation).where(AIEvaluation.id == evaluation_id)
        )
        ai_evaluation = ai_eval_result.scalar_one_or_none()
        
        if not ai_evaluation:
            raise ScoreIntegrityError("AI evaluation not found")
        
        if ai_evaluation.status.value != "completed":
            raise ScoreIntegrityError("AI evaluation must be completed before finalization")
        
        # Fetch classroom score
        score_result = await db.execute(
            select(ClassroomScore).options(
                joinedload(ClassroomScore.session)
            ).where(ClassroomScore.id == ai_evaluation.participant_id)
        )
        classroom_score = score_result.scalar_one_or_none()
        
        if not classroom_score:
            raise ScoreIntegrityError("Classroom score not found")
        
        if classroom_score.is_locked:
            raise ScoreIntegrityError("Score is already locked and cannot be finalized")
        
        # Get session mode (AI_ONLY, TEACHER_ONLY, HYBRID)
        session = classroom_score.session
        ai_mode = getattr(session, 'ai_judge_mode', 'HYBRID')
        
        # Compute final score based on mode
        ai_score = float(ai_evaluation.final_score) if ai_evaluation.final_score else None
        teacher_score = float(classroom_score.total_score) if classroom_score.total_score else None
        
        if ai_mode == 'AI_ONLY':
            if ai_score is None:
                raise ScoreIntegrityError("AI score required for AI_ONLY mode")
            final_score = ai_score
        elif ai_mode == 'TEACHER_ONLY':
            if teacher_score is None:
                raise ScoreIntegrityError("Teacher score required for TEACHER_ONLY mode")
            final_score = teacher_score
        else:  # HYBRID (default)
            if ai_score is None or teacher_score is None:
                raise ScoreIntegrityError("Both AI and teacher scores required for HYBRID mode")
            final_score = (ai_score * 0.6) + (teacher_score * 0.4)
        
        # Atomic update
        classroom_score.final_score = final_score
        classroom_score.is_locked = True
        classroom_score.locked_at = datetime.utcnow()
        classroom_score.is_draft = False  # Remove draft status
        classroom_score.evaluation_status = "finalized"  # Phase 3 critical fix
        
        await db.commit()
        
        logger.info(
            f"Evaluation {evaluation_id} finalized with score {final_score}",
            extra={
                "evaluation_id": evaluation_id,
                "final_score": final_score,
                "ai_score": ai_score,
                "teacher_score": teacher_score,
                "mode": ai_mode,
                "finalized_by": current_user.id
            }
        )
        
        return {
            "status": "finalized",
            "final_score": final_score,
            "ai_score": ai_score,
            "teacher_score": teacher_score,
            "mode": ai_mode
        }
        
    except ScoreIntegrityError:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.exception(f"Failed to finalize evaluation {evaluation_id}")
        raise ScoreIntegrityError(f"Failed to finalize evaluation: {str(e)}")


async def check_score_lock(score_id: int, db: AsyncSession) -> bool:
    """
    Check if a score is locked.
    
    Args:
        score_id: ClassroomScore ID
        db: Database session
        
    Returns:
        True if locked, False otherwise
    """
    result = await db.execute(
        select(ClassroomScore.is_locked).where(ClassroomScore.id == score_id)
    )
    return result.scalar() or False


def prevent_score_modification(score: ClassroomScore) -> None:
    """
    Raise exception if score is locked.
    
    Call this before any score modification.
    
    Args:
        score: ClassroomScore object to check
        
    Raises:
        ScoreIntegrityError: If score is locked
    """
    if score.is_locked:
        raise ScoreIntegrityError(
            f"Score {score.id} is locked since {score.locked_at} and cannot be modified"
        )


async def get_authoritative_score(score_id: int, db: AsyncSession) -> Optional[float]:
    """
    Get the authoritative final_score for ranking.
    
    Returns final_score if locked, otherwise None.
    
    Args:
        score_id: ClassroomScore ID
        db: Database session
        
    Returns:
        Final score if locked and available, None otherwise
    """
    result = await db.execute(
        select(ClassroomScore.final_score).where(
            and_(
                ClassroomScore.id == score_id,
                ClassroomScore.is_locked == True
            )
        )
    )
    return result.scalar()


# Hybrid scoring modes
class HybridMode:
    AI_ONLY = "AI_ONLY"
    TEACHER_ONLY = "TEACHER_ONLY"
    HYBRID = "HYBRID"  # Default: 60% AI + 40% Teacher
