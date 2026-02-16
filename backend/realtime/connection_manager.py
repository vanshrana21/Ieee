"""
Phase 8 — WebSocket Connection Manager

Manages WebSocket connections per session across multiple workers.
Coordinated via Redis Pub/Sub for multi-worker synchronization.
"""
import asyncio
from typing import Dict, Set, Optional, Any
from fastapi import WebSocket
from datetime import datetime, timedelta
import json
from .broadcast_adapter import BroadcastAdapter


class ConnectionManager:
    """
    Manages WebSocket connections with multi-worker coordination.
    
    Per-worker state:
    - Local WebSocket connections
    
    Cluster-wide state:
    - Redis Pub/Sub for cross-worker messaging
    
    Design principles:
    - PostgreSQL is source of truth
    - Redis is delivery-only
    - WebSocket is read-only
    - All events include event_sequence for idempotency
    """
    
    def __init__(
        self,
        broadcast_adapter: BroadcastAdapter,
        max_queue_size: int = 100
    ):
        self.broadcast_adapter = broadcast_adapter
        self.max_queue_size = max_queue_size
        
        # Local per-session connections: {session_id: {websocket: metadata}}
        self.connections: Dict[int, Dict[WebSocket, Dict[str, Any]]] = {}
        
        # Message queues per WebSocket for backpressure
        self.message_queues: Dict[WebSocket, asyncio.Queue] = {}
        
        # Last acknowledged sequence per connection
        self.last_ack: Dict[WebSocket, int] = {}
    
    async def connect(
        self,
        websocket: WebSocket,
        session_id: int,
        user_id: int,
        last_sequence: int = 0
    ) -> None:
        """
        Accept new WebSocket connection.
        
        Args:
            websocket: WebSocket object
            session_id: Session ID
            user_id: User ID
            last_sequence: Last known event sequence (for replay)
        """
        await websocket.accept()
        
        # Initialize session connection dict
        if session_id not in self.connections:
            self.connections[session_id] = {}
        
        # Store connection metadata
        self.connections[session_id][websocket] = {
            "user_id": user_id,
            "connected_at": datetime.utcnow(),
            "last_sequence": last_sequence
        }
        
        # Create message queue with backpressure
        self.message_queues[websocket] = asyncio.Queue(maxsize=self.max_queue_size)
        
        # Start sender task
        asyncio.create_task(self._message_sender(websocket))
    
    async def disconnect(self, websocket: WebSocket, session_id: int) -> None:
        """
        Remove WebSocket connection.
        
        Args:
            websocket: WebSocket to disconnect
            session_id: Session ID
        """
        if session_id in self.connections:
            self.connections[session_id].pop(websocket, None)
            if not self.connections[session_id]:
                del self.connections[session_id]
        
        # Clean up queue
        if websocket in self.message_queues:
            del self.message_queues[websocket]
        
        # Clean up ack tracking
        if websocket in self.last_ack:
            del self.last_ack[websocket]
    
    async def broadcast_to_session(
        self,
        session_id: int,
        message: Dict[str, Any],
        publish_to_redis: bool = True
    ) -> None:
        """
        Broadcast message to all local connections for session.
        
        Args:
            session_id: Session to broadcast to
            message: Message payload (must include event_sequence, event_hash)
            publish_to_redis: Also publish to Redis for other workers
        """
        if session_id not in self.connections:
            return
        
        # Serialize deterministically
        serialized = json.dumps(message, sort_keys=True)
        
        # Send to local connections
        for websocket in list(self.connections[session_id].keys()):
            queue = self.message_queues.get(websocket)
            if queue:
                try:
                    queue.put_nowait(serialized)
                except asyncio.QueueFull:
                    # Backpressure: drop oldest message
                    try:
                        queue.get_nowait()  # Remove oldest
                        queue.put_nowait(serialized)  # Add new
                    except asyncio.QueueEmpty:
                        pass
        
        # Publish to Redis for other workers
        if publish_to_redis:
            channel = f"session:{session_id}"
            await self.broadcast_adapter.publish(channel, message)
    
    async def _message_sender(self, websocket: WebSocket) -> None:
        """
        Background task to send messages from queue to WebSocket.
        
        Args:
            websocket: WebSocket to send to
        """
        queue = self.message_queues.get(websocket)
        if not queue:
            return
        
        try:
            while True:
                message = await queue.get()
                if message is None:  # Shutdown signal
                    break
                try:
                    await websocket.send_text(message)
                except Exception:
                    # Connection broken
                    break
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
    
    def get_connection_count(self, session_id: Optional[int] = None) -> int:
        """
        Get number of active connections.
        
        Args:
            session_id: Optional session to count (None for all)
        Returns:
            Number of connections
        """
        if session_id is not None:
            return len(self.connections.get(session_id, {}))
        return sum(len(conns) for conns in self.connections.values())
    
    def update_ack(self, websocket: WebSocket, sequence: int) -> None:
        """
        Update last acknowledged sequence for connection.
        
        Args:
            websocket: WebSocket connection
            sequence: Acknowledged sequence number
        """
        self.last_ack[websocket] = max(self.last_ack.get(websocket, 0), sequence)
    
    async def send_snapshot(
        self,
        websocket: WebSocket,
        session_id: int,
        db_session: Any
    ) -> None:
        """
        Send full session state snapshot.
        
        Args:
            websocket: WebSocket to send to
            session_id: Session ID
            db_session: Database session for queries
        """
        # Import here to avoid circular dependency
        from backend.orm.live_court import LiveCourtSession
        from backend.orm.exhibit import SessionExhibit
        from backend.orm.live_objection import LiveObjection
        from sqlalchemy import select
        
        # Fetch session
        result = await db_session.execute(
            select(LiveCourtSession).where(LiveCourtSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        
        if not session:
            return
        
        # Build snapshot
        snapshot = {
            "type": "SNAPSHOT",
            "session_id": session_id,
            "timestamp": datetime.utcnow().isoformat(),
            "data": session.to_dict()
        }
        
        await websocket.send_text(json.dumps(snapshot, sort_keys=True))


# Global connection manager instance (initialized on startup)
_connection_manager: Optional[ConnectionManager] = None


def get_connection_manager() -> Optional[ConnectionManager]:
    """Get global connection manager instance."""
    return _connection_manager


def set_connection_manager(manager: ConnectionManager) -> None:
    """Set global connection manager instance."""
    global _connection_manager
    _connection_manager = manager
