"""
backend/routes/oral_round_scoring.py
Phase 3.2: Judge scoring API for oral rounds
Isolated from existing routes - NEW FILE
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel, Field, validator
import json

from backend.database import get_db
from backend.orm.oral_round_score import OralRoundScore, ScoreCriterion
from backend.orm.oral_round import OralRound
from backend.orm.team import Team
from backend.orm.user import User, UserRole
from backend.routes.auth import get_current_user

router = APIRouter(prefix="/oral-rounds", tags=["oral-round-scoring"])


# ================= SCHEMAS =================

class ScoreCreate(BaseModel):
    """Request to create or update a score"""
    team_id: int
    team_side: str
    legal_reasoning: int = Field(..., ge=1, le=5, description="Legal reasoning score 1-5")
    citation_format: int = Field(..., ge=1, le=5, description="Citation format score 1-5")
    courtroom_etiquette: int = Field(..., ge=1, le=5, description="Courtroom etiquette score 1-5")
    responsiveness: int = Field(..., ge=1, le=5, description="Responsiveness score 1-5")
    time_management: int = Field(..., ge=1, le=5, description="Time management score 1-5")
    written_feedback: Optional[str] = Field(None, description="Written feedback")
    strengths: Optional[List[str]] = Field(None, description="List of strengths")
    areas_for_improvement: Optional[List[str]] = Field(None, description="Areas for improvement")
    is_draft: bool = Field(True, description="Save as draft or submit")
    
    @validator('team_side')
    def validate_side(cls, v):
        if v not in ["petitioner", "respondent"]:
            raise ValueError("team_side must be 'petitioner' or 'respondent'")
        return v


class ScoreResponse(BaseModel):
    """Score response model"""
    id: int
    round_id: int
    judge_id: int
    team_id: int
    team_side: str
    legal_reasoning: int
    citation_format: int
    courtroom_etiquette: int
    responsiveness: int
    time_management: int
    total_score: float
    max_possible: int
    written_feedback: Optional[str]
    strengths: Optional[str]
    areas_for_improvement: Optional[str]
    is_draft: bool
    is_submitted: bool
    submitted_at: Optional[str]
    created_at: str
    
    class Config:
        from_attributes = True


class RoundSummary(BaseModel):
    """Summary of all scores for a round"""
    round_id: int
    petitioner_score: Optional[ScoreResponse]
    respondent_score: Optional[ScoreResponse]
    petitioner_total: Optional[float]
    respondent_total: Optional[float]
    winning_side: Optional[str]


# ================= HELPERS =================

def _check_judge_permission(current_user: User):
    """Verify user has judge/faculty/admin role"""
    if current_user.role not in [
        UserRole.JUDGE, 
        UserRole.FACULTY, 
        UserRole.ADMIN, 
        UserRole.SUPER_ADMIN
    ]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only judges/faculty/admins can manage scores"
        )


async def _get_round_or_404(round_id: int, db: AsyncSession):
    """Fetch round or raise 404"""
    result = await db.execute(select(OralRound).where(OralRound.id == round_id))
    round_obj = result.scalar_one_or_none()
    if not round_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Oral round not found"
        )
    return round_obj


def _calculate_total_score(scores: dict) -> float:
    """Calculate average of 5 criteria"""
    total = sum([
        scores.get('legal_reasoning', 0),
        scores.get('citation_format', 0),
        scores.get('courtroom_etiquette', 0),
        scores.get('responsiveness', 0),
        scores.get('time_management', 0)
    ])
    return round(total / 5.0, 2)


# ================= ROUTES =================

@router.post("/{round_id}/scores", response_model=ScoreResponse)
async def create_or_update_score(
    round_id: int,
    score_data: ScoreCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create or update a score for a team in an oral round.
    Judges can save drafts or submit final scores.
    """
    _check_judge_permission(current_user)
    
    # Verify round exists
    oral_round = await _get_round_or_404(round_id, db)
    
    # Verify team belongs to this round
    if score_data.team_id not in [oral_round.petitioner_team_id, oral_round.respondent_team_id]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Team not part of this round"
        )
    
    # Calculate total score
    total = _calculate_total_score({
        'legal_reasoning': score_data.legal_reasoning,
        'citation_format': score_data.citation_format,
        'courtroom_etiquette': score_data.courtroom_etiquette,
        'responsiveness': score_data.responsiveness,
        'time_management': score_data.time_management
    })
    
    # Check if score already exists for this judge+team combination
    existing_result = await db.execute(
        select(OralRoundScore).where(
            OralRoundScore.round_id == round_id,
            OralRoundScore.judge_id == current_user.id,
            OralRoundScore.team_id == score_data.team_id
        )
    )
    existing = existing_result.scalar_one_or_none()
    
    if existing:
        # Update existing score
        existing.legal_reasoning = score_data.legal_reasoning
        existing.citation_format = score_data.citation_format
        existing.courtroom_etiquette = score_data.courtroom_etiquette
        existing.responsiveness = score_data.responsiveness
        existing.time_management = score_data.time_management
        existing.total_score = total
        existing.written_feedback = score_data.written_feedback
        existing.strengths = json.dumps(score_data.strengths) if score_data.strengths else None
        existing.areas_for_improvement = json.dumps(score_data.areas_for_improvement) if score_data.areas_for_improvement else None
        existing.is_draft = score_data.is_draft
        existing.is_submitted = not score_data.is_draft
        if not score_data.is_draft:
            existing.submitted_at = datetime.now(timezone.utc)
        existing.updated_at = datetime.now(timezone.utc)
        score_obj = existing
    else:
        # Create new score
        score_obj = OralRoundScore(
            round_id=round_id,
            judge_id=current_user.id,
            team_id=score_data.team_id,
            team_side=score_data.team_side,
            legal_reasoning=score_data.legal_reasoning,
            citation_format=score_data.citation_format,
            courtroom_etiquette=score_data.courtroom_etiquette,
            responsiveness=score_data.responsiveness,
            time_management=score_data.time_management,
            total_score=total,
            written_feedback=score_data.written_feedback,
            strengths=json.dumps(score_data.strengths) if score_data.strengths else None,
            areas_for_improvement=json.dumps(score_data.areas_for_improvement) if score_data.areas_for_improvement else None,
            is_draft=score_data.is_draft,
            is_submitted=not score_data.is_draft,
            submitted_at=datetime.now(timezone.utc) if not score_data.is_draft else None
        )
        db.add(score_obj)
    
    await db.commit()
    await db.refresh(score_obj)
    
    return ScoreResponse(
        id=score_obj.id,
        round_id=score_obj.round_id,
        judge_id=score_obj.judge_id,
        team_id=score_obj.team_id,
        team_side=score_obj.team_side.value if score_obj.team_side else score_data.team_side,
        legal_reasoning=score_obj.legal_reasoning,
        citation_format=score_obj.citation_format,
        courtroom_etiquette=score_obj.courtroom_etiquette,
        responsiveness=score_obj.responsiveness,
        time_management=score_obj.time_management,
        total_score=score_obj.total_score,
        max_possible=score_obj.max_possible,
        written_feedback=score_obj.written_feedback,
        strengths=score_obj.strengths,
        areas_for_improvement=score_obj.areas_for_improvement,
        is_draft=score_obj.is_draft,
        is_submitted=score_obj.is_submitted,
        submitted_at=score_obj.submitted_at.isoformat() if score_obj.submitted_at else None,
        created_at=score_obj.created_at.isoformat() if score_obj.created_at else None
    )


@router.get("/{round_id}/scores", response_model=List[ScoreResponse])
async def get_round_scores(
    round_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all scores for an oral round.
    Judges see all scores, teams see only submitted scores for their teams.
    """
    # Verify round exists
    await _get_round_or_404(round_id, db)
    
    # Build query
    query = select(OralRoundScore).where(OralRoundScore.round_id == round_id)
    
    # Non-judges only see submitted scores
    if current_user.role not in [
        UserRole.JUDGE, 
        UserRole.FACULTY, 
        UserRole.ADMIN, 
        UserRole.SUPER_ADMIN
    ]:
        query = query.where(OralRoundScore.is_submitted == True)
    
    result = await db.execute(query)
    scores = result.scalars().all()
    
    return [
        ScoreResponse(
            id=s.id,
            round_id=s.round_id,
            judge_id=s.judge_id,
            team_id=s.team_id,
            team_side=s.team_side.value if s.team_side else None,
            legal_reasoning=s.legal_reasoning,
            citation_format=s.citation_format,
            courtroom_etiquette=s.courtroom_etiquette,
            responsiveness=s.responsiveness,
            time_management=s.time_management,
            total_score=s.total_score,
            max_possible=s.max_possible,
            written_feedback=s.written_feedback,
            strengths=s.strengths,
            areas_for_improvement=s.areas_for_improvement,
            is_draft=s.is_draft,
            is_submitted=s.is_submitted,
            submitted_at=s.submitted_at.isoformat() if s.submitted_at else None,
            created_at=s.created_at.isoformat() if s.created_at else None
        )
        for s in scores
    ]


@router.get("/{round_id}/scores/summary", response_model=RoundSummary)
async def get_round_summary(
    round_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get summary of scores for both teams in a round.
    Shows petitioner's and respondent's scores side by side.
    """
    # Verify round exists
    oral_round = await _get_round_or_404(round_id, db)
    
    # Get all submitted scores for this round
    query = select(OralRoundScore).where(
        OralRoundScore.round_id == round_id,
        OralRoundScore.is_submitted == True
    )
    
    # Non-judges only see submitted scores
    if current_user.role not in [
        UserRole.JUDGE, 
        UserRole.FACULTY, 
        UserRole.ADMIN, 
        UserRole.SUPER_ADMIN
    ]:
        query = query.where(OralRoundScore.is_submitted == True)
    
    result = await db.execute(query)
    scores = result.scalars().all()
    
    # Separate by side
    petitioner_scores = [s for s in scores if s.team_side == "petitioner"]
    respondent_scores = [s for s in scores if s.team_side == "respondent"]
    
    # Get latest score for each side (in case of multiple judges)
    petitioner_score = max(petitioner_scores, key=lambda x: x.created_at) if petitioner_scores else None
    respondent_score = max(respondent_scores, key=lambda x: x.created_at) if respondent_scores else None
    
    # Calculate totals
    petitioner_total = petitioner_score.total_score if petitioner_score else None
    respondent_total = respondent_score.total_score if respondent_score else None
    
    # Determine winner
    winning_side = None
    if petitioner_total and respondent_total:
        if petitioner_total > respondent_total:
            winning_side = "petitioner"
        elif respondent_total > petitioner_total:
            winning_side = "respondent"
        else:
            winning_side = "tie"
    
    return RoundSummary(
        round_id=round_id,
        petitioner_score=ScoreResponse(
            id=petitioner_score.id,
            round_id=petitioner_score.round_id,
            judge_id=petitioner_score.judge_id,
            team_id=petitioner_score.team_id,
            team_side=petitioner_score.team_side.value,
            legal_reasoning=petitioner_score.legal_reasoning,
            citation_format=petitioner_score.citation_format,
            courtroom_etiquette=petitioner_score.courtroom_etiquette,
            responsiveness=petitioner_score.responsiveness,
            time_management=petitioner_score.time_management,
            total_score=petitioner_score.total_score,
            max_possible=petitioner_score.max_possible,
            written_feedback=petitioner_score.written_feedback,
            strengths=petitioner_score.strengths,
            areas_for_improvement=petitioner_score.areas_for_improvement,
            is_draft=petitioner_score.is_draft,
            is_submitted=petitioner_score.is_submitted,
            submitted_at=petitioner_score.submitted_at.isoformat() if petitioner_score.submitted_at else None,
            created_at=petitioner_score.created_at.isoformat()
        ) if petitioner_score else None,
        respondent_score=ScoreResponse(
            id=respondent_score.id,
            round_id=respondent_score.round_id,
            judge_id=respondent_score.judge_id,
            team_id=respondent_score.team_id,
            team_side=respondent_score.team_side.value,
            legal_reasoning=respondent_score.legal_reasoning,
            citation_format=respondent_score.citation_format,
            courtroom_etiquette=respondent_score.courtroom_etiquette,
            responsiveness=respondent_score.responsiveness,
            time_management=respondent_score.time_management,
            total_score=respondent_score.total_score,
            max_possible=respondent_score.max_possible,
            written_feedback=respondent_score.written_feedback,
            strengths=respondent_score.strengths,
            areas_for_improvement=respondent_score.areas_for_improvement,
            is_draft=respondent_score.is_draft,
            is_submitted=respondent_score.is_submitted,
            submitted_at=respondent_score.submitted_at.isoformat() if respondent_score.submitted_at else None,
            created_at=respondent_score.created_at.isoformat()
        ) if respondent_score else None,
        petitioner_total=petitioner_total,
        respondent_total=respondent_total,
        winning_side=winning_side
    )


@router.post("/{round_id}/scores/{score_id}/submit")
async def submit_score(
    round_id: int,
    score_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Submit a draft score (move from draft to final).
    Only the judge who created the score can submit it.
    """
    _check_judge_permission(current_user)
    
    # Fetch score
    result = await db.execute(
        select(OralRoundScore).where(OralRoundScore.id == score_id)
    )
    score = result.scalar_one_or_none()
    
    if not score:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Score not found"
        )
    
    # Security: Only score creator can submit
    if score.judge_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the score creator can submit"
        )
    
    # Verify score belongs to this round
    if score.round_id != round_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Score does not belong to this round"
        )
    
    # Mark as submitted
    score.is_draft = False
    score.is_submitted = True
    score.submitted_at = datetime.now(timezone.utc)
    score.updated_at = datetime.now(timezone.utc)
    
    await db.commit()
    
    return {
        "message": "Score submitted successfully",
        "score_id": score_id,
        "total_score": score.total_score
    }


@router.delete("/{round_id}/scores/{score_id}")
async def delete_score(
    round_id: int,
    score_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a score (only if it's still a draft).
    Only the judge who created the score can delete it.
    """
    _check_judge_permission(current_user)
    
    # Fetch score
    result = await db.execute(
        select(OralRoundScore).where(OralRoundScore.id == score_id)
    )
    score = result.scalar_one_or_none()
    
    if not score:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Score not found"
        )
    
    # Security: Only score creator can delete
    if score.judge_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the score creator can delete"
        )
    
    # Can only delete drafts
    if not score.is_draft:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete submitted scores"
        )
    
    await db.delete(score)
    await db.commit()
    
    return {"message": "Draft score deleted successfully"}
