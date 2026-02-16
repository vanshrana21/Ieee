"""
Phase 8 — Backpressure Protection Test Suite

Tests for bounded message queues and overflow handling.
Verifies memory stability under slow consumer conditions.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from fastapi import WebSocket

from backend.realtime.backpressure import (
    BackpressureManager, create_backpressure_manager
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def backpressure_manager():
    """Create backpressure manager with small queue for testing."""
    return BackpressureManager(max_queue_size=10, overflow_action="drop_oldest")


@pytest.fixture
def mock_websocket():
    """Create mock WebSocket."""
    ws = MagicMock(spec=WebSocket)
    ws.client = MagicMock()
    ws.client.host = "127.0.0.1"
    return ws


# =============================================================================
# Test: Basic Queue Registration
# =============================================================================

def test_register_connection(backpressure_manager, mock_websocket):
    """Test that connections are registered with queues."""
    manager = backpressure_manager
    
    queue = manager.register_connection(mock_websocket)
    
    assert mock_websocket in manager.queues
    assert queue.maxsize == 10
    assert manager.overflow_count[mock_websocket] == 0


def test_unregister_connection(backpressure_manager, mock_websocket):
    """Test that connections are properly cleaned up."""
    manager = backpressure_manager
    
    manager.register_connection(mock_websocket)
    manager.unregister_connection(mock_websocket)
    
    assert mock_websocket not in manager.queues
    assert mock_websocket not in manager.overflow_count


# =============================================================================
# Test: Message Queueing
# =============================================================================

@pytest.mark.asyncio
async def test_send_message_success(backpressure_manager, mock_websocket):
    """Test successful message queuing."""
    manager = backpressure_manager
    manager.register_connection(mock_websocket)
    
    result = await manager.send_message(mock_websocket, '{"test": "message"}')
    
    assert result is True
    assert manager.get_queue_size(mock_websocket) == 1


@pytest.mark.asyncio
async def test_send_message_unregistered(backpressure_manager, mock_websocket):
    """Test sending to unregistered connection fails."""
    manager = backpressure_manager
    # Don't register
    
    result = await manager.send_message(mock_websocket, '{"test": "message"}')
    
    assert result is False


# =============================================================================
# Test: Queue Overflow - Drop Oldest
# =============================================================================

@pytest.mark.asyncio
async def test_drop_oldest_on_overflow(backpressure_manager, mock_websocket):
    """Test that oldest messages are dropped when queue full."""
    manager = backpressure_manager
    manager.register_connection(mock_websocket)
    
    # Fill queue
    for i in range(10):
        await manager.send_message(mock_websocket, f'"msg_{i}"')
    
    assert manager.get_queue_size(mock_websocket) == 10
    
    # Add one more - should drop oldest
    result = await manager.send_message(mock_websocket, '"new_msg"')
    
    assert result is True
    assert manager.get_queue_size(mock_websocket) == 10  # Still full
    assert manager.overflow_count[mock_websocket] == 1


# =============================================================================
# Test: Queue Overflow - Disconnect
# =============================================================================

@pytest.mark.asyncio
async def test_disconnect_on_overflow(mock_websocket):
    """Test that slow clients are disconnected when configured."""
    manager = BackpressureManager(max_queue_size=5, overflow_action="disconnect")
    
    disconnect_called = False
    
    async def disconnect_handler(ws):
        nonlocal disconnect_called
        disconnect_called = True
    
    manager.register_connection(mock_websocket, on_overflow=disconnect_handler)
    
    # Fill queue
    for i in range(5):
        await manager.send_message(mock_websocket, f'"msg_{i}"')
    
    # Next message should trigger disconnect
    result = await manager.send_message(mock_websocket, '"overflow_msg"')
    
    assert result is False
    assert disconnect_called is True


# =============================================================================
# Test: Memory Stability
# =============================================================================

@pytest.mark.asyncio
async def test_memory_stable_with_slow_consumer(backpressure_manager, mock_websocket):
    """Test that memory doesn't grow unbounded with slow consumer."""
    manager = backpressure_manager
    manager.register_connection(mock_websocket)
    
    # Send many messages rapidly
    for i in range(100):
        await manager.send_message(mock_websocket, f'"message_{i}"')
    
    # Queue should still be bounded
    assert manager.get_queue_size(mock_websocket) <= 10
    assert manager.overflow_count[mock_websocket] == 90  # 100 - 10 = 90 dropped


# =============================================================================
# Test: Broadcast with Backpressure
# =============================================================================

@pytest.mark.asyncio
async def test_broadcast_with_backpressure(backpressure_manager):
    """Test broadcasting to multiple connections with backpressure."""
    manager = backpressure_manager
    
    # Create multiple mock websockets
    websockets = []
    for i in range(5):
        ws = MagicMock(spec=WebSocket)
        ws.client = MagicMock()
        ws.client.host = f"127.0.0.{i}"
        manager.register_connection(ws)
        websockets.append(ws)
    
    # Fill some queues
    for i, ws in enumerate(websockets[:3]):
        for _ in range(10):  # Fill to capacity
            await manager.send_message(ws, '"filler"')
    
    # Broadcast should handle overflow
    result = await manager.broadcast_with_backpressure(
        websockets, '{"broadcast": "message"}'
    )
    
    assert result["total"] == 5
    assert result["success"] == 5  # All should succeed (some with drops)


# =============================================================================
# Test: Queue Size Tracking
# =============================================================================

def test_get_queue_size(backpressure_manager, mock_websocket):
    """Test queue size reporting."""
    manager = backpressure_manager
    manager.register_connection(mock_websocket)
    
    assert manager.get_queue_size(mock_websocket) == 0
    
    # Add messages
    for i in range(5):
        manager.queues[mock_websocket].put_nowait(f'"msg_{i}"')
    
    assert manager.get_queue_size(mock_websocket) == 5


# =============================================================================
# Test: Overflow Statistics
# =============================================================================

def test_overflow_stats_single_connection(backpressure_manager, mock_websocket):
    """Test overflow stats for single connection."""
    manager = backpressure_manager
    manager.register_connection(mock_websocket)
    
    # Simulate overflow
    manager.overflow_count[mock_websocket] = 5
    
    stats = manager.get_overflow_stats(mock_websocket)
    
    assert stats["websocket_id"] == id(mock_websocket)
    assert stats["overflow_count"] == 5
    assert stats["queue_size"] == 0
    assert stats["max_queue_size"] == 10


def test_overflow_stats_global(backpressure_manager, mock_websocket):
    """Test global overflow stats."""
    manager = backpressure_manager
    
    # Register multiple connections
    for i in range(3):
        ws = MagicMock(spec=WebSocket)
        manager.register_connection(ws)
        manager.overflow_count[ws] = i + 1  # 1, 2, 3
    
    stats = manager.get_overflow_stats()
    
    assert stats["total_overflows"] == 6  # 1 + 2 + 3
    assert stats["active_queues"] == 3
    assert stats["total_queued_messages"] == 0
    assert stats["max_queue_size"] == 10
    assert stats["overflow_action"] == "drop_oldest"


# =============================================================================
# Test: Invalid Overflow Action
# =============================================================================

@pytest.mark.asyncio
async def test_invalid_overflow_action(mock_websocket):
    """Test that invalid overflow action defaults safely."""
    manager = BackpressureManager(max_queue_size=5, overflow_action="invalid_action")
    manager.register_connection(mock_websocket)
    
    # Fill queue
    for i in range(5):
        await manager.send_message(mock_websocket, f'"msg_{i}"')
    
    # Should not crash, just return False
    result = await manager.send_message(mock_websocket, '"overflow"')
    
    assert result is False


# =============================================================================
# Test: Global Instance Management
# =============================================================================

def test_global_instance_management():
    """Test global backpressure manager getter/setter."""
    from backend.realtime.backpressure import (
        get_backpressure_manager, set_backpressure_manager
    )
    
    # Initially None
    assert get_backpressure_manager() is None
    
    # Set manager
    manager = BackpressureManager()
    set_backpressure_manager(manager)
    
    # Should be retrievable
    assert get_backpressure_manager() is manager


def test_create_backpressure_manager_factory():
    """Test factory function."""
    from backend.realtime.backpressure import create_backpressure_manager
    
    manager = create_backpressure_manager(max_queue_size=50, overflow_action="disconnect")
    
    assert manager.max_queue_size == 50
    assert manager.overflow_action == "disconnect"


# =============================================================================
# Test: Concurrent Queue Access
# =============================================================================

@pytest.mark.asyncio
async def test_concurrent_send_messages(backpressure_manager, mock_websocket):
    """Test concurrent message sending to same queue."""
    manager = backpressure_manager
    manager.register_connection(mock_websocket)
    
    async def send_batch(start, end):
        for i in range(start, end):
            await manager.send_message(mock_websocket, f'"msg_{i}"')
    
    # Send concurrently
    await asyncio.gather(
        send_batch(0, 50),
        send_batch(50, 100),
        send_batch(100, 150)
    )
    
    # Queue should still be bounded
    assert manager.get_queue_size(mock_websocket) <= 10
    assert manager.overflow_count[mock_websocket] >= 140  # 150 - 10


# =============================================================================
# Test: Empty Queue Behavior
# =============================================================================

@pytest.mark.asyncio
async def test_empty_queue_get_oldest(backpressure_manager, mock_websocket):
    """Test handling when trying to drop oldest from empty queue."""
    manager = backpressure_manager
    manager.register_connection(mock_websocket)
    
    # Force overflow on empty queue
    import asyncio
    # Manually set queue to empty
    while not manager.queues[mock_websocket].empty():
        manager.queues[mock_websocket].get_nowait()
    
    # Directly test _handle_drop_oldest
    result = await manager._handle_drop_oldest(
        mock_websocket,
        manager.queues[mock_websocket],
        '"new_message"'
    )
    
    # Should still succeed (adds to now-empty queue)
    assert result is True
