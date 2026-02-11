"""
Classroom WebSocket Handler

WebSocket endpoint for Classroom Mode real-time communication.
Room ID pattern: classroom:{session_id}
"""
import json
from typing import Dict, Set
from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from backend.websockets.protocol import (
    EventType, BaseEvent, UserJoinedEvent, UserLeftEvent,
    ConnectionEstablishedEvent, TimerStartEvent, TimerUpdateEvent,
    SessionStateChangeEvent, ArgumentSubmittedEvent, ScoreSubmittedEvent,
    LeaderboardUpdateEvent, ErrorEvent, parse_event, validate_event
)
from backend.state_machines.classroom_session import SessionStateMachine


class ClassroomConnectionManager:
    """Manages WebSocket connections for classroom sessions."""
    
    def __init__(self):
        # Room ID -> Set of WebSocket connections
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        # Room ID -> Session data
        self.room_data: Dict[str, dict] = {}
    
    async def connect(self, websocket: WebSocket, room_id: str, user_id: str, user_role: str):
        """Accept connection and add to room."""
        await websocket.accept()
        
        if room_id not in self.active_connections:
            self.active_connections[room_id] = set()
            self.room_data[room_id] = {
                "participants": {},
                "state": "created",
                "timer": None
            }
        
        self.active_connections[room_id].add(websocket)
        
        # Store participant info
        self.room_data[room_id]["participants"][websocket] = {
            "user_id": user_id,
            "role": user_role,
            "name": f"User {user_id}"
        }
        
        # Broadcast user joined
        event = UserJoinedEvent(
            room_id=room_id,
            user_id=user_id,
            role=user_role,
            name=f"User {user_id}"
        )
        await self.broadcast(room_id, event.dict())
        
        # Send connection established
        participants = [
            {"user_id": p["user_id"], "role": p["role"], "name": p["name"]}
            for p in self.room_data[room_id]["participants"].values()
        ]
        
        established = ConnectionEstablishedEvent(
            room_id=room_id,
            participants=participants
        )
        await websocket.send_json(established.dict())
    
    def disconnect(self, websocket: WebSocket, room_id: str):
        """Remove connection from room."""
        if room_id in self.active_connections:
            self.active_connections[room_id].discard(websocket)
            
            # Get user info before removing
            participant = self.room_data[room_id]["participants"].pop(websocket, None)
            
            # Clean up empty rooms
            if not self.active_connections[room_id]:
                del self.active_connections[room_id]
                del self.room_data[room_id]
            elif participant:
                # Broadcast user left
                event = UserLeftEvent(
                    room_id=room_id,
                    user_id=participant["user_id"]
                )
                # Async broadcast would happen elsewhere
            
            return participant
        return None
    
    async def broadcast(self, room_id: str, message: dict):
        """Broadcast message to all connections in room."""
        if room_id not in self.active_connections:
            return
        
        disconnected = []
        for connection in self.active_connections[room_id]:
            try:
                await connection.send_json(message)
            except:
                disconnected.append(connection)
        
        # Clean up disconnected
        for conn in disconnected:
            self.active_connections[room_id].discard(conn)
    
    async def send_personal(self, websocket: WebSocket, message: dict):
        """Send message to specific connection."""
        try:
            await websocket.send_json(message)
        except:
            pass
    
    def get_room_participant_count(self, room_id: str) -> int:
        """Get number of participants in room."""
        if room_id in self.room_data:
            return len(self.room_data[room_id]["participants"])
        return 0


# Global connection manager
manager = ClassroomConnectionManager()


async def classroom_websocket_endpoint(
    websocket: WebSocket,
    room_id: str,
    db: Session,
    token: str = None
):
    """
    WebSocket endpoint for classroom sessions.
    
    URL: /ws/classroom/{room_id}?token={jwt}
    """
    # Validate token and get user info
    # TODO: Implement JWT validation
    user_id = "1"  # Placeholder
    user_role = "student"  # Placeholder
    
    # Connect to room
    await manager.connect(websocket, room_id, user_id, user_role)
    
    try:
        while True:
            # Receive message
            data = await websocket.receive_text()
            
            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                error = ErrorEvent(
                    room_id=room_id,
                    error_code="INVALID_JSON",
                    message="Invalid JSON format"
                )
                await manager.send_personal(websocket, error.dict())
                continue
            
            # Parse and validate event
            event = parse_event(message)
            if not event:
                error = ErrorEvent(
                    room_id=room_id,
                    error_code="INVALID_EVENT",
                    message="Unknown event type"
                )
                await manager.send_personal(websocket, error.dict())
                continue
            
            # Validate permissions
            if not validate_event(event, user_id, user_role):
                error = ErrorEvent(
                    room_id=room_id,
                    error_code="PERMISSION_DENIED",
                    message="Not authorized for this action"
                )
                await manager.send_personal(websocket, error.dict())
                continue
            
            # Handle event
            await handle_classroom_event(event, room_id, websocket, db, user_id, user_role)
            
    except WebSocketDisconnect:
        participant = manager.disconnect(websocket, room_id)
        if participant:
            # Broadcast user left
            event = UserLeftEvent(
                room_id=room_id,
                user_id=participant["user_id"]
            )
            await manager.broadcast(room_id, event.dict())


async def handle_classroom_event(
    event: BaseEvent,
    room_id: str,
    websocket: WebSocket,
    db: Session,
    user_id: str,
    user_role: str
):
    """Handle classroom-specific events."""
    
    if event.type == EventType.ARGUMENT_SUBMITTED:
        # Validate argument
        if isinstance(event, ArgumentSubmittedEvent):
            # Save to database
            # TODO: Implement DB save
            
            # Broadcast to all participants
            await manager.broadcast(room_id, event.dict())
    
    elif event.type == EventType.OBJECTION_RAISED:
        # Broadcast objection to teacher and judge
        await manager.broadcast(room_id, event.dict())
    
    elif event.type == EventType.SCORE_SUBMITTED:
        if user_role == "teacher":
            # Validate and save score
            if isinstance(event, ScoreSubmittedEvent):
                # TODO: Save to database
                
                # Broadcast score update
                await manager.broadcast(room_id, event.dict())
                
                # Check if all scores submitted
                # TODO: Check completion
                
                # If complete, broadcast leaderboard
                leaderboard = LeaderboardUpdateEvent(
                    room_id=room_id,
                    rankings=[]  # TODO: Get rankings
                )
                await manager.broadcast(room_id, leaderboard.dict())
    
    elif event.type == EventType.SESSION_STATE_CHANGE:
        if user_role == "teacher":
            # Validate state change
            # TODO: Validate with state machine
            
            # Broadcast state change
            await manager.broadcast(room_id, event.dict())
    
    elif event.type == EventType.TIMER_START:
        if user_role == "teacher":
            # Start server-side timer
            # TODO: Implement timer
            
            # Broadcast timer start
            await manager.broadcast(room_id, event.dict())
    
    elif event.type == EventType.TIMER_PAUSE:
        if user_role == "teacher":
            # Pause timer
            # TODO: Implement timer pause
            
            # Broadcast timer pause
            await manager.broadcast(room_id, event.dict())


# Timer management
async def broadcast_timer_update(room_id: str, time_remaining: int, is_paused: bool = False):
    """Broadcast timer update to room."""
    event = TimerUpdateEvent(
        room_id=room_id,
        time_remaining=time_remaining,
        is_paused=is_paused
    )
    await manager.broadcast(room_id, event.dict())


async def handle_timer_expired(room_id: str, current_speaker: str = None):
    """Handle timer expiration."""
    from backend.websockets.protocol import TimerExpiredEvent
    
    event = TimerExpiredEvent(
        room_id=room_id,
        current_speaker=current_speaker
    )
    await manager.broadcast(room_id, event.dict())
    
    # Auto-transition state if needed
    # TODO: Trigger state transition
