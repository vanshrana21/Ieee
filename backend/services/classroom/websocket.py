"""
Classroom WebSocket Handler - Phase 7
Real-time communication for classroom sessions and rounds.
"""
import json
import logging
from typing import Dict, Set, Optional
from datetime import datetime

from fastapi import WebSocket, WebSocketDisconnect, Depends, Query
from fastapi.security import HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.database import get_async_db
from backend.rbac import get_current_user_ws
from backend.orm.classroom_session import ClassroomSession, ClassroomParticipant
from backend.orm.classroom_round import ClassroomRound, RoundState
from backend.orm.classroom_round_action import ClassroomRoundAction, ActionType

logger = logging.getLogger(__name__)
security = HTTPBearer()

# Connection managers for different channels
class ConnectionManager:
    """Manages WebSocket connections for classroom sessions."""
    
    def __init__(self):
        # session_id -> {user_id: WebSocket}
        self.session_connections: Dict[int, Dict[int, WebSocket]] = {}
        # round_id -> {user_id: WebSocket}
        self.round_connections: Dict[int, Dict[int, WebSocket]] = {}
    
    async def connect_to_session(self, websocket: WebSocket, session_id: int, user_id: int):
        """Connect user to session channel."""
        await websocket.accept()
        
        if session_id not in self.session_connections:
            self.session_connections[session_id] = {}
        
        self.session_connections[session_id][user_id] = websocket
        
        logger.info(f"User {user_id} connected to session {session_id}")
    
    async def connect_to_round(self, websocket: WebSocket, round_id: int, user_id: int):
        """Connect user to round channel."""
        await websocket.accept()
        
        if round_id not in self.round_connections:
            self.round_connections[round_id] = {}
        
        self.round_connections[round_id][user_id] = websocket
        
        logger.info(f"User {user_id} connected to round {round_id}")
    
    def disconnect_from_session(self, session_id: int, user_id: int):
        """Disconnect user from session channel."""
        if session_id in self.session_connections:
            self.session_connections[session_id].pop(user_id, None)
            if not self.session_connections[session_id]:
                del self.session_connections[session_id]
        
        logger.info(f"User {user_id} disconnected from session {session_id}")
    
    def disconnect_from_round(self, round_id: int, user_id: int):
        """Disconnect user from round channel."""
        if round_id in self.round_connections:
            self.round_connections[round_id].pop(user_id, None)
            if not self.round_connections[round_id]:
                del self.round_connections[round_id]
        
        logger.info(f"User {user_id} disconnected from round {round_id}")
    
    async def broadcast_to_session(self, session_id: int, message: Dict):
        """Broadcast message to all connected session participants."""
        if session_id not in self.session_connections:
            return
        
        disconnected = []
        for user_id, websocket in self.session_connections[session_id].items():
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"Failed to send to user {user_id}: {e}")
                disconnected.append(user_id)
        
        # Clean up disconnected users
        for user_id in disconnected:
            self.disconnect_from_session(session_id, user_id)
    
    async def broadcast_to_round(self, round_id: int, message: Dict):
        """Broadcast message to all connected round participants."""
        if round_id not in self.round_connections:
            return
        
        disconnected = []
        for user_id, websocket in self.round_connections[round_id].items():
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"Failed to send to user {user_id} in round {round_id}: {e}")
                disconnected.append(user_id)
        
        for user_id in disconnected:
            self.disconnect_from_round(round_id, user_id)
    
    async def send_to_user(self, user_id: int, session_id: int, message: Dict):
        """Send message to specific user in session."""
        if session_id not in self.session_connections:
            return
        
        websocket = self.session_connections[session_id].get(user_id)
        if websocket:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"Failed to send to user {user_id}: {e}")
                self.disconnect_from_session(session_id, user_id)


# Global connection manager
manager = ConnectionManager()


class ClassroomWebSocketHandler:
    """Handles classroom WebSocket connections and messages."""
    
    # Message rate limiting (messages per second)
    RATE_LIMIT = 5
    
    def __init__(self):
        self.user_last_message: Dict[int, datetime] = {}
    
    def _check_rate_limit(self, user_id: int) -> bool:
        """Check if user is within rate limit."""
        now = datetime.utcnow()
        
        if user_id in self.user_last_message:
            elapsed = (now - self.user_last_message[user_id]).total_seconds()
            if elapsed < 1.0 / self.RATE_LIMIT:
                return False
        
        self.user_last_message[user_id] = now
        return True
    
    async def handle_session_ws(
        self,
        websocket: WebSocket,
        session_id: int,
        token: str = Query(...),
        db: AsyncSession = Depends(get_async_db)
    ):
        """
        WebSocket endpoint for classroom session real-time updates.
        
        Connection URL: /ws/classroom/session/{session_id}?token=JWT
        """
        # Authenticate
        try:
            user = await get_current_user_ws(token, db)
        except Exception as e:
            await websocket.close(code=4001, reason="Authentication failed")
            return
        
        # Verify session membership
        participant = await db.scalar(
            select(ClassroomParticipant).where(
                ClassroomParticipant.session_id == session_id,
                ClassroomParticipant.user_id == user.id
            )
        )
        
        if not participant and user.role not in ["admin", "institution_admin"]:
            await websocket.close(code=4003, reason="Not a session participant")
            return
        
        # Connect
        await manager.connect_to_session(websocket, session_id, user.id)
        
        # Update last seen
        if participant:
            participant.last_seen_at = datetime.utcnow()
            await db.commit()
        
        # Send initial state
        await self._send_initial_state(websocket, session_id, db)
        
        try:
            while True:
                # Receive message
                data = await websocket.receive_text()
                
                # Rate limiting
                if not self._check_rate_limit(user.id):
                    await websocket.send_json({
                        "type": "error",
                        "code": "rate_limited",
                        "message": "Too many messages. Please slow down."
                    })
                    continue
                
                # Process message
                try:
                    message = json.loads(data)
                    await self._handle_session_message(
                        message, websocket, session_id, user.id, db
                    )
                except json.JSONDecodeError:
                    await websocket.send_json({
                        "type": "error",
                        "code": "invalid_json",
                        "message": "Invalid JSON format"
                    })
                
        except WebSocketDisconnect:
            manager.disconnect_from_session(session_id, user.id)
            
            # Log disconnect
            if participant:
                participant.is_connected = False
                await db.commit()
    
    async def handle_round_ws(
        self,
        websocket: WebSocket,
        round_id: int,
        token: str = Query(...),
        db: AsyncSession = Depends(get_async_db)
    ):
        """
        WebSocket endpoint for round-specific real-time updates.
        
        Connection URL: /ws/classroom/round/{round_id}?token=JWT
        """
        # Authenticate
        try:
            user = await get_current_user_ws(token, db)
        except Exception as e:
            await websocket.close(code=4001, reason="Authentication failed")
            return
        
        # Verify round participation
        round_obj = await db.scalar(
            select(ClassroomRound).where(ClassroomRound.id == round_id)
        )
        
        if not round_obj:
            await websocket.close(code=4004, reason="Round not found")
            return
        
        is_participant = user.id in [
            round_obj.petitioner_id,
            round_obj.respondent_id,
            round_obj.judge_id
        ]
        
        if not is_participant and user.role not in ["admin", "teacher"]:
            await websocket.close(code=4003, reason="Not a round participant")
            return
        
        # Connect
        await manager.connect_to_round(websocket, round_id, user.id)
        
        # Send initial round state
        await self._send_round_state(websocket, round_obj)
        
        try:
            while True:
                data = await websocket.receive_text()
                
                # Rate limiting
                if not self._check_rate_limit(user.id):
                    await websocket.send_json({
                        "type": "error",
                        "code": "rate_limited",
                        "message": "Too many messages. Please slow down."
                    })
                    continue
                
                # Process message
                try:
                    message = json.loads(data)
                    await self._handle_round_message(
                        message, websocket, round_id, user.id, db
                    )
                except json.JSONDecodeError:
                    await websocket.send_json({
                        "type": "error",
                        "code": "invalid_json",
                        "message": "Invalid JSON format"
                    })
                
        except WebSocketDisconnect:
            manager.disconnect_from_round(round_id, user.id)
    
    async def _send_initial_state(
        self,
        websocket: WebSocket,
        session_id: int,
        db: AsyncSession
    ):
        """Send initial session state to newly connected client."""
        session = await db.scalar(
            select(ClassroomSession).where(ClassroomSession.id == session_id)
        )
        
        if session:
            await websocket.send_json({
                "type": "session.init",
                "session": {
                    "id": session.id,
                    "title": session.title,
                    "current_state": session.current_state,
                    "remaining_time": session.remaining_time
                }
            })
    
    async def _send_round_state(self, websocket: WebSocket, round_obj: ClassroomRound):
        """Send round state to newly connected client."""
        await websocket.send_json({
            "type": "round.init",
            "round": round_obj.to_minimal_dict()
        })
    
    async def _handle_session_message(
        self,
        message: Dict,
        websocket: WebSocket,
        session_id: int,
        user_id: int,
        db: AsyncSession
    ):
        """Handle incoming session WebSocket message."""
        msg_type = message.get("type")
        
        if msg_type == "ping":
            await websocket.send_json({"type": "pong", "timestamp": datetime.utcnow().isoformat()})
        
        elif msg_type == "presence.heartbeat":
            # Update last seen
            participant = await db.scalar(
                select(ClassroomParticipant).where(
                    ClassroomParticipant.session_id == session_id,
                    ClassroomParticipant.user_id == user_id
                )
            )
            if participant:
                participant.last_seen_at = datetime.utcnow()
                participant.is_connected = True
                await db.commit()
            
            await websocket.send_json({"type": "presence.ack"})
        
        elif msg_type == "chat.message":
            # Broadcast chat message to session
            chat_msg = {
                "type": "chat.message",
                "user_id": user_id,
                "text": message.get("text", ""),
                "timestamp": datetime.utcnow().isoformat()
            }
            await manager.broadcast_to_session(session_id, chat_msg)
        
        else:
            await websocket.send_json({
                "type": "error",
                "code": "unknown_type",
                "message": f"Unknown message type: {msg_type}"
            })
    
    async def _handle_round_message(
        self,
        message: Dict,
        websocket: WebSocket,
        round_id: int,
        user_id: int,
        db: AsyncSession
    ):
        """Handle incoming round WebSocket message."""
        msg_type = message.get("type")
        
        if msg_type == "ping":
            await websocket.send_json({"type": "pong"})
        
        elif msg_type == "action.transition.request":
            # Client is requesting state transition
            # This should be validated and processed via REST API, not directly
            await websocket.send_json({
                "type": "action.transition.ack",
                "message": "Transition request received. Processing via API..."
            })
        
        elif msg_type == "chat.message":
            # Round-specific chat
            chat_msg = {
                "type": "chat.message",
                "round_id": round_id,
                "user_id": user_id,
                "text": message.get("text", ""),
                "timestamp": datetime.utcnow().isoformat()
            }
            await manager.broadcast_to_round(round_id, chat_msg)
        
        elif msg_type == "objection.raise":
            # Handle objection raised
            await self._handle_objection(round_id, user_id, message, db)
        
        else:
            await websocket.send_json({
                "type": "error",
                "code": "unknown_type",
                "message": f"Unknown message type: {msg_type}"
            })
    
    async def _handle_objection(
        self,
        round_id: int,
        user_id: int,
        message: Dict,
        db: AsyncSession
    ):
        """Handle objection raised via WebSocket."""
        # Log the objection
        action = ClassroomRoundAction(
            round_id=round_id,
            session_id=message.get("session_id"),
            actor_user_id=user_id,
            action_type=ActionType.OBJECTION_RAISED,
            payload={
                "objection_type": message.get("objection_type"),
                "content": message.get("content")
            }
        )
        db.add(action)
        await db.commit()
        
        # Broadcast to round
        await manager.broadcast_to_round(round_id, {
            "type": "objection.raised",
            "raised_by": user_id,
            "objection_type": message.get("objection_type"),
            "timestamp": datetime.utcnow().isoformat()
        })


# Global handler instance
ws_handler = ClassroomWebSocketHandler()


# =============================================================================
# WebSocket Routes
# =============================================================================

async def classroom_session_websocket(
    websocket: WebSocket,
    session_id: int,
    token: str = Query(...),
    db: AsyncSession = Depends(get_async_db)
):
    """WebSocket endpoint for session-level updates."""
    await ws_handler.handle_session_ws(websocket, session_id, token, db)


async def classroom_round_websocket(
    websocket: WebSocket,
    round_id: int,
    token: str = Query(...),
    db: AsyncSession = Depends(get_async_db)
):
    """WebSocket endpoint for round-level updates."""
    await ws_handler.handle_round_ws(websocket, round_id, token, db)


# =============================================================================
# Redis Pub/Sub Integration (for multi-server deployments)
# =============================================================================

class RedisPubSub:
    """Redis pub/sub for broadcasting across multiple server instances."""
    
    def __init__(self, redis_client):
        self.redis = redis_client
        self.subscribers: Dict[str, Set] = {}
    
    async def publish(self, channel: str, message: Dict):
        """Publish message to Redis channel."""
        if self.redis:
            await self.redis.publish(channel, json.dumps(message))
    
    async def subscribe(self, channel: str, callback):
        """Subscribe to Redis channel."""
        # Implementation depends on your Redis client
        pass


# =============================================================================
# Helper functions for broadcasting from REST endpoints
# =============================================================================

async def broadcast_session_update(session_id: int, update_type: str, data: Dict):
    """Broadcast update to all session participants."""
    await manager.broadcast_to_session(session_id, {
        "type": f"session.{update_type}",
        "data": data,
        "timestamp": datetime.utcnow().isoformat()
    })


async def broadcast_round_update(round_id: int, update_type: str, data: Dict):
    """Broadcast update to all round participants."""
    await manager.broadcast_to_round(round_id, {
        "type": f"round.{update_type}",
        "data": data,
        "timestamp": datetime.utcnow().isoformat()
    })


async def broadcast_round_state_change(
    round_id: int,
    from_state: str,
    to_state: str,
    actor_id: int
):
    """Broadcast state change to all round participants."""
    await manager.broadcast_to_round(round_id, {
        "type": "round.state_change",
        "from_state": from_state,
        "to_state": to_state,
        "actor_id": actor_id,
        "timestamp": datetime.utcnow().isoformat()
    })
