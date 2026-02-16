"""
Live Broadcast Adapter — Phase 8 Elite Hardening

Scaling Architecture for WebSocket Broadcast Layer.

This module defines the BroadcastAdapter interface and provides:
- LocalMemoryBroadcastAdapter (default, single-process)
- RedisBroadcastAdapter (stub, documented for horizontal scaling)

Usage:
    from backend.services.live_broadcast_adapter import get_broadcast_adapter
    
    adapter = get_broadcast_adapter()
    await adapter.publish(session_id=123, event={"type": "turn_started"})

Scaling:
    For single-server deployments: LocalMemoryBroadcastAdapter (default)
    For multi-worker deployments: RedisBroadcastAdapter (requires Redis setup)

Future Scaling Path:
    1. Deploy Redis cluster
    2. Configure REDIS_URL environment variable
    3. Swap adapter: BroadcastManager.set_adapter(RedisBroadcastAdapter(redis_client))
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Set, Optional, Callable
from datetime import datetime
import asyncio


# =============================================================================
# Broadcast Adapter Interface
# =============================================================================

class BroadcastAdapter(ABC):
    """
    Abstract base class for broadcast adapters.
    
    Implementations must support:
    - publish: Broadcast event to all subscribers of a session
    - subscribe: Register a callback for session events
    - unsubscribe: Remove a callback registration
    """
    
    @abstractmethod
    async def publish(self, session_id: int, event: Dict[str, Any]) -> None:
        """
        Publish an event to all subscribers of a session.
        
        Args:
            session_id: ID of the live courtroom session
            event: Event dictionary to broadcast
        """
        pass
    
    @abstractmethod
    async def subscribe(
        self,
        session_id: int,
        callback: Callable[[Dict[str, Any]], None]
    ) -> None:
        """
        Subscribe to events for a session.
        
        Args:
            session_id: ID of the live courtroom session
            callback: Async function to call when event is received
        """
        pass
    
    @abstractmethod
    async def unsubscribe(
        self,
        session_id: int,
        callback: Callable[[Dict[str, Any]], None]
    ) -> None:
        """
        Unsubscribe from events for a session.
        
        Args:
            session_id: ID of the live courtroom session
            callback: The callback to remove
        """
        pass
    
    @abstractmethod
    def get_subscriber_count(self, session_id: int) -> int:
        """Get number of active subscribers for a session."""
        pass


# =============================================================================
# Local Memory Broadcast Adapter (Default)
# =============================================================================

class LocalMemoryBroadcastAdapter(BroadcastAdapter):
    """
    In-memory broadcast adapter for single-process deployments.
    
    This is the default adapter and works for:
    - Development environments
    - Single-worker deployments
    - Small-scale production (single server)
    
    Limitations:
    - Events only reach clients connected to same process
    - Does not support horizontal scaling across multiple servers
    """
    
    def __init__(self):
        # Map of session_id -> set of callback functions
        self._subscribers: Dict[int, Set[Callable[[Dict[str, Any]], None]]] = {}
        self._lock = asyncio.Lock()
    
    async def publish(self, session_id: int, event: Dict[str, Any]) -> None:
        """
        Publish event to all local subscribers.
        
        Adds metadata to event:
        - published_at: ISO timestamp
        - publisher_node: "local" (for compatibility with distributed adapters)
        """
        async with self._lock:
            subscribers = self._subscribers.get(session_id, set()).copy()
        
        # Add metadata
        event_with_meta = {
            **event,
            "_meta": {
                "published_at": datetime.utcnow().isoformat(),
                "publisher_node": "local"
            }
        }
        
        # Call all subscribers
        disconnected = []
        for callback in subscribers:
            try:
                await callback(event_with_meta)
            except Exception:
                # Mark for removal if callback fails
                disconnected.append(callback)
        
        # Clean up disconnected subscribers
        if disconnected:
            async with self._lock:
                if session_id in self._subscribers:
                    for callback in disconnected:
                        self._subscribers[session_id].discard(callback)
    
    async def subscribe(
        self,
        session_id: int,
        callback: Callable[[Dict[str, Any]], None]
    ) -> None:
        """Register a callback for session events."""
        async with self._lock:
            if session_id not in self._subscribers:
                self._subscribers[session_id] = set()
            self._subscribers[session_id].add(callback)
    
    async def unsubscribe(
        self,
        session_id: int,
        callback: Callable[[Dict[str, Any]], None]
    ) -> None:
        """Remove a callback registration."""
        async with self._lock:
            if session_id in self._subscribers:
                self._subscribers[session_id].discard(callback)
                if not self._subscribers[session_id]:
                    del self._subscribers[session_id]
    
    def get_subscriber_count(self, session_id: int) -> int:
        """Get number of active subscribers for a session."""
        return len(self._subscribers.get(session_id, set()))


# =============================================================================
# Redis Broadcast Adapter (Stub for Horizontal Scaling)
# =============================================================================

class RedisBroadcastAdapter(BroadcastAdapter):
    """
    Redis-backed broadcast adapter for horizontal scaling.
    
    This is a DOCUMENTED STUB. Full implementation requires:
    - Redis server/cluster setup
    - aioredis or redis-py-asyncio dependency
    - Channel naming convention: "live_session:{session_id}"
    
    Architecture:
    - Each worker subscribes to Redis pub/sub channels
    - Events published to Redis are broadcast to all workers
    - Workers then forward to their local WebSocket connections
    
    Usage:
        import aioredis
        redis = await aioredis.create_redis_pool('redis://localhost')
        adapter = RedisBroadcastAdapter(redis)
        BroadcastManager.set_adapter(adapter)
    
    Future Implementation Steps:
    1. Add aioredis to requirements.txt
    2. Implement subscribe() using Redis pub/sub
    3. Implement publish() using redis.publish()
    4. Handle connection failures with retry logic
    5. Add metrics: published_events, subscriber_count
    """
    
    def __init__(self, redis_client=None):
        """
        Initialize Redis adapter.
        
        Args:
            redis_client: Redis client instance (aioredis.Redis or similar)
        """
        self._redis = redis_client
        self._local_callbacks: Dict[int, Set[Callable]] = {}
        self._lock = asyncio.Lock()
        
        # Documented stub - raise if called without Redis client
        if redis_client is None:
            raise NotImplementedError(
                "RedisBroadcastAdapter is a documented stub. "
                "To use in production: implement with aioredis, "
                "configure Redis cluster, and pass redis_client to constructor."
            )
    
    async def publish(self, session_id: int, event: Dict[str, Any]) -> None:
        """
        Publish event to Redis channel.
        
        Channel: f"live_session:{session_id}"
        """
        if not self._redis:
            raise RuntimeError("Redis client not configured")
        
        # Add metadata for distributed tracing
        event_with_meta = {
            **event,
            "_meta": {
                "published_at": datetime.utcnow().isoformat(),
                "publisher_node": "TODO: get_node_id()",
                "channel": f"live_session:{session_id}"
            }
        }
        
        # Publish to Redis
        channel = f"live_session:{session_id}"
        await self._redis.publish(channel, event_with_meta)
    
    async def subscribe(
        self,
        session_id: int,
        callback: Callable[[Dict[str, Any]], None]
    ) -> None:
        """
        Subscribe to Redis pub/sub channel.
        
        Implementation note:
        - Start background task to listen to Redis channel
        - Call callback for each received message
        - Handle reconnection on Redis failure
        """
        async with self._lock:
            if session_id not in self._local_callbacks:
                self._local_callbacks[session_id] = set()
            self._local_callbacks[session_id].add(callback)
        
        # TODO: Implement Redis pub/sub subscription
        # channel = f"live_session:{session_id}"
        # await self._redis.subscribe(channel)
        # asyncio.create_task(self._listen_to_channel(channel))
    
    async def unsubscribe(
        self,
        session_id: int,
        callback: Callable[[Dict[str, Any]], None]
    ) -> None:
        """Unsubscribe from Redis channel."""
        async with self._lock:
            if session_id in self._local_callbacks:
                self._local_callbacks[session_id].discard(callback)
    
    def get_subscriber_count(self, session_id: int) -> int:
        """Get local subscriber count (not global across cluster)."""
        return len(self._local_callbacks.get(session_id, set()))
    
    # TODO: Implement _listen_to_channel method for Redis pub/sub
    # async def _listen_to_channel(self, channel: str):
    #     while True:
    #         try:
    #             message = await self._redis.get_message()
    #             if message:
    #                 await self._dispatch_to_callbacks(channel, message)
    #         except Exception:
    #             await asyncio.sleep(1)  # Reconnect delay


# =============================================================================
# Broadcast Manager (Singleton)
# =============================================================================

class BroadcastManager:
    """
    Singleton manager for broadcast adapter.
    
    Usage:
        # Get default adapter
        adapter = BroadcastManager.get_adapter()
        
        # Set custom adapter (for scaling)
        BroadcastManager.set_adapter(RedisBroadcastAdapter(redis_client))
    """
    
    _instance: Optional[BroadcastAdapter] = None
    _lock = asyncio.Lock()
    
    @classmethod
    def get_adapter(cls) -> BroadcastAdapter:
        """Get or create the broadcast adapter."""
        if cls._instance is None:
            cls._instance = LocalMemoryBroadcastAdapter()
        return cls._instance
    
    @classmethod
    def set_adapter(cls, adapter: BroadcastAdapter) -> None:
        """Set a custom broadcast adapter (for scaling)."""
        cls._instance = adapter
    
    @classmethod
    def reset(cls) -> None:
        """Reset to default adapter (useful for testing)."""
        cls._instance = LocalMemoryBroadcastAdapter()


# =============================================================================
# Convenience Functions
# =============================================================================

def get_broadcast_adapter() -> BroadcastAdapter:
    """Get the current broadcast adapter instance."""
    return BroadcastManager.get_adapter()


async def publish_event(session_id: int, event: Dict[str, Any]) -> None:
    """
    Convenience function to publish an event.
    
    Args:
        session_id: ID of the live courtroom session
        event: Event dictionary with at least "type" key
    """
    adapter = get_broadcast_adapter()
    await adapter.publish(session_id, event)
