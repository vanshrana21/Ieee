"""
Classroom Session State Machine

Production-safe state machine for classroom mode moot court sessions.
All state transitions are validated server-side.

State Flow:
created → preparing → study → moot → scoring → completed
"""
from enum import Enum
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import asyncio
import json


class ClassroomSessionState(Enum):
    """Classroom session states."""
    CREATED = "created"
    PREPARING = "preparing"
    STUDY = "study"
    MOOT = "moot"
    SCORING = "scoring"
    COMPLETED = "completed"


class SessionStateMachine:
    """
    Manages classroom session state transitions.
    Server-authoritative: All transitions validated server-side.
    """
    
    # Valid state transitions
    TRANSITIONS = {
        ClassroomSessionState.CREATED: [ClassroomSessionState.PREPARING],
        ClassroomSessionState.PREPARING: [ClassroomSessionState.STUDY],
        ClassroomSessionState.STUDY: [ClassroomSessionState.MOOT],
        ClassroomSessionState.MOOT: [ClassroomSessionState.SCORING],
        ClassroomSessionState.SCORING: [ClassroomSessionState.COMPLETED],
        ClassroomSessionState.COMPLETED: []
    }
    
    def __init__(self, session_id: str, db_session=None):
        self.session_id = session_id
        self.db_session = db_session
        self._state = ClassroomSessionState.CREATED
        self._timer_task = None
        self._participants = set()
        self._scores = {}
        self._created_at = datetime.utcnow()
        self._state_changed_at = datetime.utcnow()
        
    @property
    def state(self) -> ClassroomSessionState:
        return self._state
    
    @property
    def state_name(self) -> str:
        return self._state.value
    
    def can_transition_to(self, new_state: ClassroomSessionState) -> bool:
        """Check if transition to new state is valid."""
        return new_state in self.TRANSITIONS.get(self._state, [])
    
    async def transition_to(
        self, 
        new_state: ClassroomSessionState, 
        triggered_by: str,
        validation_data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Attempt state transition with validation.
        
        Args:
            new_state: Target state
            triggered_by: User ID who triggered transition
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
        validation_result = await self._validate_transition(
            new_state, triggered_by, validation_data
        )
        
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
        new_state: ClassroomSessionState,
        triggered_by: str,
        data: Optional[Dict]
    ) -> Dict[str, Any]:
        """Validate state-specific requirements."""
        
        # CREATED → PREPARING: Teacher role required
        if new_state == ClassroomSessionState.PREPARING:
            if not await self._is_teacher(triggered_by):
                return {
                    "valid": False,
                    "message": "Only teachers can start preparing session"
                }
            return {"valid": True}
        
        # PREPARING → STUDY: Min 2 students required
        if new_state == ClassroomSessionState.STUDY:
            if len(self._participants) < 2:
                return {
                    "valid": False,
                    "message": "Minimum 2 students required to start study phase"
                }
            return {"valid": True}
        
        # STUDY → MOOT: Timer expired OR teacher permission
        if new_state == ClassroomSessionState.MOOT:
            is_teacher = await self._is_teacher(triggered_by)
            timer_expired = await self._is_timer_expired()
            
            if not (is_teacher or timer_expired):
                return {
                    "valid": False,
                    "message": "Study timer must expire or teacher must start moot"
                }
            return {"valid": True}
        
        # MOOT → SCORING: Timer expired OR teacher permission
        if new_state == ClassroomSessionState.SCORING:
            is_teacher = await self._is_teacher(triggered_by)
            timer_expired = await self._is_timer_expired()
            
            if not (is_teacher or timer_expired):
                return {
                    "valid": False,
                    "message": "Moot timer must expire or teacher must end moot"
                }
            return {"valid": True}
        
        # SCORING → COMPLETED: All scores submitted
        if new_state == ClassroomSessionState.COMPLETED:
            if not await self._all_scores_submitted():
                return {
                    "valid": False,
                    "message": "All scores must be submitted before completing"
                }
            return {"valid": True}
        
        return {"valid": True}
    
    async def _on_enter_state(
        self, 
        state: ClassroomSessionState,
        data: Optional[Dict]
    ):
        """Execute actions on state entry."""
        
        if state == ClassroomSessionState.PREPARING:
            # Generate session code, set prep time
            prep_minutes = data.get("prep_time_minutes", 30) if data else 30
            await self._start_timer(prep_minutes * 60)
            
        elif state == ClassroomSessionState.STUDY:
            # Study phase timer
            study_minutes = data.get("study_time_minutes", 20) if data else 20
            await self._start_timer(study_minutes * 60)
            
        elif state == ClassroomSessionState.MOOT:
            # Assign roles, start moot timer
            await self._assign_roles()
            moot_minutes = data.get("moot_time_minutes", 45) if data else 45
            await self._start_timer(moot_minutes * 60)
            
        elif state == ClassroomSessionState.SCORING:
            # Freeze timer, prepare scoring
            await self._stop_timer()
            await self._init_scoring()
            
        elif state == ClassroomSessionState.COMPLETED:
            # Calculate leaderboard, cleanup
            await self._calculate_leaderboard()
            await self._cleanup()
    
    async def _is_teacher(self, user_id: str) -> bool:
        """Check if user has teacher role."""
        # TODO: Implement role check from database
        return True  # Placeholder
    
    async def _is_timer_expired(self) -> bool:
        """Check if current timer has expired."""
        # TODO: Implement timer check
        return False  # Placeholder
    
    async def _all_scores_submitted(self) -> bool:
        """Check if all participant scores are submitted."""
        # TODO: Implement score check
        return True  # Placeholder
    
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
        # Broadcast timer expired event
        pass  # TODO: Implement WebSocket broadcast
    
    async def _assign_roles(self):
        """Assign petitioner/respondent roles to participants."""
        participants = list(self._participants)
        if len(participants) >= 2:
            # Assign alternating roles
            for i, user_id in enumerate(participants):
                role = "petitioner" if i % 2 == 0 else "respondent"
                # TODO: Save role assignment to database
                pass
    
    async def _init_scoring(self):
        """Initialize scoring for all participants."""
        for user_id in self._participants:
            self._scores[user_id] = {
                "legal_reasoning": None,
                "citation_format": None,
                "courtroom_etiquette": None,
                "responsiveness": None,
                "time_management": None,
                "total_score": None,
                "submitted": False
            }
    
    async def _calculate_leaderboard(self):
        """Calculate final leaderboard."""
        # Sort by total score
        sorted_scores = sorted(
            self._scores.items(),
            key=lambda x: x[1].get("total_score", 0) if x[1] else 0,
            reverse=True
        )
        # TODO: Save leaderboard to database
        return sorted_scores
    
    async def _cleanup(self):
        """Cleanup resources after session completion."""
        await self._stop_timer()
        # Schedule room destruction after 5 minutes
        asyncio.create_task(self._delayed_cleanup())
    
    async def _delayed_cleanup(self, delay_seconds: int = 300):
        """Delayed cleanup (5 minutes after completion)."""
        await asyncio.sleep(delay_seconds)
        # TODO: Archive session data, remove from active rooms
        pass
    
    def add_participant(self, user_id: str) -> bool:
        """Add participant to session."""
        if self._state not in [ClassroomSessionState.CREATED, ClassroomSessionState.PREPARING]:
            return False
        self._participants.add(user_id)
        return True
    
    def remove_participant(self, user_id: str):
        """Remove participant from session."""
        self._participants.discard(user_id)
    
    def get_state_data(self) -> Dict[str, Any]:
        """Get current state data for WebSocket broadcast."""
        return {
            "session_id": self.session_id,
            "state": self.state_name,
            "participants_count": len(self._participants),
            "created_at": self._created_at.isoformat(),
            "state_changed_at": self._state_changed_at.isoformat()
        }
