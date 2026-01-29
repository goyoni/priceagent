"""Robust HTTP client with rate limiting, retries, and error handling."""

import asyncio
from typing import Optional
from urllib.parse import urlparse

import httpx
import structlog

from src.tools.scraping.rate_limiter import get_rate_limiter

logger = structlog.get_logger()

# Simpler headers that work better with most sites
# The Sec-* headers often trigger anti-bot protection
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "he,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

# Domains with known SSL issues - use verify=False
SSL_BYPASS_DOMAINS = {"wisebuy.co.il", "www.wisebuy.co.il"}


class RobustHttpClient:
    """HTTP client with rate limiting, retries, and graceful error handling."""

    def __init__(
        self,
        timeout: float = 15.0,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        """Initialize the HTTP client.

        Args:
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
            retry_delay: Base delay between retries (exponential backoff)
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._rate_limiter = get_rate_limiter()

    async def get(
        self,
        url: str,
        headers: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> Optional[httpx.Response]:
        """Fetch URL with rate limiting and retries.

        Returns None on failure instead of raising exceptions.
        This allows calling code to gracefully handle failures.

        Args:
            url: URL to fetch
            headers: Optional additional headers
            params: Optional query parameters

        Returns:
            httpx.Response on success, None on failure
        """
        domain = urlparse(url).netloc

        # Apply rate limiting
        await self._rate_limiter.acquire(url)

        # Determine SSL verification
        verify_ssl = domain not in SSL_BYPASS_DOMAINS

        merged_headers = {**BROWSER_HEADERS, **(headers or {})}

        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(
                    timeout=self.timeout,
                    follow_redirects=True,
                    verify=verify_ssl,
                ) as client:
                    response = await client.get(
                        url, headers=merged_headers, params=params
                    )

                    # Handle rate limiting (429)
                    if response.status_code == 429:
                        retry_after = int(response.headers.get("Retry-After", 60))
                        logger.warning(
                            "Rate limited by server",
                            url=url,
                            retry_after=retry_after,
                            attempt=attempt + 1,
                        )
                        await asyncio.sleep(min(retry_after, 30))
                        continue

                    # Handle 403 with retry
                    if response.status_code == 403:
                        logger.warning(
                            "Forbidden response",
                            url=url,
                            attempt=attempt + 1,
                        )
                        if attempt < self.max_retries - 1:
                            await asyncio.sleep(self.retry_delay * (attempt + 1))
                            continue
                        return None

                    # Handle other client errors (4xx)
                    if 400 <= response.status_code < 500:
                        logger.warning(
                            "Client error",
                            url=url,
                            status=response.status_code,
                        )
                        return None

                    # Handle server errors (5xx) with retry
                    if response.status_code >= 500:
                        logger.warning(
                            "Server error",
                            url=url,
                            status=response.status_code,
                            attempt=attempt + 1,
                        )
                        if attempt < self.max_retries - 1:
                            await asyncio.sleep(self.retry_delay * (attempt + 1))
                            continue
                        return None

                    return response

            except httpx.TimeoutException:
                logger.warning(
                    "Request timeout",
                    url=url,
                    attempt=attempt + 1,
                )
            except httpx.ConnectError as e:
                # DNS errors, connection refused, etc. - don't retry
                logger.warning(
                    "Connection error",
                    url=url,
                    error=str(e),
                )
                return None
            except Exception as e:
                logger.warning(
                    "Unexpected HTTP error",
                    url=url,
                    error=str(e),
                    attempt=attempt + 1,
                )

            if attempt < self.max_retries - 1:
                await asyncio.sleep(self.retry_delay * (attempt + 1))

        logger.warning("All retry attempts exhausted", url=url)
        return None


# Global instance for reuse
_http_client: Optional[RobustHttpClient] = None


def get_http_client() -> RobustHttpClient:
    """Get or create the global HTTP client instance."""
    global _http_client
    if _http_client is None:
        _http_client = RobustHttpClient()
    return _http_client


def reset_http_client() -> None:
    """Reset the global HTTP client (useful for testing)."""
    global _http_client
    _http_client = None
