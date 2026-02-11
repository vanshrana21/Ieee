"""
Phase 2: Virtual Courtroom Infrastructure - Timer WebSocket Handler

Handles timer events via WebSocket with proper validation and database sync.
Integrates with Phase 0 database schema and Phase 1 state management.
"""

from typing import Dict, Any, Optional
from datetime import datetime
import logging
from fastapi import WebSocket, HTTPException
from pydantic import BaseModel, validator

from backend.websockets.courtroom import WebSocketManager
from backend.rbac.courtroom_permissions import has_permission, UserRole, CourtroomAction
from backend.orm.oral_round import OralRound

logger = logging.getLogger(__name__)


# Pydantic models for type-safe message validation
class TimerStartMessage(BaseModel):
    """Timer start message schema"""
    speaker_role: str
    time_remaining: int
    timestamp: str

    @validator('speaker_role')
    def validate_speaker_role(cls, v):
        if v not in ['petitioner', 'respondent', 'judge']:
            raise ValueError('speaker_role must be petitioner, respondent, or judge')
        return v


class TimerPauseMessage(BaseModel):
    """Timer pause message schema"""
    time_remaining: int
    timestamp: str


class TimerResumeMessage(BaseModel):
    """Timer resume message schema"""
    time_remaining: int
    timestamp: str


class TimerResetMessage(BaseModel):
    """Timer reset message schema"""
    time_remaining: int
    timestamp: str


class TimerZeroMessage(BaseModel):
    """Timer zero message schema"""
    speaker_role: str
    timestamp: str


class TimerSyncMessage(BaseModel):
    """Timer sync message schema"""
    time_remaining: int
    is_paused: bool
    speaker_role: str
    timestamp: str


class TimerHandler:
    """
    Handles WebSocket timer events with validation and database synchronization.
    """

    def __init__(self, db_session, websocket_manager: WebSocketManager):
        self.db = db_session
        self.ws_manager = websocket_manager
        self.timer_map = {
            'petitioner': 900,  # 15 minutes
            'respondent': 900,  # 15 minutes
            'judge': 300        # 5 minutes
        }

    async def handle_timer_start(
        self,
        websocket: WebSocket,
        round_id: int,
        user_id: int,
        user_role: UserRole,
        data: Dict[str, Any]
    ) -> None:
        """
        Handle timer_start event.
        
        Validates user permission, updates database, broadcasts to all clients.
        """
        try:
            # Validate message
            message = TimerStartMessage(**data)

            # Check permissions
            if not has_permission(user_role, CourtroomAction.CONTROL_TIMER):
                await self.ws_manager.send_to_user(
                    round_id,
                    user_id,
                    {
                        'type': 'error',
                        'message': 'Permission denied: Cannot control timer',
                        'timestamp': datetime.utcnow().isoformat()
                    }
                )
                return

            # Update database
            oral_round = self.db.query(OralRound).filter(OralRound.id == round_id).first()
            if not oral_round:
                await self.ws_manager.send_to_user(
                    round_id,
                    user_id,
                    {
                        'type': 'error',
                        'message': 'Round not found',
                        'timestamp': datetime.utcnow().isoformat()
                    }
                )
                return

            oral_round.current_speaker = message.speaker_role
            oral_round.time_remaining = message.time_remaining
            oral_round.is_paused = False
            oral_round.updated_at = datetime.utcnow()

            self.db.commit()

            # Broadcast to all clients in room
            broadcast_message = {
                'type': 'timer_update',
                'data': {
                    'action': 'start',
                    'speaker_role': message.speaker_role,
                    'time_remaining': message.time_remaining,
                    'timestamp': datetime.utcnow().isoformat()
                }
            }

            await self.ws_manager.broadcast_to_room(round_id, broadcast_message)

            logger.info(f"Timer started for round {round_id}, speaker: {message.speaker_role}")

        except Exception as e:
            logger.error(f"Error handling timer_start: {e}")
            await self.ws_manager.send_to_user(
                round_id,
                user_id,
                {
                    'type': 'error',
                    'message': f'Failed to start timer: {str(e)}',
                    'timestamp': datetime.utcnow().isoformat()
                }
            )

    async def handle_timer_pause(
        self,
        websocket: WebSocket,
        round_id: int,
        user_id: int,
        user_role: UserRole,
        data: Dict[str, Any]
    ) -> None:
        """
        Handle timer_pause event.
        
        Validates user permission, updates database, broadcasts to all clients.
        """
        try:
            # Validate message
            message = TimerPauseMessage(**data)

            # Check permissions
            if not has_permission(user_role, CourtroomAction.CONTROL_TIMER):
                await self.ws_manager.send_to_user(
                    round_id,
                    user_id,
                    {
                        'type': 'error',
                        'message': 'Permission denied: Cannot control timer',
                        'timestamp': datetime.utcnow().isoformat()
                    }
                )
                return

            # Update database
            oral_round = self.db.query(OralRound).filter(OralRound.id == round_id).first()
            if not oral_round:
                await self.ws_manager.send_to_user(
                    round_id,
                    user_id,
                    {
                        'type': 'error',
                        'message': 'Round not found',
                        'timestamp': datetime.utcnow().isoformat()
                    }
                )
                return

            oral_round.is_paused = True
            oral_round.time_remaining = message.time_remaining
            oral_round.updated_at = datetime.utcnow()

            self.db.commit()

            # Broadcast to all clients in room
            broadcast_message = {
                'type': 'timer_update',
                'data': {
                    'action': 'pause',
                    'time_remaining': message.time_remaining,
                    'timestamp': datetime.utcnow().isoformat()
                }
            }

            await self.ws_manager.broadcast_to_room(round_id, broadcast_message)

            logger.info(f"Timer paused for round {round_id}")

        except Exception as e:
            logger.error(f"Error handling timer_pause: {e}")
            await self.ws_manager.send_to_user(
                round_id,
                user_id,
                {
                    'type': 'error',
                    'message': f'Failed to pause timer: {str(e)}',
                    'timestamp': datetime.utcnow().isoformat()
                }
            )

    async def handle_timer_resume(
        self,
        websocket: WebSocket,
        round_id: int,
        user_id: int,
        user_role: UserRole,
        data: Dict[str, Any]
    ) -> None:
        """
        Handle timer_resume event.
        
        Validates user permission, updates database, broadcasts to all clients.
        """
        try:
            # Validate message
            message = TimerResumeMessage(**data)

            # Check permissions
            if not has_permission(user_role, CourtroomAction.CONTROL_TIMER):
                await self.ws_manager.send_to_user(
                    round_id,
                    user_id,
                    {
                        'type': 'error',
                        'message': 'Permission denied: Cannot control timer',
                        'timestamp': datetime.utcnow().isoformat()
                    }
                )
                return

            # Update database
            oral_round = self.db.query(OralRound).filter(OralRound.id == round_id).first()
            if not oral_round:
                await self.ws_manager.send_to_user(
                    round_id,
                    user_id,
                    {
                        'type': 'error',
                        'message': 'Round not found',
                        'timestamp': datetime.utcnow().isoformat()
                    }
                )
                return

            oral_round.is_paused = False
            oral_round.time_remaining = message.time_remaining
            oral_round.updated_at = datetime.utcnow()

            self.db.commit()

            # Broadcast to all clients in room
            broadcast_message = {
                'type': 'timer_update',
                'data': {
                    'action': 'resume',
                    'time_remaining': message.time_remaining,
                    'timestamp': datetime.utcnow().isoformat()
                }
            }

            await self.ws_manager.broadcast_to_room(round_id, broadcast_message)

            logger.info(f"Timer resumed for round {round_id}")

        except Exception as e:
            logger.error(f"Error handling timer_resume: {e}")
            await self.ws_manager.send_to_user(
                round_id,
                user_id,
                {
                    'type': 'error',
                    'message': f'Failed to resume timer: {str(e)}',
                    'timestamp': datetime.utcnow().isoformat()
                }
            )

    async def handle_timer_reset(
        self,
        websocket: WebSocket,
        round_id: int,
        user_id: int,
        user_role: UserRole,
        data: Dict[str, Any]
    ) -> None:
        """
        Handle timer_reset event.
        
        Validates user permission, updates database, broadcasts to all clients.
        """
        try:
            # Validate message
            message = TimerResetMessage(**data)

            # Check permissions
            if not has_permission(user_role, CourtroomAction.CONTROL_TIMER):
                await self.ws_manager.send_to_user(
                    round_id,
                    user_id,
                    {
                        'type': 'error',
                        'message': 'Permission denied: Cannot control timer',
                        'timestamp': datetime.utcnow().isoformat()
                    }
                )
                return

            # Update database
            oral_round = self.db.query(OralRound).filter(OralRound.id == round_id).first()
            if not oral_round:
                await self.ws_manager.send_to_user(
                    round_id,
                    user_id,
                    {
                        'type': 'error',
                        'message': 'Round not found',
                        'timestamp': datetime.utcnow().isoformat()
                    }
                )
                return

            oral_round.time_remaining = message.time_remaining
            oral_round.is_paused = True
            oral_round.updated_at = datetime.utcnow()

            self.db.commit()

            # Broadcast to all clients in room
            broadcast_message = {
                'type': 'timer_update',
                'data': {
                    'action': 'reset',
                    'time_remaining': message.time_remaining,
                    'timestamp': datetime.utcnow().isoformat()
                }
            }

            await self.ws_manager.broadcast_to_room(round_id, broadcast_message)

            logger.info(f"Timer reset for round {round_id}")

        except Exception as e:
            logger.error(f"Error handling timer_reset: {e}")
            await self.ws_manager.send_to_user(
                round_id,
                user_id,
                {
                    'type': 'error',
                    'message': f'Failed to reset timer: {str(e)}',
                    'timestamp': datetime.utcnow().isoformat()
                }
            )

    async def handle_timer_zero(
        self,
        websocket: WebSocket,
        round_id: int,
        user_id: int,
        user_role: UserRole,
        data: Dict[str, Any]
    ) -> None:
        """
        Handle timer_zero event.
        
        Updates database, broadcasts to all clients.
        """
        try:
            # Validate message
            message = TimerZeroMessage(**data)

            # Update database
            oral_round = self.db.query(OralRound).filter(OralRound.id == round_id).first()
            if oral_round:
                oral_round.time_remaining = 0
                oral_round.is_paused = True
                oral_round.updated_at = datetime.utcnow()
                self.db.commit()

            # Broadcast to all clients in room
            broadcast_message = {
                'type': 'timer_update',
                'data': {
                    'action': 'zero',
                    'speaker_role': message.speaker_role,
                    'time_remaining': 0,
                    'timestamp': datetime.utcnow().isoformat()
                }
            }

            await self.ws_manager.broadcast_to_room(round_id, broadcast_message)

            logger.info(f"Timer zero for round {round_id}")

        except Exception as e:
            logger.error(f"Error handling timer_zero: {e}")

    async def handle_timer_sync(
        self,
        websocket: WebSocket,
        round_id: int,
        user_id: int,
        user_role: UserRole,
        data: Dict[str, Any]
    ) -> None:
        """
        Handle timer_sync event for periodic synchronization.
        
        Validates and broadcasts to all clients.
        """
        try:
            # Validate message
            message = TimerSyncMessage(**data)

            # Check permissions
            if not has_permission(user_role, CourtroomAction.CONTROL_TIMER):
                return  # Silently ignore unauthorized syncs

            # Broadcast sync to all clients
            broadcast_message = {
                'type': 'timer_sync',
                'data': {
                    'time_remaining': message.time_remaining,
                    'is_paused': message.is_paused,
                    'speaker_role': message.speaker_role,
                    'timestamp': datetime.utcnow().isoformat()
                }
            }

            await self.ws_manager.broadcast_to_room(round_id, broadcast_message)

        except Exception as e:
            logger.error(f"Error handling timer_sync: {e}")

    def get_timer_for_role(self, role: str) -> int:
        """Get timer duration for a specific role."""
        return self.timer_map.get(role, 0)
