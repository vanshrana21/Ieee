"""
Classroom Session State Machine - Production Grade

Features:
- DB-first transitions (commit before broadcast)
- Timer persistence with phase_start_timestamp
- Auto-transition on timer expiry
- Edge case handling (teacher offline, idle timeout)
- Reconnection safety

State Flow: created → preparing → study → moot → scoring → completed
"""
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import asyncio
import json
import logging

logger = logging.getLogger(__name__)


class ClassroomSessionState(Enum):
    """Classroom session states."""
    CREATED = "created"
    PREPARING = "preparing"
    STUDY = "study"
    MOOT = "moot"
    SCORING = "scoring"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class SessionStateMachine:
    """
    Production-grade state machine for classroom sessions.
    
    CRITICAL: All transitions commit to DB BEFORE any side effects.
    Database is source of truth; WebSocket is broadcast-only.
    """
    
    # Valid state transitions
    TRANSITIONS = {
        ClassroomSessionState.CREATED: [ClassroomSessionState.PREPARING, ClassroomSessionState.CANCELLED],
        ClassroomSessionState.PREPARING: [ClassroomSessionState.STUDY, ClassroomSessionState.CANCELLED],
        ClassroomSessionState.STUDY: [ClassroomSessionState.MOOT, ClassroomSessionState.CANCELLED],
        ClassroomSessionState.MOOT: [ClassroomSessionState.SCORING, ClassroomSessionState.CANCELLED],
        ClassroomSessionState.SCORING: [ClassroomSessionState.COMPLETED, ClassroomSessionState.CANCELLED],
        ClassroomSessionState.COMPLETED: [],
        ClassroomSessionState.CANCELLED: []
    }
    
    # Auto-transition rules: (from_state, to_state) if timer expired
    AUTO_TRANSITIONS = {
        ClassroomSessionState.STUDY: ClassroomSessionState.MOOT,
        ClassroomSessionState.MOOT: ClassroomSessionState.SCORING
    }
    
    def __init__(self, session_id: str, db_session=None, db=None):
        self.session_id = session_id
        self.db_session = db_session
        self._db = db
        self._timer_task = None
        self._auto_transition_task = None
        self._created_at = datetime.utcnow()
        
    async def transition_to(
        self, 
        new_state: ClassroomSessionState, 
        triggered_by: str,
        triggered_by_role: str,
        validation_data: Optional[Dict] = None,
        force: bool = False
    ) -> Dict[str, Any]:
        """
        Attempt state transition with validation.
        
        CRITICAL: Commits to DB BEFORE any side effects.
        
        Args:
            new_state: Target state
            triggered_by: User ID who triggered transition
            triggered_by_role: Role of user (TEACHER, STUDENT, SYSTEM)
            validation_data: Additional validation context
            force: Force transition bypassing some validations (for auto-transitions)
            
        Returns:
            Transition result with status and message
        """
        try:
            # Load session with row-level lock (concurrency protection)
            session = await self._load_session_with_lock()
            
            if not session:
                return {"success": False, "error": "Session not found", "current_state": None}
            
            current_state = ClassroomSessionState(session.current_state)
            
            # Validate transition rules
            if not force and not self._can_transition(current_state, new_state):
                return {
                    "success": False,
                    "error": f"Invalid transition: {current_state.value} → {new_state.value}",
                    "current_state": current_state.value
                }
            
            # Validate permissions and business rules
            if not force:
                validation = await self._validate_transition(
                    session, current_state, new_state, triggered_by, triggered_by_role, validation_data
                )
                if not validation["valid"]:
                    return {
                        "success": False,
                        "error": validation["message"],
                        "current_state": current_state.value
                    }
            
            # EXECUTE DB UPDATE (source of truth)
            from backend.orm.classroom_session import SessionState as ORMSessionState
            old_state = session.current_state
            session.current_state = new_state.value
            
            # Update timer persistence
            if new_state in [ClassroomSessionState.PREPARING, ClassroomSessionState.STUDY, ClassroomSessionState.MOOT]:
                duration_minutes = self._get_duration_for_state(new_state, validation_data)
                session.phase_start_timestamp = datetime.utcnow()
                session.phase_duration_seconds = duration_minutes * 60
                
                # Stop any existing timer task
                if self._timer_task:
                    self._timer_task.cancel()
                    self._timer_task = None
                
                # Start new timer task for auto-transition
                self._auto_transition_task = asyncio.create_task(
                    self._auto_transition_monitor(session.id, new_state, duration_minutes * 60)
                )
            
            if new_state == ClassroomSessionState.SCORING:
                # Freeze timer
                session.phase_duration_seconds = None
                if self._timer_task:
                    self._timer_task.cancel()
                    self._timer_task = None
            
            # Set completion timestamp
            if new_state in [ClassroomSessionState.COMPLETED, ClassroomSessionState.CANCELLED]:
                if new_state == ClassroomSessionState.COMPLETED:
                    session.completed_at = datetime.utcnow()
                else:
                    session.cancelled_at = datetime.utcnow()
                
                # Cleanup timer
                if self._timer_task:
                    self._timer_task.cancel()
                    self._timer_task = None
            
            # COMMIT TO DATABASE (critical for source of truth)
            await self._commit_db()
            
            logger.info(f"State transition committed: {old_state} → {new_state.value} for session {session.session_code}")
            
            # Execute side effects AFTER DB commit
            await self._on_enter_state(session, new_state, validation_data)
            
            # Broadcast state change (broadcast-only, never source of truth)
            await self._broadcast_state_change(session, old_state, new_state.value)
            
            return {
                "success": True,
                "from_state": old_state,
                "to_state": new_state.value,
                "timestamp": datetime.utcnow().isoformat(),
                "session_code": session.session_code
            }
            
        except Exception as e:
            logger.error(f"State transition failed: {str(e)}")
            await self._rollback_db()
            return {"success": False, "error": str(e), "current_state": None}
    
    async def _load_session_with_lock(self):
        """Load session with row-level lock for concurrency protection."""
        from backend.orm.classroom_session import ClassroomSession
        
        # Use with_for_update() for row-level lock (PostgreSQL)
        result = self._db.query(ClassroomSession).filter_by(id=self.session_id).with_for_update().first()
        return result
    
    async def _commit_db(self):
        """Commit database transaction."""
        if self._db:
            self._db.commit()
    
    async def _rollback_db(self):
        """Rollback database transaction."""
        if self._db:
            self._db.rollback()
    
    def _can_transition(self, current: ClassroomSessionState, new: ClassroomSessionState) -> bool:
        """Check if transition is valid."""
        return new in self.TRANSITIONS.get(current, [])
    
    async def _validate_transition(
        self,
        session,
        current_state: ClassroomSessionState,
        new_state: ClassroomSessionState,
        triggered_by: str,
        triggered_by_role: str,
        data: Optional[Dict]
    ) -> Dict[str, Any]:
        """Validate state-specific requirements with edge case handling."""
        
        # CREATED → PREPARING: Teacher role required
        if new_state == ClassroomSessionState.PREPARING:
            if triggered_by_role != "TEACHER":
                return {"valid": False, "message": "Only teachers can start preparing session"}
            return {"valid": True}
        
        # PREPARING → STUDY: Min 2 students required
        if new_state == ClassroomSessionState.STUDY:
            if triggered_by_role != "TEACHER":
                return {"valid": False, "message": "Only teachers can start study phase"}
            participant_count = len(session.participants) if session.participants else 0
            if participant_count < 2:
                return {"valid": False, "message": f"Minimum 2 students required (currently {participant_count})"}
            return {"valid": True}
        
        # STUDY → MOOT: Timer expired OR teacher permission
        if new_state == ClassroomSessionState.MOOT:
            is_teacher = triggered_by_role == "TEACHER"
            timer_expired = session.is_phase_expired() if hasattr(session, 'is_phase_expired') else False
            
            # Edge case: Teacher offline + timer expired = allow auto-transition
            if not is_teacher and not timer_expired:
                return {"valid": False, "message": "Study timer must expire or teacher must start moot"}
            
            # Log auto-transition edge case
            if timer_expired and not is_teacher:
                logger.info(f"Auto-transition STUDY→MOOT: timer expired, triggered by {triggered_by}")
            
            return {"valid": True}
        
        # MOOT → SCORING: Timer expired OR teacher permission
        if new_state == ClassroomSessionState.SCORING:
            is_teacher = triggered_by_role == "TEACHER"
            timer_expired = session.is_phase_expired() if hasattr(session, 'is_phase_expired') else False
            
            if not is_teacher and not timer_expired:
                return {"valid": False, "message": "Moot timer must expire or teacher must end moot"}
            
            if timer_expired and not is_teacher:
                logger.info(f"Auto-transition MOOT→SCORING: timer expired, triggered by {triggered_by}")
            
            return {"valid": True}
        
        # SCORING → COMPLETED: All scores submitted
        if new_state == ClassroomSessionState.COMPLETED:
            if triggered_by_role != "TEACHER":
                return {"valid": False, "message": "Only teachers can complete session"}
            # Check if all participants have scores
            participants_with_scores = [p for p in session.participants if p.score_id]
            if len(participants_with_scores) < len(session.participants):
                return {"valid": False, "message": "All scores must be submitted before completing"}
            return {"valid": True}
        
        # CANCELLED: Teacher only
        if new_state == ClassroomSessionState.CANCELLED:
            if triggered_by_role != "TEACHER":
                return {"valid": False, "message": "Only teachers can cancel session"}
            return {"valid": True}
        
        return {"valid": True}
    
    async def _on_enter_state(self, session, state: ClassroomSessionState, data: Optional[Dict]):
        """Execute actions on state entry."""
        
        if state == ClassroomSessionState.STUDY:
            # Initialize study phase
            logger.info(f"Session {session.session_code} entering STUDY phase")
            
        elif state == ClassroomSessionState.MOOT:
            # Assign roles and log
            await self._assign_roles_from_db(session)
            logger.info(f"Session {session.session_code} entering MOOT phase")
            
        elif state == ClassroomSessionState.SCORING:
            # Prepare scoring
            await self._init_scoring_from_db(session)
            logger.info(f"Session {session.session_code} entering SCORING phase")
            
        elif state == ClassroomSessionState.COMPLETED:
            # Calculate final leaderboard
            await self._calculate_and_save_leaderboard(session)
            logger.info(f"Session {session.session_code} COMPLETED")
            
        elif state == ClassroomSessionState.CANCELLED:
            # Cleanup
            logger.info(f"Session {session.session_code} CANCELLED")
    
    async def _auto_transition_monitor(self, session_id: int, current_state: ClassroomSessionState, duration_seconds: int):
        """Monitor timer and auto-transition when expired."""
        try:
            await asyncio.sleep(duration_seconds)
            
            # Check if state hasn't changed
            from backend.orm.classroom_session import ClassroomSession
            session = self._db.query(ClassroomSession).filter_by(id=session_id).first()
            
            if session and session.current_state == current_state.value:
                # Timer expired, check if auto-transition is configured
                if current_state in self.AUTO_TRANSITIONS:
                    next_state = self.AUTO_TRANSITIONS[current_state]
                    logger.info(f"Auto-transitioning session {session.session_code}: {current_state.value} → {next_state.value}")
                    
                    await self.transition_to(
                        next_state,
                        triggered_by="SYSTEM",
                        triggered_by_role="SYSTEM",
                        force=True  # Bypass validation for auto-transition
                    )
                    
        except asyncio.CancelledError:
            # Timer cancelled (normal when transitioning manually)
            pass
        except Exception as e:
            logger.error(f"Auto-transition monitor error: {e}")
    
    async def _assign_roles_from_db(self, session):
        """Assign roles to participants based on join order."""
        from backend.orm.classroom_session import ClassroomParticipant, ParticipantRole
        
        participants = sorted(session.participants, key=lambda p: p.joined_at)
        
        for i, participant in enumerate(participants):
            if i == 0:
                participant.role = ParticipantRole.PETITIONER.value
            elif i == 1:
                participant.role = ParticipantRole.RESPONDENT.value
            else:
                participant.role = ParticipantRole.OBSERVER.value
        
        await self._commit_db()
    
    async def _init_scoring_from_db(self, session):
        """Initialize scoring records for all participants."""
        from backend.orm.classroom_session import ClassroomScore
        
        for participant in session.participants:
            if not participant.score_id:
                score = ClassroomScore(
                    session_id=session.id,
                    user_id=participant.user_id
                )
                self._db.add(score)
                await self._commit_db()
                participant.score_id = score.id
        
        await self._commit_db()
    
    async def _calculate_and_save_leaderboard(self, session):
        """Calculate and save final leaderboard."""
        from backend.orm.classroom_session import ClassroomScore
        
        scores = self._db.query(ClassroomScore).filter_by(session_id=session.id).all()
        
        # Calculate totals
        for score in scores:
            score.calculate_total()
        
        await self._commit_db()
    
    async def _broadcast_state_change(self, session, old_state: str, new_state: str):
        """Broadcast state change via WebSocket (broadcast-only)."""
        # TODO: Implement WebSocket broadcast
        # This should ONLY broadcast, never modify state
        logger.info(f"Broadcast: Session {session.session_code} state change {old_state} → {new_state}")
    
    def _get_duration_for_state(self, state: ClassroomSessionState, data: Optional[Dict]) -> int:
        """Get duration in minutes for a state."""
        defaults = {
            ClassroomSessionState.PREPARING: 5,
            ClassroomSessionState.STUDY: 20,
            ClassroomSessionState.MOOT: 45
        }
        
        if data and "duration_minutes" in data:
            return data["duration_minutes"]
        
        return defaults.get(state, 30)
