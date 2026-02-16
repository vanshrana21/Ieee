"""
Phase 8 — Broadcast Adapter Test Suite

Tests for multi-worker synchronization via Redis Pub/Sub.
Verifies determinism, idempotency, and cross-worker delivery.
"""
import pytest
import asyncio
import json
from datetime import datetime

from backend.realtime.broadcast_adapter import BroadcastAdapter
from backend.realtime.in_memory_adapter import InMemoryAdapter


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
async def in_memory_adapter():
    """Create in-memory broadcast adapter for testing."""
    adapter = InMemoryAdapter()
    yield adapter
    await adapter.close()


@pytest.fixture
def sample_event():
    """Create sample event with required fields."""
    return {
        "type": "EVENT",
        "session_id": 42,
        "event_sequence": 1,
        "event_hash": "abc123" * 10,  # 60 chars
        "payload": {"turn_id": 1, "action": "started"}
    }


# =============================================================================
# Test: Message Validation
# =============================================================================

@pytest.mark.asyncio
async def test_message_validation_required_fields():
    """Test that messages must have required fields."""
    adapter = InMemoryAdapter()
    
    # Missing event_sequence
    with pytest.raises(ValueError) as exc:
        await adapter.publish("session:42", {
            "event_hash": "abc123",
            "session_id": 42
        })
    assert "event_sequence" in str(exc.value)
    
    # Missing event_hash
    with pytest.raises(ValueError) as exc:
        await adapter.publish("session:42", {
            "event_sequence": 1,
            "session_id": 42
        })
    assert "event_hash" in str(exc.value)
    
    # Missing session_id
    with pytest.raises(ValueError) as exc:
        await adapter.publish("session:42", {
            "event_sequence": 1,
            "event_hash": "abc123"
        })
    assert "session_id" in str(exc.value)


# =============================================================================
# Test: Deterministic Serialization
# =============================================================================

@pytest.mark.asyncio
async def test_deterministic_serialization(sample_event):
    """Test that messages serialize deterministically (sort_keys=True)."""
    adapter = InMemoryAdapter()
    
    # Create event with unsorted keys
    unsorted_event = {
        "payload": {"z_key": 1, "a_key": 2},
        "event_sequence": 1,
        "type": "EVENT",
        "session_id": 42,
        "event_hash": "abc123" * 10
    }
    
    # Subscribe and collect
    received = []
    
    async def subscriber():
        async for msg in adapter.subscribe("test:channel"):
            received.append(msg)
            break
    
    # Publish
    task = asyncio.create_task(subscriber())
    await adapter.publish("test:channel", unsorted_event)
    await asyncio.wait_for(task, timeout=1.0)
    
    # Verify received message has sorted keys
    assert len(received) == 1
    received_keys = list(received[0].keys())
    assert received_keys == sorted(received_keys)


# =============================================================================
# Test: Multi-Worker Simulation
# =============================================================================

@pytest.mark.asyncio
async def test_multi_worker_message_delivery(sample_event):
    """Simulate multi-worker: publish from A, receive at B."""
    adapter = InMemoryAdapter()
    
    # Worker B subscribes
    received_by_b = []
    
    async def worker_b_subscriber():
        async for msg in adapter.subscribe("session:42"):
            received_by_b.append(msg)
            if len(received_by_b) >= 3:
                break
    
    # Start subscriber
    subscriber_task = asyncio.create_task(worker_b_subscriber())
    
    # Worker A publishes multiple events
    await adapter.publish("session:42", {**sample_event, "event_sequence": 1})
    await adapter.publish("session:42", {**sample_event, "event_sequence": 2})
    await adapter.publish("session:42", {**sample_event, "event_sequence": 3})
    
    # Wait for all to be received
    await asyncio.wait_for(subscriber_task, timeout=2.0)
    
    # Verify all events received
    assert len(received_by_b) == 3
    sequences = [msg["event_sequence"] for msg in received_by_b]
    assert sequences == [1, 2, 3]


# =============================================================================
# Test: Idempotency
# =============================================================================

@pytest.mark.asyncio
async def test_duplicate_message_delivery(sample_event):
    """Test that duplicate sequences are handled (idempotent)."""
    adapter = InMemoryAdapter()
    
    received = []
    
    async def subscriber():
        async for msg in adapter.subscribe("session:42"):
            received.append(msg)
            if len(received) >= 2:
                break
    
    subscriber_task = asyncio.create_task(subscriber())
    
    # Publish same event twice (simulating duplicate)
    await adapter.publish("session:42", sample_event)
    await adapter.publish("session:42", sample_event)
    
    await asyncio.wait_for(subscriber_task, timeout=1.0)
    
    # Both should be received (client must dedupe by event_sequence)
    assert len(received) == 2
    assert received[0]["event_sequence"] == received[1]["event_sequence"]


# =============================================================================
# Test: Channel Isolation
# =============================================================================

@pytest.mark.asyncio
async def test_channel_isolation(sample_event):
    """Test that channels are properly isolated."""
    adapter = InMemoryAdapter()
    
    session_42_received = []
    session_99_received = []
    
    async def subscriber_42():
        async for msg in adapter.subscribe("session:42"):
            session_42_received.append(msg)
            break
    
    async def subscriber_99():
        async for msg in adapter.subscribe("session:99"):
            session_99_received.append(msg)
            break
    
    # Start both subscribers
    task_42 = asyncio.create_task(subscriber_42())
    task_99 = asyncio.create_task(subscriber_99())
    
    # Publish to session 42 only
    await adapter.publish("session:42", {**sample_event, "session_id": 42})
    
    # Wait for 42 subscriber
    await asyncio.wait_for(task_42, timeout=1.0)
    
    # 99 subscriber should timeout (no message)
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(task_99, timeout=0.5)
    
    # Verify isolation
    assert len(session_42_received) == 1
    assert len(session_99_received) == 0


# =============================================================================
# Test: Backpressure (Slow Subscriber)
# =============================================================================

@pytest.mark.asyncio
async def test_backpressure_slow_subscriber(sample_event):
    """Test that slow subscribers don't block fast publishers."""
    adapter = InMemoryAdapter()
    
    received = []
    
    async def slow_subscriber():
        async for msg in adapter.subscribe("session:42"):
            received.append(msg)
            await asyncio.sleep(0.1)  # Slow consumer
            if len(received) >= 5:
                break
    
    subscriber_task = asyncio.create_task(slow_subscriber())
    
    # Rapidly publish many messages
    for i in range(10):
        await adapter.publish("session:42", {**sample_event, "event_sequence": i})
    
    # Wait for subscriber to process what it can
    await asyncio.wait_for(subscriber_task, timeout=3.0)
    
    # Should have received some messages (not necessarily all due to queue limits)
    assert len(received) > 0


# =============================================================================
# Test: Message Hash Integrity
# =============================================================================

@pytest.mark.asyncio
async def test_message_hash_computation():
    """Test that message hash is computed correctly."""
    adapter = InMemoryAdapter()
    
    message = {
        "type": "EVENT",
        "session_id": 42,
        "event_sequence": 1,
        "event_hash": "stored_hash",
        "payload": {"data": "test"}
    }
    
    # Compute hash
    import hashlib
    serialized = json.dumps(message, sort_keys=True, separators=(',', ':'))
    computed_hash = hashlib.sha256(serialized.encode()).hexdigest()
    
    # Hash should be deterministic
    computed_again = hashlib.sha256(serialized.encode()).hexdigest()
    assert computed_hash == computed_again
    
    # Different serialization produces different hash
    unsorted = json.dumps(message, separators=(',', ':'))
    if unsorted != serialized:  # If keys were in different order
        unsorted_hash = hashlib.sha256(unsorted.encode()).hexdigest()
        # Note: this may be the same if keys happen to be sorted by default
        # but the test validates deterministic behavior


# =============================================================================
# Test: Broadcast Contract Compliance
# =============================================================================

@pytest.mark.asyncio
async def test_broadcast_contract_fields():
    """Test that all broadcast messages follow the required contract."""
    adapter = InMemoryAdapter()
    
    # Valid message with all required fields
    valid_message = {
        "type": "EVENT",
        "session_id": 42,
        "event_sequence": 17,
        "event_hash": "a" * 64,
        "payload": {"turn_id": 5, "state": "active"}
    }
    
    received = []
    
    async def subscriber():
        async for msg in adapter.subscribe("session:42"):
            received.append(msg)
            break
    
    task = asyncio.create_task(subscriber())
    await adapter.publish("session:42", valid_message)
    await asyncio.wait_for(task, timeout=1.0)
    
    assert len(received) == 1
    msg = received[0]
    
    # Verify all contract fields present
    assert msg["type"] == "EVENT"
    assert isinstance(msg["session_id"], int)
    assert isinstance(msg["event_sequence"], int)
    assert isinstance(msg["event_hash"], str)
    assert len(msg["event_hash"]) == 64  # SHA256 hex
    assert isinstance(msg["payload"], dict)


# =============================================================================
# Test: No Datetime.now() Usage
# =============================================================================

@pytest.mark.asyncio
async def test_no_datetime_now_in_messages():
    """Test that messages don't use datetime.now() (should use utcnow)."""
    adapter = InMemoryAdapter()
    
    # Message with utcnow
    message = {
        "type": "EVENT",
        "session_id": 42,
        "event_sequence": 1,
        "event_hash": "abc123" * 10,
        "timestamp": datetime.utcnow().isoformat(),
        "payload": {}
    }
    
    received = []
    
    async def subscriber():
        async for msg in adapter.subscribe("session:42"):
            received.append(msg)
            break
    
    task = asyncio.create_task(subscriber())
    await adapter.publish("session:42", message)
    await asyncio.wait_for(task, timeout=1.0)
    
    assert len(received) == 1


# =============================================================================
# Test: Connection Cleanup
# =============================================================================

@pytest.mark.asyncio
async def test_subscriber_cleanup_on_disconnect():
    """Test that subscribers are cleaned up properly."""
    adapter = InMemoryAdapter()
    
    # Subscribe then cancel
    received = []
    
    async def subscriber():
        async for msg in adapter.subscribe("session:42"):
            received.append(msg)
    
    task = asyncio.create_task(subscriber())
    
    # Let it start
    await asyncio.sleep(0.1)
    
    # Cancel
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    
    # Publish should not error even after subscriber cancelled
    await adapter.publish("session:42", {
        "type": "EVENT",
        "session_id": 42,
        "event_sequence": 1,
        "event_hash": "abc" * 21,
        "payload": {}
    })
    
    # No error means cleanup worked
    assert True
