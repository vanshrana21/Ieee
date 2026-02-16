"""
Phase 8 — In-Memory Broadcast Adapter (Development Mode)

Local-only broadcast implementation using asyncio.Queue.
No Redis dependency for development/testing.
"""
import asyncio
import json
from typing import Dict, Any, Set
from .broadcast_adapter import BroadcastAdapter


class InMemoryAdapter(BroadcastAdapter):
    """
    In-memory broadcast adapter for development.
    
    Uses asyncio.Queue for local-only message passing.
    Deterministic and idempotent like production adapter.
    """
    
    def __init__(self):
        self._channels: Dict[str, Set[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()
    
    async def publish(self, channel: str, message: Dict[str, Any]) -> None:
        """
        Publish message to in-memory channel.
        
        Args:
            channel: Channel name
            message: Message payload (must have event_sequence, event_hash)
        """
        self.validate_message(message)
        
        # Serialize deterministically
        serialized = self._serialize_message(message)
        
        # Send to all subscribers
        async with self._lock:
            if channel in self._channels:
                # Copy to avoid modification during iteration
                queues = list(self._channels[channel])
                for queue in queues:
                    try:
                        queue.put_nowait(serialized)
                    except asyncio.QueueFull:
                        # Drop if subscriber is slow (backpressure)
                        pass
    
    async def subscribe(self, channel: str):
        """
        Subscribe to channel and yield messages.
        
        Args:
            channel: Channel name
        Yields:
            Parsed message dicts
        """
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        
        async with self._lock:
            if channel not in self._channels:
                self._channels[channel] = set()
            self._channels[channel].add(queue)
        
        try:
            while True:
                serialized = await queue.get()
                try:
                    yield json.loads(serialized)
                except json.JSONDecodeError:
                    # Skip corrupted messages
                    continue
        finally:
            # Cleanup on unsubscribe
            async with self._lock:
                if channel in self._channels:
                    self._channels[channel].discard(queue)
    
    async def close(self) -> None:
        """Close all channels."""
        async with self._lock:
            for channel in self._channels:
                for queue in self._channels[channel]:
                    queue.put_nowait(None)  # Signal shutdown
            self._channels.clear()
