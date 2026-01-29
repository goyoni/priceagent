"""Tests for Google Search scraper price extraction."""

import pytest
from src.tools.scraping.google.google_search_scraper import GoogleSearchScraper


class TestExtractPriceFromText:
    """Tests for _extract_price_from_text method.

    This method extracts prices from SerpAPI snippet text.
    It should correctly identify Israeli Shekel prices and reject false positives.
    """

    @pytest.fixture
    def scraper(self):
        """Create a GoogleSearchScraper instance."""
        return GoogleSearchScraper()

    # Valid price extraction tests
    def test_extracts_price_with_shekel_prefix(self, scraper):
        """Should extract price with ₪ prefix."""
        text = "מחיר מבצע: ₪1,499"
        result = scraper._extract_price_from_text(text)
        assert result == 1499.0

    def test_extracts_price_with_shekel_suffix(self, scraper):
        """Should extract price with ₪ suffix."""
        text = "המחיר הטוב ביותר: 2,500₪"
        result = scraper._extract_price_from_text(text)
        assert result == 2500.0

    def test_extracts_price_with_hebrew_currency(self, scraper):
        """Should extract price with ש\"ח suffix."""
        text = 'סה"כ לתשלום: 3,200 ש"ח'
        result = scraper._extract_price_from_text(text)
        assert result == 3200.0

    def test_extracts_price_with_ils_prefix(self, scraper):
        """Should extract price with ILS prefix."""
        text = "Price: ILS 4,500.00"
        result = scraper._extract_price_from_text(text)
        assert result == 4500.0

    def test_extracts_price_with_decimal(self, scraper):
        """Should extract price with decimal places."""
        text = "₪1,234.99 בלבד!"
        result = scraper._extract_price_from_text(text)
        assert result == 1234.99

    # False positive rejection tests - THESE ARE THE KEY TESTS
    def test_rejects_year_as_price(self, scraper):
        """Should NOT extract year numbers as prices.

        This is a common false positive - years like 2023, 2024 are not prices.
        """
        text = "iPhone 15 Pro Max 256GB - דגם 2024 חדש"
        result = scraper._extract_price_from_text(text)
        assert result is None, "Year 2024 should not be extracted as price"

    def test_rejects_model_number_as_price(self, scraper):
        """Should NOT extract model numbers as prices.

        Model numbers like A2234, GT5000 should not be matched.
        """
        text = "Samsung Galaxy S24 Ultra 512GB model SM-S928B"
        result = scraper._extract_price_from_text(text)
        assert result is None, "Model number should not be extracted as price"

    def test_rejects_storage_size_as_price(self, scraper):
        """Should NOT extract storage sizes as prices.

        Numbers like 256GB, 512GB should not be matched.
        """
        text = "MacBook Pro M3 with 512GB SSD storage"
        result = scraper._extract_price_from_text(text)
        assert result is None, "Storage size 512 should not be extracted as price"

    def test_rejects_phone_number_as_price(self, scraper):
        """Should NOT extract phone numbers as prices."""
        text = "צור קשר: 050-1234567 לפרטים נוספים"
        result = scraper._extract_price_from_text(text)
        assert result is None, "Phone number should not be extracted as price"

    def test_rejects_order_number_as_price(self, scraper):
        """Should NOT extract order/product codes as prices."""
        text = "מק\"ט: 123456 - מוצר מעולה"
        result = scraper._extract_price_from_text(text)
        assert result is None, "Product code should not be extracted as price"

    def test_extracts_real_price_ignoring_year(self, scraper):
        """Should extract the real price even when year is present."""
        text = "iPhone 15 Pro Max 2024 - ₪5,499 במלאי"
        result = scraper._extract_price_from_text(text)
        assert result == 5499.0, "Should extract ₪5,499 and ignore 2024"

    def test_extracts_real_price_ignoring_storage(self, scraper):
        """Should extract the real price even when storage size is present."""
        text = "Samsung 256GB - מחיר: ₪3,200"
        result = scraper._extract_price_from_text(text)
        assert result == 3200.0, "Should extract ₪3,200 and ignore 256"

    # Edge cases
    def test_returns_none_for_empty_text(self, scraper):
        """Should return None for empty text."""
        result = scraper._extract_price_from_text("")
        assert result is None

    def test_returns_none_for_none_input(self, scraper):
        """Should return None for None input."""
        result = scraper._extract_price_from_text(None)
        assert result is None

    def test_returns_none_for_text_without_price(self, scraper):
        """Should return None when no price is present."""
        text = "מוצר מצוין עם משלוח חינם"
        result = scraper._extract_price_from_text(text)
        assert result is None

    def test_rejects_price_below_minimum(self, scraper):
        """Should reject prices below reasonable minimum."""
        text = "₪0.50 per unit"
        result = scraper._extract_price_from_text(text)
        assert result is None, "Price below 1 ILS should be rejected"

    def test_rejects_price_above_maximum(self, scraper):
        """Should reject prices above reasonable maximum."""
        text = "₪2,000,000"
        result = scraper._extract_price_from_text(text)
        assert result is None, "Price above 1M ILS should be rejected"

    def test_extracts_larger_price_over_cashback(self, scraper):
        """Should extract the main product price, not small cashback amounts.

        Real-world case: citydeal.co.il showing "קבלו ₪7 בחזרה" (Get ₪7 back)
        before the actual price "₪9,890".
        Should extract 9890, not 7.
        """
        text = "Samsung מקרר 4 דלתות - קבלו ₪7 בחזרה! מחיר: ₪9,890 יבואן רשמי"
        result = scraper._extract_price_from_text(text)
        assert result == 9890.0, f"Should extract main price 9890, not cashback 7. Got {result}"

    def test_extracts_larger_price_over_small_discount(self, scraper):
        """Should extract the main product price, not small discount amounts."""
        text = "מקרר Samsung 678 ליטר - חסכו ₪50! עכשיו רק ₪12,500"
        result = scraper._extract_price_from_text(text)
        assert result == 12500.0, f"Should extract main price 12500, not discount 50. Got {result}"

    def test_extracts_product_price_over_shipping_threshold(self, scraper):
        """Should extract product price, not free shipping threshold."""
        text = "משלוח חינם בקניה מעל ₪200! טלוויזיה Samsung 55 אינץ׳ - ₪3,499"
        result = scraper._extract_price_from_text(text)
        assert result == 3499.0, f"Should extract product price 3499, not shipping threshold 200. Got {result}"

    def test_ignores_very_small_shekel_amounts(self, scraper):
        """Small amounts under 50 ILS are likely not product prices."""
        text = "₪7 בונוס | Samsung RF72DG9620B1 מקרר - 9,890 ש\"ח"
        result = scraper._extract_price_from_text(text)
        assert result == 9890.0, f"Should extract product price 9890, not bonus 7. Got {result}"
