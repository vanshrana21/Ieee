"""
Phase 8 — Broadcast Adapter Interface

Abstract base class for broadcast implementations.
Deterministic, idempotent, server-authoritative design.
"""
import abc
import json
import hashlib
from typing import Dict, Any


class BroadcastAdapter(abc.ABC):
    """
    Abstract base class for broadcast adapters.
    
    Guarantees:
    - Deterministic message serialization (sort_keys=True)
    - Idempotent delivery (event_sequence + event_hash)
    - Server-authoritative (DB source of truth)
    - Delivery-only (Redis is not source of truth)
    """
    
    @abc.abstractmethod
    async def publish(self, channel: str, message: Dict[str, Any]) -> None:
        """
        Publish message to channel.
        
        Args:
            channel: Channel name (e.g., "session:42")
            message: Message payload (must contain event_sequence and event_hash)
        """
        raise NotImplementedError
    
    @abc.abstractmethod
    async def subscribe(self, channel: str):
        """
        Subscribe to channel and yield messages.
        
        Args:
            channel: Channel name to subscribe to
        Yields:
            Parsed message dict
        """
        raise NotImplementedError
    
    @abc.abstractmethod
    async def close(self) -> None:
        """Close adapter connections."""
        raise NotImplementedError
    
    def _serialize_message(self, message: Dict[str, Any]) -> str:
        """
        Serialize message deterministically.
        
        Requirements:
        - sort_keys=True for determinism
        - No pretty printing (compact)
        
        Args:
            message: Message dict to serialize
        Returns:
            JSON string
        """
        return json.dumps(message, sort_keys=True, separators=(',', ':'))
    
    def _compute_message_hash(self, message: Dict[str, Any]) -> str:
        """
        Compute SHA256 hash of message for integrity.
        
        Args:
            message: Message dict
        Returns:
            Hex digest of SHA256 hash
        """
        serialized = self._serialize_message(message)
        return hashlib.sha256(serialized.encode()).hexdigest()
    
    def validate_message(self, message: Dict[str, Any]) -> bool:
        """
        Validate message has required fields for idempotency.
        
        Required fields:
        - event_sequence: int
        - event_hash: str
        - session_id: int
        
        Args:
            message: Message to validate
        Returns:
            True if valid
        Raises:
            ValueError: If required fields missing
        """
        required = ["event_sequence", "event_hash", "session_id"]
        missing = [f for f in required if f not in message]
        if missing:
            raise ValueError(f"Message missing required fields: {missing}")
        return True
