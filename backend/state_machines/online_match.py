"""
Online Match State Machine

Production-safe state machine for online 1v1 moot court matches.
All state transitions are validated server-side.

State Flow:
searching → matched → prep → live → scoring → rating_update → finished
"""
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import asyncio


class OnlineMatchState(Enum):
    """Online match states."""
    SEARCHING = "searching"
    MATCHED = "matched"
    PREP = "prep"
    LIVE = "live"
    SCORING = "scoring"
    RATING_UPDATE = "rating_update"
    FINISHED = "finished"


class OnlineMatchStateMachine:
    """
    Manages online 1v1 match state transitions.
    Server-authoritative: All transitions validated server-side.
    """
    
    # Valid state transitions
    TRANSITIONS = {
        OnlineMatchState.SEARCHING: [OnlineMatchState.MATCHED],
        OnlineMatchState.MATCHED: [OnlineMatchState.PREP],
        OnlineMatchState.PREP: [OnlineMatchState.LIVE],
        OnlineMatchState.LIVE: [OnlineMatchState.SCORING],
        OnlineMatchState.SCORING: [OnlineMatchState.RATING_UPDATE],
        OnlineMatchState.RATING_UPDATE: [OnlineMatchState.FINISHED],
        OnlineMatchState.FINISHED: []
    }
    
    def __init__(self, match_id: str, db_session=None):
        self.match_id = match_id
        self.db_session = db_session
        self._state = OnlineMatchState.SEARCHING
        self._player1_id = None
        self._player2_id = None
        self._player1_role = None
        self._player2_role = None
        self._player1_ready = False
        self._player2_ready = False
        self._player1_connected = False
        self._player2_connected = False
        self._timer_task = None
        self._scores = {}
        self._winner_id = None
        self._created_at = datetime.utcnow()
        self._state_changed_at = datetime.utcnow()
        self._started_at = None
        self._completed_at = None
        
    @property
    def state(self) -> OnlineMatchState:
        return self._state
    
    @property
    def state_name(self) -> str:
        return self._state.value
    
    @property
    def player1_id(self) -> Optional[str]:
        return self._player1_id
    
    @property
    def player2_id(self) -> Optional[str]:
        return self._player2_id
    
    def can_transition_to(self, new_state: OnlineMatchState) -> bool:
        """Check if transition to new state is valid."""
        return new_state in self.TRANSITIONS.get(self._state, [])
    
    async def transition_to(
        self, 
        new_state: OnlineMatchState,
        validation_data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Attempt state transition with validation.
        
        Args:
            new_state: Target state
            validation_data: Additional validation context
            
        Returns:
            Transition result with status and message
        """
        # Validate transition
        if not self.can_transition_to(new_state):
            return {
                "success": False,
                "error": f"Invalid transition: {self.state_name} → {new_state.value}",
                "current_state": self.state_name
            }
        
        # State-specific validation
        validation_result = await self._validate_transition(new_state, validation_data)
        
        if not validation_result["valid"]:
            return {
                "success": False,
                "error": validation_result["message"],
                "current_state": self.state_name
            }
        
        # Execute transition
        old_state = self._state
        self._state = new_state
        self._state_changed_at = datetime.utcnow()
        
        # Execute state entry actions
        await self._on_enter_state(new_state, validation_data)
        
        return {
            "success": True,
            "from_state": old_state.value,
            "to_state": new_state.value,
            "timestamp": self._state_changed_at.isoformat()
        }
    
    async def _validate_transition(
        self, 
        new_state: OnlineMatchState,
        data: Optional[Dict]
    ) -> Dict[str, Any]:
        """Validate state-specific requirements."""
        
        # SEARCHING → MATCHED: Opponent found with valid rating match
        if new_state == OnlineMatchState.MATCHED:
            if not self._player1_id or not self._player2_id:
                return {
                    "valid": False,
                    "message": "Both players must be assigned before matching"
                }
            
            # Check rating match (±100 points)
            rating_diff = await self._get_rating_difference()
            if rating_diff > 100:
                return {
                    "valid": False,
                    "message": "Rating difference too large for fair match"
                }
            
            return {"valid": True}
        
        # MATCHED → PREP: Both players ready
        if new_state == OnlineMatchState.PREP:
            if not (self._player1_ready and self._player2_ready):
                return {
                    "valid": False,
                    "message": "Both players must be ready"
                }
            if not (self._player1_connected and self._player2_connected):
                return {
                    "valid": False,
                    "message": "Both players must be connected"
                }
            return {"valid": True}
        
        # PREP → LIVE: Prep timer expired
        if new_state == OnlineMatchState.LIVE:
            timer_expired = await self._is_timer_expired()
            if not timer_expired:
                return {
                    "valid": False,
                    "message": "Prep timer must expire"
                }
            return {"valid": True}
        
        # LIVE → SCORING: Moot timer expired
        if new_state == OnlineMatchState.SCORING:
            timer_expired = await self._is_timer_expired()
            if not timer_expired:
                return {
                    "valid": False,
                    "message": "Moot timer must expire"
                }
            
            # Anti-cheat: Minimum match duration (5 minutes)
            if self._started_at:
                elapsed = (datetime.utcnow() - self._started_at).total_seconds()
                if elapsed < 300:  # 5 minutes
                    return {
                        "valid": False,
                        "message": "Minimum match duration not met"
                    }
            
            return {"valid": True}
        
        # SCORING → RATING_UPDATE: AI scores calculated
        if new_state == OnlineMatchState.RATING_UPDATE:
            if not await self._scores_calculated():
                return {
                    "valid": False,
                    "message": "AI scores must be calculated first"
                }
            return {"valid": True}
        
        # RATING_UPDATE → FINISHED: Ratings updated
        if new_state == OnlineMatchState.FINISHED:
            if not await self._ratings_updated():
                return {
                    "valid": False,
                    "message": "Ratings must be updated before finishing"
                }
            return {"valid": True}
        
        return {"valid": True}
    
    async def _on_enter_state(
        self, 
        state: OnlineMatchState,
        data: Optional[Dict]
    ):
        """Execute actions on state entry."""
        
        if state == OnlineMatchState.MATCHED:
            # Create match room, assign roles
            await self._assign_roles(data)
            
        elif state == OnlineMatchState.PREP:
            # Start prep timer (10 minutes)
            await self._start_timer(600)  # 10 minutes
            
        elif state == OnlineMatchState.LIVE:
            # Start moot timer, enable argument submission
            self._started_at = datetime.utcnow()
            moot_minutes = data.get("moot_time_minutes", 30) if data else 30
            await self._start_timer(moot_minutes * 60)
            
        elif state == OnlineMatchState.SCORING:
            # Freeze timer, calculate AI scores
            await self._stop_timer()
            await self._calculate_ai_scores()
            
        elif state == OnlineMatchState.RATING_UPDATE:
            # Calculate ELO rating changes
            await self._calculate_rating_changes()
            await self._update_ratings()
            
        elif state == OnlineMatchState.FINISHED:
            # Close match room, show results
            self._completed_at = datetime.utcnow()
            await self._cleanup()
    
    async def _get_rating_difference(self) -> int:
        """Get rating difference between players."""
        # TODO: Fetch ratings from database
        return 0  # Placeholder
    
    async def _is_timer_expired(self) -> bool:
        """Check if current timer has expired."""
        # TODO: Implement timer check
        return False  # Placeholder
    
    async def _scores_calculated(self) -> bool:
        """Check if AI scores are calculated."""
        # TODO: Check if scores exist
        return True  # Placeholder
    
    async def _ratings_updated(self) -> bool:
        """Check if ratings are updated."""
        # TODO: Check if ratings updated
        return True  # Placeholder
    
    async def _assign_roles(self, data: Optional[Dict]):
        """Assign petitioner/respondent roles."""
        if data and "player1_role" in data:
            self._player1_role = data["player1_role"]
            self._player2_role = "respondent" if data["player1_role"] == "petitioner" else "petitioner"
        else:
            # Random assignment
            import random
            self._player1_role = random.choice(["petitioner", "respondent"])
            self._player2_role = "respondent" if self._player1_role == "petitioner" else "petitioner"
    
    async def _start_timer(self, duration_seconds: int):
        """Start server-side timer."""
        if self._timer_task:
            self._timer_task.cancel()
        
        async def timer_callback():
            await asyncio.sleep(duration_seconds)
            await self._on_timer_expired()
        
        self._timer_task = asyncio.create_task(timer_callback())
    
    async def _stop_timer(self):
        """Stop current timer."""
        if self._timer_task:
            self._timer_task.cancel()
            self._timer_task = None
    
    async def _on_timer_expired(self):
        """Handle timer expiration."""
        # Auto-transition based on current state
        if self._state == OnlineMatchState.PREP:
            await self.transition_to(OnlineMatchState.LIVE)
        elif self._state == OnlineMatchState.LIVE:
            await self.transition_to(OnlineMatchState.SCORING)
    
    async def _calculate_ai_scores(self):
        """Calculate AI scores for both players."""
        # TODO: Call AI service for scoring
        self._scores = {
            self._player1_id: {
                "legal_reasoning": 0,
                "citation_format": 0,
                "courtroom_etiquette": 0,
                "responsiveness": 0,
                "time_management": 0,
                "total_score": 0
            },
            self._player2_id: {
                "legal_reasoning": 0,
                "citation_format": 0,
                "courtroom_etiquette": 0,
                "responsiveness": 0,
                "time_management": 0,
                "total_score": 0
            }
        }
    
    async def _calculate_rating_changes(self):
        """Calculate ELO rating changes."""
        # TODO: Use RatingService for calculation
        # Determine winner based on scores
        p1_score = self._scores.get(self._player1_id, {}).get("total_score", 0)
        p2_score = self._scores.get(self._player2_id, {}).get("total_score", 0)
        
        if p1_score > p2_score:
            self._winner_id = self._player1_id
        elif p2_score > p1_score:
            self._winner_id = self._player2_id
        else:
            # Draw
            pass
    
    async def _update_ratings(self):
        """Update player ratings in database."""
        # TODO: Update ratings via RatingService
        pass
    
    async def _cleanup(self):
        """Cleanup resources after match completion."""
        await self._stop_timer()
        # Schedule room destruction after 5 minutes
        asyncio.create_task(self._delayed_cleanup())
    
    async def _delayed_cleanup(self, delay_seconds: int = 300):
        """Delayed cleanup (5 minutes after completion)."""
        await asyncio.sleep(delay_seconds)
        # TODO: Archive match data, remove from active rooms
        pass
    
    def set_player1(self, player_id: str):
        """Set player 1."""
        self._player1_id = player_id
    
    def set_player2(self, player_id: str):
        """Set player 2."""
        self._player2_id = player_id
    
    def set_player_ready(self, player_id: str, ready: bool = True):
        """Set player ready status."""
        if player_id == self._player1_id:
            self._player1_ready = ready
        elif player_id == self._player2_id:
            self._player2_ready = ready
    
    def set_player_connected(self, player_id: str, connected: bool = True):
        """Set player connection status."""
        if player_id == self._player1_id:
            self._player1_connected = connected
        elif player_id == self._player2_id:
            self._player2_connected = connected
    
    def get_state_data(self) -> Dict[str, Any]:
        """Get current state data for WebSocket broadcast."""
        return {
            "match_id": self.match_id,
            "state": self.state_name,
            "player1_id": self._player1_id,
            "player2_id": self._player2_id,
            "player1_role": self._player1_role,
            "player2_role": self._player2_role,
            "player1_ready": self._player1_ready,
            "player2_ready": self._player2_ready,
            "player1_connected": self._player1_connected,
            "player2_connected": self._player2_connected,
            "created_at": self._created_at.isoformat(),
            "state_changed_at": self._state_changed_at.isoformat(),
            "started_at": self._started_at.isoformat() if self._started_at else None
        }
    
    def get_match_result(self) -> Optional[Dict[str, Any]]:
        """Get match result data (only if finished)."""
        if self._state != OnlineMatchState.FINISHED:
            return None
        
        return {
            "match_id": self.match_id,
            "winner_id": self._winner_id,
            "player1_score": self._scores.get(self._player1_id, {}),
            "player2_score": self._scores.get(self._player2_id, {}),
            "completed_at": self._completed_at.isoformat() if self._completed_at else None
        }
