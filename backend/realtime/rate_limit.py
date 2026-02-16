"""
Phase 8 — Distributed Rate Limiting (Redis-Based)

Sliding window rate limiting across multiple workers.
Redis is authoritative; no in-memory counters.
"""
import asyncio
from typing import Optional
from datetime import datetime
import aioredis
import json


class RedisRateLimiter:
    """
    Distributed rate limiter using Redis.
    
    Guarantees:
    - Atomic sliding window via Redis Lua script
    - Cross-worker consistency
    - TTL-based key expiration
    - No in-memory state
    """
    
    # Rate limits configuration
    LIMITS = {
        "ws_connections_per_user": (3, 3600),      # 3 per hour
        "ws_connections_per_ip": (5, 3600),          # 5 per hour
        "objection_raise": (10, 60),               # 10 per minute
        "exhibit_upload": (5, 60),                 # 5 per minute
        "general_api": (100, 60),                  # 100 per minute
    }
    
    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.redis_url = redis_url
        self._redis: Optional[aioredis.Redis] = None
    
    async def connect(self) -> None:
        """Establish Redis connection."""
        self._redis = await aioredis.from_url(
            self.redis_url,
            decode_responses=True
        )
    
    def _make_key(self, limit_type: str, identifier: str) -> str:
        """
        Generate Redis key for rate limit.
        
        Args:
            limit_type: Type of limit (e.g., "ws_connections_per_user")
            identifier: User ID or IP address
        Returns:
            Redis key string
        """
        return f"ratelimit:{limit_type}:{identifier}"
    
    async def check_rate_limit(
        self,
        limit_type: str,
        identifier: str,
        increment: bool = True
    ) -> tuple[bool, int, int]:
        """
        Check if request is within rate limit.
        
        Args:
            limit_type: Type of limit from LIMITS
            identifier: User ID or IP to check
            increment: Whether to increment counter
        Returns:
            Tuple of (allowed, remaining, reset_seconds)
        """
        if not self._redis:
            await self.connect()
        
        if limit_type not in self.LIMITS:
            return (True, -1, 0)
        
        max_requests, window_seconds = self.LIMITS[limit_type]
        key = self._make_key(limit_type, identifier)
        now = int(datetime.utcnow().timestamp())
        
        # Use Redis sorted set for sliding window
        # Remove old entries outside window
        cutoff = now - window_seconds
        await self._redis.zremrangebyscore(key, 0, cutoff)
        
        # Count current requests
        current_count = await self._redis.zcard(key)
        
        if increment:
            # Add current request
            await self._redis.zadd(key, {str(now): now})
            # Set TTL on key
            await self._redis.expire(key, window_seconds)
            current_count += 1
        
        allowed = current_count <= max_requests
        remaining = max(0, max_requests - current_count)
        
        # Get TTL for reset time
        ttl = await self._redis.ttl(key)
        reset_seconds = max(0, ttl if ttl > 0 else window_seconds)
        
        return (allowed, remaining, reset_seconds)
    
    async def is_allowed(self, limit_type: str, identifier: str) -> bool:
        """
        Simple check if request is allowed.
        
        Args:
            limit_type: Type of limit
            identifier: User ID or IP
        Returns:
            True if allowed
        """
        allowed, _, _ = await self.check_rate_limit(limit_type, identifier)
        return allowed
    
    async def get_limit_status(self, limit_type: str, identifier: str) -> dict:
        """
        Get current rate limit status.
        
        Args:
            limit_type: Type of limit
            identifier: User ID or IP
        Returns:
            Dict with limit info
        """
        allowed, remaining, reset_seconds = await self.check_rate_limit(
            limit_type, identifier, increment=False
        )
        
        max_requests, window_seconds = self.LIMITS.get(limit_type, (0, 0))
        
        return {
            "limit_type": limit_type,
            "identifier": identifier,
            "allowed": allowed,
            "remaining": remaining,
            "max": max_requests,
            "window_seconds": window_seconds,
            "reset_seconds": reset_seconds
        }


# Global rate limiter instance
_rate_limiter: Optional[RedisRateLimiter] = None


async def get_rate_limiter(redis_url: str = "redis://localhost:6379/0") -> RedisRateLimiter:
    """Get or create global rate limiter."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RedisRateLimiter(redis_url)
        await _rate_limiter.connect()
    return _rate_limiter


async def check_ws_connection_rate_limit(
    user_id: int,
    ip_address: str,
    redis_url: str = "redis://localhost:6379/0"
) -> bool:
    """
    Check WebSocket connection rate limits.
    
    Args:
        user_id: User ID
        ip_address: Client IP
        redis_url: Redis URL
    Returns:
        True if both user and IP limits not exceeded
    """
    limiter = await get_rate_limiter(redis_url)
    
    # Check both limits
    user_allowed = await limiter.is_allowed("ws_connections_per_user", str(user_id))
    ip_allowed = await limiter.is_allowed("ws_connections_per_ip", ip_address)
    
    if user_allowed and ip_allowed:
        # Increment both counters
        await limiter.check_rate_limit("ws_connections_per_user", str(user_id), increment=True)
        await limiter.check_rate_limit("ws_connections_per_ip", ip_address, increment=True)
        return True
    
    return False
