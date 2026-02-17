"""
Phase 6 — Player Profile Service

Comprehensive player profile with stats, history, and performance metrics.
"""
from typing import Dict, Any, Optional, List
from sqlalchemy import select, func, and_, or_, desc, asc, case, Float
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.orm.player_ratings import PlayerRating, RatingHistory
from backend.orm.user import User
from backend.orm.online_match import Match
from backend.services.competitive_leaderboard_service import CompetitiveLeaderboardService


class PlayerProfileService:
    """Service for player profile operations."""

    @staticmethod
    async def get_player_profile(
        db: AsyncSession,
        user_id: int
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
        # Get user
        user_result = await db.execute(
            select(User).where(User.id == user_id)
        )
        user = user_result.scalar_one_or_none()
        
        if not user:
            raise ValueError(f"User {user_id} not found")
        
        # Get or create rating
        rating_result = await db.execute(
            select(PlayerRating).where(PlayerRating.user_id == user_id)
        )
        rating = rating_result.scalar_one_or_none()
        
        if not rating:
            rating = PlayerRating(user_id=user_id, current_rating=1000)
            db.add(rating)
            await db.flush()
        
        # Calculate global rank
        global_rank = await CompetitiveLeaderboardService.get_player_rank(db, user_id)
        total_players = await CompetitiveLeaderboardService.get_total_players(db)
        
        percentile_rank = None
        if total_players > 0 and global_rank:
            percentile_rank = round(((total_players - global_rank + 1) / total_players) * 100, 2)
        
        # Rating stats
        win_rate = rating.get_win_rate()
        
        # Average match score (from finalized matches)
        avg_score_query = (
            select(func.avg(
                case(
                    (Match.player1_id == user_id, Match.player_1_score),
                    else_=Match.player_2_score
                )
            ))
            .where(
                and_(
                    Match.state == "finalized",
                    Match.is_locked.is_(True),
                    Match.rating_processed.is_(True),
                    Match.is_ai_match.is_(False),
                    or_(Match.player1_id == user_id, Match.player2_id == user_id)
                )
            )
        )
        avg_score_result = await db.execute(avg_score_query)
        average_score = round(float(avg_score_result.scalar() or 0.0), 2)
        
        # Performance metrics
        # Rating delta last 10 matches
        last_10_query = (
            select(RatingHistory.rating_change)
            .where(RatingHistory.user_id == user_id)
            .order_by(desc(RatingHistory.timestamp))
            .limit(10)
        )
        last_10_result = await db.execute(last_10_query)
        last_10_changes = [row[0] for row in last_10_result.all()]
        rating_delta_last_10 = sum(last_10_changes)
        
        # Strongest win / worst loss
        wins_query = (
            select(RatingHistory.opponent_rating)
            .where(
                and_(
                    RatingHistory.user_id == user_id,
                    RatingHistory.result == "win"
                )
            )
            .order_by(desc(RatingHistory.opponent_rating))
            .limit(1)
        )
        strongest_win_result = await db.execute(wins_query)
        strongest_win = strongest_win_result.scalar()
        
        losses_query = (
            select(RatingHistory.opponent_rating)
            .where(
                and_(
                    RatingHistory.user_id == user_id,
                    RatingHistory.result == "loss"
                )
            )
            .order_by(asc(RatingHistory.opponent_rating))
            .limit(1)
        )
        worst_loss_result = await db.execute(losses_query)
        worst_loss = worst_loss_result.scalar()
        
        # Average round score (from MatchRound)
        from backend.orm.online_match import MatchRound
        avg_round_query = (
            select(func.avg(MatchRound.final_score))
            .join(Match, MatchRound.match_id == Match.id)
            .where(
                and_(
                    MatchRound.player_id == user_id,
                    MatchRound.is_locked.is_(True),
                    Match.state == "finalized",
                    Match.is_ai_match.is_(False)
                )
            )
        )
        avg_round_result = await db.execute(avg_round_query)
        average_round_score = round(float(avg_round_result.scalar() or 0.0), 2)
        
        # Recent matches (last 10)
        recent_matches_query = (
            select(Match, RatingHistory)
            .join(
                RatingHistory,
                and_(
                    RatingHistory.match_id == Match.id,
                    RatingHistory.user_id == user_id
                )
            )
            .where(
                and_(
                    Match.state == "finalized",
                    Match.is_locked.is_(True),
                    Match.rating_processed.is_(True),
                    Match.is_ai_match.is_(False),
                    or_(Match.player1_id == user_id, Match.player2_id == user_id)
                )
            )
            .order_by(desc(Match.finalized_at))
            .limit(10)
        )
        recent_matches_result = await db.execute(recent_matches_query)
        recent_matches = []
        
        for match, history in recent_matches_result.all():
            # Get opponent info
            opponent_id = match.player2_id if match.player1_id == user_id else match.player1_id
            opponent_result = await db.execute(
                select(User.full_name).where(User.id == opponent_id)
            )
            opponent_name = opponent_result.scalar() or "Unknown"
            
            # Get player's score
            player_score = match.player_1_score if match.player1_id == user_id else match.player_2_score
            
            recent_matches.append({
                "match_id": match.id,
                "opponent_id": opponent_id,
                "opponent_name": opponent_name,
                "opponent_rating_at_match": history.opponent_rating,
                "result": history.result,
                "rating_change": history.rating_change,
                "final_match_score": round(float(player_score or 0.0), 2),
                "date": match.finalized_at.isoformat() if match.finalized_at else None
            })
        
        # Rating history graph data
        history_query = (
            select(RatingHistory.timestamp, RatingHistory.new_rating)
            .where(RatingHistory.user_id == user_id)
            .order_by(asc(RatingHistory.timestamp))
        )
        history_result = await db.execute(history_query)
        rating_history_graph = [
            {
                "date": row[0].isoformat() if row[0] else None,
                "rating": row[1]
            }
            for row in history_result.all()
        ]
        
        return {
            "user_basic_info": {
                "user_id": user.id,
                "username": user.full_name,
                "email": user.email
            },
            "rating_stats": {
                "current_rating": rating.current_rating,
                "peak_rating": rating.peak_rating,
                "global_rank": global_rank,
                "percentile_rank": percentile_rank,
                "win_rate": win_rate,
                "average_score": average_score,
                "total_matches": rating.matches_played
            },
            "performance_metrics": {
                "average_round_score": average_round_score,
                "average_match_score": average_score,
                "rating_delta_last_10": rating_delta_last_10,
                "strongest_win": strongest_win,
                "worst_loss": worst_loss
            },
            "recent_matches": recent_matches,
            "rating_history_graph_data": rating_history_graph
        }
