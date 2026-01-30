"""Tests for ALM scraper."""

import pytest

from src.tools.scraping.israel.alm_scraper import AlmScraper, get_alm_price, is_alm_url


class TestIsAlmUrl:
    """Tests for is_alm_url helper."""

    def test_alm_domain_detected(self):
        """ALM URLs should be detected."""
        assert is_alm_url("https://www.alm.co.il/114600021.html") is True
        assert is_alm_url("https://alm.co.il/product") is True
        assert is_alm_url("http://www.alm.co.il/something") is True

    def test_non_alm_domain_not_detected(self):
        """Non-ALM URLs should not be detected."""
        assert is_alm_url("https://www.zap.co.il/product") is False
        assert is_alm_url("https://www.bug.co.il/product") is False
        assert is_alm_url("https://www.ksp.co.il/product") is False

    def test_case_insensitive(self):
        """Detection should be case insensitive."""
        assert is_alm_url("https://www.ALM.co.il/product") is True
        assert is_alm_url("https://WWW.ALM.CO.IL/product") is True


class TestAlmScraper:
    """Tests for AlmScraper class."""

    @pytest.fixture
    def scraper(self):
        """Create an AlmScraper instance."""
        return AlmScraper()

    def test_scraper_config(self, scraper):
        """Scraper should have correct config."""
        assert scraper.config.name == "alm"
        assert "alm.co.il" in scraper.config.base_url

    @pytest.mark.asyncio
    async def test_get_seller_details(self, scraper):
        """Should return ALM seller info."""
        seller = await scraper.get_seller_details("https://www.alm.co.il/product")
        assert seller is not None
        assert seller.id == "alm"
        assert "alm" in seller.name.lower() or "א.ל.מ" in seller.name

    @pytest.mark.asyncio
    async def test_extract_contact_info(self, scraper):
        """Should return ALM WhatsApp number."""
        contact = await scraper.extract_contact_info("https://www.alm.co.il/product")
        assert contact is not None
        assert contact.startswith("+972")


class TestGetAlmPrice:
    """Tests for get_alm_price helper."""

    @pytest.mark.asyncio
    async def test_get_price_for_valid_sku(self):
        """Should get correct price for valid product."""
        # This is a real product - 114600021 is a Bosch microwave
        price = await get_alm_price("https://www.alm.co.il/114600021.html")
        # Price should be around 2090 (may vary over time)
        assert price is not None
        assert price > 1000  # Definitely not 175
        assert price < 5000  # Reasonable upper bound for a microwave

    @pytest.mark.asyncio
    async def test_get_price_for_invalid_sku(self):
        """Should return None for invalid product."""
        price = await get_alm_price("https://www.alm.co.il/nonexistent999999.html")
        assert price is None

    @pytest.mark.asyncio
    async def test_get_price_for_non_alm_url(self):
        """Should return None for non-ALM URLs."""
        # get_alm_price doesn't check if URL is ALM, it just tries to extract SKU
        # For a completely invalid URL, it should fail gracefully
        price = await get_alm_price("not-a-valid-url")
        assert price is None
