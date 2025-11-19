"""
Rate Limiter for Webhook Receiver

Simple token bucket rate limiter to protect against DoS attacks.
Uses in-memory storage with periodic cleanup.
"""

import time
from dataclasses import dataclass
from threading import Lock

from aci.common.logging_setup import get_logger

logger = get_logger(__name__)


@dataclass
class TokenBucket:
    """Token bucket for rate limiting"""

    capacity: int  # Maximum tokens
    tokens: float  # Current tokens
    rate: float  # Tokens added per second
    last_update: float  # Last update timestamp


class RateLimiter:
    """
    Thread-safe token bucket rate limiter.

    Uses the token bucket algorithm:
    - Each identifier (IP, trigger_id, etc.) gets a bucket
    - Buckets refill at a constant rate
    - Requests consume tokens
    - If no tokens available, request is rate limited
    """

    def __init__(
        self,
        rate: int = 10,  # requests per second
        capacity: int = 20,  # burst capacity
        cleanup_interval: int = 3600,  # cleanup every hour
    ):
        """
        Initialize rate limiter.

        Args:
            rate: Number of requests allowed per second
            capacity: Maximum burst capacity
            cleanup_interval: How often to cleanup old buckets (seconds)
        """
        self.rate = rate
        self.capacity = capacity
        self.cleanup_interval = cleanup_interval

        self.buckets: dict[str, TokenBucket] = {}
        self.lock = Lock()
        self.last_cleanup = time.time()

    def allow(self, identifier: str, cost: int = 1) -> tuple[bool, dict[str, any]]:
        """
        Check if request is allowed.

        Args:
            identifier: Unique identifier (IP address, trigger_id, etc.)
            cost: Number of tokens to consume (default 1)

        Returns:
            Tuple of (allowed: bool, metadata: dict)
            metadata contains: remaining, reset_time, retry_after
        """
        with self.lock:
            now = time.time()

            # Periodic cleanup
            if now - self.last_cleanup > self.cleanup_interval:
                self._cleanup(now)

            # Get or create bucket
            if identifier not in self.buckets:
                self.buckets[identifier] = TokenBucket(
                    capacity=self.capacity,
                    tokens=self.capacity,
                    rate=self.rate,
                    last_update=now,
                )

            bucket = self.buckets[identifier]

            # Refill tokens based on time passed
            time_passed = now - bucket.last_update
            bucket.tokens = min(
                bucket.capacity,
                bucket.tokens + (time_passed * bucket.rate),
            )
            bucket.last_update = now

            # Check if enough tokens available
            if bucket.tokens >= cost:
                bucket.tokens -= cost
                allowed = True
                retry_after = 0
            else:
                allowed = False
                # Calculate when next token will be available
                tokens_needed = cost - bucket.tokens
                retry_after = int(tokens_needed / bucket.rate) + 1

            metadata = {
                "remaining": int(bucket.tokens),
                "limit": bucket.capacity,
                "reset_time": now + (bucket.capacity / bucket.rate),
                "retry_after": retry_after,
            }

            return allowed, metadata

    def _cleanup(self, now: float):
        """
        Remove old buckets to prevent memory leak.

        Args:
            now: Current timestamp
        """
        # Remove buckets that haven't been used in last hour
        idle_threshold = now - self.cleanup_interval
        before_count = len(self.buckets)

        self.buckets = {k: v for k, v in self.buckets.items() if v.last_update > idle_threshold}

        after_count = len(self.buckets)
        removed = before_count - after_count

        if removed > 0:
            logger.info(f"Rate limiter cleanup: removed {removed} idle buckets")

        self.last_cleanup = now

    def reset(self, identifier: str):
        """
        Reset rate limit for a specific identifier.

        Args:
            identifier: Identifier to reset
        """
        with self.lock:
            if identifier in self.buckets:
                del self.buckets[identifier]
                logger.info(f"Reset rate limit for {identifier}")

    def stats(self) -> dict[str, any]:
        """
        Get rate limiter statistics.

        Returns:
            Dict with stats
        """
        with self.lock:
            return {
                "total_buckets": len(self.buckets),
                "rate_limit": self.rate,
                "capacity": self.capacity,
                "cleanup_interval": self.cleanup_interval,
            }


# Global rate limiter instances
_webhook_rate_limiter: RateLimiter | None = None
_global_rate_limiter: RateLimiter | None = None


def get_webhook_rate_limiter() -> RateLimiter:
    """
    Get singleton webhook rate limiter.

    Returns:
        RateLimiter instance
    """
    global _webhook_rate_limiter

    if _webhook_rate_limiter is None:
        # Per-trigger rate limit: 10 requests/second, burst of 20
        _webhook_rate_limiter = RateLimiter(rate=10, capacity=20)
        logger.info("Initialized webhook rate limiter (10 req/s, burst=20)")

    return _webhook_rate_limiter


def get_global_rate_limiter() -> RateLimiter:
    """
    Get singleton global rate limiter (by IP).

    Returns:
        RateLimiter instance
    """
    global _global_rate_limiter

    if _global_rate_limiter is None:
        # Global rate limit per IP: 100 requests/second, burst of 200
        _global_rate_limiter = RateLimiter(rate=100, capacity=200)
        logger.info("Initialized global rate limiter (100 req/s, burst=200)")

    return _global_rate_limiter
