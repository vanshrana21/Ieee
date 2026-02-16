"""
Live Courtroom WebSocket Routes — Phase 8

WebSocket endpoint for real-time courtroom session communication.

Route: /ws/live-session/{live_session_id}

Security:
- JWT validation on connection
- Institution scope validation
- Role-based access control

Features:
- Real-time event broadcasting
- Session state snapshots
- Event replay on reconnect
- No in-memory-only state (all truth from DB)
"""
import json
from typing import Dict, Any, Optional, Set
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from backend.database import get_db, async_session_maker
from backend.dependencies import get_current_user_ws, get_current_user
from backend.orm.user import User, UserRole
from backend.orm.live_courtroom import (
    LiveCourtSession, LiveSessionEvent, LiveSessionStatus,
    VisibilityMode
)
from backend.services.live_courtroom_service import (
    get_session_state,
    get_events_since,
    get_timer_status,
    verify_live_event_chain
)

router = APIRouter()

# =============================================================================
# Connection Manager (Tracks active WebSocket connections)
# =============================================================================

class ConnectionManager:
    """
    Manages WebSocket connections for live courtroom sessions.
    
    Elite Hardening: Includes flood protection with rate limiting.
    
    Note: This only tracks connections for broadcasting.
    All state truth comes from the database.
    """
    
    # Elite Hardening: Rate limiting config
    MAX_MESSAGES_PER_WINDOW = 20  # Max messages allowed
    RATE_WINDOW_SECONDS = 10  # Time window for rate limit
    
    def __init__(self):
        # Map of live_session_id -> set of WebSocket connections
        self.active_connections: Dict[int, Set[WebSocket]] = {}
        # Map of connection -> metadata (user_id, institution_id, etc.)
        self.connection_metadata: Dict[WebSocket, Dict[str, Any]] = {}
        # Elite Hardening: Rate tracking per connection
        self.connection_rate_tracker: Dict[WebSocket, Dict[str, Any]] = {}
    
    async def connect(
        self,
        websocket: WebSocket,
        live_session_id: int,
        user: User
    ) -> bool:
        """
        Accept a new WebSocket connection.
        
        Args:
            websocket: WebSocket connection
            live_session_id: ID of the live session
            user: Authenticated user
            
        Returns:
            True if connection accepted, False otherwise
        """
        # Accept the connection
        await websocket.accept()
        
        # Track connection
        if live_session_id not in self.active_connections:
            self.active_connections[live_session_id] = set()
        
        self.active_connections[live_session_id].add(websocket)
        self.connection_metadata[websocket] = {
            "user_id": user.id,
            "institution_id": user.institution_id,
            "role": user.role.value if user.role else None,
            "connected_at": datetime.utcnow().isoformat(),
            "live_session_id": live_session_id
        }
        
        # Elite Hardening: Initialize rate tracking
        now = datetime.utcnow()
        self.connection_rate_tracker[websocket] = {
            "message_count": 0,
            "window_start": now,
            "warning_sent": False
        }
        
        return True
    
    def _check_rate_limit(self, websocket: WebSocket) -> tuple[bool, bool]:
        """
        Elite Hardening: Check if connection has exceeded rate limit.
        
        Returns:
            (allowed, should_disconnect): 
            - allowed: True if message can proceed
            - should_disconnect: True if should force disconnect
        """
        tracker = self.connection_rate_tracker.get(websocket)
        if not tracker:
            return True, False
        
        now = datetime.utcnow()
        window_start = tracker["window_start"]
        elapsed = (now - window_start).total_seconds()
        
        # Reset window if expired
        if elapsed >= self.RATE_WINDOW_SECONDS:
            tracker["message_count"] = 1
            tracker["window_start"] = now
            tracker["warning_sent"] = False
            return True, False
        
        # Increment count
        tracker["message_count"] += 1
        
        # Check if exceeded limit
        if tracker["message_count"] > self.MAX_MESSAGES_PER_WINDOW:
            if not tracker["warning_sent"]:
                # First violation - send warning
                tracker["warning_sent"] = True
                return False, False  # Block this message, but don't disconnect yet
            else:
                # Second violation - disconnect
                return False, True
        
        return True, False
    
    def disconnect(self, websocket: WebSocket, live_session_id: int) -> None:
        """Remove a WebSocket connection."""
        if live_session_id in self.active_connections:
            self.active_connections[live_session_id].discard(websocket)
            
            # Clean up empty sets
            if not self.active_connections[live_session_id]:
                del self.active_connections[live_session_id]
        
        # Clean up metadata
        if websocket in self.connection_metadata:
            del self.connection_metadata[websocket]
        
        # Elite Hardening: Clean up rate tracker
        if websocket in self.connection_rate_tracker:
            del self.connection_rate_tracker[websocket]
    
    async def broadcast(
        self,
        live_session_id: int,
        message: Dict[str, Any],
        exclude: Optional[WebSocket] = None
    ) -> None:
        """
        Broadcast a message to all connections for a session.
        
        Args:
            live_session_id: ID of the live session
            message: Message to broadcast
            exclude: Optional connection to exclude
        """
        if live_session_id not in self.active_connections:
            return
        
        disconnected = []
        
        for connection in self.active_connections[live_session_id]:
            if connection == exclude:
                continue
            
            try:
                await connection.send_json(message)
            except Exception:
                # Mark for removal
                disconnected.append(connection)
        
        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn, live_session_id)
    
    async def send_to_user(
        self,
        websocket: WebSocket,
        message: Dict[str, Any]
    ) -> bool:
        """Send a message to a specific connection."""
        try:
            await websocket.send_json(message)
            return True
        except Exception:
            return False
    
    def get_connection_count(self, live_session_id: int) -> int:
        """Get number of active connections for a session."""
        return len(self.active_connections.get(live_session_id, set()))


# Global connection manager instance
manager = ConnectionManager()


# =============================================================================
# WebSocket Authentication & Authorization
# =============================================================================

async def validate_websocket_auth(
    websocket: WebSocket,
    token: str
) -> Optional[User]:
    """
    Validate JWT token and return user.
    
    Args:
        websocket: WebSocket connection
        token: JWT token string
        
    Returns:
        User if valid, None otherwise
    """
    from backend.auth import decode_access_token
    from backend.database import async_session_maker
    
    try:
        payload = decode_access_token(token)
        if not payload:
            return None
        
        user_id = payload.get("sub")
        if not user_id:
            return None
        
        async with async_session_maker() as db:
            result = await db.execute(
                select(User).where(User.id == int(user_id))
            )
            user = result.scalar_one_or_none()
            
            if not user or not user.is_active:
                return None
            
            return user
            
    except Exception:
        return None


async def check_session_access(
    live_session_id: int,
    user: User,
    db: AsyncSession
) -> tuple[bool, Optional[LiveCourtSession]]:
    """
    Check if user has access to a live session.
    
    Args:
        live_session_id: ID of the live session
        user: User to check
        db: Database session
        
    Returns:
        Tuple of (has_access, session)
    """
    result = await db.execute(
        select(LiveCourtSession).where(LiveCourtSession.id == live_session_id)
    )
    session = result.scalar_one_or_none()
    
    if not session:
        return False, None
    
    # Super admin always has access
    if user.role == UserRole.teacher:
        return True, session
    
    # Check visibility mode
    if session.visibility_mode == VisibilityMode.PUBLIC:
        return True, session
    
    if session.visibility_mode == VisibilityMode.PRIVATE:
        # Only host institution
        if user.institution_id == session.institution_id:
            return True, session
        return False, session
    
    if session.visibility_mode in [VisibilityMode.INSTITUTION, VisibilityMode.NATIONAL]:
        # Check if user's institution is involved
        # For now, same-institution access
        if user.institution_id == session.institution_id:
            return True, session
        
        # For tournament matches, check if user's institution is participating
        if session.tournament_match_id:
            from backend.orm.national_network import TournamentMatch, TournamentTeam
            
            result = await db.execute(
                select(TournamentMatch).where(
                    TournamentMatch.id == session.tournament_match_id
                )
            )
            match = result.scalar_one_or_none()
            
            if match:
                # Check if user's institution is one of the teams
                result = await db.execute(
                    select(TournamentTeam).where(
                        and_(
                            TournamentTeam.id.in_([
                                match.petitioner_team_id,
                                match.respondent_team_id
                            ]),
                            TournamentTeam.institution_id == user.institution_id
                        )
                    )
                )
                if result.scalar_one_or_none():
                    return True, session
        
        return False, session
    
    return False, session


# =============================================================================
# WebSocket Endpoint
# =============================================================================

@router.websocket("/ws/live-session/{live_session_id}")
async def live_session_websocket(
    websocket: WebSocket,
    live_session_id: int,
    token: str = Query(..., description="JWT access token"),
    last_event_id: Optional[int] = Query(None, description="Last event ID for replay")
):
    """
    WebSocket endpoint for live courtroom sessions.
    
    Protocol:
    1. Client connects with JWT token
    2. Server validates auth and session access
    3. Server sends current state snapshot
    4. Server replays events since last_event_id (if provided)
    5. Server broadcasts new events as they occur
    6. Client can send ping to keep connection alive
    
    Message Format (Server -> Client):
    {
        "type": "state_snapshot" | "event_replay" | "new_event" | "error" | "ping",
        "data": {...},
        "timestamp": "2026-02-14T10:30:00Z"
    }
    
    Args:
        websocket: WebSocket connection
        live_session_id: ID of the live session
        token: JWT access token
        last_event_id: Optional last event ID for replay
    """
    # Validate authentication
    user = await validate_websocket_auth(websocket, token)
    
    if not user:
        await websocket.accept()
        await websocket.send_json({
            "type": "error",
            "data": {"message": "Authentication failed"},
            "timestamp": datetime.utcnow().isoformat()
        })
        await websocket.close(code=4001, reason="Authentication failed")
        return
    
    # Check session access
    async with async_session_maker() as db:
        has_access, session = await check_session_access(live_session_id, user, db)
        
        if not has_access:
            await websocket.accept()
            await websocket.send_json({
                "type": "error",
                "data": {"message": "Access denied to this session"},
                "timestamp": datetime.utcnow().isoformat()
            })
            await websocket.close(code=4003, reason="Access denied")
            return
        
        # Accept connection
        await manager.connect(websocket, live_session_id, user)
        
        try:
            # Send initial state snapshot
            state = await get_session_state(live_session_id, db)
            
            await manager.send_to_user(websocket, {
                "type": "state_snapshot",
                "data": state,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            # Replay events since last_event_id (for reconnect)
            if last_event_id:
                events = await get_events_since(live_session_id, last_event_id, db)
                
                for event in events:
                    await manager.send_to_user(websocket, {
                        "type": "event_replay",
                        "data": event.to_dict(),
                        "timestamp": datetime.utcnow().isoformat()
                    })
                
                # Send replay complete message
                await manager.send_to_user(websocket, {
                    "type": "replay_complete",
                    "data": {
                        "events_replayed": len(events),
                        "last_replayed_event_id": events[-1].id if events else last_event_id
                    },
                    "timestamp": datetime.utcnow().isoformat()
                })
            
            # Send connection confirmation
            await manager.send_to_user(websocket, {
                "type": "connected",
                "data": {
                    "session_id": live_session_id,
                    "user_id": user.id,
                    "connected_at": datetime.utcnow().isoformat(),
                    "active_connections": manager.get_connection_count(live_session_id)
                },
                "timestamp": datetime.utcnow().isoformat()
            })
            
            # Main message loop
            while True:
                try:
                    # Elite Hardening: Check rate limit before processing message
                    allowed, should_disconnect = manager._check_rate_limit(websocket)
                    
                    if should_disconnect:
                        # Too many violations - disconnect
                        await manager.send_to_user(websocket, {
                            "type": "error",
                            "data": {"message": "Rate limit exceeded. Connection terminated."},
                            "timestamp": datetime.utcnow().isoformat()
                        })
                        await websocket.close(code=4008, reason="Rate limit exceeded")
                        break
                    
                    if not allowed:
                        # First violation - send warning but keep connection
                        await manager.send_to_user(websocket, {
                            "type": "warning",
                            "data": {
                                "message": f"Rate limit warning: max {manager.MAX_MESSAGES_PER_WINDOW} messages per {manager.RATE_WINDOW_SECONDS} seconds"
                            },
                            "timestamp": datetime.utcnow().isoformat()
                        })
                        continue
                    
                    # Receive message from client
                    message = await websocket.receive_json()
                    
                    msg_type = message.get("type")
                    
                    if msg_type == "ping":
                        # Respond with pong
                        await manager.send_to_user(websocket, {
                            "type": "pong",
                            "data": {"server_time": datetime.utcnow().isoformat()},
                            "timestamp": datetime.utcnow().isoformat()
                        })
                    
                    elif msg_type == "request_state":
                        # Client requesting fresh state
                        async with async_session_maker() as state_db:
                            fresh_state = await get_session_state(live_session_id, state_db)
                            
                            await manager.send_to_user(websocket, {
                                "type": "state_snapshot",
                                "data": fresh_state,
                                "timestamp": datetime.utcnow().isoformat()
                            })
                    
                    elif msg_type == "request_timer":
                        # Client requesting timer update
                        turn_id = message.get("turn_id")
                        if turn_id:
                            async with async_session_maker() as timer_db:
                                timer_status = await get_timer_status(turn_id, timer_db)
                                
                                await manager.send_to_user(websocket, {
                                    "type": "timer_update",
                                    "data": timer_status,
                                    "timestamp": datetime.utcnow().isoformat()
                                })
                    
                    elif msg_type == "verify_chain":
                        # Client requesting chain verification
                        async with async_session_maker() as verify_db:
                            verification = await verify_live_event_chain(live_session_id, verify_db)
                            
                            await manager.send_to_user(websocket, {
                                "type": "chain_verification",
                                "data": verification,
                                "timestamp": datetime.utcnow().isoformat()
                            })
                    
                    else:
                        # Unknown message type
                        await manager.send_to_user(websocket, {
                            "type": "error",
                            "data": {"message": f"Unknown message type: {msg_type}"},
                            "timestamp": datetime.utcnow().isoformat()
                        })
                
                except json.JSONDecodeError:
                    await manager.send_to_user(websocket, {
                        "type": "error",
                        "data": {"message": "Invalid JSON"},
                        "timestamp": datetime.utcnow().isoformat()
                    })
                
                except Exception as e:
                    await manager.send_to_user(websocket, {
                        "type": "error",
                        "data": {"message": str(e)},
                        "timestamp": datetime.utcnow().isoformat()
                    })
        
        except WebSocketDisconnect:
            pass
        
        finally:
            # Clean up connection
            manager.disconnect(websocket, live_session_id)
            
            # Notify others about disconnection
            await manager.broadcast(
                live_session_id,
                {
                    "type": "user_disconnected",
                    "data": {
                        "user_id": user.id,
                        "active_connections": manager.get_connection_count(live_session_id)
                    },
                    "timestamp": datetime.utcnow().isoformat()
                },
                exclude=websocket
            )


# =============================================================================
# HTTP Endpoints for Session Management
# =============================================================================

@router.get("/live-sessions/{live_session_id}/ws-info")
async def get_websocket_info(
    live_session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get WebSocket connection info for a live session.
    
    Returns WebSocket URL and connection parameters.
    """
    # Check access
    has_access, session = await check_session_access(live_session_id, current_user, db)
    
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this session"
        )
    
    # Get last event ID for replay
    from sqlalchemy import select as sa_select
    result = await db.execute(
        sa_select(LiveSessionEvent)
        .where(LiveSessionEvent.live_session_id == live_session_id)
        .order_by(LiveSessionEvent.id.desc())
        .limit(1)
    )
    last_event = result.scalar_one_or_none()
    
    return {
        "websocket_url": f"/ws/live-session/{live_session_id}",
        "query_params": {
            "token": "<jwt_token>",
            "last_event_id": last_event.id if last_event else None
        },
        "session_id": live_session_id,
        "status": session.status if session else None,
        "active_connections": manager.get_connection_count(live_session_id),
        "last_event_id": last_event.id if last_event else None
    }


@router.post("/live-sessions/{live_session_id}/broadcast")
async def broadcast_message(
    live_session_id: int,
    message: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Broadcast a message to all connected clients.
    
    Requires: ADMIN, JUDGE, or SUPER_ADMIN role
    """
    # Check access
    has_access, _ = await check_session_access(live_session_id, current_user, db)
    
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this session"
        )
    
    # Check role
    allowed_roles = [UserRole.teacher, UserRole.teacher, UserRole.teacher]
    if current_user.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to broadcast"
        )
    
    # Broadcast message
    await manager.broadcast(
        live_session_id,
        {
            "type": "broadcast",
            "data": message,
            "sender_id": current_user.id,
            "timestamp": datetime.utcnow().isoformat()
        }
    )
    
    return {
        "success": True,
        "live_session_id": live_session_id,
        "active_connections": manager.get_connection_count(live_session_id)
    }


# =============================================================================
# Event Broadcasting Function (for service layer)
# =============================================================================

async def broadcast_event(
    live_session_id: int,
    event: LiveSessionEvent
) -> None:
    """
    Broadcast a new event to all connected WebSocket clients.
    
    This function is called by the service layer after creating events.
    
    Args:
        live_session_id: ID of the live session
        event: The event to broadcast
    """
    await manager.broadcast(
        live_session_id,
        {
            "type": "new_event",
            "data": event.to_dict(),
            "timestamp": datetime.utcnow().isoformat()
        }
    )


async def broadcast_timer_update(
    live_session_id: int,
    turn_id: int,
    timer_status: Dict[str, Any]
) -> None:
    """
    Broadcast a timer update to all connected clients.
    
    Args:
        live_session_id: ID of the live session
        turn_id: ID of the turn
        timer_status: Timer status dictionary
    """
    await manager.broadcast(
        live_session_id,
        {
            "type": "timer_update",
            "data": {
                "turn_id": turn_id,
                **timer_status
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    )


async def broadcast_state_change(
    live_session_id: int,
    change_type: str,
    data: Dict[str, Any]
) -> None:
    """
    Broadcast a state change to all connected clients.
    
    Args:
        live_session_id: ID of the live session
        change_type: Type of change (e.g., "session_paused", "turn_started")
        data: Change data
    """
    await manager.broadcast(
        live_session_id,
        {
            "type": change_type,
            "data": data,
            "timestamp": datetime.utcnow().isoformat()
        }
    )
