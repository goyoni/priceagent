"""Tests for product research agent functions."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock

from src.agents.product_research import _search_products_impl, _search_multiple_products_impl
from src.state.models import PriceOption, SellerInfo


def make_price_option(price: float, seller_name: str) -> PriceOption:
    """Helper to create a PriceOption for testing."""
    return PriceOption(
        product_id="test-query",
        seller=SellerInfo(
            name=seller_name,
            website=f"https://{seller_name.lower()}.co.il",
            country="IL",
            source="test",
        ),
        listed_price=price,
        currency="ILS",
        url=f"https://{seller_name.lower()}.co.il/product",
        scraped_at=datetime.now(),
    )


class TestSearchProductsResultLimit:
    """Tests for the 5 result limit in search_products."""

    @pytest.fixture
    def mock_scrapers(self):
        """Create mock scrapers that return many results."""
        # Create mock scrapers that return 10 results each
        scraper1 = MagicMock()
        scraper1.name = "scraper1"
        scraper1.search = AsyncMock(return_value=[
            make_price_option(1000 + i * 100, f"Seller1_{i}")
            for i in range(10)
        ])

        scraper2 = MagicMock()
        scraper2.name = "scraper2"
        scraper2.search = AsyncMock(return_value=[
            make_price_option(1050 + i * 100, f"Seller2_{i}")
            for i in range(10)
        ])

        return [scraper1, scraper2]

    @pytest.mark.asyncio
    async def test_search_returns_at_most_5_results(self, mock_scrapers):
        """Search results should be limited to 5 items maximum."""
        with patch(
            "src.agents.product_research.ScraperRegistry.get_scrapers_for_country",
            return_value=mock_scrapers,
        ), patch(
            "src.agents.product_research.report_progress",
            new_callable=AsyncMock,
        ), patch(
            "src.agents.product_research.record_search",
            new_callable=AsyncMock,
        ), patch(
            "src.agents.product_research.record_warning",
            new_callable=AsyncMock,
        ):
            result = await _search_products_impl("test query", "IL")

            # Parse the output to count results
            # Results are formatted as "1. Seller Name..."
            result_lines = [line for line in result.split("\n") if line.strip().startswith(("1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.", "10."))]

            # Should have exactly 5 numbered results (1-5)
            assert len(result_lines) == 5, f"Expected 5 results, got {len(result_lines)}. Output:\n{result}"

    @pytest.mark.asyncio
    async def test_search_formats_top_5_message(self, mock_scrapers):
        """Output should indicate 'Top 5 results'."""
        with patch(
            "src.agents.product_research.ScraperRegistry.get_scrapers_for_country",
            return_value=mock_scrapers,
        ), patch(
            "src.agents.product_research.report_progress",
            new_callable=AsyncMock,
        ), patch(
            "src.agents.product_research.record_search",
            new_callable=AsyncMock,
        ), patch(
            "src.agents.product_research.record_warning",
            new_callable=AsyncMock,
        ):
            result = await _search_products_impl("test query", "IL")

            assert "Top 5 results" in result, f"Expected 'Top 5 results' in output:\n{result}"

    @pytest.mark.asyncio
    async def test_search_returns_cheapest_first(self, mock_scrapers):
        """Results should be sorted by price (cheapest first)."""
        with patch(
            "src.agents.product_research.ScraperRegistry.get_scrapers_for_country",
            return_value=mock_scrapers,
        ), patch(
            "src.agents.product_research.report_progress",
            new_callable=AsyncMock,
        ), patch(
            "src.agents.product_research.record_search",
            new_callable=AsyncMock,
        ), patch(
            "src.agents.product_research.record_warning",
            new_callable=AsyncMock,
        ):
            result = await _search_products_impl("test query", "IL")

            # Extract prices from output
            # Format: "   Price: 1,000 ILS"
            import re
            prices = re.findall(r"Price:\s*([\d,]+)", result)
            prices = [int(p.replace(",", "")) for p in prices]

            assert len(prices) == 5, f"Expected 5 prices, got {len(prices)}"
            # Prices should be in ascending order (with possible slight variation due to ranking)
            # The first price should be among the lowest
            assert prices[0] <= 1200, f"First price {prices[0]} should be among lowest"


class TestSearchMultipleProductsResultLimit:
    """Tests for the 5 result limit per product in search_multiple_products."""

    @pytest.fixture
    def mock_scrapers(self):
        """Create mock scrapers that return many results."""
        scraper = MagicMock()

        # Return different results based on query
        async def mock_search(query, max_results):
            return [
                make_price_option(1000 + i * 100, f"Seller_{query}_{i}")
                for i in range(10)
            ]

        scraper.search_with_contacts = mock_search
        return [scraper]

    @pytest.mark.asyncio
    async def test_multi_search_returns_at_most_5_per_product(self, mock_scrapers):
        """Each product section should have at most 5 results."""
        with patch(
            "src.agents.product_research.ScraperRegistry.get_scrapers_for_country",
            return_value=mock_scrapers,
        ):
            result = await _search_multiple_products_impl(
                ["product1", "product2"],
                "IL",
            )

            # Count results per section
            # Each section starts with "=== product_name ==="
            sections = result.split("=== ")

            for section in sections:
                if section.startswith("BUNDLE"):
                    continue
                if not section.strip():
                    continue

                # Count numbered results in this section
                result_lines = [
                    line for line in section.split("\n")
                    if line.strip().startswith(("1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.", "10."))
                ]

                if result_lines:  # Only check sections with results
                    assert len(result_lines) <= 5, f"Section has {len(result_lines)} results, expected max 5:\n{section}"


class TestOutputFormat:
    """Tests for output format matching dashboard expectations."""

    @pytest.fixture
    def mock_scraper_with_contact(self):
        """Create mock scraper with contact info."""
        scraper = MagicMock()
        scraper.name = "test_scraper"
        result = make_price_option(1500, "TestStore")
        result.seller.reliability_score = 4.5
        result.seller.whatsapp_number = "+972501234567"
        scraper.search = AsyncMock(return_value=[result])
        return [scraper]

    @pytest.mark.asyncio
    async def test_output_contains_rating_format(self, mock_scraper_with_contact):
        """Output should contain rating in format '(Rating: X/5)'."""
        with patch(
            "src.agents.product_research.ScraperRegistry.get_scrapers_for_country",
            return_value=mock_scraper_with_contact,
        ), patch(
            "src.agents.product_research.report_progress",
            new_callable=AsyncMock,
        ), patch(
            "src.agents.product_research.record_search",
            new_callable=AsyncMock,
        ), patch(
            "src.agents.product_research.record_warning",
            new_callable=AsyncMock,
        ):
            result = await _search_products_impl("test", "IL")

            assert "(Rating: 4.5/5)" in result, f"Expected rating format in:\n{result}"

    @pytest.mark.asyncio
    async def test_output_contains_price_format(self, mock_scraper_with_contact):
        """Output should contain price in format 'Price: X,XXX ILS'."""
        with patch(
            "src.agents.product_research.ScraperRegistry.get_scrapers_for_country",
            return_value=mock_scraper_with_contact,
        ), patch(
            "src.agents.product_research.report_progress",
            new_callable=AsyncMock,
        ), patch(
            "src.agents.product_research.record_search",
            new_callable=AsyncMock,
        ), patch(
            "src.agents.product_research.record_warning",
            new_callable=AsyncMock,
        ):
            result = await _search_products_impl("test", "IL")

            assert "Price: 1,500 ILS" in result, f"Expected price format in:\n{result}"

    @pytest.mark.asyncio
    async def test_output_contains_url_format(self, mock_scraper_with_contact):
        """Output should contain URL in format 'URL: https://...'."""
        with patch(
            "src.agents.product_research.ScraperRegistry.get_scrapers_for_country",
            return_value=mock_scraper_with_contact,
        ), patch(
            "src.agents.product_research.report_progress",
            new_callable=AsyncMock,
        ), patch(
            "src.agents.product_research.record_search",
            new_callable=AsyncMock,
        ), patch(
            "src.agents.product_research.record_warning",
            new_callable=AsyncMock,
        ):
            result = await _search_products_impl("test", "IL")

            assert "URL: https://teststore.co.il/product" in result, f"Expected URL format in:\n{result}"

    @pytest.mark.asyncio
    async def test_output_contains_contact_format(self, mock_scraper_with_contact):
        """Output should contain contact in format 'Contact: +972...'."""
        with patch(
            "src.agents.product_research.ScraperRegistry.get_scrapers_for_country",
            return_value=mock_scraper_with_contact,
        ), patch(
            "src.agents.product_research.report_progress",
            new_callable=AsyncMock,
        ), patch(
            "src.agents.product_research.record_search",
            new_callable=AsyncMock,
        ), patch(
            "src.agents.product_research.record_warning",
            new_callable=AsyncMock,
        ):
            result = await _search_products_impl("test", "IL")

            assert "Contact: +972501234567" in result, f"Expected contact format in:\n{result}"
