"""Tests for RobustHttpClient."""

import pytest
import httpx
from unittest.mock import patch, AsyncMock, MagicMock

from src.tools.scraping.http_client import (
    RobustHttpClient,
    SSL_BYPASS_DOMAINS,
    BROWSER_HEADERS,
    get_http_client,
    reset_http_client,
)


class TestSSLBypassDomains:
    """Tests for SSL bypass domain configuration."""

    def test_wisebuy_in_bypass_list(self):
        """wisebuy.co.il should bypass SSL verification."""
        assert "wisebuy.co.il" in SSL_BYPASS_DOMAINS
        assert "www.wisebuy.co.il" in SSL_BYPASS_DOMAINS


class TestBrowserHeaders:
    """Tests for browser headers configuration.

    Headers are kept simple to avoid triggering anti-bot systems.
    Some sites block requests with Sec-* headers as they indicate automation.
    """

    def test_user_agent_present(self):
        """User-Agent header should be set."""
        assert "User-Agent" in BROWSER_HEADERS
        assert "Mozilla" in BROWSER_HEADERS["User-Agent"]

    def test_accept_headers_present(self):
        """Accept headers should be configured."""
        assert "Accept" in BROWSER_HEADERS
        assert "Accept-Language" in BROWSER_HEADERS

    def test_simplified_headers_no_sec_fetch(self):
        """Sec-Fetch-* headers should NOT be present.

        These headers can trigger anti-bot detection on some Israeli
        e-commerce sites. The simplified header set works better.
        """
        assert "Sec-Fetch-Dest" not in BROWSER_HEADERS
        assert "Sec-Fetch-Mode" not in BROWSER_HEADERS
        assert "Sec-Fetch-Site" not in BROWSER_HEADERS

    def test_simplified_headers_no_sec_ch_ua(self):
        """Sec-CH-UA headers should NOT be present.

        These client hints can trigger anti-bot detection.
        """
        assert "Sec-CH-UA" not in BROWSER_HEADERS
        assert "Sec-CH-UA-Mobile" not in BROWSER_HEADERS

    def test_essential_headers_only(self):
        """Only essential headers should be present."""
        # These are the only headers that should be in the simplified set
        essential = {"User-Agent", "Accept", "Accept-Language", "Accept-Encoding", "Connection"}
        assert set(BROWSER_HEADERS.keys()) == essential


class TestRobustHttpClient:
    """Tests for RobustHttpClient class."""

    @pytest.fixture(autouse=True)
    def reset_client(self):
        """Reset the global client before and after each test."""
        reset_http_client()
        yield
        reset_http_client()

    @pytest.fixture
    def mock_rate_limiter(self):
        """Mock the rate limiter to not actually wait."""
        with patch("src.tools.scraping.http_client.get_rate_limiter") as mock:
            limiter = MagicMock()
            limiter.acquire = AsyncMock(return_value=0.0)
            mock.return_value = limiter
            yield limiter

    def test_init_defaults(self, mock_rate_limiter):
        """Test default initialization values."""
        client = RobustHttpClient()
        assert client.timeout == 15.0
        assert client.max_retries == 3
        assert client.retry_delay == 1.0

    def test_init_custom_values(self, mock_rate_limiter):
        """Test custom initialization values."""
        client = RobustHttpClient(timeout=30.0, max_retries=5, retry_delay=2.0)
        assert client.timeout == 30.0
        assert client.max_retries == 5
        assert client.retry_delay == 2.0

    @pytest.mark.asyncio
    async def test_get_success(self, mock_rate_limiter):
        """Test successful GET request."""
        client = RobustHttpClient(retry_delay=0.01)

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.text = "Success"

        with patch("httpx.AsyncClient") as mock_async_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.get.return_value = mock_response
            mock_async_client.return_value.__aenter__.return_value = mock_client_instance

            result = await client.get("https://example.com")

            assert result is not None
            assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_get_returns_none_on_404(self, mock_rate_limiter):
        """Test that 404 returns None."""
        client = RobustHttpClient(retry_delay=0.01)

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 404

        with patch("httpx.AsyncClient") as mock_async_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.get.return_value = mock_response
            mock_async_client.return_value.__aenter__.return_value = mock_client_instance

            result = await client.get("https://example.com/missing")

            assert result is None

    @pytest.mark.asyncio
    async def test_get_retries_on_500(self, mock_rate_limiter):
        """Test that 500 errors trigger retry."""
        client = RobustHttpClient(max_retries=3, retry_delay=0.01)

        mock_response_500 = MagicMock(spec=httpx.Response)
        mock_response_500.status_code = 500

        mock_response_200 = MagicMock(spec=httpx.Response)
        mock_response_200.status_code = 200
        mock_response_200.text = "Success"

        with patch("httpx.AsyncClient") as mock_async_client:
            mock_client_instance = AsyncMock()
            # First two calls return 500, third returns 200
            mock_client_instance.get.side_effect = [
                mock_response_500,
                mock_response_500,
                mock_response_200,
            ]
            mock_async_client.return_value.__aenter__.return_value = mock_client_instance

            result = await client.get("https://example.com")

            assert result is not None
            assert result.status_code == 200
            assert mock_client_instance.get.call_count == 3

    @pytest.mark.asyncio
    async def test_get_returns_none_on_connection_error(self, mock_rate_limiter):
        """Test that connection errors return None without retrying."""
        client = RobustHttpClient(retry_delay=0.01)

        with patch("httpx.AsyncClient") as mock_async_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.get.side_effect = httpx.ConnectError("DNS lookup failed")
            mock_async_client.return_value.__aenter__.return_value = mock_client_instance

            result = await client.get("https://example.com")

            assert result is None
            # Should not retry on connection errors
            assert mock_client_instance.get.call_count == 1

    @pytest.mark.asyncio
    async def test_get_retries_on_timeout(self, mock_rate_limiter):
        """Test that timeouts trigger retry."""
        client = RobustHttpClient(max_retries=3, retry_delay=0.01)

        mock_response_200 = MagicMock(spec=httpx.Response)
        mock_response_200.status_code = 200
        mock_response_200.text = "Success"

        with patch("httpx.AsyncClient") as mock_async_client:
            mock_client_instance = AsyncMock()
            # First two calls timeout, third succeeds
            mock_client_instance.get.side_effect = [
                httpx.TimeoutException("timeout"),
                httpx.TimeoutException("timeout"),
                mock_response_200,
            ]
            mock_async_client.return_value.__aenter__.return_value = mock_client_instance

            result = await client.get("https://example.com")

            assert result is not None
            assert result.status_code == 200
            assert mock_client_instance.get.call_count == 3

    @pytest.mark.asyncio
    async def test_get_returns_none_on_403_after_retries(self, mock_rate_limiter):
        """Test that 403 returns None after retrying."""
        client = RobustHttpClient(max_retries=3, retry_delay=0.01)

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 403

        with patch("httpx.AsyncClient") as mock_async_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.get.return_value = mock_response
            mock_async_client.return_value.__aenter__.return_value = mock_client_instance

            result = await client.get("https://example.com/forbidden")

            assert result is None
            # Should have retried max_retries times
            assert mock_client_instance.get.call_count == 3

    @pytest.mark.asyncio
    async def test_rate_limiter_called(self, mock_rate_limiter):
        """Test that rate limiter is invoked before request."""
        client = RobustHttpClient(retry_delay=0.01)

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_async_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.get.return_value = mock_response
            mock_async_client.return_value.__aenter__.return_value = mock_client_instance

            await client.get("https://example.com")

            mock_rate_limiter.acquire.assert_called_once_with("https://example.com")

    @pytest.mark.asyncio
    async def test_headers_merged(self, mock_rate_limiter):
        """Test that custom headers are merged with browser headers."""
        client = RobustHttpClient(retry_delay=0.01)

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_async_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.get.return_value = mock_response
            mock_async_client.return_value.__aenter__.return_value = mock_client_instance

            await client.get(
                "https://example.com", headers={"X-Custom": "value"}
            )

            call_kwargs = mock_client_instance.get.call_args[1]
            assert "X-Custom" in call_kwargs["headers"]
            assert "User-Agent" in call_kwargs["headers"]


class TestGetHttpClient:
    """Tests for the global client getter."""

    @pytest.fixture(autouse=True)
    def reset_client(self):
        """Reset the global client before and after each test."""
        reset_http_client()
        yield
        reset_http_client()

    def test_returns_same_instance(self):
        """get_http_client should return the same instance."""
        with patch("src.tools.scraping.http_client.get_rate_limiter"):
            client1 = get_http_client()
            client2 = get_http_client()
            assert client1 is client2

    def test_reset_creates_new_instance(self):
        """reset_http_client should allow creating a new instance."""
        with patch("src.tools.scraping.http_client.get_rate_limiter"):
            client1 = get_http_client()
            reset_http_client()
            client2 = get_http_client()
            assert client1 is not client2
