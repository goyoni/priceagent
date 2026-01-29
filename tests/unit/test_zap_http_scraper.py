"""Tests for ZAP HTTP scraper."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import httpx

from src.tools.scraping.israel.zap_http_scraper import ZapHttpScraper


class TestZapHttpScraper:
    """Tests for ZapHttpScraper class."""

    @pytest.fixture
    def scraper(self):
        """Create a ZapHttpScraper instance."""
        return ZapHttpScraper()

    def test_initialization(self, scraper):
        """Test that scraper initializes correctly."""
        assert scraper.name == "zap_http"
        assert "zap.co.il" in scraper.base_url

    @pytest.mark.asyncio
    async def test_search_uses_valid_headers(self, scraper):
        """Test that search() can be called without NameError.

        This test verifies that BROWSER_HEADERS is properly defined/imported
        in the ZAP scraper module. A NameError here would indicate a missing
        import that would cause the scraper to fail silently.
        """
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.text = "<html><body>No products</body></html>"
        mock_response.url = "https://www.zap.co.il/search.aspx?keyword=test"

        with patch("httpx.AsyncClient") as mock_async_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.get.return_value = mock_response
            mock_async_client.return_value.__aenter__.return_value = mock_client_instance

            # This should NOT raise NameError for BROWSER_HEADERS
            results = await scraper.search("test query")

            # Verify client was created (meaning BROWSER_HEADERS was valid)
            mock_async_client.assert_called_once()
            assert results == []  # No products in mock response

    @pytest.mark.asyncio
    async def test_search_passes_browser_headers(self, scraper):
        """Test that search passes appropriate browser headers to httpx."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.text = "<html><body>No products</body></html>"
        mock_response.url = "https://www.zap.co.il/search.aspx?keyword=test"

        with patch("httpx.AsyncClient") as mock_async_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.get.return_value = mock_response
            mock_async_client.return_value.__aenter__.return_value = mock_client_instance

            await scraper.search("test query")

            # Check that headers were passed to AsyncClient
            call_kwargs = mock_async_client.call_args[1]
            assert "headers" in call_kwargs
            headers = call_kwargs["headers"]

            # Verify essential browser headers are present
            assert "User-Agent" in headers
            assert "Mozilla" in headers["User-Agent"]
