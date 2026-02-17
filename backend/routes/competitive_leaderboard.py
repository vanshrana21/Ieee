"""
Phase 6 — Competitive Leaderboard API Routes

Endpoints for ranked competitive leaderboard and player profiles.
"""
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.rbac import get_current_user
from backend.orm.user import User
from backend.services.competitive_leaderboard_service import CompetitiveLeaderboardService
from backend.services.player_profile_service import PlayerProfileService


router = APIRouter(prefix="/api/leaderboard", tags=["Competitive Leaderboard"])


@router.get("")
async def get_leaderboard(
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Get global competitive leaderboard.
    
    Query params:
    - page: Page number (1-indexed)
    - limit: Results per page (max 500)
    """
    offset = (page - 1) * limit
    
    leaderboard = await CompetitiveLeaderboardService.get_global_leaderboard(
        db=db,
        limit=limit,
        offset=offset
    )
    
    total_players = await CompetitiveLeaderboardService.get_total_players(db)
    total_pages = (total_players + limit - 1) // limit if total_players > 0 else 1
    
    return {
        "success": True,
        "leaderboard": leaderboard,
        "pagination": {
            "page": page,
            "limit": limit,
            "total_players": total_players,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1
        }
    }


@router.get("/player/{user_id}")
async def get_player_profile(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Get comprehensive player profile.
    
    Returns:
    - user_basic_info
    - rating_stats
    - performance_metrics
    - recent_matches
    - rating_history_graph_data
    """
    try:
        profile = await PlayerProfileService.get_player_profile(db, user_id)
        return {
            "success": True,
            "profile": profile
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.get("/player/{user_id}/rating-history")
async def get_rating_history(
    user_id: int,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Get player rating history.
    
    Returns chronological list of rating changes.
    """
    from sqlalchemy import select, desc
    from backend.orm.player_ratings import RatingHistory
    from backend.orm.online_match import Match
    
    # Verify user exists
    from backend.orm.user import User as UserModel
    user_result = await db.execute(
        select(UserModel).where(UserModel.id == user_id)
    )
    if not user_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    history_query = (
        select(RatingHistory, Match.finalized_at)
        .join(Match, RatingHistory.match_id == Match.id)
        .where(RatingHistory.user_id == user_id)
        .order_by(desc(RatingHistory.timestamp))
        .limit(limit)
    )
    
    result = await db.execute(history_query)
    history = []
    
    for rh, match_date in result.all():
        history.append({
            "match_id": rh.match_id,
            "old_rating": rh.old_rating,
            "new_rating": rh.new_rating,
            "rating_change": rh.rating_change,
            "opponent_rating": rh.opponent_rating,
            "result": rh.result,
            "timestamp": rh.timestamp.isoformat() if rh.timestamp else None,
            "match_date": match_date.isoformat() if match_date else None
        })
    
    return {
        "success": True,
        "user_id": user_id,
        "history": history,
        "count": len(history)
    }


@router.get("/player/{user_id}/recent-matches")
async def get_recent_matches(
    user_id: int,
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Get player's recent matches.
    
    Returns last N finalized matches with opponent info and results.
    """
    profile = await PlayerProfileService.get_player_profile(db, user_id)
    
    recent_matches = profile.get("recent_matches", [])[:limit]
    
    return {
        "success": True,
        "user_id": user_id,
        "matches": recent_matches,
        "count": len(recent_matches)
    }
