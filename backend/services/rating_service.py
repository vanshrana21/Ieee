"""
Rating Service

ELO rating calculations for Online 1v1 Mode.
Server-side only - no client calculations.
"""
from typing import Dict, Tuple, Optional
from datetime import datetime, timedelta
import math

from backend.orm.player_ratings import PlayerRating, RatingHistory
from backend.orm.online_match import Match


class RatingService:
    """
    ELO rating service for online 1v1 matches.
    Implements modified ELO with K-factor adjustments.
    """
    
    # Constants
    INITIAL_RATING = 1000
    MAX_RATING_GAIN = 50  # Anti-cheat: max gain per match
    MIN_MATCH_DURATION_SECONDS = 300  # 5 minutes minimum
    RATING_DECAY_DAYS = 30
    RATING_DECAY_POINTS = 50
    
    @staticmethod
    def calculate_expected_score(rating_a: int, rating_b: int) -> float:
        """
        Calculate expected score for player A against player B.
        
        Formula: Ea = 1 / (1 + 10^((Rb - Ra) / 400))
        
        Args:
            rating_a: Rating of player A
            rating_b: Rating of player B
            
        Returns:
            Expected score (0.0 to 1.0)
        """
        return 1 / (1 + math.pow(10, (rating_b - rating_a) / 400))
    
    @staticmethod
    def calculate_new_rating(
        current_rating: int,
        expected_score: float,
        actual_score: float,
        k_factor: int
    ) -> int:
        """
        Calculate new rating after match.
        
        Formula: R_new = R_old + K * (S_actual - S_expected)
        
        Args:
            current_rating: Current rating
            expected_score: Expected score (0.0 to 1.0)
            actual_score: Actual score (1.0 for win, 0.5 for draw, 0.0 for loss)
            k_factor: K-factor based on experience
            
        Returns:
            New rating (clamped to valid range)
        """
        rating_change = k_factor * (actual_score - expected_score)
        
        # Anti-cheat: Limit rating change
        rating_change = max(-RatingService.MAX_RATING_GAIN, 
                          min(RatingService.MAX_RATING_GAIN, rating_change))
        
        new_rating = int(current_rating + rating_change)
        
        # Ensure rating doesn't go below floor (e.g., 100)
        return max(100, new_rating)
    
    @staticmethod
    def calculate_match_ratings(
        player1_rating: int,
        player2_rating: int,
        player1_score: float,
        player2_score: float,
        player1_k: int = 32,
        player2_k: int = 32
    ) -> Dict[str, int]:
        """
        Calculate new ratings for both players after match.
        
        Args:
            player1_rating: Player 1 current rating
            player2_rating: Player 2 current rating
            player1_score: Player 1 total score (0-25 scale)
            player2_score: Player 2 total score (0-25 scale)
            player1_k: Player 1 K-factor
            player2_k: Player 2 K-factor
            
        Returns:
            Dictionary with new ratings and changes
        """
        # Determine winner based on scores
        score_diff = player1_score - player2_score
        
        if score_diff > 0.5:
            # Player 1 wins
            p1_actual = 1.0
            p2_actual = 0.0
            winner = "player1"
        elif score_diff < -0.5:
            # Player 2 wins
            p1_actual = 0.0
            p2_actual = 1.0
            winner = "player2"
        else:
            # Draw
            p1_actual = 0.5
            p2_actual = 0.5
            winner = "draw"
        
        # Calculate expected scores
        p1_expected = RatingService.calculate_expected_score(player1_rating, player2_rating)
        p2_expected = RatingService.calculate_expected_score(player2_rating, player1_rating)
        
        # Calculate new ratings
        p1_new = RatingService.calculate_new_rating(
            player1_rating, p1_expected, p1_actual, player1_k
        )
        p2_new = RatingService.calculate_new_rating(
            player2_rating, p2_expected, p2_actual, player2_k
        )
        
        return {
            "player1_old_rating": player1_rating,
            "player1_new_rating": p1_new,
            "player1_rating_change": p1_new - player1_rating,
            "player2_old_rating": player2_rating,
            "player2_new_rating": p2_new,
            "player2_rating_change": p2_new - player2_rating,
            "winner": winner,
            "was_upset": (winner == "player2" and player2_rating < player1_rating) or
                        (winner == "player1" and player1_rating < player2_rating)
        }
    
    @staticmethod
    def validate_match_duration(start_time: datetime, end_time: datetime) -> bool:
        """
        Validate match duration for anti-cheat.
        
        Args:
            start_time: Match start time
            end_time: Match end time
            
        Returns:
            True if valid duration, False otherwise
        """
        if not start_time or not end_time:
            return False
        
        duration = (end_time - start_time).total_seconds()
        return duration >= RatingService.MIN_MATCH_DURATION_SECONDS
    
    @staticmethod
    def calculate_rating_decay(
        current_rating: int,
        last_active_at: datetime,
        decay_days: int = None,
        decay_points: int = None
    ) -> int:
        """
        Calculate rating decay for inactive players.
        
        Args:
            current_rating: Current rating
            last_active_at: Last activity timestamp
            decay_days: Days before decay applies (default: 30)
            decay_points: Points to decay per period (default: 50)
            
        Returns:
            New rating after decay
        """
        decay_days = decay_days or RatingService.RATING_DECAY_DAYS
        decay_points = decay_points or RatingService.RATING_DECAY_POINTS
        
        if not last_active_at:
            return current_rating
        
        days_inactive = (datetime.utcnow() - last_active_at).days
        
        if days_inactive < decay_days:
            return current_rating
        
        # Calculate decay periods
        periods = days_inactive // decay_days
        total_decay = periods * decay_points
        
        new_rating = max(100, current_rating - total_decay)
        return new_rating
    
    @staticmethod
    def get_rating_tier(rating: int) -> str:
        """
        Get rating tier/division name.
        
        Args:
            rating: Current rating
            
        Returns:
            Tier name
        """
        if rating >= 2000:
            return "Diamond"
        elif rating >= 1800:
            return "Platinum"
        elif rating >= 1600:
            return "Gold"
        elif rating >= 1400:
            return "Silver"
        elif rating >= 1200:
            return "Bronze"
        else:
            return "Rookie"
    
    @staticmethod
    def get_matchmaking_range(rating: int, expansion: int = 0) -> Tuple[int, int]:
        """
        Get rating range for matchmaking.
        
        Args:
            rating: Player's current rating
            expansion: Range expansion factor (increases over time waiting)
            
        Returns:
            Tuple of (min_rating, max_rating)
        """
        base_range = 100
        range_size = base_range + (expansion * 50)
        
        min_rating = max(100, rating - range_size)
        max_rating = rating + range_size
        
        return (min_rating, max_rating)

    @staticmethod
    async def process_rating_update_for_match(db_session, match: Match) -> None:
        """
        Phase 4 safety guard:
        Rating updates must only occur for non-AI, finalized matches.
        """
        if match.is_ai_match or match.state != "finalized":
            # Explicitly skip AI matches and non-finalized matches
            return

        # Placeholder for Phase 5 rating logic.
        # Intentionally left without implementation in Phase 4.
    
    @classmethod
    async def process_match_result(
        cls,
        db_session,
        match_id: int,
        player1_id: int,
        player2_id: int,
        player1_score: float,
        player2_score: float,
        match_start_time: datetime,
        match_end_time: datetime
    ) -> Dict:
        """
        Process complete match and update ratings.
        
        Args:
            db_session: Database session
            match_id: Match ID
            player1_id: Player 1 user ID
            player2_id: Player 2 user ID
            player1_score: Player 1 total score
            player2_score: Player 2 total score
            match_start_time: Match start timestamp
            match_end_time: Match end timestamp
            
        Returns:
            Match result with rating changes
        """
        # Validate match duration
        if not cls.validate_match_duration(match_start_time, match_end_time):
            raise ValueError("Match duration too short - possible anti-cheat violation")
        
        # Get player ratings
        p1_rating = db_session.query(PlayerRating).filter(
            PlayerRating.user_id == player1_id
        ).first()
        
        p2_rating = db_session.query(PlayerRating).filter(
            PlayerRating.user_id == player2_id
        ).first()
        
        # Create ratings if don't exist
        if not p1_rating:
            p1_rating = PlayerRating(user_id=player1_id, current_rating=cls.INITIAL_RATING)
            db_session.add(p1_rating)
        
        if not p2_rating:
            p2_rating = PlayerRating(user_id=player2_id, current_rating=cls.INITIAL_RATING)
            db_session.add(p2_rating)
        
        # Get K-factors
        p1_k = p1_rating.get_k_factor()
        p2_k = p2_rating.get_k_factor()
        
        # Calculate new ratings
        result = cls.calculate_match_ratings(
            p1_rating.current_rating,
            p2_rating.current_rating,
            player1_score,
            player2_score,
            p1_k,
            p2_k
        )
        
        # Determine results
        if result["winner"] == "player1":
            p1_result = "win"
            p2_result = "loss"
        elif result["winner"] == "player2":
            p1_result = "loss"
            p2_result = "win"
        else:
            p1_result = "draw"
            p2_result = "draw"
        
        # Update ratings
        p1_history = p1_rating.update_rating(
            result["player1_new_rating"],
            match_id,
            p2_rating.current_rating,
            p1_result
        )
        
        p2_history = p2_rating.update_rating(
            result["player2_new_rating"],
            match_id,
            p1_rating.current_rating,
            p2_result
        )
        
        # Add history entries
        db_session.add(p1_history)
        db_session.add(p2_history)
        
        # Commit
        db_session.commit()
        
        return {
            "match_id": match_id,
            "player1": {
                "user_id": player1_id,
                "old_rating": result["player1_old_rating"],
                "new_rating": result["player1_new_rating"],
                "change": result["player1_rating_change"],
                "tier": cls.get_rating_tier(result["player1_new_rating"])
            },
            "player2": {
                "user_id": player2_id,
                "old_rating": result["player2_old_rating"],
                "new_rating": result["player2_new_rating"],
                "change": result["player2_rating_change"],
                "tier": cls.get_rating_tier(result["player2_new_rating"])
            },
            "winner": result["winner"],
            "was_upset": result["was_upset"]
        }
