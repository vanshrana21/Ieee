"""
backend/routes/rankings.py
Phase 5E: Ranking and leaderboard API routes
"""
import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc

from backend.database import get_db
from backend.services.ranking_service import RankingService
from backend.orm.ranking import TeamRanking, RankingType, RankStatus, Leaderboard, WinnerSelection, TieBreakRule
from backend.orm.competition import Competition, CompetitionRound
from backend.orm.team import Team
from backend.orm.user import User, UserRole
from backend.rbac import get_current_user
from backend.errors import ErrorCode

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/rankings", tags=["Rankings"])


# ================= SCHEMAS =================

class ComputeRankingsRequest(BaseModel):
    """Request to compute rankings"""
    ranking_type: RankingType = RankingType.OVERALL
    round_id: Optional[int] = None


class TieBreakRuleCreate(BaseModel):
    """Create tie-break rule"""
    rule_name: str
    description: Optional[str] = None
    criterion: str  # issue_framing, legal_reasoning, etc.
    comparison: str = "higher"  # higher, lower
    rule_order: int = 1


class WinnerSelectRequest(BaseModel):
    """Request to select winners"""
    round_id: Optional[int] = None
    manual_override: Optional[dict] = None  # For manual winner selection


# ================= RANKING COMPUTATION =================

@router.post("/compute", status_code=200)
async def compute_rankings(
    competition_id: int = Query(...),
    data: ComputeRankingsRequest = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 5E: Compute team rankings from judge scores.
    Admin/Faculty only.
    """
    # Check permissions
    if current_user.role not in [UserRole.FACULTY, UserRole.ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(
            status_code=403,
            detail="Only Faculty/Admin can compute rankings"
        )
    
    # Verify competition access
    comp_result = await db.execute(
        select(Competition).where(Competition.id == competition_id)
    )
    competition = comp_result.scalar_one_or_none()
    
    if not competition:
        raise HTTPException(status_code=404, detail="Competition not found")
    
    if current_user.role != UserRole.SUPER_ADMIN and current_user.institution_id != competition.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Compute rankings
    rankings = await RankingService.compute_team_rankings(
        competition_id=competition_id,
        ranking_type=data.ranking_type if data else RankingType.OVERALL,
        round_id=data.round_id if data else None,
        db=db,
        computed_by=current_user.id
    )
    
    return {
        "success": True,
        "competition_id": competition_id,
        "ranking_type": data.ranking_type.value if data else RankingType.OVERALL.value,
        "teams_ranked": len(rankings),
        "rankings": [r.to_dict(include_details=False) for r in rankings],
        "message": f"Rankings computed successfully. {len(rankings)} teams ranked."
    }


@router.get("", status_code=200)
async def list_rankings(
    competition_id: int = Query(...),
    ranking_type: Optional[RankingType] = Query(None),
    include_draft: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 5E: List team rankings.
    Students see only published rankings.
    """
    # Verify competition access
    comp_result = await db.execute(
        select(Competition).where(Competition.id == competition_id)
    )
    competition = comp_result.scalar_one_or_none()
    
    if not competition:
        raise HTTPException(status_code=404, detail="Competition not found")
    
    if current_user.role != UserRole.SUPER_ADMIN and current_user.institution_id != competition.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Build query
    query = select(TeamRanking).where(TeamRanking.competition_id == competition_id)
    
    if ranking_type:
        query = query.where(TeamRanking.ranking_type == ranking_type)
    
    # Students only see published rankings
    if current_user.role == UserRole.STUDENT:
        query = query.where(TeamRanking.is_published == True)
    elif not include_draft:
        query = query.where(TeamRanking.is_published == True)
    
    query = query.order_by(TeamRanking.rank)
    
    result = await db.execute(query)
    rankings = result.scalars().all()
    
    return {
        "success": True,
        "competition_id": competition_id,
        "rankings": [r.to_dict(include_details=(current_user.role != UserRole.STUDENT)) for r in rankings],
        "count": len(rankings)
    }


@router.get("/{ranking_id}", status_code=200)
async def get_ranking(
    ranking_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get specific team ranking details.
    """
    result = await db.execute(
        select(TeamRanking).where(TeamRanking.id == ranking_id)
    )
    ranking = result.scalar_one_or_none()
    
    if not ranking:
        raise HTTPException(status_code=404, detail="Ranking not found")
    
    # Check access
    if current_user.role != UserRole.SUPER_ADMIN and current_user.institution_id != ranking.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Students only see published rankings
    if current_user.role == UserRole.STUDENT and not ranking.is_published:
        raise HTTPException(status_code=404, detail="Ranking not found")
    
    return {
        "success": True,
        "ranking": ranking.to_dict(include_details=(current_user.role != UserRole.STUDENT))
    }


# ================= PUBLISH RANKINGS =================

@router.post("/publish", status_code=200)
async def publish_rankings(
    competition_id: int = Query(...),
    ranking_type: RankingType = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 5E: Publish rankings to make them visible to students.
    Admin only.
    """
    if current_user.role not in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(status_code=403, detail="Only Admin can publish rankings")
    
    # Verify competition
    comp_result = await db.execute(
        select(Competition).where(Competition.id == competition_id)
    )
    competition = comp_result.scalar_one_or_none()
    
    if not competition:
        raise HTTPException(status_code=404, detail="Competition not found")
    
    if current_user.role != UserRole.SUPER_ADMIN and current_user.institution_id != competition.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Update rankings
    result = await db.execute(
        select(TeamRanking).where(
            and_(
                TeamRanking.competition_id == competition_id,
                TeamRanking.ranking_type == ranking_type
            )
        )
    )
    rankings = result.scalars().all()
    
    for ranking in rankings:
        ranking.is_published = True
        ranking.status = RankStatus.PUBLISHED
        ranking.published_at = datetime.utcnow()
        ranking.published_by = current_user.id
    
    await db.commit()
    
    logger.info(f"Rankings published: competition={competition_id}, type={ranking_type.value}")
    
    return {
        "success": True,
        "message": f"{len(rankings)} rankings published",
        "published_count": len(rankings)
    }


# ================= LEADERBOARD =================

@router.post("/leaderboard/generate", status_code=200)
async def generate_leaderboard(
    competition_id: int = Query(...),
    ranking_type: RankingType = Query(...),
    title: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 5E: Generate leaderboard view.
    """
    # Check permissions
    if current_user.role not in [UserRole.FACULTY, UserRole.ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    # Verify competition
    comp_result = await db.execute(
        select(Competition).where(Competition.id == competition_id)
    )
    competition = comp_result.scalar_one_or_none()
    
    if not competition:
        raise HTTPException(status_code=404, detail="Competition not found")
    
    if current_user.role != UserRole.SUPER_ADMIN and current_user.institution_id != competition.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Generate leaderboard
    leaderboard = await RankingService.generate_leaderboard(
        competition_id=competition_id,
        ranking_type=ranking_type,
        db=db,
        title=title,
        description=f"Official {ranking_type.value} rankings"
    )
    
    if not leaderboard:
        raise HTTPException(status_code=400, detail="No published rankings available for leaderboard")
    
    return {
        "success": True,
        "leaderboard": leaderboard.to_dict()
    }


@router.get("/leaderboard/view", status_code=200)
async def view_leaderboard(
    competition_id: int = Query(...),
    ranking_type: RankingType = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 5E: Public leaderboard view.
    Students see only published leaderboards.
    """
    # Verify competition access
    comp_result = await db.execute(
        select(Competition).where(Competition.id == competition_id)
    )
    competition = comp_result.scalar_one_or_none()
    
    if not competition:
        raise HTTPException(status_code=404, detail="Competition not found")
    
    if current_user.role != UserRole.SUPER_ADMIN and current_user.institution_id != competition.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get leaderboard
    result = await db.execute(
        select(Leaderboard).where(
            and_(
                Leaderboard.competition_id == competition_id,
                Leaderboard.ranking_type == ranking_type
            )
        )
    )
    leaderboard = result.scalar_one_or_none()
    
    if not leaderboard:
        raise HTTPException(status_code=404, detail="Leaderboard not found")
    
    # Students only see published leaderboards
    if current_user.role == UserRole.STUDENT and not leaderboard.is_published:
        raise HTTPException(status_code=404, detail="Leaderboard not found")
    
    return {
        "success": True,
        "leaderboard": leaderboard.to_dict()
    }


@router.post("/leaderboard/{leaderboard_id}/publish", status_code=200)
async def publish_leaderboard(
    leaderboard_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Publish leaderboard for public viewing.
    """
    if current_user.role not in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(status_code=403, detail="Only Admin can publish leaderboards")
    
    result = await db.execute(
        select(Leaderboard).where(Leaderboard.id == leaderboard_id)
    )
    leaderboard = result.scalar_one_or_none()
    
    if not leaderboard:
        raise HTTPException(status_code=404, detail="Leaderboard not found")
    
    if current_user.role != UserRole.SUPER_ADMIN:
        # Get competition for institution check
        comp_result = await db.execute(
            select(Competition).where(Competition.id == leaderboard.competition_id)
        )
        competition = comp_result.scalar_one_or_none()
        if current_user.institution_id != competition.institution_id:
            raise HTTPException(status_code=403, detail="Access denied")
    
    leaderboard.is_published = True
    leaderboard.published_at = datetime.utcnow()
    
    await db.commit()
    
    return {
        "success": True,
        "message": "Leaderboard published successfully"
    }


# ================= TIE-BREAK RULES =================

@router.post("/tie-break-rules", status_code=201)
async def create_tie_break_rule(
    competition_id: int = Query(...),
    data: TieBreakRuleCreate = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 5E: Create tie-break rule for competition.
    """
    if current_user.role not in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(status_code=403, detail="Only Admin can create tie-break rules")
    
    # Verify competition
    comp_result = await db.execute(
        select(Competition).where(Competition.id == competition_id)
    )
    competition = comp_result.scalar_one_or_none()
    
    if not competition:
        raise HTTPException(status_code=404, detail="Competition not found")
    
    if current_user.role != UserRole.SUPER_ADMIN and current_user.institution_id != competition.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    rule = TieBreakRule(
        institution_id=competition.institution_id,
        competition_id=competition_id,
        rule_name=data.rule_name,
        rule_description=data.description,
        criterion=data.criterion,
        comparison=data.comparison,
        rule_order=data.rule_order,
        is_active=True
    )
    
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    
    return {
        "success": True,
        "rule": rule.to_dict()
    }


@router.get("/tie-break-rules", status_code=200)
async def list_tie_break_rules(
    competition_id: int = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List tie-break rules for competition.
    """
    result = await db.execute(
        select(TieBreakRule).where(
            TieBreakRule.competition_id == competition_id
        ).order_by(TieBreakRule.rule_order)
    )
    rules = result.scalars().all()
    
    return {
        "success": True,
        "competition_id": competition_id,
        "rules": [r.to_dict() for r in rules]
    }


# ================= WINNER SELECTION =================

@router.post("/winners/select", status_code=200)
async def select_winners(
    competition_id: int = Query(...),
    data: WinnerSelectRequest = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 5E: Select official winners based on rankings.
    Admin only.
    """
    if current_user.role not in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(status_code=403, detail="Only Admin can select winners")
    
    # Verify competition
    comp_result = await db.execute(
        select(Competition).where(Competition.id == competition_id)
    )
    competition = comp_result.scalar_one_or_none()
    
    if not competition:
        raise HTTPException(status_code=404, detail="Competition not found")
    
    if current_user.role != UserRole.SUPER_ADMIN and current_user.institution_id != competition.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Select winners
    winners = await RankingService.select_winners(
        competition_id=competition_id,
        round_id=data.round_id if data else None,
        db=db,
        selected_by=current_user.id
    )
    
    return {
        "success": True,
        "winners": [w.to_dict() for w in winners],
        "message": f"{len(winners)} winners officially selected"
    }


@router.get("/winners", status_code=200)
async def list_winners(
    competition_id: int = Query(...),
    round_id: Optional[int] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 5E: List official winners.
    """
    # Verify competition access
    comp_result = await db.execute(
        select(Competition).where(Competition.id == competition_id)
    )
    competition = comp_result.scalar_one_or_none()
    
    if not competition:
        raise HTTPException(status_code=404, detail="Competition not found")
    
    if current_user.role != UserRole.SUPER_ADMIN and current_user.institution_id != competition.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Build query
    query = select(WinnerSelection).where(
        WinnerSelection.competition_id == competition_id
    )
    
    if round_id:
        query = query.where(WinnerSelection.round_id == round_id)
    
    query = query.order_by(WinnerSelection.rank)
    
    result = await db.execute(query)
    winners = result.scalars().all()
    
    return {
        "success": True,
        "competition_id": competition_id,
        "winners": [w.to_dict() for w in winners],
        "count": len(winners)
    }
