"""
Phase 5 — Official ELO Rating Engine

Chess-style rating updates for finalized online matches.

Guarantees:
- Runs only for finalized, locked, non-AI matches
- Runs at most once per match (match.rating_processed + history uniqueness)
- Zero-sum rating changes between players
- Rating history is immutable once written
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.orm.online_match import Match
from backend.orm.player_ratings import PlayerRating, RatingHistory


class EloRatingService:
    """Server-side ELO rating calculator."""

    @staticmethod
    def _get_k_factor(games_played: int) -> int:
        """
        K-factor selection:
        - < 30 games  -> 40
        - < 100 games -> 20
        - else        -> 10
        """
        if games_played < 30:
            return 40
        if games_played < 100:
            return 20
        return 10

    @staticmethod
    def _expected_score(ra: int, rb: int) -> float:
        """Ea = 1 / (1 + 10 ** ((Rb - Ra) / 400))."""
        return 1.0 / (1.0 + math.pow(10.0, (rb - ra) / 400.0))

    @classmethod
    async def process_rating_update_for_match(
        cls,
        match_id: int,
        db: AsyncSession,
    ) -> None:
        """
        Apply ELO rating update for a single finalized match.

        MUST be called from within the same transaction that finalizes the match.
        This function does not commit or rollback by itself.
        """
        # Lock match row
        result = await db.execute(
            select(Match).where(Match.id == match_id).with_for_update()
        )
        match = result.scalar_one_or_none()

        if not match:
            raise ValueError(f"Match {match_id} not found for rating update")

        # AI matches are explicitly excluded from rating logic
        if match.is_ai_match:
            return

        # Strict validation
        if match.state != "finalized":
            raise ValueError("Cannot update rating: match is not finalized")
        if not match.is_locked:
            raise ValueError("Cannot update rating: match is not locked")
        if match.rating_processed:
            raise ValueError("Rating already processed for this match")
        if not match.winner_id:
            raise ValueError("Cannot update rating: winner_id is missing")
        if not match.player1_id or not match.player2_id:
            raise ValueError("Cannot update rating: both players are required")
        
        # Phase 6: Failsafe assertion
        assert match.rating_processed is False, "Match already rated - double processing prevented"

        p1_id = match.player1_id
        p2_id = match.player2_id

        # Lock both PlayerRating rows
        ratings_result = await db.execute(
            select(PlayerRating).where(
                PlayerRating.user_id.in_([p1_id, p2_id])
            ).with_for_update()
        )
        rating_rows = ratings_result.scalars().all()

        ratings_by_user: Dict[int, PlayerRating] = {r.user_id: r for r in rating_rows}

        # Create defaults if missing
        for uid in (p1_id, p2_id):
            if uid not in ratings_by_user:
                pr = PlayerRating(user_id=uid, current_rating=1000, peak_rating=1000)
                db.add(pr)
                await db.flush()
                ratings_by_user[uid] = pr

        p1_rating = ratings_by_user[p1_id]
        p2_rating = ratings_by_user[p2_id]

        ra = int(p1_rating.current_rating)
        rb = int(p2_rating.current_rating)

        # Determine actual scores based on match scores
        s1 = float(match.player_1_score or 0.0)
        s2 = float(match.player_2_score or 0.0)

        if s1 == s2:
            # Draw
            a1 = a2 = 0.5
            p1_result = "draw"
            p2_result = "draw"
        elif match.winner_id == p1_id:
            a1, a2 = 1.0, 0.0
            p1_result, p2_result = "win", "loss"
        elif match.winner_id == p2_id:
            a1, a2 = 0.0, 1.0
            p1_result, p2_result = "loss", "win"
        else:
            raise ValueError("winner_id does not match either player")

        # Expected scores
        e1 = cls._expected_score(ra, rb)
        e2 = cls._expected_score(rb, ra)

        # K-factors based on games played
        k1 = cls._get_k_factor(p1_rating.matches_played)
        k2 = cls._get_k_factor(p2_rating.matches_played)

        # Raw deltas
        delta1_raw = k1 * (a1 - e1)
        delta2_raw = k2 * (a2 - e2)

        # Apply rounding for player 1
        new_ra = int(round(ra + delta1_raw))
        delta1 = new_ra - ra

        # Enforce strict zero-sum: player 2 delta is negative of player 1
        delta2 = -delta1
        new_rb = rb + delta2

        # Apply updates to PlayerRating rows
        p1_rating.current_rating = new_ra
        if new_ra > p1_rating.peak_rating:
            p1_rating.peak_rating = new_ra

        p2_rating.current_rating = new_rb
        if new_rb > p2_rating.peak_rating:
            p2_rating.peak_rating = new_rb

        # Update match statistics
        p1_rating.matches_played += 1
        p2_rating.matches_played += 1

        if p1_result == "win":
            p1_rating.wins += 1
            p2_rating.losses += 1
        elif p1_result == "loss":
            p1_rating.losses += 1
            p2_rating.wins += 1
        else:
            p1_rating.draws += 1
            p2_rating.draws += 1

        now = datetime.utcnow()
        p1_rating.last_active_at = now
        p2_rating.last_active_at = now

        # Track last match processed
        p1_rating.last_match_id = match.id
        p2_rating.last_match_id = match.id

        # Create immutable history rows
        h1 = RatingHistory(
            user_id=p1_id,
            match_id=match.id,
            old_rating=ra,
            new_rating=new_ra,
            rating_change=delta1,
            opponent_rating=rb,
            result=p1_result,
        )
        h2 = RatingHistory(
            user_id=p2_id,
            match_id=match.id,
            old_rating=rb,
            new_rating=new_rb,
            rating_change=delta2,
            opponent_rating=ra,
            result=p2_result,
        )

        db.add(h1)
        db.add(h2)

        # Mark match as processed to enforce single execution
        match.rating_processed = True

