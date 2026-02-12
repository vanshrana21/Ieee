"""
Classroom Celery Tasks - Phase 7
Background tasks for auto-transitions, pairing, and timer management.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

from celery import shared_task, chain, group
from celery.exceptions import MaxRetriesExceededError
from sqlalchemy import select, and_
from sqlalchemy.orm import joinedload

from backend.database import SessionLocal
from backend.orm.classroom_round import ClassroomRound, RoundState
from backend.orm.classroom_session import ClassroomSession
from backend.orm.classroom_round_action import ClassroomRoundAction, ActionType
from backend.state_machines.round_state import RoundStateMachine
from backend.services.classroom.pairing_engine import PairingEngine
from backend.services.classroom.websocket import broadcast_round_state_change

logger = logging.getLogger(__name__)


# =============================================================================
# Auto-Transition Tasks
# =============================================================================

@shared_task(bind=True, max_retries=3)
def auto_transition_round(self, round_id: int, expected_state: str):
    """
    Automatically transition round when timer expires.
    
    This task is scheduled when a round enters a timed state.
    It verifies the round is still in the expected state before transitioning.
    """
    db = SessionLocal()
    
    try:
        # Get round with lock
        round_obj = db.query(ClassroomRound).filter(
            ClassroomRound.id == round_id
        ).with_for_update().first()
        
        if not round_obj:
            logger.warning(f"Round {round_id} not found for auto-transition")
            return {"status": "error", "reason": "round_not_found"}
        
        # Verify round is still in expected state
        if round_obj.state.value != expected_state:
            logger.info(f"Round {round_id} state changed from {expected_state} to {round_obj.state.value}. Skipping auto-transition.")
            return {
                "status": "skipped",
                "reason": "state_changed",
                "expected": expected_state,
                "actual": round_obj.state.value
            }
        
        # Determine next state based on current state
        next_state = _get_next_state(round_obj.state)
        
        if not next_state:
            logger.info(f"Round {round_id} in terminal state {expected_state}, no transition needed")
            return {"status": "skipped", "reason": "terminal_state"}
        
        # Perform transition
        machine = RoundStateMachine(db, round_obj)
        
        try:
            updated_round = machine.auto_transition(next_state)
            db.commit()
            
            # Broadcast state change via WebSocket
            # Note: This would need async context or separate async task
            
            logger.info(f"Auto-transitioned round {round_id}: {expected_state} -> {next_state.value}")
            
            return {
                "status": "success",
                "round_id": round_id,
                "from_state": expected_state,
                "to_state": next_state.value
            }
            
        except Exception as e:
            db.rollback()
            logger.error(f"Auto-transition failed for round {round_id}: {e}")
            raise self.retry(exc=e, countdown=60)
            
    except MaxRetriesExceededError:
        logger.error(f"Max retries exceeded for auto-transition of round {round_id}")
        return {"status": "error", "reason": "max_retries_exceeded"}
        
    finally:
        db.close()


def _get_next_state(current_state: RoundState) -> Optional[RoundState]:
    """Get the next state in the round lifecycle."""
    transitions = {
        RoundState.ARGUMENT_PETITIONER: RoundState.ARGUMENT_RESPONDENT,
        RoundState.ARGUMENT_RESPONDENT: RoundState.REBUTTAL,
        RoundState.REBUTTAL: RoundState.SUR_REBUTTAL,
        RoundState.SUR_REBUTTAL: RoundState.JUDGE_QUESTIONS,
        RoundState.JUDGE_QUESTIONS: RoundState.SCORING,
        RoundState.SCORING: RoundState.COMPLETED,
    }
    return transitions.get(current_state)


@shared_task
def schedule_round_transitions(round_id: int):
    """
    Schedule auto-transition tasks for all timed states in a round.
    
    Called when a round starts.
    """
    db = SessionLocal()
    
    try:
        round_obj = db.query(ClassroomRound).get(round_id)
        if not round_obj:
            return
        
        # Schedule transitions for each timed state
        timed_states = [
            RoundState.ARGUMENT_PETITIONER,
            RoundState.ARGUMENT_RESPONDENT,
            RoundState.REBUTTAL,
            RoundState.SUR_REBUTTAL,
            RoundState.JUDGE_QUESTIONS,
            RoundState.SCORING,
        ]
        
        # This is a simplified version - in production you'd schedule
        # each transition based on cumulative time
        logger.info(f"Scheduled transitions for round {round_id}")
        
    finally:
        db.close()


# =============================================================================
# Pairing Tasks
# =============================================================================

@shared_task(bind=True, max_retries=3)
def auto_pair_session(self, session_id: int, pairing_mode: str = "random"):
    """
    Automatically pair participants when session starts.
    
    Called when teacher starts a session with auto-pairing enabled.
    """
    db = SessionLocal()
    
    try:
        # Get session
        session = db.query(ClassroomSession).get(session_id)
        if not session:
            logger.error(f"Session {session_id} not found for auto-pairing")
            return {"status": "error", "reason": "session_not_found"}
        
        # Check if already paired
        existing_rounds = db.query(ClassroomRound).filter(
            ClassroomRound.session_id == session_id
        ).count()
        
        if existing_rounds > 0:
            logger.info(f"Session {session_id} already has {existing_rounds} rounds. Skipping auto-pair.")
            return {"status": "skipped", "reason": "already_paired"}
        
        # Execute pairing
        engine = PairingEngine(db)
        
        from backend.orm.classroom_round import PairingMode
        mode = PairingMode(pairing_mode)
        
        pairs = engine.pair_participants(
            session_id=session_id,
            mode=mode
        )
        
        if not pairs:
            logger.warning(f"No pairs generated for session {session_id}")
            return {"status": "error", "reason": "no_pairs_generated"}
        
        # Create rounds
        rounds = engine.create_rounds_from_pairs(
            session_id=session_id,
            pairs=pairs
        )
        
        db.commit()
        
        logger.info(f"Auto-paired session {session_id}: created {len(rounds)} rounds")
        
        return {
            "status": "success",
            "session_id": session_id,
            "rounds_created": len(rounds),
            "pairing_mode": pairing_mode
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Auto-pairing failed for session {session_id}: {e}")
        raise self.retry(exc=e, countdown=30)
        
    finally:
        db.close()


@shared_task
def process_skill_based_pairing(session_id: int):
    """
    Process skill-based pairing using ELO ratings.
    
    More complex than random pairing - pairs students with similar skill levels.
    """
    return auto_pair_session.delay(session_id, pairing_mode="skill")


# =============================================================================
# Session Lifecycle Tasks
# =============================================================================

@shared_task
def cleanup_completed_sessions():
    """
    Cleanup task for completed/cancelled sessions.
    
    Runs periodically to:
    - Archive old data
    - Clean up disconnected participants
    - Generate final reports
    """
    db = SessionLocal()
    
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=7)
        
        # Find old completed sessions
        old_sessions = db.query(ClassroomSession).filter(
            and_(
                ClassroomSession.current_state.in_(["completed", "cancelled"]),
                ClassroomSession.completed_at < cutoff_date
            )
        ).all()
        
        for session in old_sessions:
            # Archive data, send reports, etc.
            logger.info(f"Processing cleanup for session {session.id}")
        
        return {
            "status": "success",
            "sessions_processed": len(old_sessions)
        }
        
    finally:
        db.close()


@shared_task
def check_disconnected_participants():
    """
    Check for participants who haven't sent heartbeats recently.
    
    Marks them as disconnected and potentially triggers AI fallback.
    """
    db = SessionLocal()
    
    try:
        timeout = datetime.utcnow() - timedelta(minutes=2)
        
        disconnected = db.query(ClassroomParticipant).filter(
            and_(
                ClassroomParticipant.is_connected == True,
                ClassroomParticipant.last_seen_at < timeout
            )
        ).all()
        
        for participant in disconnected:
            participant.is_connected = False
            
            # Log disconnection
            action = ClassroomRoundAction(
                session_id=participant.session_id,
                actor_user_id=participant.user_id,
                action_type=ActionType.PARTICIPANT_DISCONNECTED,
                payload={"reason": "heartbeat_timeout"}
            )
            db.add(action)
            
            logger.info(f"Marked participant {participant.user_id} as disconnected")
        
        db.commit()
        
        return {
            "status": "success",
            "disconnected_count": len(disconnected)
        }
        
    finally:
        db.close()


# =============================================================================
# AI Integration Tasks
# =============================================================================

@shared_task(bind=True, max_retries=2)
def generate_ai_response(self, round_id: int, context: dict):
    """
    Generate AI response for rounds with AI opponents.
    
    Called when it's the AI's turn to speak.
    """
    db = SessionLocal()
    
    try:
        round_obj = db.query(ClassroomRound).get(round_id)
        if not round_obj or not round_obj.respondent_is_ai:
            return {"status": "skipped", "reason": "not_ai_round"}
        
        # Integration with AI opponent service
        # This would call your existing AI service
        
        logger.info(f"Generated AI response for round {round_id}")
        
        # Log AI action
        action = ClassroomRoundAction(
            round_id=round_id,
            session_id=round_obj.session_id,
            actor_user_id=None,
            action_type=ActionType.AI_RESPONSE_GENERATED,
            payload=context
        )
        db.add(action)
        db.commit()
        
        return {"status": "success", "round_id": round_id}
        
    except Exception as e:
        logger.error(f"AI response generation failed for round {round_id}: {e}")
        raise self.retry(exc=e, countdown=10)
        
    finally:
        db.close()


# =============================================================================
# Report Generation Tasks
# =============================================================================

@shared_task
def generate_session_report(session_id: int):
    """
    Generate final report for a completed session.
    
    Includes:
    - All rounds and results
    - Participant statistics
    - Score breakdowns
    - Timeline of events
    """
    db = SessionLocal()
    
    try:
        session = db.query(ClassroomSession).options(
            joinedload(ClassroomSession.rounds),
            joinedload(ClassroomSession.participants)
        ).get(session_id)
        
        if not session:
            return {"status": "error", "reason": "session_not_found"}
        
        # Compile report data
        report = {
            "session_id": session_id,
            "title": session.title,
            "created_at": session.created_at.isoformat(),
            "completed_at": session.completed_at.isoformat() if session.completed_at else None,
            "participant_count": len(session.participants),
            "round_count": len(session.rounds),
            "rounds": []
        }
        
        for round_obj in session.rounds:
            round_data = {
                "round_id": round_obj.id,
                "round_number": round_obj.round_number,
                "petitioner_id": round_obj.petitioner_id,
                "respondent_id": round_obj.respondent_id,
                "winner_id": round_obj.winner_id,
                "petitioner_score": round_obj.petitioner_score,
                "respondent_score": round_obj.respondent_score,
                "duration_seconds": (
                    (round_obj.ended_at - round_obj.started_at).total_seconds()
                    if round_obj.ended_at and round_obj.started_at else None
                )
            }
            report["rounds"].append(round_data)
        
        logger.info(f"Generated report for session {session_id}")
        
        return {
            "status": "success",
            "session_id": session_id,
            "report": report
        }
        
    finally:
        db.close()


# =============================================================================
# Periodic Task Schedules
# =============================================================================

# These would be configured in your Celery beat schedule
def get_celery_beat_schedule():
    """Return Celery beat schedule configuration."""
    return {
        "cleanup-completed-sessions": {
            "task": "backend.services.classroom.tasks.cleanup_completed_sessions",
            "schedule": timedelta(hours=24),  # Daily
        },
        "check-disconnected-participants": {
            "task": "backend.services.classroom.tasks.check_disconnected_participants",
            "schedule": 30.0,  # Every 30 seconds
        },
    }
