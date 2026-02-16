"""
Phase 8 — Backpressure Protection

Prevents memory exhaustion from slow WebSocket clients.
Bounded queues with configurable overflow behavior.
"""
import asyncio
from typing import Dict, Optional, Callable
from fastapi import WebSocket
import logging

logger = logging.getLogger(__name__)


class BackpressureManager:
    """
    Manages message queues with backpressure protection.
    
    Design:
    - Each WebSocket gets fixed-size queue (default 100)
    - When queue full: drop oldest message (configurable)
    - Track overflow statistics
    - Never allow unbounded growth
    """
    
    def __init__(
        self,
        max_queue_size: int = 100,
        overflow_action: str = "drop_oldest"
    ):
        """
        Initialize backpressure manager.
        
        Args:
            max_queue_size: Maximum messages per queue
            overflow_action: "drop_oldest" or "disconnect"
        """
        self.max_queue_size = max_queue_size
        self.overflow_action = overflow_action
        
        # Message queues: {websocket: asyncio.Queue}
        self.queues: Dict[WebSocket, asyncio.Queue] = {}
        
        # Overflow statistics
        self.overflow_count: Dict[WebSocket, int] = {}
        
        # Disconnect callbacks
        self.disconnect_handlers: Dict[WebSocket, Callable] = {}
    
    def register_connection(
        self,
        websocket: WebSocket,
        on_overflow: Optional[Callable] = None
    ) -> asyncio.Queue:
        """
        Register new WebSocket with message queue.
        
        Args:
            websocket: WebSocket to manage
            on_overflow: Callback when overflow occurs
        Returns:
            Message queue for this connection
        """
        queue: asyncio.Queue = asyncio.Queue(maxsize=self.max_queue_size)
        self.queues[websocket] = queue
        self.overflow_count[websocket] = 0
        
        if on_overflow:
            self.disconnect_handlers[websocket] = on_overflow
        
        return queue
    
    def unregister_connection(self, websocket: WebSocket) -> None:
        """
        Remove WebSocket and clean up resources.
        
        Args:
            websocket: WebSocket to remove
        """
        self.queues.pop(websocket, None)
        self.overflow_count.pop(websocket, None)
        self.disconnect_handlers.pop(websocket, None)
    
    async def send_message(
        self,
        websocket: WebSocket,
        message: str
    ) -> bool:
        """
        Send message with backpressure handling.
        
        Args:
            websocket: Target WebSocket
            message: Message to send (JSON string)
        Returns:
            True if message queued successfully
        """
        queue = self.queues.get(websocket)
        if not queue:
            return False
        
        try:
            queue.put_nowait(message)
            return True
        except asyncio.QueueFull:
            # Handle overflow
            self.overflow_count[websocket] = self.overflow_count.get(websocket, 0) + 1
            
            if self.overflow_action == "drop_oldest":
                return await self._handle_drop_oldest(websocket, queue, message)
            elif self.overflow_action == "disconnect":
                return await self._handle_disconnect(websocket)
            else:
                logger.warning(f"Unknown overflow action: {self.overflow_action}")
                return False
    
    async def _handle_drop_oldest(
        self,
        websocket: WebSocket,
        queue: asyncio.Queue,
        message: str
    ) -> bool:
        """
        Drop oldest message and queue new one.
        
        Args:
            websocket: WebSocket connection
            queue: Message queue
            message: New message to queue
        Returns:
            True if successful
        """
        try:
            # Remove oldest
            old_message = queue.get_nowait()
            logger.debug(f"Dropped message due to backpressure: {old_message[:50]}...")
            
            # Add new message
            queue.put_nowait(message)
            return True
        except asyncio.QueueEmpty:
            # Queue became empty, try again
            try:
                queue.put_nowait(message)
                return True
            except asyncio.QueueFull:
                return False
    
    async def _handle_disconnect(self, websocket: WebSocket) -> bool:
        """
        Disconnect client due to backpressure.
        
        Args:
            websocket: WebSocket to disconnect
        Returns:
            False (disconnected)
        """
        logger.warning(f"Disconnecting slow client due to backpressure: {websocket}")
        
        # Call disconnect handler if registered
        handler = self.disconnect_handlers.get(websocket)
        if handler:
            try:
                await handler(websocket)
            except Exception as e:
                logger.error(f"Error in disconnect handler: {e}")
        
        return False
    
    def get_queue_size(self, websocket: WebSocket) -> int:
        """
        Get current queue size for connection.
        
        Args:
            websocket: WebSocket to check
        Returns:
            Number of queued messages
        """
        queue = self.queues.get(websocket)
        return queue.qsize() if queue else 0
    
    def get_overflow_stats(self, websocket: Optional[WebSocket] = None) -> dict:
        """
        Get overflow statistics.
        
        Args:
            websocket: Optional specific connection (None for all)
        Returns:
            Dict with statistics
        """
        if websocket:
            return {
                "websocket_id": id(websocket),
                "overflow_count": self.overflow_count.get(websocket, 0),
                "queue_size": self.get_queue_size(websocket),
                "max_queue_size": self.max_queue_size
            }
        
        # Global stats
        total_overflows = sum(self.overflow_count.values())
        total_queues = len(self.queues)
        total_messages = sum(q.qsize() for q in self.queues.values())
        
        return {
            "total_overflows": total_overflows,
            "active_queues": total_queues,
            "total_queued_messages": total_messages,
            "max_queue_size": self.max_queue_size,
            "overflow_action": self.overflow_action
        }
    
    async def broadcast_with_backpressure(
        self,
        websockets: list[WebSocket],
        message: str
    ) -> dict:
        """
        Broadcast message to multiple connections with backpressure.
        
        Args:
            websockets: List of target WebSockets
            message: Message to broadcast
        Returns:
            Dict with success/failure counts
        """
        success = 0
        failed = 0
        dropped = 0
        
        for ws in websockets:
            queue = self.queues.get(ws)
            if not queue:
                failed += 1
                continue
            
            try:
                queue.put_nowait(message)
                success += 1
            except asyncio.QueueFull:
                # Try to drop oldest
                if self.overflow_action == "drop_oldest":
                    if await self._handle_drop_oldest(ws, queue, message):
                        success += 1
                        dropped += 1
                    else:
                        failed += 1
                else:
                    failed += 1
        
        return {
            "success": success,
            "failed": failed,
            "dropped": dropped,
            "total": len(websockets)
        }


# Global backpressure manager instance
_backpressure_manager: Optional[BackpressureManager] = None


def get_backpressure_manager() -> Optional[BackpressureManager]:
    """Get global backpressure manager."""
    return _backpressure_manager


def set_backpressure_manager(manager: BackpressureManager) -> None:
    """Set global backpressure manager."""
    global _backpressure_manager
    _backpressure_manager = manager


def create_backpressure_manager(
    max_queue_size: int = 100,
    overflow_action: str = "drop_oldest"
) -> BackpressureManager:
    """Factory function to create backpressure manager."""
    return BackpressureManager(max_queue_size, overflow_action)
