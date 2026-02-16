"""
Phase 5 — Hardened Live Courtroom WebSocket Layer

Server-authoritative with:
- Read-only state broadcasting
- No state mutations via WebSocket
- Institution-scoped connections
- Event replay on reconnect
- Deterministic message ordering
"""
import json
from typing import Dict, List, Optional, Set
from datetime import datetime

from fastapi import WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.dependencies import get_current_user
from backend.orm.user import User, UserRole
from backend.orm.live_court import (
    LiveCourtSession, LiveTurn, LiveEventLog,
    LiveCourtStatus, LiveTurnState
)
from backend.services.live_court_service import (
    get_session_by_id, get_turns_by_session, get_events_by_session,
    get_active_turn, get_timer_state
)


# =============================================================================
# Connection Manager
# =============================================================================

class LiveCourtConnectionManager:
    """
    Manages WebSocket connections for live courtroom sessions.
    
    Key features:
    - Per-session connection tracking
    - Institution-scoped access
    - Event sequence tracking for replay
    - No state mutations allowed
    """
    
    def __init__(self):
        # Map: session_id -> {websocket: user_id}
        self.active_connections: Dict[int, Dict[WebSocket, int]] = {}
        # Map: websocket -> last_event_sequence
        self.connection_sequences: Dict[WebSocket, int] = {}
    
    async def connect(
        self,
        websocket: WebSocket,
        session_id: int,
        user: User
    ) -> bool:
        """
        Connect a websocket to a session.
        
        Returns True if connected, False if rejected.
        """
        await websocket.accept()
        
        if session_id not in self.active_connections:
            self.active_connections[session_id] = {}
        
        self.active_connections[session_id][websocket] = user.id
        self.connection_sequences[websocket] = 0
        
        return True
    
    def disconnect(self, websocket: WebSocket, session_id: int):
        """Disconnect a websocket from a session."""
        if session_id in self.active_connections:
            self.active_connections[session_id].pop(websocket, None)
            
            # Clean up empty session
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]
        
        self.connection_sequences.pop(websocket, None)
    
    async def send_to_connection(
        self,
        websocket: WebSocket,
        message: Dict
    ):
        """Send a message to a specific connection."""
        try:
            # Always use sort_keys for deterministic JSON
            await websocket.send_text(json.dumps(message, sort_keys=True))
        except Exception:
            # Connection may be closed
            pass
    
    async def broadcast_to_session(
        self,
        session_id: int,
        message: Dict,
        exclude: Optional[Set[WebSocket]] = None
    ):
        """Broadcast a message to all connections in a session."""
        if session_id not in self.active_connections:
            return
        
        exclude = exclude or set()
        
        # Copy connection list to avoid modification during iteration
        connections = list(self.active_connections[session_id].keys())
        
        for websocket in connections:
            if websocket not in exclude:
                await self.send_to_connection(websocket, message)
    
    def update_sequence(self, websocket: WebSocket, sequence: int):
        """Update the last seen event sequence for a connection."""
        self.connection_sequences[websocket] = sequence
    
    def get_sequence(self, websocket: WebSocket) -> int:
        """Get the last seen event sequence for a connection."""
        return self.connection_sequences.get(websocket, 0)


# Global connection manager
manager = LiveCourtConnectionManager()


# =============================================================================
# WebSocket Endpoint
# =============================================================================

async def live_court_websocket(
    websocket: WebSocket,
    session_id: int,
    last_sequence: int = 0,
    db: AsyncSession = Depends(get_db)
):
    """
    WebSocket endpoint for live courtroom.
    
    Protocol:
    1. On connect: Send full snapshot
    2. On reconnect (last_sequence > 0): Send only new events
    3. Server pushes: State updates, timer ticks, events
    4. Client messages: Ignored (read-only) or ACK only
    
    Args:
        session_id: Session ID to connect to
        last_sequence: Last seen event sequence (for reconnect)
    
    No state mutations allowed via WebSocket.
    All mutations via HTTP only.
    """
    # Authenticate user from query params
    try:
        # Get token from query params
        token = websocket.query_params.get("token")
        if not token:
            await websocket.close(code=1008, reason="Authentication required")
            return
        
        # Validate token and get user
        # This would typically use your JWT validation
        # For now, we'll use a simplified version
        from backend.dependencies import get_current_user_from_token
        user = await get_current_user_from_token(token, db)
        
        if not user:
            await websocket.close(code=1008, reason="Invalid authentication")
            return
        
    except Exception:
        await websocket.close(code=1008, reason="Authentication failed")
        return
    
    # Verify session access
    result = await db.execute(
        select(LiveCourtSession)
        .where(
            and_(
                LiveCourtSession.id == session_id,
                LiveCourtSession.institution_id == user.institution_id
            )
        )
    )
    session = result.scalar_one_or_none()
    
    if not session:
        await websocket.close(code=1008, reason="Session not found or access denied")
        return
    
    # Connect to manager
    connected = await manager.connect(websocket, session_id, user)
    if not connected:
        await websocket.close(code=1011, reason="Connection failed")
        return
    
    try:
        # Send initial state
        if last_sequence > 0:
            # Reconnect: Send only new events
            events = await get_events_by_session(session_id, db, last_sequence)
            
            if events:
                reconnect_message = {
                    "type": "RECONNECT_SYNC",
                    "session_id": session_id,
                    "from_sequence": last_sequence,
                    "events": [e.to_dict() for e in events],
                    "timestamp": datetime.utcnow().isoformat()
                }
                await manager.send_to_connection(websocket, reconnect_message)
                
                # Update last seen sequence
                if events:
                    manager.update_sequence(websocket, events[-1].event_sequence)
        else:
            # New connection: Send full snapshot
            snapshot = await build_full_snapshot(session_id, db)
            snapshot["type"] = "FULL_SNAPSHOT"
            snapshot["timestamp"] = datetime.utcnow().isoformat()
            
            await manager.send_to_connection(websocket, snapshot)
        
        # Listen for messages (mostly ACKs or heartbeats)
        while True:
            try:
                # Receive message from client
                data = await websocket.receive_text()
                
                try:
                    message = json.loads(data)
                except json.JSONDecodeError:
                    await manager.send_to_connection(websocket, {
                        "type": "ERROR",
                        "error": "Invalid JSON"
                    })
                    continue
                
                # Handle client messages
                msg_type = message.get("type", "").upper()
                
                if msg_type == "PING":
                    # Heartbeat response
                    await manager.send_to_connection(websocket, {
                        "type": "PONG",
                        "timestamp": datetime.utcnow().isoformat()
                    })
                
                elif msg_type == "ACK":
                    # Client acknowledging receipt
                    ack_sequence = message.get("last_sequence", 0)
                    manager.update_sequence(websocket, ack_sequence)
                
                elif msg_type == "REQUEST_STATE":
                    # Client requesting current state
                    state = await build_full_snapshot(session_id, db)
                    state["type"] = "STATE_UPDATE"
                    state["timestamp"] = datetime.utcnow().isoformat()
                    
                    await manager.send_to_connection(websocket, state)
                
                else:
                    # Reject state mutations
                    await manager.send_to_connection(websocket, {
                        "type": "ERROR",
                        "error": "State mutations not allowed via WebSocket. Use HTTP API."
                    })
            
            except WebSocketDisconnect:
                break
            except Exception as e:
                # Log error but keep connection open
                await manager.send_to_connection(websocket, {
                    "type": "ERROR",
                    "error": "Internal error"
                })
    
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket, session_id)


# =============================================================================
# Snapshot Builder
# =============================================================================

async def build_full_snapshot(
    session_id: int,
    db: AsyncSession
) -> Dict:
    """
    Build a complete snapshot of session state.
    
    Includes:
    - Session details
    - All turns
    - All events
    - Current timer state
    """
    # Get session
    session = await get_session_by_id(session_id, db)
    
    # Get turns
    turns = await get_turns_by_session(session_id, db)
    
    # Get events
    events = await get_events_by_session(session_id, db)
    
    # Get timer state
    timer = await get_timer_state(session_id, db)
    
    return {
        "session_id": session_id,
        "session": session.to_dict() if session else None,
        "turns": [t.to_dict() for t in turns],
        "events": [e.to_dict() for e in events],
        "timer": timer,
        "total_events": len(events),
        "last_event_sequence": events[-1].event_sequence if events else 0
    }


# =============================================================================
# Broadcast Helpers (Called from HTTP routes)
# =============================================================================

async def broadcast_turn_started(
    session_id: int,
    turn: LiveTurn
):
    """Broadcast turn started event to all connected clients."""
    message = {
        "type": "TURN_STARTED",
        "session_id": session_id,
        "turn": turn.to_dict(),
        "timestamp": datetime.utcnow().isoformat()
    }
    await manager.broadcast_to_session(session_id, message)


async def broadcast_turn_ended(
    session_id: int,
    turn: LiveTurn
):
    """Broadcast turn ended event to all connected clients."""
    message = {
        "type": "TURN_ENDED",
        "session_id": session_id,
        "turn": turn.to_dict(),
        "timestamp": datetime.utcnow().isoformat()
    }
    await manager.broadcast_to_session(session_id, message)


async def broadcast_session_status_change(
    session_id: int,
    status: LiveCourtStatus
):
    """Broadcast session status change to all connected clients."""
    message = {
        "type": "SESSION_STATUS_CHANGE",
        "session_id": session_id,
        "status": status.value,
        "timestamp": datetime.utcnow().isoformat()
    }
    await manager.broadcast_to_session(session_id, message)


async def broadcast_timer_tick(
    session_id: int,
    timer_state: Dict
):
    """Broadcast timer tick to all connected clients."""
    message = {
        "type": "TIMER_TICK",
        "session_id": session_id,
        "timer": timer_state,
        "timestamp": datetime.utcnow().isoformat()
    }
    await manager.broadcast_to_session(session_id, message)


async def broadcast_event(
    session_id: int,
    event: LiveEventLog
):
    """Broadcast a new event to all connected clients."""
    message = {
        "type": "EVENT",
        "session_id": session_id,
        "event": event.to_dict(),
        "timestamp": datetime.utcnow().isoformat()
    }
    await manager.broadcast_to_session(session_id, message)
