"""
Phase 8 — Rate Limiting Test Suite

Tests for distributed rate limiting using Redis.
Verifies cross-worker consistency and proper TTL handling.
"""
import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch

from backend.realtime.rate_limit import RedisRateLimiter


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
async def mock_rate_limiter():
    """Create mock rate limiter for testing without Redis."""
    limiter = RedisRateLimiter("redis://localhost:6379/0")
    
    # Mock Redis with in-memory storage
    mock_data = {}
    
    class MockRedis:
        async def zremrangebyscore(self, key, min_score, max_score):
            if key in mock_data:
                mock_data[key] = [
                    (score, member) for score, member in mock_data[key]
                    if score > max_score
                ]
            return 0
        
        async def zcard(self, key):
            return len(mock_data.get(key, []))
        
        async def zadd(self, key, mapping):
            if key not in mock_data:
                mock_data[key] = []
            for member, score in mapping.items():
                mock_data[key].append((score, member))
        
        async def expire(self, key, seconds):
            return True
        
        async def ttl(self, key):
            return 300  # Mock 5 minutes
    
    limiter._redis = MockRedis()
    yield limiter


# =============================================================================
# Test: Basic Rate Limiting
# =============================================================================

@pytest.mark.asyncio
async def test_basic_rate_limit_allow(mock_rate_limiter):
    """Test that requests within limit are allowed."""
    limiter = mock_rate_limiter
    
    # First request should be allowed
    allowed, remaining, reset = await limiter.check_rate_limit(
        "objection_raise", "user_1"
    )
    assert allowed is True
    assert remaining == 9  # 10 - 1 = 9
    
    # Make more requests up to limit
    for i in range(9):
        allowed, remaining, reset = await limiter.check_rate_limit(
            "objection_raise", "user_1"
        )
        assert allowed is True
    
    # Next request should be blocked
    allowed, remaining, reset = await limiter.check_rate_limit(
        "objection_raise", "user_1"
    )
    assert allowed is False
    assert remaining == 0


# =============================================================================
# Test: Cross-Worker Consistency
# =============================================================================

@pytest.mark.asyncio
async def test_cross_worker_consistency(mock_rate_limiter):
    """Test that rate limits are consistent across multiple workers."""
    limiter = mock_rate_limiter
    
    # Simulate requests from different "workers" for same user
    user_id = "user_shared"
    
    # Worker 1: 3 requests
    for _ in range(3):
        await limiter.check_rate_limit("objection_raise", user_id)
    
    # Worker 2: 3 more requests (same Redis)
    for _ in range(3):
        await limiter.check_rate_limit("objection_raise", user_id)
    
    # Worker 3: 4 more requests
    for _ in range(4):
        await limiter.check_rate_limit("objection_raise", user_id)
    
    # 11th request should be blocked regardless of "worker"
    allowed, _, _ = await limiter.check_rate_limit("objection_raise", user_id)
    assert allowed is False


# =============================================================================
# Test: WebSocket Connection Limits
# =============================================================================

@pytest.mark.asyncio
async def test_ws_connection_per_user_limit(mock_rate_limiter):
    """Test WebSocket connection limit per user."""
    limiter = mock_rate_limiter
    
    user_id = "test_user"
    
    # Allow up to 3 connections per user per hour
    for i in range(3):
        allowed, remaining, _ = await limiter.check_rate_limit(
            "ws_connections_per_user", user_id
        )
        assert allowed is True, f"Connection {i+1} should be allowed"
    
    # 4th connection should be blocked
    allowed, remaining, _ = await limiter.check_rate_limit(
        "ws_connections_per_user", user_id
    )
    assert allowed is False
    assert remaining == 0


@pytest.mark.asyncio
async def test_ws_connection_per_ip_limit(mock_rate_limiter):
    """Test WebSocket connection limit per IP."""
    limiter = mock_rate_limiter
    
    ip = "192.168.1.100"
    
    # Allow up to 5 connections per IP per hour
    for i in range(5):
        allowed, _, _ = await limiter.check_rate_limit(
            "ws_connections_per_ip", ip
        )
        assert allowed is True
    
    # 6th connection should be blocked
    allowed, _, _ = await limiter.check_rate_limit(
        "ws_connections_per_ip", ip
    )
    assert allowed is False


# =============================================================================
# Test: Different Limits Are Isolated
# =============================================================================

@pytest.mark.asyncio
async def test_different_limits_isolated(mock_rate_limiter):
    """Test that different rate limit types are isolated."""
    limiter = mock_rate_limiter
    
    user_id = "user_multi"
    
    # Exhaust objection limit
    for _ in range(10):
        await limiter.check_rate_limit("objection_raise", user_id)
    
    allowed, _, _ = await limiter.check_rate_limit("objection_raise", user_id)
    assert allowed is False  # Objections blocked
    
    # But exhibit uploads should still work
    allowed, _, _ = await limiter.check_rate_limit("exhibit_upload", user_id)
    assert allowed is True  # Exhibits allowed


# =============================================================================
# Test: TTL and Window Reset
# =============================================================================

@pytest.mark.asyncio
async def test_rate_limit_window_reset():
    """Test that rate limit window resets after TTL."""
    # This test would need real Redis or more sophisticated mocking
    # For now, verify TTL is returned correctly
    
    limiter = RedisRateLimiter("redis://localhost:6379/0")
    
    # Mock with TTL tracking
    class MockRedisWithTTL:
        def __init__(self):
            self.data = {}
            self.ttls = {}
        
        async def zremrangebyscore(self, key, min_score, max_score):
            return 0
        
        async def zcard(self, key):
            return len(self.data.get(key, []))
        
        async def zadd(self, key, mapping):
            if key not in self.data:
                self.data[key] = []
                self.ttls[key] = 60
            for member, score in mapping.items():
                self.data[key].append((score, member))
        
        async def expire(self, key, seconds):
            self.ttls[key] = seconds
            return True
        
        async def ttl(self, key):
            return self.ttls.get(key, -1)
    
    limiter._redis = MockRedisWithTTL()
    
    # Make request
    allowed, remaining, reset = await limiter.check_rate_limit(
        "objection_raise", "user_1"
    )
    
    assert allowed is True
    assert reset > 0  # Should have TTL


# =============================================================================
# Test: Unknown Limit Type
# =============================================================================

@pytest.mark.asyncio
async def test_unknown_limit_type(mock_rate_limiter):
    """Test that unknown limit types are allowed (fail open)."""
    limiter = mock_rate_limiter
    
    allowed, remaining, reset = await limiter.check_rate_limit(
        "unknown_limit_type", "user_1"
    )
    
    # Unknown types should be allowed
    assert allowed is True


# =============================================================================
# Test: Get Limit Status
# =============================================================================

@pytest.mark.asyncio
async def test_get_limit_status(mock_rate_limiter):
    """Test retrieving current rate limit status."""
    limiter = mock_rate_limiter
    
    # Make some requests
    await limiter.check_rate_limit("objection_raise", "user_1")
    await limiter.check_rate_limit("objection_raise", "user_1")
    
    # Get status without incrementing
    status = await limiter.get_limit_status("objection_raise", "user_1")
    
    assert status["limit_type"] == "objection_raise"
    assert status["identifier"] == "user_1"
    assert status["allowed"] is True
    assert status["remaining"] == 8  # 10 - 2 = 8
    assert status["max"] == 10


# =============================================================================
# Test: Is Allowed Helper
# =============================================================================

@pytest.mark.asyncio
async def test_is_allowed_helper(mock_rate_limiter):
    """Test simple is_allowed helper function."""
    limiter = mock_rate_limiter
    
    # First request
    assert await limiter.is_allowed("objection_raise", "user_1") is True
    
    # Exhaust limit
    for _ in range(9):
        await limiter.check_rate_limit("objection_raise", "user_1")
    
    # Should be blocked
    assert await limiter.is_allowed("objection_raise", "user_1") is False


# =============================================================================
# Test: Different Users Are Isolated
# =============================================================================

@pytest.mark.asyncio
async def test_user_isolation(mock_rate_limiter):
    """Test that rate limits are isolated per user."""
    limiter = mock_rate_limiter
    
    # Exhaust user_1's limit
    for _ in range(10):
        await limiter.check_rate_limit("objection_raise", "user_1")
    
    # user_1 blocked
    assert await limiter.is_allowed("objection_raise", "user_1") is False
    
    # user_2 should still be allowed
    assert await limiter.is_allowed("objection_raise", "user_2") is True


# =============================================================================
# Test: Concurrent Requests
# =============================================================================

@pytest.mark.asyncio
async def test_concurrent_rate_limit_requests(mock_rate_limiter):
    """Test rate limiting under concurrent load."""
    limiter = mock_rate_limiter
    
    user_id = "concurrent_user"
    
    async def make_request():
        return await limiter.check_rate_limit("objection_raise", user_id)
    
    # Make 15 concurrent requests
    results = await asyncio.gather(*[make_request() for _ in range(15)])
    
    # Count allowed vs blocked
    allowed_count = sum(1 for r in results if r[0])
    blocked_count = sum(1 for r in results if not r[0])
    
    # At most 10 should be allowed (limit is 10)
    assert allowed_count <= 10
    assert blocked_count >= 5


# =============================================================================
# Test: Rate Limit Key Format
# =============================================================================

@pytest.mark.asyncio
async def test_rate_limit_key_format():
    """Test that rate limit keys follow expected format."""
    limiter = RedisRateLimiter()
    
    key = limiter._make_key("ws_connections_per_user", "user_123")
    
    assert key == "ratelimit:ws_connections_per_user:user_123"
    assert key.startswith("ratelimit:")
    assert "user_123" in key
    assert "ws_connections_per_user" in key
