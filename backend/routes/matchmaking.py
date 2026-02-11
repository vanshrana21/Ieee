"""
Matchmaking API Routes

REST API endpoints for Online 1v1 Mode (B2C).
"""
from fastapi import APIRouter, HTTPException, Depends, status, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
import random

from backend.database import get_db
from backend.orm.online_match import Match, MatchParticipant, MatchScore, MatchState, MatchCategory
from backend.orm.player_ratings import PlayerRating, MatchmakingQueue, RatingHistory
from backend.services.rating_service import RatingService


router = APIRouter(
    prefix="/api/matchmaking",
    tags=["matchmaking"]
)


def get_current_user():
    """Get current user from auth token."""
    return {"id": 1, "role": "student", "name": "Test Player", "rating": 1000}


@router.post("/queue/join", status_code=status.HTTP_201_CREATED)
async def join_queue(
    preferred_category: Optional[MatchCategory] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Join matchmaking queue."""
    # Check if already in queue
    existing = db.query(MatchmakingQueue).filter(
        MatchmakingQueue.user_id == current_user["id"]
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Already in queue")
    
    # Get player rating
    rating = db.query(PlayerRating).filter(
        PlayerRating.user_id == current_user["id"]
    ).first()
    
    if not rating:
        rating = PlayerRating(user_id=current_user["id"], current_rating=1000)
        db.add(rating)
        db.commit()
    
    # Calculate matchmaking range
    min_rating, max_rating = RatingService.get_matchmaking_range(rating.current_rating)
    
    # Add to queue
    queue_entry = MatchmakingQueue(
        user_id=current_user["id"],
        rating_min=min_rating,
        rating_max=max_rating,
        preferred_category=preferred_category.value if preferred_category else None
    )
    
    db.add(queue_entry)
    db.commit()
    
    return {
        "success": True,
        "message": "Joined matchmaking queue",
        "estimated_wait": "30-60 seconds",
        "rating_range": {"min": min_rating, "max": max_rating}
    }


@router.post("/queue/leave")
async def leave_queue(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Leave matchmaking queue."""
    queue_entry = db.query(MatchmakingQueue).filter(
        MatchmakingQueue.user_id == current_user["id"]
    ).first()
    
    if queue_entry:
        db.delete(queue_entry)
        db.commit()
    
    return {"success": True, "message": "Left matchmaking queue"}


@router.get("/queue/status")
async def queue_status(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get current queue status."""
    queue_entry = db.query(MatchmakingQueue).filter(
        MatchmakingQueue.user_id == current_user["id"]
    ).first()
    
    if not queue_entry:
        return {"in_queue": False}
    
    # Count players in queue
    total_in_queue = db.query(MatchmakingQueue).count()
    
    return {
        "in_queue": True,
        "joined_at": queue_entry.joined_at.isoformat(),
        "total_in_queue": total_in_queue,
        "rating_range": {
            "min": queue_entry.rating_min,
            "max": queue_entry.rating_max
        }
    }


@router.post("/match/find")
async def find_match(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Try to find a match."""
    player_entry = db.query(MatchmakingQueue).filter(
        MatchmakingQueue.user_id == current_user["id"]
    ).first()
    
    if not player_entry:
        raise HTTPException(status_code=400, detail="Not in queue")
    
    # Find opponent in same rating range
    opponent = db.query(MatchmakingQueue).filter(
        MatchmakingQueue.user_id != current_user["id"],
        MatchmakingQueue.rating_min <= player_entry.rating_max,
        MatchmakingQueue.rating_max >= player_entry.rating_min
    ).order_by(MatchmakingQueue.joined_at).first()
    
    if not opponent:
        return {
            "match_found": False,
            "message": "No opponent found yet, keep waiting..."
        }
    
    # Get topics
    topics = [
        "Right to Privacy vs National Security",
        "Freedom of Speech vs Hate Speech",
        "Property Rights vs Eminent Domain",
        "Data Protection vs Corporate Interests"
    ]
    
    # Create match
    match = Match(
        player1_id=current_user["id"],
        player2_id=opponent.user_id,
        player1_role=random.choice(["petitioner", "respondent"]),
        player2_role="respondent" if random.choice(["petitioner", "respondent"]) == "petitioner" else "petitioner",
        topic=random.choice(topics),
        category=MatchCategory.CONSTITUTIONAL.value,
        current_state=MatchState.MATCHED.value
    )
    
    db.add(match)
    db.commit()
    db.refresh(match)
    
    # Create participants
    p1 = MatchParticipant(match_id=match.id, user_id=current_user["id"], role=match.player1_role)
    p2 = MatchParticipant(match_id=match.id, user_id=opponent.user_id, role=match.player2_role)
    
    db.add(p1)
    db.add(p2)
    
    # Remove from queue
    db.delete(player_entry)
    db.delete(opponent)
    
    db.commit()
    
    return {
        "match_found": True,
        "match": match.to_dict(),
        "join_url": f"/html/online-1v1.html?match_id={match.id}"
    }


@router.get("/matches/{match_id}")
async def get_match(
    match_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get match details."""
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    
    # Check if user is participant
    if current_user["id"] not in [match.player1_id, match.player2_id]:
        raise HTTPException(status_code=403, detail="Not a participant in this match")
    
    return {
        "match": match.to_dict(),
        "participants": [p.to_dict() for p in match.participants],
        "scores": [s.to_dict() for s in match.scores],
        "is_player1": current_user["id"] == match.player1_id,
        "your_role": match.player1_role if current_user["id"] == match.player1_id else match.player2_role
    }


@router.post("/matches/{match_id}/ready")
async def set_ready(
    match_id: int,
    ready: bool = True,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Set player ready status."""
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    
    # Check if participant
    participant = db.query(MatchParticipant).filter(
        MatchParticipant.match_id == match_id,
        MatchParticipant.user_id == current_user["id"]
    ).first()
    
    if not participant:
        raise HTTPException(status_code=403, detail="Not a participant")
    
    participant.is_ready = ready
    db.commit()
    
    return {"success": True, "ready": ready}


@router.get("/matches/{match_id}/opponent")
async def get_opponent(
    match_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get opponent info."""
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    
    opponent_id = match.player2_id if current_user["id"] == match.player1_id else match.player1_id
    
    # Get opponent rating
    opponent_rating = db.query(PlayerRating).filter(
        PlayerRating.user_id == opponent_id
    ).first()
    
    return {
        "opponent_id": opponent_id,
        "opponent_rating": opponent_rating.current_rating if opponent_rating else 1000,
        "opponent_tier": RatingService.get_rating_tier(opponent_rating.current_rating) if opponent_rating else "Rookie"
    }


@router.get("/ratings/my")
async def get_my_rating(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get current user's rating."""
    rating = db.query(PlayerRating).filter(
        PlayerRating.user_id == current_user["id"]
    ).first()
    
    if not rating:
        rating = PlayerRating(user_id=current_user["id"], current_rating=1000)
        db.add(rating)
        db.commit()
        db.refresh(rating)
    
    return {
        "rating": rating.to_dict(),
        "tier": RatingService.get_rating_tier(rating.current_rating),
        "next_tier": RatingService.get_rating_tier(rating.current_rating + 200)
    }


@router.get("/ratings/leaderboard")
async def get_leaderboard(
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get global rating leaderboard."""
    ratings = db.query(PlayerRating).order_by(
        PlayerRating.current_rating.desc()
    ).limit(limit).all()
    
    leaderboard = []
    for rank, rating in enumerate(ratings, 1):
        leaderboard.append({
            "rank": rank,
            "user_id": rating.user_id,
            "rating": rating.current_rating,
            "tier": RatingService.get_rating_tier(rating.current_rating),
            "matches_played": rating.matches_played,
            "win_rate": round(rating.get_win_rate(), 2)
        })
    
    return {"leaderboard": leaderboard}


@router.get("/ratings/history")
async def get_rating_history(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get user's rating history."""
    history = db.query(RatingHistory).filter(
        RatingHistory.user_id == current_user["id"]
    ).order_by(
        RatingHistory.timestamp.desc()
    ).limit(limit).all()
    
    return {
        "history": [h.to_dict() for h in history]
    }


@router.post("/matches/{match_id}/complete")
async def complete_match(
    match_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Complete match and calculate ratings."""
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    
    if match.current_state != MatchState.SCORING.value:
        raise HTTPException(status_code=400, detail="Match not in scoring state")
    
    # Get scores
    scores = db.query(MatchScore).filter(MatchScore.match_id == match_id).all()
    if len(scores) < 2:
        raise HTTPException(status_code=400, detail="Scores not submitted")
    
    p1_score = next((s for s in scores if s.user_id == match.player1_id), None)
    p2_score = next((s for s in scores if s.user_id == match.player2_id), None)
    
    if not p1_score or not p2_score:
        raise HTTPException(status_code=400, detail="Missing scores")
    
    # Calculate winner
    if p1_score.total_score > p2_score.total_score:
        match.winner_id = match.player1_id
    elif p2_score.total_score > p1_score.total_score:
        match.winner_id = match.player2_id
    # Draw if equal
    
    # Update ratings
    result = await RatingService.process_match_result(
        db,
        match_id,
        match.player1_id,
        match.player2_id,
        p1_score.total_score or 0,
        p2_score.total_score or 0,
        match.started_at or match.created_at,
        datetime.utcnow()
    )
    
    # Update match state
    match.current_state = MatchState.FINISHED.value
    match.completed_at = datetime.utcnow()
    db.commit()
    
    return {
        "success": True,
        "match_result": result
    }
