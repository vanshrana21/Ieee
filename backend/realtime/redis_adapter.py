"""
Phase 8 — Redis Broadcast Adapter (Production Mode)

Redis Pub/Sub implementation for multi-worker synchronization.
Deterministic, idempotent, delivery-only.
"""
import asyncio
import json
from typing import Dict, Any, Optional
import aioredis
from .broadcast_adapter import BroadcastAdapter


class RedisAdapter(BroadcastAdapter):
    """
    Redis Pub/Sub adapter for production multi-worker deployment.
    
    Guarantees:
    - Deterministic JSON serialization (sort_keys=True)
    - Cross-worker message delivery
    - Automatic reconnection
    - No Redis as source of truth (delivery only)
    """
    
    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.redis_url = redis_url
        self._redis: Optional[aioredis.Redis] = None
        self._pubsub: Optional[aioredis.client.PubSub] = None
        self._subscriber_tasks: Dict[str, asyncio.Task] = {}
    
    async def connect(self) -> None:
        """Establish Redis connection."""
        self._redis = await aioredis.from_url(
            self.redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_keepalive=True,
            retry_on_timeout=True
        )
    
    async def publish(self, channel: str, message: Dict[str, Any]) -> None:
        """
        Publish message to Redis channel.
        
        Args:
            channel: Channel name (format: "session:{session_id}")
            message: Message payload
        """
        if not self._redis:
            await self.connect()
        
        self.validate_message(message)
        
        # Serialize deterministically
        serialized = self._serialize_message(message)
        
        # Publish to Redis
        await self._redis.publish(channel, serialized)
    
    async def subscribe(self, channel: str):
        """
        Subscribe to Redis channel and yield messages.
        
        Args:
            channel: Channel name to subscribe to
        Yields:
            Parsed message dicts
        """
        if not self._redis:
            await self.connect()
        
        if not self._pubsub:
            self._pubsub = self._redis.pubsub()
        
        await self._pubsub.subscribe(channel)
        
        try:
            async for message in self._pubsub.listen():
                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        yield data
                    except json.JSONDecodeError:
                        # Skip corrupted messages
                        continue
        finally:
            await self._pubsub.unsubscribe(channel)
    
    async def close(self) -> None:
        """Close Redis connections."""
        if self._pubsub:
            await self._pubsub.close()
        if self._redis:
            await self._redis.close()


async def create_broadcast_adapter(
    use_redis: bool = False,
    redis_url: str = "redis://localhost:6379/0"
) -> BroadcastAdapter:
    """
    Factory function to create appropriate broadcast adapter.
    
    Args:
        use_redis: True for RedisAdapter, False for InMemoryAdapter
        redis_url: Redis connection URL
    Returns:
        Configured BroadcastAdapter instance
    """
    if use_redis:
        adapter = RedisAdapter(redis_url)
        await adapter.connect()
        return adapter
    else:
        from .in_memory_adapter import InMemoryAdapter
        return InMemoryAdapter()
