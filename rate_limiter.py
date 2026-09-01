import asyncio
import time
import logging

logger = logging.getLogger(__name__)

class TokenBucketRateLimiter:
    """Async token bucket rate limiter enforcing AIVerse API limit of 3 req/sec."""

    def __init__(self, rate: float = 3.0, capacity: float = 3.0):
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self):
        """Wait until a token is available to make an API request."""
        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self.last_update
                self.last_update = now
                self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)

                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return
                else:
                    wait_time = (1.0 - self.tokens) / self.rate
                    await asyncio.sleep(wait_time)

api_rate_limiter = TokenBucketRateLimiter(rate=3.0, capacity=3.0)
