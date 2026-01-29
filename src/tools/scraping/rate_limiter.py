"""Per-domain rate limiting for scrapers using token bucket algorithm."""

import asyncio
import time
from collections import defaultdict
from urllib.parse import urlparse

import structlog

logger = structlog.get_logger()


class TokenBucket:
    """Token bucket rate limiter for a single domain."""

    def __init__(self, rate: float = 2.0, capacity: int = 5):
        """Initialize token bucket.

        Args:
            rate: Tokens added per second
            capacity: Maximum number of tokens in the bucket
        """
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> float:
        """Acquire a token, waiting if necessary.

        Returns:
            Time waited in seconds
        """
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last_update = now

            if self.tokens >= 1:
                self.tokens -= 1
                return 0.0

            # Need to wait for a token
            wait_time = (1 - self.tokens) / self.rate
            await asyncio.sleep(wait_time)
            self.tokens = 0
            self.last_update = time.monotonic()
            return wait_time


class DomainRateLimiter:
    """Rate limiter that maintains separate buckets per domain."""

    def __init__(self, default_rate: float = 2.0, default_capacity: int = 5):
        """Initialize domain rate limiter.

        Args:
            default_rate: Default tokens per second for new domains
            default_capacity: Default bucket capacity for new domains
        """
        self.default_rate = default_rate
        self.default_capacity = default_capacity
        self._buckets: dict[str, TokenBucket] = {}
        self._domain_configs: dict[str, tuple[float, int]] = {}
        self._lock = asyncio.Lock()

    def configure_domain(self, domain: str, rate: float, capacity: int) -> None:
        """Configure rate limit for a specific domain.

        Args:
            domain: Domain to configure
            rate: Tokens per second
            capacity: Maximum bucket capacity
        """
        self._domain_configs[domain] = (rate, capacity)

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        parsed = urlparse(url)
        return parsed.netloc or url

    async def _get_bucket(self, domain: str) -> TokenBucket:
        """Get or create bucket for a domain."""
        async with self._lock:
            if domain not in self._buckets:
                config = self._domain_configs.get(
                    domain, (self.default_rate, self.default_capacity)
                )
                self._buckets[domain] = TokenBucket(rate=config[0], capacity=config[1])
            return self._buckets[domain]

    async def acquire(self, url: str) -> float:
        """Acquire permission to access a URL.

        Args:
            url: URL to access

        Returns:
            Time waited in seconds
        """
        domain = self._extract_domain(url)
        bucket = await self._get_bucket(domain)
        wait_time = await bucket.acquire()
        if wait_time > 0:
            logger.debug("Rate limited", domain=domain, wait_time=wait_time)
        return wait_time


# Global rate limiter instance
_rate_limiter: DomainRateLimiter | None = None


def get_rate_limiter() -> DomainRateLimiter:
    """Get the global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = DomainRateLimiter()
        # Configure known domains with appropriate limits
        _rate_limiter.configure_domain("www.zap.co.il", rate=2.0, capacity=5)
        _rate_limiter.configure_domain("zap.co.il", rate=2.0, capacity=5)
        # Domains with known blocking/SSL issues - use slower rates
        _rate_limiter.configure_domain("wisebuy.co.il", rate=0.5, capacity=2)
        _rate_limiter.configure_domain("www.wisebuy.co.il", rate=0.5, capacity=2)
        _rate_limiter.configure_domain("netoneto.co.il", rate=0.5, capacity=2)
        _rate_limiter.configure_domain("www.netoneto.co.il", rate=0.5, capacity=2)
        # Google - be respectful to avoid blocks
        _rate_limiter.configure_domain("google.com", rate=0.2, capacity=1)
        _rate_limiter.configure_domain("www.google.com", rate=0.2, capacity=1)
        _rate_limiter.configure_domain("www.google.co.il", rate=0.2, capacity=1)
    return _rate_limiter
