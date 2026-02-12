"""
Round State Machine - Phase 7
Strict server-side state enforcement for classroom rounds.
"""
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.orm.classroom_round import ClassroomRound, RoundState
from backend.orm.classroom_round_action import ClassroomRoundAction, ActionType
from backend.orm.classroom_session import ClassroomSession

logger = logging.getLogger(__name__)


class InvalidTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""
    pass


class UnauthorizedActionError(Exception):
    """Raised when an unauthorized user attempts an action."""
    pass


class RoundStateMachine:
    """
    Server-side state machine for classroom rounds.
    
    Enforces valid state transitions, logs all actions, and handles
    timing, concurrency, and authorization.
    """
    
    # Valid state transitions: {current_state: [allowed_next_states]}
    ALLOWED_TRANSITIONS: Dict[RoundState, List[RoundState]] = {
        RoundState.WAITING: [
            RoundState.ARGUMENT_PETITIONER,
            RoundState.CANCELLED
        ],
        RoundState.ARGUMENT_PETITIONER: [
            RoundState.ARGUMENT_RESPONDENT,
            RoundState.PAUSED,
            RoundState.CANCELLED
        ],
        RoundState.ARGUMENT_RESPONDENT: [
            RoundState.REBUTTAL,
            RoundState.PAUSED,
            RoundState.CANCELLED
        ],
        RoundState.REBUTTAL: [
            RoundState.SUR_REBUTTAL,
            RoundState.JUDGE_QUESTIONS,
            RoundState.PAUSED,
            RoundState.CANCELLED
        ],
        RoundState.SUR_REBUTTAL: [
            RoundState.JUDGE_QUESTIONS,
            RoundState.PAUSED,
            RoundState.CANCELLED
        ],
        RoundState.JUDGE_QUESTIONS: [
            RoundState.SCORING,
            RoundState.PAUSED,
            RoundState.CANCELLED
        ],
        RoundState.SCORING: [
            RoundState.COMPLETED,
            RoundState.PAUSED
        ],
        RoundState.PAUSED: [
            # Can resume to any previous state (handled specially)
        ],
        RoundState.COMPLETED: [],
        RoundState.CANCELLED: []
    }
    
    # State timing defaults (in seconds)
    DEFAULT_PHASE_TIMES: Dict[RoundState, int] = {
        RoundState.ARGUMENT_PETITIONER: 600,    # 10 minutes
        RoundState.ARGUMENT_RESPONDENT: 600,  # 10 minutes
        RoundState.REBUTTAL: 180,              # 3 minutes
        RoundState.SUR_REBUTTAL: 180,          # 3 minutes
        RoundState.JUDGE_QUESTIONS: 300,       # 5 minutes
        RoundState.SCORING: 300,               # 5 minutes
    }
    
    def __init__(self, db: AsyncSession, round_obj: ClassroomRound):
        self.db = db
        self.round = round_obj
        self._original_state = round_obj.state
        self._original_version = round_obj.version
    
    def _is_valid_transition(self, from_state: RoundState, to_state: RoundState) -> bool:
        """Check if a state transition is valid."""
        # Special case: paused state can resume to previous state
        if from_state == RoundState.PAUSED:
            return to_state == self.round.previous_state
        
        allowed = self.ALLOWED_TRANSITIONS.get(from_state, [])
        return to_state in allowed
    
    def _is_authorized(self, actor_id: int, action: str) -> bool:
        """Check if actor is authorized to perform action."""
        # Teacher/creator can do everything
        # Judge can control round flow
        # Participants can only submit arguments
        # AI can only respond when configured
        
        # Get actor info from round
        is_teacher = actor_id == self.round.session.teacher_id if hasattr(self.round, 'session') else False
        is_judge = actor_id == self.round.judge_id
        is_petitioner = actor_id == self.round.petitioner_id
        is_respondent = actor_id == self.round.respondent_id
        
        if action in ["transition", "pause", "cancel", "force_advance"]:
            return is_teacher or is_judge
        elif action in ["submit_argument", "objection"]:
            return is_petitioner or is_respondent
        elif action in ["score", "declare_winner"]:
            return is_judge or is_teacher
        
        return False
    
    async def transition(
        self,
        actor_id: int,
        new_state: RoundState,
        payload: Optional[Dict[str, Any]] = None,
        force: bool = False,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> ClassroomRound:
        """
        Transition round to new state with validation and logging.
        
        Args:
            actor_id: User performing the action
            new_state: Target state
            payload: Additional data for the action
            force: Bypass validation (teacher only)
            ip_address: For audit logging
            user_agent: For audit logging
            
        Returns:
            Updated ClassroomRound
            
        Raises:
            InvalidTransitionError: If transition is invalid
            UnauthorizedActionError: If actor is not authorized
        """
        # Validate transition
        if not force and not self._is_valid_transition(self.round.state, new_state):
            raise InvalidTransitionError(
                f"Cannot transition from {self.round.state.value} to {new_state.value}. "
                f"Allowed: {[s.value for s in self.ALLOWED_TRANSITIONS.get(self.round.state, [])]}"
            )
        
        # Check authorization (skip for forced transitions by teacher)
        if not force and not self._is_authorized(actor_id, "transition"):
            raise UnauthorizedActionError(
                f"User {actor_id} is not authorized to transition round {self.round.id}"
            )
        
        # Acquire row lock for concurrency safety
        await self.db.execute(
            select(ClassroomRound)
            .where(ClassroomRound.id == self.round.id)
            .with_for_update()
        )
        
        # Check for concurrent modification (optimistic locking)
        result = await self.db.execute(
            select(ClassroomRound.version)
            .where(ClassroomRound.id == self.round.id)
        )
        current_version = result.scalar()
        
        if current_version != self._original_version:
            await self.db.rollback()
            raise ConcurrentModificationError(
                f"Round {self.round.id} was modified by another process. "
                f"Expected version {self._original_version}, found {current_version}"
            )
        
        # Store previous state for pause/resume
        old_state = self.round.state
        if new_state == RoundState.PAUSED:
            self.round.previous_state = old_state
        
        # Update round state
        self.round.state = new_state
        self.round.version += 1
        
        # Set phase timing for timed states
        if new_state in self.DEFAULT_PHASE_TIMES:
            self.round.start_phase(new_state.value, self.DEFAULT_PHASE_TIMES[new_state])
        
        # Mark completion time
        if new_state in [RoundState.COMPLETED, RoundState.CANCELLED]:
            self.round.ended_at = datetime.utcnow()
        
        # Log the action
        action_log = ClassroomRoundAction.from_transition(
            round_id=self.round.id,
            session_id=self.round.session_id,
            actor_id=actor_id,
            action_type=ActionType.STATE_TRANSITION if not force else ActionType.FORCE_STATE_CHANGE,
            from_state=old_state.value,
            to_state=new_state.value,
            payload={
                "forced": force,
                **(payload or {})
            },
            ip_address=ip_address,
            user_agent=user_agent
        )
        self.db.add(action_log)
        
        # Add to round logs
        self.round.add_log_entry(
            "state_transition",
            actor_id,
            {"from": old_state.value, "to": new_state.value, "forced": force}
        )
        
        await self.db.flush()
        
        logger.info(
            f"Round {self.round.id} transitioned: {old_state.value} -> {new_state.value} "
            f"by user {actor_id} (forced={force})"
        )
        
        return self.round
    
    async def pause(self, actor_id: int, ip_address: Optional[str] = None) -> ClassroomRound:
        """Pause the round."""
        return await self.transition(
            actor_id=actor_id,
            new_state=RoundState.PAUSED,
            ip_address=ip_address
        )
    
    async def resume(self, actor_id: int, ip_address: Optional[str] = None) -> ClassroomRound:
        """Resume from paused state."""
        if self.round.state != RoundState.PAUSED:
            raise InvalidTransitionError("Can only resume from PAUSED state")
        
        if not self.round.previous_state:
            raise InvalidTransitionError("No previous state to resume to")
        
        return await self.transition(
            actor_id=actor_id,
            new_state=self.round.previous_state,
            ip_address=ip_address
        )
    
    async def auto_transition(self, target_state: RoundState) -> ClassroomRound:
        """
        Automatic transition (e.g., timer expiration).
        Used by background Celery tasks.
        """
        # Verify round is still in expected state before auto-transitioning
        await self.db.refresh(self.round)
        
        # Only auto-transition from timed states
        if self.round.state not in self.DEFAULT_PHASE_TIMES:
            logger.warning(f"Cannot auto-transition from {self.round.state.value}")
            return self.round
        
        return await self.transition(
            actor_id=0,  # System actor
            new_state=target_state,
            payload={"auto": True, "reason": "timer_expired"}
        )
    
    async def submit_score(
        self,
        actor_id: int,
        petitioner_score: float,
        respondent_score: float,
        winner_id: Optional[int] = None,
        feedback: Optional[Dict] = None
    ) -> ClassroomRound:
        """Submit scores for the round."""
        if not self._is_authorized(actor_id, "score"):
            raise UnauthorizedActionError("Not authorized to submit scores")
        
        self.round.petitioner_score = petitioner_score
        self.round.respondent_score = respondent_score
        
        if winner_id:
            self.round.winner_id = winner_id
        else:
            # Auto-determine winner
            if petitioner_score > respondent_score:
                self.round.winner_id = self.round.petitioner_id
            elif respondent_score > petitioner_score:
                self.round.winner_id = self.round.respondent_id
        
        # Log the scoring
        action_log = ClassroomRoundAction(
            round_id=self.round.id,
            session_id=self.round.session_id,
            actor_user_id=actor_id,
            action_type=ActionType.SCORE_SUBMITTED,
            payload={
                "petitioner_score": petitioner_score,
                "respondent_score": respondent_score,
                "winner_id": self.round.winner_id,
                "feedback": feedback
            }
        )
        self.db.add(action_log)
        
        await self.db.flush()
        
        return self.round
    
    async def extend_time(self, actor_id: int, additional_seconds: int) -> ClassroomRound:
        """Extend current phase time (teacher/judge only)."""
        if not self._is_authorized(actor_id, "transition"):
            raise UnauthorizedActionError("Not authorized to extend time")
        
        if self.round.phase_duration_seconds:
            self.round.phase_duration_seconds += additional_seconds
        
        action_log = ClassroomRoundAction(
            round_id=self.round.id,
            session_id=self.round.session_id,
            actor_user_id=actor_id,
            action_type=ActionType.TIME_EXTENDED,
            payload={"additional_seconds": additional_seconds}
        )
        self.db.add(action_log)
        
        await self.db.flush()
        
        return self.round
    
    @classmethod
    async def get_machine(cls, db: AsyncSession, round_id: int) -> "RoundStateMachine":
        """Factory method to get state machine for a round."""
        result = await db.execute(
            select(ClassroomRound)
            .where(ClassroomRound.id == round_id)
            .options(selectinload(ClassroomRound.session))
        )
        round_obj = result.scalar_one_or_none()
        
        if not round_obj:
            raise ValueError(f"Round {round_id} not found")
        
        return cls(db, round_obj)
    
    @classmethod
    async def create_round(
        cls,
        db: AsyncSession,
        session_id: int,
        round_number: int,
        petitioner_id: int,
        respondent_id: int,
        judge_id: Optional[int] = None,
        pairing_mode: str = "random",
        creator_id: int = 0
    ) -> ClassroomRound:
        """Factory method to create a new round."""
        round_obj = ClassroomRound(
            session_id=session_id,
            round_number=round_number,
            petitioner_id=petitioner_id,
            respondent_id=respondent_id,
            judge_id=judge_id,
            state=RoundState.WAITING,
            pairing_mode=pairing_mode
        )
        
        db.add(round_obj)
        await db.flush()
        
        # Log creation
        action = ClassroomRoundAction(
            round_id=round_obj.id,
            session_id=session_id,
            actor_user_id=creator_id,
            action_type=ActionType.ROUND_CREATED,
            payload={
                "petitioner_id": petitioner_id,
                "respondent_id": respondent_id,
                "judge_id": judge_id,
                "pairing_mode": pairing_mode
            }
        )
        db.add(action)
        await db.flush()
        
        logger.info(f"Created round {round_obj.id} for session {session_id}")
        
        return round_obj


class ConcurrentModificationError(Exception):
    """Raised when optimistic locking detects concurrent modification."""
    pass
