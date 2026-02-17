"""
Phase 6 — Competitive Leaderboard Service

National leaderboard for ranked moot court matches.
Uses ELO ratings exclusively from Phase 5.
"""
from typing import List, Dict, Any, Optional
from sqlalchemy import select, func, and_, or_, desc, asc, Float
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.orm.player_ratings import PlayerRating, RatingHistory
from backend.orm.user import User
from backend.orm.online_match import Match


class CompetitiveLeaderboardService:
    """Service for competitive ranked leaderboard operations."""

    @staticmethod
    async def get_global_leaderboard(
        db: AsyncSession,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get global leaderboard ordered by rating.
        
        Ordering:
        1. current_rating DESC
        2. wins DESC
        3. win_rate DESC
        4. last_active_at DESC
        5. user_id ASC (deterministic)
        
        Excludes players with matches_played = 0.
        """
        # Subquery for win_rate calculation
        win_rate_expr = func.cast(
            func.cast(PlayerRating.wins, Float) / 
            func.nullif(PlayerRating.matches_played, 0) * 100,
            Float
        ).label('win_rate')
        
        # Base query: join PlayerRating with User
        query = (
            select(
                PlayerRating,
                User.full_name.label('username'),
                win_rate_expr
            )
            .join(User, PlayerRating.user_id == User.id)
            .where(PlayerRating.matches_played > 0)
            .order_by(
                desc(PlayerRating.current_rating),
                desc(PlayerRating.wins),
                desc(win_rate_expr),
                desc(PlayerRating.last_active_at),
                asc(PlayerRating.user_id)
            )
            .limit(limit)
            .offset(offset)
        )
        
        result = await db.execute(query)
        rows = result.all()
        
        # Calculate rank (1-indexed)
        rank = offset + 1
        leaderboard = []
        
        for pr, username, win_rate in rows:
            # Get rating trend (last 5 matches)
            trend_query = (
                select(func.sum(RatingHistory.rating_change))
                .where(RatingHistory.user_id == pr.user_id)
                .order_by(desc(RatingHistory.timestamp))
                .limit(5)
            )
            trend_result = await db.execute(trend_query)
            trend_sum = trend_result.scalar() or 0
            
            trend = "neutral"
            if trend_sum > 0:
                trend = "up"
            elif trend_sum < 0:
                trend = "down"
            
            leaderboard.append({
                "rank": rank,
                "user_id": pr.user_id,
                "username": username,
                "current_rating": pr.current_rating,
                "peak_rating": pr.peak_rating,
                "matches_played": pr.matches_played,
                "wins": pr.wins,
                "losses": pr.losses,
                "draws": pr.draws,
                "win_rate": round(win_rate or 0.0, 2),
                "rating_trend": trend,
                "last_active_at": pr.last_active_at.isoformat() if pr.last_active_at else None
            })
            rank += 1
        
        return leaderboard

    @staticmethod
    async def get_player_rank(
        db: AsyncSession,
        user_id: int
    ) -> Optional[int]:
        """
        Calculate global rank for a player.
        
        Rank = COUNT(*) WHERE current_rating > player_rating + tie-break resolution
        """
        # Get player's rating
        player_result = await db.execute(
            select(PlayerRating).where(PlayerRating.user_id == user_id)
        )
        player_rating = player_result.scalar_one_or_none()
        
        if not player_rating or player_rating.matches_played == 0:
            return None
        
        # Count players with higher rating
        higher_rating_count = await db.execute(
            select(func.count(PlayerRating.id))
            .where(
                and_(
                    PlayerRating.matches_played > 0,
                    or_(
                        PlayerRating.current_rating > player_rating.current_rating,
                        and_(
                            PlayerRating.current_rating == player_rating.current_rating,
                            or_(
                                PlayerRating.wins > player_rating.wins,
                                and_(
                                    PlayerRating.wins == player_rating.wins,
                                    PlayerRating.user_id < player_rating.user_id
                                )
                            )
                        )
                    )
                )
            )
        )
        
        rank = higher_rating_count.scalar() + 1
        return rank

    @staticmethod
    async def get_total_players(db: AsyncSession) -> int:
        """Get total number of players with at least one match."""
        result = await db.execute(
            select(func.count(PlayerRating.id))
            .where(PlayerRating.matches_played > 0)
        )
        return result.scalar() or 0
