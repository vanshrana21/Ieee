"""
Phase 0: Virtual Courtroom Infrastructure - WebSocket Manager

Room-based WebSocket connection management for real-time courtroom sync.
Handles connection lifecycle, broadcasting, and room cleanup.
"""
from typing import Dict, List
from fastapi import WebSocket
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class RoomParticipant:
    """Metadata for a participant in a courtroom room."""
    
    def __init__(self, user_id: int, role: str, websocket: WebSocket):
        self.user_id = user_id
        self.role = role
        self.websocket = websocket
        self.joined_at = datetime.utcnow()
    
    def to_dict(self):
        """Convert participant to dictionary."""
        return {
            "user_id": self.user_id,
            "role": self.role,
            "joined_at": self.joined_at.isoformat()
        }


class CourtroomConnection:
    """Represents a single WebSocket connection in a courtroom"""
    def __init__(self, websocket: WebSocket, user_id: int, role: str):
        self.websocket = websocket
        self.user_id = user_id
        self.role = role  # "judge", "petitioner", "respondent", "observer"


class WebSocketManager:
    """
    Manages WebSocket connections for courtroom rooms.
    
    Attributes:
        active_connections: Dict mapping room_id to list of (WebSocket, participant) tuples
        room_metadata: Dict mapping room_id to room metadata including participants
    """
    def __init__(self):
        # room_id -> List[(WebSocket, RoomParticipant)]
        self.active_connections: Dict[str, List[tuple]] = {}
        # room_id -> Room metadata
        self.room_metadata: Dict[str, dict] = {}
        # Track room states (timer info, etc.)
        self.room_states: Dict[str, dict] = {}
        logger.info("WebSocketManager initialized")
    
    async def connect(self, websocket: WebSocket, room_id: str, user_id: int, role: str):
        """
        Accept WebSocket connection and add to room.
        Broadcast user_joined event to all participants.
        """
        await websocket.accept()
        
        # Create participant metadata
        participant = RoomParticipant(user_id, role, websocket)
        connection = CourtroomConnection(websocket, user_id, role)
        
        # Add to room connections
        if room_id not in self.active_connections:
            self.active_connections[room_id] = []
        self.active_connections[room_id].append((websocket, participant))
        
        # Update room metadata
        if room_id not in self.room_metadata:
            self.room_metadata[room_id] = {
                "created_at": datetime.utcnow().isoformat(),
                "participants": []
            }
        self.room_metadata[room_id]["participants"].append(participant.to_dict())
        
        logger.info(f"User {user_id} ({role}) connected to room {room_id}")
        
        # Send current room state to the new connection
        if room_id in self.room_states:
            await self.send_to_connection(connection, {
                "type": "connection_established",
                "data": {
                    "room_state": self.room_states[room_id],
                    "participants": self.get_room_participants(room_id)
                }
            })
        else:
            await self.send_to_connection(connection, {
                "type": "connection_established",
                "data": {
                    "participants": self.get_room_participants(room_id)
                }
            })
        
        # Broadcast user_joined event
        await self.broadcast(room_id, {
            "type": "user_joined",
            "data": {
                "user_id": user_id,
                "role": role,
                "timestamp": datetime.utcnow().isoformat()
            }
        })
    
    async def disconnect(self, websocket: WebSocket, room_id: str, user_id: int = None):
        """
        Remove WebSocket from room and broadcast user_left.
        Cleanup room if empty.
        """
        if room_id not in self.active_connections:
            return
        
        # Find and remove the connection
        removed_role = None
        for i, (ws, participant) in enumerate(self.active_connections[room_id]):
            if ws == websocket:
                removed_role = participant.role
                user_id = participant.user_id
                self.active_connections[room_id].pop(i)
                break
        
        # Remove from metadata
        if room_id in self.room_metadata:
            participants = self.room_metadata[room_id].get("participants", [])
            self.room_metadata[room_id]["participants"] = [
                p for p in participants if p.get("user_id") != user_id
            ]
        
        logger.info(f"User {user_id} disconnected from room {room_id}")
        
        # Broadcast user_left
        if removed_role:
            await self.broadcast(room_id, {
                "type": "user_left",
                "data": {
                    "user_id": user_id,
                    "role": removed_role,
                    "timestamp": datetime.utcnow().isoformat()
                }
            })
        
        # Cleanup empty room
        if not self.active_connections[room_id]:
            del self.active_connections[room_id]
            if room_id in self.room_metadata:
                del self.room_metadata[room_id]
            if room_id in self.room_states:
                del self.room_states[room_id]
            logger.info(f"Room {room_id} cleaned up (empty)")
    
    async def broadcast(self, room_id: str, message: dict, exclude_user_id: int = None):
        """
        Broadcast JSON message to all connections in room.
        Handle connection errors gracefully and log failed sends.
        """
        if room_id not in self.active_connections:
            return (0, 0)
        
        # Add timestamp if not present
        if "timestamp" not in message:
            message["timestamp"] = datetime.utcnow().isoformat()
        
        message_str = json.dumps(message)
        success_count = 0
        failure_count = 0
        disconnected = []
        
        for websocket, participant in self.active_connections[room_id]:
            if exclude_user_id and participant.user_id == exclude_user_id:
                continue
            
            try:
                await websocket.send_text(message_str)
                success_count += 1
            except Exception as e:
                logger.warning(f"Failed to send to user {participant.user_id}: {e}")
                failure_count += 1
                disconnected.append((websocket, participant))
        
        # Clean up disconnected clients
        for ws, participant in disconnected:
            await self.disconnect(ws, room_id, participant.user_id)
        
        return (success_count, failure_count)
    
    async def send_to_connection(self, connection: CourtroomConnection, message: dict):
        """Send message to a specific connection"""
        try:
            await connection.websocket.send_json(message)
        except Exception as e:
            logger.warning(f"Failed to send to user {connection.user_id}: {e}")
    
    async def send_to_user(self, room_id: str, user_id: int, message: dict):
        """Send message to a specific user in a room"""
        if room_id not in self.active_connections:
            return
        
        for websocket, participant in self.active_connections[room_id]:
            if participant.user_id == user_id:
                try:
                    await websocket.send_json(message)
                except Exception as e:
                    logger.warning(f"Failed to send to user {user_id}: {e}")
                break
    
    async def send_to_role(self, room_id: str, role: str, message: dict):
        """Send message to all users with a specific role"""
        if room_id not in self.active_connections:
            return
        
        for websocket, participant in self.active_connections[room_id]:
            if participant.role == role:
                try:
                    await websocket.send_json(message)
                except Exception as e:
                    logger.warning(f"Failed to send to role {role}: {e}")
    
    def get_room_participants(self, room_id: str) -> List[dict]:
        """
        Get list of participants in a room.
        Returns: [{"user_id": int, "role": str, "joined_at": str}, ...]
        """
        if room_id not in self.active_connections:
            return []
        
        return [participant.to_dict() for _, participant in self.active_connections[room_id]]
    
    def get_room_count(self, room_id: str) -> int:
        """Get number of active connections in a room."""
        return len(self.active_connections.get(room_id, []))
    
    def get_all_rooms(self) -> List[str]:
        """Get list of all active room IDs."""
        return list(self.active_connections.keys())
    
    async def cleanup_empty_rooms(self):
        """
        Remove rooms with no active connections.
        Run every 5 minutes via background task.
        """
        empty_rooms = [
            room_id for room_id, connections in self.active_connections.items()
            if not connections
        ]
        
        for room_id in empty_rooms:
            del self.active_connections[room_id]
            if room_id in self.room_metadata:
                del self.room_metadata[room_id]
            if room_id in self.room_states:
                del self.room_states[room_id]
            logger.info(f"Cleaned up empty room: {room_id}")
        
        return len(empty_rooms)
    
    def update_room_state(self, room_id: str, state_update: dict):
        """Update the persisted state for a room"""
        if room_id not in self.room_states:
            self.room_states[room_id] = {}
        self.room_states[room_id].update(state_update)
    
    def get_room_state(self, room_id: str) -> dict:
        """Get current state for a room"""
        return self.room_states.get(room_id, {})
    
    def get_connection_count(self, room_id: str) -> int:
        """Alias for get_room_count for backward compatibility"""
        return self.get_room_count(room_id)


# Global manager instance
manager = WebSocketManager()


async def handle_courtroom_message(room_id: str, user_id: int, role: str, data: dict):
    """
    Handle incoming courtroom WebSocket messages.
    Routes messages appropriately and updates room state.
    """
    msg_type = data.get("type")
    
    if msg_type == "timer_start":
        # Broadcast timer start to all participants
        await manager.broadcast(room_id, {
            "type": "timer_update",
            "action": "start",
            "speaker_role": data.get("speaker_role"),
            "time_remaining": data.get("time_remaining"),
            "timestamp": data.get("timestamp")
        })
        manager.update_room_state(room_id, {
            "timer_running": True,
            "speaker_role": data.get("speaker_role"),
            "time_remaining": data.get("time_remaining")
        })
    
    elif msg_type == "timer_pause":
        await manager.broadcast(room_id, {
            "type": "timer_update",
            "action": "pause",
            "time_remaining": data.get("time_remaining")
        })
        manager.update_room_state(room_id, {
            "timer_running": False,
            "time_remaining": data.get("time_remaining")
        })
    
    elif msg_type == "timer_reset":
        await manager.broadcast(room_id, {
            "type": "timer_update",
            "action": "reset",
            "time_remaining": data.get("time_remaining")
        })
        manager.update_room_state(room_id, {
            "timer_running": False,
            "time_remaining": data.get("time_remaining")
        })
    
    elif msg_type == "objection_raised":
        # Notify judge and all participants
        await manager.broadcast(room_id, {
            "type": "objection_raised",
            "objection_type": data.get("objection_type"),
            "raised_by": user_id,
            "raised_by_role": role,
            "reason": data.get("reason"),
            "timestamp": data.get("timestamp")
        })
    
    elif msg_type == "objection_ruling":
        # Only judges can rule on objections
        if role == "judge":
            await manager.broadcast(room_id, {
                "type": "objection_ruling",
                "objection_id": data.get("objection_id"),
                "ruling": data.get("ruling"),  # "sustained" or "overruled"
                "ruling_reason": data.get("ruling_reason"),
                "penalty_applied": data.get("penalty_applied", False),
                "timestamp": data.get("timestamp")
            })
    
    elif msg_type == "speaker_change":
        # Broadcast speaker transition
        await manager.broadcast(room_id, {
            "type": "speaker_change",
            "previous_speaker": data.get("previous_speaker"),
            "new_speaker": data.get("new_speaker"),
            "new_time_remaining": data.get("new_time_remaining")
        })
        manager.update_room_state(room_id, {
            "current_speaker": data.get("new_speaker"),
            "time_remaining": data.get("new_time_remaining")
        })
    
    elif msg_type == "score_update":
        # Only judges send score updates
        if role == "judge":
            await manager.broadcast(room_id, {
                "type": "score_update",
                "team_id": data.get("team_id"),
                "category": data.get("category"),
                "score": data.get("score"),
                "feedback": data.get("feedback"),
                "timestamp": data.get("timestamp")
            })
    
    elif msg_type == "round_complete":
        # Round ended
        if role == "judge":
            await manager.broadcast(room_id, {
                "type": "round_complete",
                "final_scores": data.get("final_scores"),
                "timestamp": data.get("timestamp")
            })
            manager.update_room_state(room_id, {"status": "completed"})
    
    elif msg_type == "ping":
        # Keep-alive response
        await manager.send_to_user(room_id, user_id, {"type": "pong"})
    
    else:
        logger.warning(f"Unknown message type: {msg_type}")
