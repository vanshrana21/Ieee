"""
Phase 8 — WebSocket Server

WebSocket endpoint for real-time session updates.
Read-only, server-authoritative, idempotent delivery.
"""
import json
import asyncio
from typing import Optional, Dict, Any
from fastapi import WebSocket, WebSocketDisconnect, Query, Depends
from fastapi.security import HTTPBearer
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.orm.live_court import LiveCourtSession, LiveEventLog, LiveEventType
from backend.database import get_db
from backend.realtime.connection_manager import (
    ConnectionManager, get_connection_manager, set_connection_manager
)
from backend.realtime.backpressure import (
    BackpressureManager, get_backpressure_manager, set_backpressure_manager
)
from backend.realtime.rate_limit import check_ws_connection_rate_limit
from backend.realtime.broadcast_adapter import BroadcastAdapter
from backend.realtime.in_memory_adapter import InMemoryAdapter


# Allowed client message types
ALLOWED_CLIENT_MESSAGES = {"PING", "ACK", "REQUEST_STATE"}


async def get_current_user_ws(token: str) -> Optional[Dict[str, Any]]:
    """
    Validate JWT token and return user info.
    
    Args:
        token: JWT token from query param
    Returns:
        User dict or None if invalid
    """
    try:
        from jose import jwt
        from backend.config import settings
        
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        return {
            "user_id": payload.get("sub"),
            "institution_id": payload.get("institution_id"),
            "role": payload.get("role")
        }
    except Exception:
        return None


async def websocket_endpoint(
    websocket: WebSocket,
    session_id: int,
    token: str = Query(...),
    last_sequence: int = Query(0),
    db: AsyncSession = Depends(get_db)
):
    """
    WebSocket endpoint for real-time session updates.
    
    URL: /live/ws/{session_id}?token={jwt}&last_sequence={n}
    
    Allowed client messages:
    - {"type": "PING"}
    - {"type": "ACK", "last_sequence": 20}
    - {"type": "REQUEST_STATE"}
    
    Server messages:
    - {"type": "EVENT", "event_sequence": n, "event_hash": "...", "payload": {...}}
    - {"type": "SNAPSHOT", "data": {...}}
    - {"type": "PONG"}
    
    Args:
        websocket: WebSocket connection
        session_id: Session ID from URL path
        token: JWT token for authentication
        last_sequence: Last known event sequence for replay
        db: Database session
    """
    # Validate user
    user = await get_current_user_ws(token)
    if not user:
        await websocket.close(code=1008, reason="Invalid token")
        return
    
    # Validate institution scoping
    result = await db.execute(
        select(LiveCourtSession).where(LiveCourtSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    
    if not session:
        await websocket.close(code=1008, reason="Session not found")
        return
    
    if session.institution_id != user.get("institution_id"):
        await websocket.close(code=1008, reason="Institution mismatch")
        return
    
    # Rate limiting
    client_ip = websocket.client.host if websocket.client else "unknown"
    rate_allowed = await check_ws_connection_rate_limit(
        user_id=user["user_id"],
        ip_address=client_ip
    )
    
    if not rate_allowed:
        await websocket.close(code=1008, reason="Rate limit exceeded")
        return
    
    # Get or initialize connection manager
    manager = get_connection_manager()
    if not manager:
        # Initialize with in-memory adapter for dev
        adapter = InMemoryAdapter()
        manager = ConnectionManager(adapter)
        set_connection_manager(manager)
    
    # Accept connection
    await manager.connect(
        websocket=websocket,
        session_id=session_id,
        user_id=user["user_id"],
        last_sequence=last_sequence
    )
    
    try:
        # Send snapshot if requested via last_sequence
        if last_sequence > 0:
            # Send delta (events after last_sequence)
            await send_delta_events(websocket, session_id, last_sequence, db)
        else:
            # Send full snapshot
            await manager.send_snapshot(websocket, session_id, db)
        
        # Main message loop
        while True:
            try:
                # Receive client message
                data = await websocket.receive_text()
                
                try:
                    message = json.loads(data)
                except json.JSONDecodeError:
                    # Send error and continue
                    await websocket.send_text(json.dumps({
                        "type": "ERROR",
                        "message": "Invalid JSON"
                    }, sort_keys=True))
                    continue
                
                msg_type = message.get("type")
                
                # Validate message type
                if msg_type not in ALLOWED_CLIENT_MESSAGES:
                    await websocket.send_text(json.dumps({
                        "type": "ERROR",
                        "message": f"Invalid message type. Allowed: {ALLOWED_CLIENT_MESSAGES}"
                    }, sort_keys=True))
                    continue
                
                # Handle message
                if msg_type == "PING":
                    await websocket.send_text(json.dumps({
                        "type": "PONG",
                        "timestamp": datetime.utcnow().isoformat()
                    }, sort_keys=True))
                
                elif msg_type == "ACK":
                    ack_sequence = message.get("last_sequence", 0)
                    manager.update_ack(websocket, ack_sequence)
                
                elif msg_type == "REQUEST_STATE":
                    await manager.send_snapshot(websocket, session_id, db)
            
            except WebSocketDisconnect:
                break
            except Exception as e:
                # Log and continue
                print(f"WebSocket error: {e}")
                continue
    
    finally:
        # Cleanup
        await manager.disconnect(websocket, session_id)


async def send_delta_events(
    websocket: WebSocket,
    session_id: int,
    last_sequence: int,
    db: AsyncSession
) -> None:
    """
    Send events that occurred after last_sequence.
    
    Args:
        websocket: WebSocket to send to
        session_id: Session ID
        last_sequence: Last known sequence number
        db: Database session
    """
    result = await db.execute(
        select(LiveEventLog)
        .where(
            LiveEventLog.session_id == session_id,
            LiveEventLog.event_sequence > last_sequence
        )
        .order_by(LiveEventLog.event_sequence.asc())
    )
    events = result.scalars().all()
    
    for event in events:
        message = {
            "type": "EVENT",
            "session_id": session_id,
            "event_sequence": event.event_sequence,
            "event_hash": event.event_hash,
            "payload": json.loads(event.payload_json)
        }
        await websocket.send_text(json.dumps(message, sort_keys=True))


async def start_redis_subscriber(
    broadcast_adapter: BroadcastAdapter,
    connection_manager: ConnectionManager
) -> None:
    """
    Start Redis subscriber task to receive cross-worker messages.
    
    Args:
        broadcast_adapter: Redis adapter with subscribe capability
        connection_manager: Local connection manager to broadcast to
    """
    # Subscribe to all session channels (pattern)
    # In production, subscribe to "session:*" pattern
    # For now, subscribe to specific channels as needed
    
    async def handle_redis_message(channel: str, message: dict):
        """Handle message from Redis and broadcast locally."""
        # Extract session_id from channel name (session:{id})
        parts = channel.split(":")
        if len(parts) == 2 and parts[0] == "session":
            try:
                session_id = int(parts[1])
                # Broadcast to local connections (don't publish back to Redis)
                await connection_manager.broadcast_to_session(
                    session_id, message, publish_to_redis=False
                )
            except ValueError:
                pass
    
    # This would be started per worker on specific channels
    # Implementation depends on deployment topology
    pass


# Export main endpoint for FastAPI router
__all__ = ["websocket_endpoint"]
