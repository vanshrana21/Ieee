"""
Player Ratings Database Models

ELO rating system for Online 1v1 Mode.
Isolated from Classroom Mode - no shared tables.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime, timedelta

from backend.orm.base import Base


class PlayerRating(Base):
    """Player rating table - ELO system."""
    __tablename__ = "player_ratings"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False, index=True)
    
    # Current rating
    current_rating = Column(Integer, default=1000, nullable=False)
    peak_rating = Column(Integer, default=1000, nullable=False)
    
    # Match statistics
    matches_played = Column(Integer, default=0, nullable=False)
    wins = Column(Integer, default=0, nullable=False)
    losses = Column(Integer, default=0, nullable=False)
    draws = Column(Integer, default=0, nullable=False)
    
    # Activity tracking
    last_active_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Last processed match (for audit / inspection)
    last_match_id = Column(Integer, ForeignKey("matches.id"), nullable=True)
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    rating_history = relationship(
        "RatingHistory",
        back_populates="player_rating",
        cascade="all, delete-orphan",
        foreign_keys=lambda: [RatingHistory.player_rating_id]
    )
    
    def get_k_factor(self) -> int:
        """
        Calculate K-factor based on match count.
        - New players (< 5 matches): K = 40
        - Standard players (5-20 matches): K = 32
        - Experienced players (> 20 matches): K = 16
        """
        if self.matches_played < 5:
            return 40
        elif self.matches_played <= 20:
            return 32
        else:
            return 16
    
    def update_rating(self, new_rating: int, match_id: int, opponent_rating: int, result: str):
        """
        Update rating with history tracking.
        
        Args:
            new_rating: New calculated rating
            match_id: Match ID for history
            opponent_rating: Opponent's rating at time of match
            result: 'win', 'loss', or 'draw'
        """
        old_rating = self.current_rating
        
        # Update rating
        self.current_rating = new_rating
        if new_rating > self.peak_rating:
            self.peak_rating = new_rating
        
        # Update stats
        self.matches_played += 1
        if result == 'win':
            self.wins += 1
        elif result == 'loss':
            self.losses += 1
        else:
            self.draws += 1
        
        self.last_active_at = datetime.utcnow()
        
        # Create history entry
        return RatingHistory(
            user_id=self.user_id,
            player_rating_id=self.id,
            match_id=match_id,
            old_rating=old_rating,
            new_rating=new_rating,
            rating_change=new_rating - old_rating,
            opponent_rating=opponent_rating,
            result=result
        )
    
    def is_inactive(self, days: int = 30) -> bool:
        """Check if player is inactive (no matches for specified days)."""
        if not self.last_active_at:
            return True
        threshold = datetime.utcnow() - timedelta(days=days)
        return self.last_active_at < threshold
    
    def get_win_rate(self) -> float:
        """Calculate win rate percentage."""
        if self.matches_played == 0:
            return 0.0
        return (self.wins / self.matches_played) * 100
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "current_rating": self.current_rating,
            "peak_rating": self.peak_rating,
            "matches_played": self.matches_played,
            "wins": self.wins,
            "losses": self.losses,
            "draws": self.draws,
            "win_rate": round(self.get_win_rate(), 2),
            "k_factor": self.get_k_factor(),
            "last_active_at": self.last_active_at.isoformat() if self.last_active_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


class RatingHistory(Base):
    """Rating history table - tracks all rating changes."""
    __tablename__ = "rating_history"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False, index=True)
    player_rating_id = Column(
        Integer,
        ForeignKey("player_ratings.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Rating data
    old_rating = Column(Integer, nullable=False)
    new_rating = Column(Integer, nullable=False)
    rating_change = Column(Integer, nullable=False)
    opponent_rating = Column(Integer, nullable=False)
    result = Column(String(10), nullable=False)  # win, loss, draw
    
    # Timestamp
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    player_rating = relationship(
        "PlayerRating",
        back_populates="rating_history",
        foreign_keys=[player_rating_id]
    )
    user = relationship("User")
    match = relationship("Match")
    
    # Composite index for efficient queries and uniqueness per (user, match)
    __table_args__ = (
        Index('idx_rating_history_user_time', 'user_id', 'timestamp'),
        UniqueConstraint('user_id', 'match_id', name='uq_rating_history_user_match'),
    )
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "match_id": self.match_id,
            "old_rating": self.old_rating,
            "new_rating": self.new_rating,
            "rating_change": self.rating_change,
            "opponent_rating": self.opponent_rating,
            "result": self.result,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None
        }


class MatchmakingQueue(Base):
    """Matchmaking queue for online 1v1."""
    __tablename__ = "matchmaking_queue"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False, index=True)
    
    # Search criteria
    rating_min = Column(Integer, nullable=True)
    rating_max = Column(Integer, nullable=True)
    preferred_category = Column(String(50), nullable=True)
    
    # Queue metadata
    joined_at = Column(DateTime(timezone=True), server_default=func.now())
    last_ping_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Index for efficient matching
    __table_args__ = (
        Index('idx_queue_rating', 'rating_min', 'rating_max'),
        Index('idx_queue_joined', 'joined_at'),
    )
    
    def is_stale(self, minutes: int = 2) -> bool:
        """Check if queue entry is stale (no ping for specified minutes)."""
        threshold = datetime.utcnow() - timedelta(minutes=minutes)
        return self.last_ping_at < threshold
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "rating_min": self.rating_min,
            "rating_max": self.rating_max,
            "preferred_category": self.preferred_category,
            "joined_at": self.joined_at.isoformat() if self.joined_at else None,
            "last_ping_at": self.last_ping_at.isoformat() if self.last_ping_at else None
        }


# Add relationships to User model
def add_user_relationships():
    """Add rating relationships to User model."""
    from backend.orm.user import User
    
    User.player_rating = relationship("PlayerRating", back_populates="user", uselist=False)
    User.matchmaking_queue_entry = relationship("MatchmakingQueue", back_populates="user", uselist=False)
