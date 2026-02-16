"""
backend/routes/oral_round_ai_hybrid.py
Phase 4: AI Hybrid Modes API for Oral Rounds
3 modes: AI Judge, AI Opponent, AI Coach
Isolated from existing routes - NEW FILE
7 endpoints total
"""
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from pydantic import BaseModel, Field
import json

from backend.database import get_db
from backend.orm.ai_judge_evaluation import AIJudgeEvaluation
from backend.orm.ai_opponent_session import AIOpponentSession, AIOpponentRole, AIOpponentSide
from backend.orm.ai_coach_hint import AICoachHint, HintType
from backend.orm.oral_round import OralRound
from backend.orm.team import Team, TeamMember
from backend.orm.user import User, UserRole
from backend.routes.auth import get_current_user

router = APIRouter(prefix="/oral-rounds", tags=["ai-hybrid-modes"])


# ================= SCHEMAS =================

# AI Judge Schemas
class AIJudgeEvaluateRequest(BaseModel):
    team_id: int
    team_side: str = Field(..., pattern="^(petitioner|respondent)$")
    argument_text: str = Field(..., min_length=10, max_length=5000)


class AIJudgeScore(BaseModel):
    legal_accuracy: int = Field(..., ge=1, le=5)
    citation: int = Field(..., ge=1, le=5)
    etiquette: int = Field(..., ge=1, le=5)
    structure: int = Field(..., ge=1, le=5)
    persuasiveness: int = Field(..., ge=1, le=5)


class AIBehaviorData(BaseModel):
    has_my_lord: bool
    valid_scc_citation: bool
    cites_case_properly: bool
    uses_precedent: bool


class AIJudgeEvaluationResponse(BaseModel):
    id: int
    round_id: int
    team_id: int
    team_name: Optional[str]
    team_side: str
    submitted_by_user_id: int
    submitted_by_name: Optional[str]
    argument_text: str
    ai_feedback: str
    ai_scores: AIJudgeScore
    ai_behavior_data: AIBehaviorData
    is_official: bool
    created_at: str
    
    class Config:
        from_attributes = True


# AI Opponent Schemas
class AIOpponentEnableRequest(BaseModel):
    team_id: int
    ai_role: str = Field(..., pattern="^(speaker_1|speaker_2|researcher_1|researcher_2)$")
    opponent_side: str = Field(..., pattern="^(petitioner|respondent)$")
    context_summary: Optional[str] = None


class AIOpponentSessionResponse(BaseModel):
    id: int
    round_id: int
    team_id: int
    team_name: Optional[str]
    ai_role: str
    opponent_side: str
    is_active: bool
    created_at: str
    
    class Config:
        from_attributes = True


# AI Coach Schemas
class AICoachHintResponse(BaseModel):
    id: int
    round_id: int
    team_id: int
    user_id: int
    user_name: Optional[str]
    hint_type: str
    hint_text: str
    trigger_keyword: Optional[str]
    is_displayed: bool
    is_dismissed: bool
    created_at: str
    
    class Config:
        from_attributes = True


# ================= HELPERS =================

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


def _check_judge_permission(current_user: User):
    """Verify user can mark AI scores as official"""
    if current_user.role not in [
        UserRole.teacher, 
        UserRole.teacher, 
        UserRole.teacher, 
        UserRole.teacher
    ]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only judges/faculty/admins can mark AI scores as official"
        )


async def _check_team_captain(team_id: int, user_id: int, db: AsyncSession):
    """Verify user is team captain"""
    result = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == user_id
        )
    )
    member = result.scalar_one_or_none()
    if not member or not member.is_captain:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only team captains can manage AI opponents"
        )


def _mock_ai_analysis(argument_text: str, team_side: str) -> dict:
    """
    Mock AI analysis for development.
    In production, this calls ai_judge_service.analyze_argument()
    """
    # Extract case names for citation analysis
    case_names = ["Puttaswamy", "Navtej", "Vishaka", "Kesavananda"]
    found_cases = [c for c in case_names if c.lower() in argument_text.lower()]
    
    has_my_lord = "my lord" in argument_text.lower() or "my lords" in argument_text.lower()
    has_scc_format = any(f"({year})" in argument_text for year in ["2017", "2018", "2019", "2020"])
    cites_case = len(found_cases) > 0
    uses_precedent = any(word in argument_text.lower() for word in ["relied upon", "following", "cited in", "as held in"])
    
    # Calculate scores
    legal_score = min(5, 3 + len(found_cases))
    citation_score = 5 if has_scc_format else 3 if cites_case else 2
    etiquette_score = 5 if has_my_lord else 3
    structure_score = 4 if uses_precedent else 3
    persuasive_score = 4
    
    # Build feedback
    feedback_parts = []
    if not has_my_lord:
        feedback_parts.append("Missing formal address. Start with 'My Lord' or 'My Lords'.")
    if cites_case and not has_scc_format:
        feedback_parts.append(f"Cite cases in SCC format: e.g., '(2017) 10 SCC 1' for {found_cases[0]}.")
    if not cites_case:
        feedback_parts.append("Consider citing relevant case law to strengthen your argument.")
    if not uses_precedent:
        feedback_parts.append("Use phrases like 'as held in' to demonstrate precedent application.")
    
    feedback = " ".join(feedback_parts) if feedback_parts else "Good argument structure. Well done!"
    
    # Generate next question if appropriate
    if cites_case:
        feedback += f" Next question: Cite {found_cases[0]} as (2017) 10 SCC 1."
    
    return {
        "feedback": feedback,
        "scores": {
            "legal_accuracy": legal_score,
            "citation": citation_score,
            "etiquette": etiquette_score,
            "structure": structure_score,
            "persuasiveness": persuasive_score
        },
        "behavior": {
            "has_my_lord": has_my_lord,
            "valid_scc_citation": has_scc_format,
            "cites_case_properly": cites_case,
            "uses_precedent": uses_precedent
        }
    }


# ================= AI JUDGE ROUTES (Mode 1) =================

@router.post("/{round_id}/ai-judge/evaluate", response_model=AIJudgeEvaluationResponse)
async def ai_judge_evaluate(
    round_id: int,
    request: AIJudgeEvaluateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Submit argument to AI judge for evaluation.
    All participants can submit. Returns AI feedback, scores, and behavior badges.
    """
    # Verify round exists
    round_obj = await _get_round_or_404(round_id, db)
    
    # Verify team belongs to round
    if request.team_id not in [round_obj.petitioner_team_id, round_obj.respondent_team_id]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Team not part of this round"
        )
    
    # Call AI analysis (mock for now - in production calls ai_judge_service)
    ai_result = _mock_ai_analysis(request.argument_text, request.team_side)
    
    # Create evaluation record
    evaluation = AIJudgeEvaluation(
        round_id=round_id,
        team_id=request.team_id,
        team_side=request.team_side,
        submitted_by_user_id=current_user.id,
        argument_text=request.argument_text,
        submitted_at=datetime.now(timezone.utc),
        ai_feedback=ai_result["feedback"],
        ai_scores_json=json.dumps(ai_result["scores"]),
        ai_behavior_data_json=json.dumps(ai_result["behavior"]),
        is_official=False
    )
    
    db.add(evaluation)
    await db.commit()
    await db.refresh(evaluation)
    
    # Get team name
    team_result = await db.execute(select(Team).where(Team.id == request.team_id))
    team = team_result.scalar_one_or_none()
    
    return AIJudgeEvaluationResponse(
        id=evaluation.id,
        round_id=evaluation.round_id,
        team_id=evaluation.team_id,
        team_name=team.name if team else None,
        team_side=evaluation.team_side.value,
        submitted_by_user_id=evaluation.submitted_by_user_id,
        submitted_by_name=current_user.name,
        argument_text=evaluation.argument_text,
        ai_feedback=evaluation.ai_feedback,
        ai_scores=AIJudgeScore(**ai_result["scores"]),
        ai_behavior_data=AIBehaviorData(**ai_result["behavior"]),
        is_official=evaluation.is_official,
        created_at=evaluation.created_at.isoformat()
    )


@router.get("/{round_id}/ai-judge/evaluations", response_model=List[AIJudgeEvaluationResponse])
async def list_ai_judge_evaluations(
    round_id: int,
    official_only: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List all AI judge evaluations for a round.
    Everyone can view. Filter by official_only to see only official scores.
    """
    # Verify round exists
    await _get_round_or_404(round_id, db)
    
    # Build query
    query = select(AIJudgeEvaluation).where(AIJudgeEvaluation.round_id == round_id)
    
    if official_only:
        query = query.where(AIJudgeEvaluation.is_official == True)
    
    query = query.order_by(desc(AIJudgeEvaluation.created_at))
    
    result = await db.execute(query)
    evaluations = result.scalars().all()
    
    responses = []
    for eval in evaluations:
        scores = json.loads(eval.ai_scores_json) if eval.ai_scores_json else {}
        behavior = json.loads(eval.ai_behavior_data_json) if eval.ai_behavior_data_json else {}
        
        # Get team name
        team_result = await db.execute(select(Team).where(Team.id == eval.team_id))
        team = team_result.scalar_one_or_none()
        
        # Get submitter name
        user_result = await db.execute(select(User).where(User.id == eval.submitted_by_user_id))
        user = user_result.scalar_one_or_none()
        
        responses.append(AIJudgeEvaluationResponse(
            id=eval.id,
            round_id=eval.round_id,
            team_id=eval.team_id,
            team_name=team.name if team else None,
            team_side=eval.team_side.value,
            submitted_by_user_id=eval.submitted_by_user_id,
            submitted_by_name=user.name if user else None,
            argument_text=eval.argument_text,
            ai_feedback=eval.ai_feedback,
            ai_scores=AIJudgeScore(**scores),
            ai_behavior_data=AIBehaviorData(**behavior),
            is_official=eval.is_official,
            created_at=eval.created_at.isoformat()
        ))
    
    return responses


@router.post("/{round_id}/ai-judge/evaluations/{eval_id}/mark-official", response_model=AIJudgeEvaluationResponse)
async def mark_ai_score_official(
    round_id: int,
    eval_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Mark an AI evaluation as the official score.
    Only judges/faculty/admins can do this.
    """
    _check_judge_permission(current_user)
    
    # Verify round exists
    await _get_round_or_404(round_id, db)
    
    # Fetch evaluation
    result = await db.execute(
        select(AIJudgeEvaluation).where(AIJudgeEvaluation.id == eval_id)
    )
    evaluation = result.scalar_one_or_none()
    
    if not evaluation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AI evaluation not found"
        )
    
    # Verify evaluation belongs to this round
    if evaluation.round_id != round_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Evaluation does not belong to this round"
        )
    
    # Mark as official
    evaluation.mark_official(current_user.id)
    await db.commit()
    await db.refresh(evaluation)
    
    scores = json.loads(evaluation.ai_scores_json) if evaluation.ai_scores_json else {}
    behavior = json.loads(evaluation.ai_behavior_data_json) if evaluation.ai_behavior_data_json else {}
    
    team_result = await db.execute(select(Team).where(Team.id == evaluation.team_id))
    team = team_result.scalar_one_or_none()
    
    return AIJudgeEvaluationResponse(
        id=evaluation.id,
        round_id=evaluation.round_id,
        team_id=evaluation.team_id,
        team_name=team.name if team else None,
        team_side=evaluation.team_side.value,
        submitted_by_user_id=evaluation.submitted_by_user_id,
        submitted_by_name=evaluation.submitted_by.name if evaluation.submitted_by else None,
        argument_text=evaluation.argument_text,
        ai_feedback=evaluation.ai_feedback,
        ai_scores=AIJudgeScore(**scores),
        ai_behavior_data=AIBehaviorData(**behavior),
        is_official=evaluation.is_official,
        created_at=evaluation.created_at.isoformat()
    )


# ================= AI OPPONENT ROUTES (Mode 2) =================

@router.post("/{round_id}/ai-opponent/enable", response_model=AIOpponentSessionResponse)
async def enable_ai_opponent(
    round_id: int,
    request: AIOpponentEnableRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Enable AI opponent for a team.
    Only team captains can do this.
    """
    # Verify team captain
    await _check_team_captain(request.team_id, current_user.id, db)
    
    # Verify round exists
    round_obj = await _get_round_or_404(round_id, db)
    
    # Verify team belongs to round
    if request.team_id not in [round_obj.petitioner_team_id, round_obj.respondent_team_id]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Team not part of this round"
        )
    
    # Check if active session already exists
    existing = await db.execute(
        select(AIOpponentSession).where(
            AIOpponentSession.round_id == round_id,
            AIOpponentSession.team_id == request.team_id,
            AIOpponentSession.is_active == True
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="AI opponent already active for this team in this round"
        )
    
    # Create context summary if not provided
    context = request.context_summary or f"Oral round between teams. AI playing {request.ai_role} for {request.opponent_side} side."
    
    # Create session
    session = AIOpponentSession(
        round_id=round_id,
        team_id=request.team_id,
        ai_role=request.ai_role,
        opponent_side=request.opponent_side,
        context_summary=context,
        is_active=True,
        created_by_user_id=current_user.id
    )
    
    db.add(session)
    await db.commit()
    await db.refresh(session)
    
    # Get team name
    team_result = await db.execute(select(Team).where(Team.id == request.team_id))
    team = team_result.scalar_one_or_none()
    
    return AIOpponentSessionResponse(
        id=session.id,
        round_id=session.round_id,
        team_id=session.team_id,
        team_name=team.name if team else None,
        ai_role=session.ai_role.value,
        opponent_side=session.opponent_side.value,
        is_active=session.is_active,
        created_at=session.created_at.isoformat()
    )


@router.post("/{round_id}/ai-opponent/disable")
async def disable_ai_opponent(
    round_id: int,
    team_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Disable AI opponent for a team.
    Only team captains can do this.
    """
    # Verify team captain
    await _check_team_captain(team_id, current_user.id, db)
    
    # Verify round exists
    await _get_round_or_404(round_id, db)
    
    # Find active session
    result = await db.execute(
        select(AIOpponentSession).where(
            AIOpponentSession.round_id == round_id,
            AIOpponentSession.team_id == team_id,
            AIOpponentSession.is_active == True
        )
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active AI opponent session found"
        )
    
    # End session
    session.end_session()
    await db.commit()
    
    return {"message": "AI opponent disabled successfully"}


@router.get("/{round_id}/ai-opponent/sessions")
async def list_ai_opponent_sessions(
    round_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List AI opponent sessions for a round.
    Everyone can view.
    """
    await _get_round_or_404(round_id, db)
    
    result = await db.execute(
        select(AIOpponentSession).where(
            AIOpponentSession.round_id == round_id
        ).order_by(desc(AIOpponentSession.created_at))
    )
    sessions = result.scalars().all()
    
    return [
        {
            "id": s.id,
            "round_id": s.round_id,
            "team_id": s.team_id,
            "team_name": s.team.name if s.team else None,
            "ai_role": s.ai_role.value,
            "opponent_side": s.opponent_side.value,
            "is_active": s.is_active,
            "created_at": s.created_at.isoformat(),
            "ended_at": s.ended_at.isoformat() if s.ended_at else None
        }
        for s in sessions
    ]


# ================= AI COACH ROUTES (Mode 3) =================

@router.get("/{round_id}/ai-coach/hints", response_model=List[AICoachHintResponse])
async def get_ai_coach_hints(
    round_id: int,
    hint_type: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get active AI coach hints for team members.
    Returns hints from last 5 minutes, not dismissed.
    """
    await _get_round_or_404(round_id, db)
    
    # Only show hints for this user
    five_minutes_ago = datetime.now(timezone.utc) - timedelta(minutes=5)
    
    query = select(AICoachHint).where(
        AICoachHint.round_id == round_id,
        AICoachHint.user_id == current_user.id,
        AICoachHint.created_at >= five_minutes_ago,
        AICoachHint.is_dismissed == False
    ).order_by(desc(AICoachHint.created_at))
    
    if hint_type:
        try:
            type_enum = HintType(hint_type)
            query = query.where(AICoachHint.hint_type == type_enum)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid hint type: {hint_type}"
            )
    
    result = await db.execute(query)
    hints = result.scalars().all()
    
    # Mark hints as displayed
    for hint in hints:
        if not hint.is_displayed:
            hint.display()
    
    await db.commit()
    
    return [
        AICoachHintResponse(
            id=h.id,
            round_id=h.round_id,
            team_id=h.team_id,
            user_id=h.user_id,
            user_name=h.user.name if h.user else None,
            hint_type=h.hint_type.value,
            hint_text=h.hint_text,
            trigger_keyword=h.trigger_keyword,
            is_displayed=h.is_displayed,
            is_dismissed=h.is_dismissed,
            created_at=h.created_at.isoformat()
        )
        for h in hints
    ]


@router.post("/{round_id}/ai-coach/hints/{hint_id}/dismiss")
async def dismiss_ai_coach_hint(
    round_id: int,
    hint_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Dismiss an AI coach hint.
    Only the hint recipient can dismiss.
    """
    await _get_round_or_404(round_id, db)
    
    # Fetch hint
    result = await db.execute(
        select(AICoachHint).where(AICoachHint.id == hint_id)
    )
    hint = result.scalar_one_or_none()
    
    if not hint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hint not found"
        )
    
    # Verify ownership
    if hint.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Can only dismiss your own hints"
        )
    
    # Verify hint belongs to this round
    if hint.round_id != round_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Hint does not belong to this round"
        )
    
    # Dismiss
    hint.dismiss(current_user.id)
    await db.commit()
    
    return {"message": "Hint dismissed successfully"}


@router.post("/{round_id}/ai-coach/hints")
async def create_ai_coach_hint(
    round_id: int,
    hint_type: str,
    hint_text: str,
    trigger_keyword: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new AI coach hint.
    Used by client-side analysis or auto-generation.
    """
    await _get_round_or_404(round_id, db)
    
    # Validate hint type
    try:
        type_enum = HintType(hint_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid hint type: {hint_type}"
        )
    
    # Get team membership
    team_result = await db.execute(
        select(TeamMember).where(TeamMember.user_id == current_user.id)
    )
    team_member = team_result.scalar_one_or_none()
    team_id = team_member.team_id if team_member else None
    
    # Create hint
    hint = AICoachHint(
        round_id=round_id,
        team_id=team_id,
        user_id=current_user.id,
        hint_type=type_enum,
        hint_text=hint_text,
        trigger_keyword=trigger_keyword,
        is_displayed=False,
        is_dismissed=False
    )
    
    db.add(hint)
    await db.commit()
    await db.refresh(hint)
    
    return AICoachHintResponse(
        id=hint.id,
        round_id=hint.round_id,
        team_id=hint.team_id,
        user_id=hint.user_id,
        user_name=current_user.name,
        hint_type=hint.hint_type.value,
        hint_text=hint.hint_text,
        trigger_keyword=hint.trigger_keyword,
        is_displayed=hint.is_displayed,
        is_dismissed=hint.is_dismissed,
        created_at=hint.created_at.isoformat()
    )
