"""Tests for PriceExtractor."""

import pytest

from src.tools.scraping.price_extractor import (
    PriceExtractor,
    PriceResult,
    get_price_extractor,
)


class TestPriceResult:
    """Tests for PriceResult NamedTuple."""

    def test_creation(self):
        """Test creating a PriceResult."""
        result = PriceResult(price=1234.00, confidence=0.95, source="json_ld")
        assert result.price == 1234.00
        assert result.confidence == 0.95
        assert result.source == "json_ld"


class TestPriceExtractor:
    """Tests for PriceExtractor class."""

    @pytest.fixture
    def extractor(self):
        """Create a fresh extractor for each test."""
        return PriceExtractor()

    # JSON-LD extraction tests
    def test_extract_from_json_ld_with_offers(self, extractor):
        """Extract price from JSON-LD with offers structure."""
        html = """
        <html>
        <head>
            <script type="application/ld+json">
            {
                "@type": "Product",
                "name": "Test Product",
                "offers": {
                    "@type": "Offer",
                    "price": "1234.00",
                    "priceCurrency": "ILS"
                }
            }
            </script>
        </head>
        <body></body>
        </html>
        """
        result = extractor.extract(html)
        assert result is not None
        assert result.price == 1234.00
        assert result.confidence >= 0.9
        assert result.source == "json_ld"

    def test_extract_from_json_ld_with_low_price(self, extractor):
        """Extract lowPrice from JSON-LD offers."""
        html = """
        <script type="application/ld+json">
        {
            "@type": "Product",
            "offers": {
                "lowPrice": "999.99",
                "highPrice": "1999.99"
            }
        }
        </script>
        """
        result = extractor.extract(html)
        assert result is not None
        assert result.price == 999.99
        assert result.source == "json_ld"

    def test_extract_from_json_ld_with_offers_array(self, extractor):
        """Extract price from JSON-LD with offers as array."""
        html = """
        <script type="application/ld+json">
        {
            "@type": "Product",
            "offers": [
                {"price": "500"},
                {"price": "600"}
            ]
        }
        </script>
        """
        result = extractor.extract(html)
        assert result is not None
        assert result.price == 500.0

    def test_extract_from_json_ld_nested(self, extractor):
        """Extract price from nested JSON-LD structure."""
        html = """
        <script type="application/ld+json">
        {
            "@graph": [
                {
                    "@type": "Product",
                    "offers": {"price": "2500"}
                }
            ]
        }
        </script>
        """
        result = extractor.extract(html)
        assert result is not None
        assert result.price == 2500.0

    # Microdata extraction tests
    def test_extract_from_microdata_content_attr(self, extractor):
        """Extract price from microdata with content attribute."""
        html = """
        <html>
        <body>
            <span itemprop="price" content="5678">5,678 ILS</span>
        </body>
        </html>
        """
        result = extractor.extract(html)
        assert result is not None
        assert result.price == 5678.0
        assert result.source == "microdata"

    def test_extract_from_microdata_text(self, extractor):
        """Extract price from microdata text when no content attr."""
        html = """
        <div itemprop="price">₪3,456</div>
        """
        result = extractor.extract(html)
        assert result is not None
        assert result.price == 3456.0

    # Meta tags extraction tests
    def test_extract_from_og_price_meta(self, extractor):
        """Extract price from OpenGraph meta tag."""
        html = """
        <html>
        <head>
            <meta property="og:price:amount" content="7890">
        </head>
        </html>
        """
        result = extractor.extract(html)
        assert result is not None
        assert result.price == 7890.0
        assert result.source == "meta_tags"

    def test_extract_from_product_price_meta(self, extractor):
        """Extract price from product:price:amount meta tag."""
        html = """
        <meta property="product:price:amount" content="1599">
        """
        result = extractor.extract(html)
        assert result is not None
        assert result.price == 1599.0

    # Price elements extraction tests
    def test_extract_from_price_class(self, extractor):
        """Extract price from element with price class."""
        html = """
        <div class="product-price">₪4,999</div>
        """
        result = extractor.extract(html)
        assert result is not None
        assert result.price == 4999.0
        assert result.source == "price_elements"

    def test_extract_from_data_price_attr(self, extractor):
        """Extract price from data-price attribute."""
        html = """
        <span class="price" data-price="2999.99">Price: ₪2,999.99</span>
        """
        result = extractor.extract(html)
        assert result is not None
        assert result.price == 2999.99

    def test_extract_from_price_current_class(self, extractor):
        """Extract price from combined price+current classes."""
        html = """
        <span class="price-current final">₪1,850</span>
        """
        result = extractor.extract(html)
        assert result is not None
        assert result.price == 1850.0

    # Regex fallback tests
    def test_extract_from_regex_shekel_prefix(self, extractor):
        """Extract price with shekel symbol prefix."""
        html = """
        <p>מחיר: ₪2,500</p>
        """
        result = extractor.extract(html)
        assert result is not None
        assert result.price == 2500.0

    def test_extract_from_regex_shekel_suffix(self, extractor):
        """Extract price with shekel symbol suffix."""
        html = """
        <p>Total: 3,200₪</p>
        """
        result = extractor.extract(html)
        assert result is not None
        assert result.price == 3200.0

    def test_extract_from_regex_hebrew_currency(self, extractor):
        """Extract price with Hebrew currency notation (ש"ח)."""
        html = """
        <p>המחיר הסופי: 1,599 ש"ח</p>
        """
        result = extractor.extract(html)
        assert result is not None
        assert result.price == 1599.0

    def test_extract_from_regex_ils_prefix(self, extractor):
        """Extract price with ILS prefix."""
        html = """
        <span>ILS 4,200.50</span>
        """
        result = extractor.extract(html)
        assert result is not None
        assert result.price == 4200.50

    # Price validation tests
    def test_invalid_price_too_low_rejected(self, extractor):
        """Prices below 1 ILS should be rejected."""
        html = """
        <span class="price">₪0.50</span>
        """
        result = extractor.extract(html)
        assert result is None

    def test_invalid_price_too_high_rejected(self, extractor):
        """Prices above 500,000 ILS should be rejected."""
        html = """
        <span class="price">₪1,000,000</span>
        """
        result = extractor.extract(html)
        assert result is None

    def test_valid_price_at_boundary(self, extractor):
        """Prices at boundaries should be accepted."""
        # min_price is 50 ILS by default, max is 500,000
        html_low = '<span class="price">₪50</span>'
        html_high = '<span class="price">₪500,000</span>'

        result_low = extractor.extract(html_low)
        result_high = extractor.extract(html_high)

        assert result_low is not None
        assert result_low.price == 50.0

        assert result_high is not None
        assert result_high.price == 500000.0

    # Edge cases
    def test_no_price_found_returns_none(self, extractor):
        """Return None when no price is found."""
        html = """
        <html>
        <body>
            <h1>Product Title</h1>
            <p>This product is amazing!</p>
        </body>
        </html>
        """
        result = extractor.extract(html)
        assert result is None

    def test_empty_html_returns_none(self, extractor):
        """Return None for empty HTML."""
        result = extractor.extract("")
        assert result is None

    def test_malformed_json_ld_fallback(self, extractor):
        """Fall back to other strategies if JSON-LD is malformed."""
        html = """
        <script type="application/ld+json">
        { invalid json here }
        </script>
        <span class="price">₪999</span>
        """
        result = extractor.extract(html)
        assert result is not None
        assert result.price == 999.0
        # Should fall back to price_elements or regex
        assert result.source != "json_ld"

    def test_price_with_decimals(self, extractor):
        """Extract price with decimal values."""
        html = """
        <script type="application/ld+json">
        {"offers": {"price": "1234.99"}}
        </script>
        """
        result = extractor.extract(html)
        assert result is not None
        assert result.price == 1234.99

    def test_price_with_thousands_separator(self, extractor):
        """Extract price with comma thousands separator."""
        html = """
        <div class="price">₪12,345</div>
        """
        result = extractor.extract(html)
        assert result is not None
        assert result.price == 12345.0

    def test_confidence_ordering(self, extractor):
        """Test that JSON-LD has higher confidence than regex."""
        html_json_ld = """
        <script type="application/ld+json">
        {"offers": {"price": "1000"}}
        </script>
        """
        html_regex = """
        <p>מחיר: ₪1000</p>
        """

        result_json_ld = extractor.extract(html_json_ld)
        result_regex = extractor.extract(html_regex)

        assert result_json_ld.confidence > result_regex.confidence


class TestGetPriceExtractor:
    """Tests for the global extractor getter."""

    def test_returns_same_instance(self):
        """get_price_extractor should return the same instance."""
        extractor1 = get_price_extractor()
        extractor2 = get_price_extractor()
        assert extractor1 is extractor2

    def test_returns_price_extractor_instance(self):
        """get_price_extractor should return a PriceExtractor."""
        extractor = get_price_extractor()
        assert isinstance(extractor, PriceExtractor)


class TestInstallmentPriceFiltering:
    """Tests for filtering installment/payment plan prices.

    Installment prices like "36 payments of ₪100" should NOT be extracted
    as the product price. The extractor should look for the total price instead.
    """

    @pytest.fixture
    def extractor(self):
        return PriceExtractor()

    def test_filters_hebrew_installment_price(self, extractor):
        """Should NOT extract installment price from Hebrew text."""
        html = """
        <div class="price-section">
            <span class="installment">36 תשלומים של ₪100</span>
            <span class="total-price" itemprop="price" content="3600">₪3,600</span>
        </div>
        """
        result = extractor.extract(html)
        assert result is not None
        assert result.price == 3600.0, f"Should extract total price 3600, not installment 100. Got {result.price}"

    def test_filters_english_installment_price(self, extractor):
        """Should NOT extract installment price from English text."""
        html = """
        <div class="price-box">
            <p>Or 12 payments of ₪250</p>
            <span class="price" data-price="3000">₪3,000</span>
        </div>
        """
        result = extractor.extract(html)
        assert result is not None
        assert result.price == 3000.0, f"Should extract total price 3000, not installment 250. Got {result.price}"

    def test_filters_monthly_payment_price(self, extractor):
        """Should NOT extract monthly payment as main price."""
        html = """
        <div class="product-price">
            <div class="monthly">החל מ-₪83 לחודש</div>
            <div class="full-price" itemprop="price" content="999">מחיר מלא: ₪999</div>
        </div>
        """
        result = extractor.extract(html)
        assert result is not None
        assert result.price == 999.0, f"Should extract full price 999, not monthly 83. Got {result.price}"


class TestOldPriceFiltering:
    """Tests for filtering crossed-out/old prices.

    When a product shows both old and new price, should extract the current price.
    """

    @pytest.fixture
    def extractor(self):
        return PriceExtractor()

    def test_extracts_current_price_not_old(self, extractor):
        """Should extract current price, not crossed-out old price."""
        html = """
        <div class="price-container">
            <span class="old-price" style="text-decoration: line-through">₪2,000</span>
            <span class="current-price" itemprop="price" content="1500">₪1,500</span>
        </div>
        """
        result = extractor.extract(html)
        assert result is not None
        assert result.price == 1500.0, f"Should extract current price 1500, not old 2000. Got {result.price}"

    def test_extracts_sale_price_not_original(self, extractor):
        """Should extract sale price when both are shown."""
        html = """
        <div class="pricing">
            <del class="was-price">₪1,800</del>
            <ins class="now-price" data-price="1200">₪1,200</ins>
        </div>
        """
        result = extractor.extract(html)
        assert result is not None
        assert result.price == 1200.0, f"Should extract sale price 1200, not original 1800. Got {result.price}"


class TestRelatedProductsFiltering:
    """Tests for filtering prices from related/recommended products section.

    The main product price should be extracted, not prices from sidebar ads
    or "related products" sections.
    """

    @pytest.fixture
    def extractor(self):
        return PriceExtractor()

    def test_extracts_main_product_price_not_related(self, extractor):
        """Should extract main product price, not related product prices."""
        html = """
        <div class="product-page">
            <div class="main-product">
                <h1>iPhone 15 Pro</h1>
                <span itemprop="price" content="4999">₪4,999</span>
            </div>
            <div class="related-products">
                <div class="related-item">
                    <span class="price">₪199</span> <!-- Phone case -->
                </div>
                <div class="related-item">
                    <span class="price">₪99</span> <!-- Screen protector -->
                </div>
            </div>
        </div>
        """
        result = extractor.extract(html)
        assert result is not None
        assert result.price == 4999.0, f"Should extract main product price 4999. Got {result.price}"

    def test_ignores_advertisement_prices(self, extractor):
        """Should ignore prices in advertisement sections."""
        html = """
        <div class="page">
            <div class="ad-banner">
                <span>Special offer! ₪50 off!</span>
            </div>
            <div class="product-info">
                <meta property="product:price:amount" content="2500">
                <span class="product-price">₪2,500</span>
            </div>
            <div class="sponsored">
                <span class="price">₪899</span>
            </div>
        </div>
        """
        result = extractor.extract(html)
        assert result is not None
        assert result.price == 2500.0, f"Should extract product price 2500. Got {result.price}"


class TestBuyButtonProximity:
    """Tests for prioritizing prices near add-to-cart/buy buttons.

    Prices that appear near purchase buttons are more likely to be the
    actual product price.
    """

    @pytest.fixture
    def extractor(self):
        return PriceExtractor()

    def test_prioritizes_price_near_add_to_cart(self, extractor):
        """Should prioritize price near 'Add to Cart' button."""
        html = """
        <div class="page">
            <div class="header-promo">
                <span>משלוח חינם מעל ₪200</span>
            </div>
            <div class="product-purchase-section">
                <span class="main-price" itemprop="price" content="1299">₪1,299</span>
                <button class="add-to-cart">הוסף לסל</button>
            </div>
        </div>
        """
        result = extractor.extract(html)
        assert result is not None
        assert result.price == 1299.0, f"Should extract price near buy button. Got {result.price}"

    def test_json_ld_preferred_over_random_prices(self, extractor):
        """JSON-LD should be preferred even when other prices exist."""
        html = """
        <script type="application/ld+json">
        {
            "@type": "Product",
            "name": "Samsung TV",
            "offers": {"price": "3499"}
        }
        </script>
        <div class="shipping-notice">משלוח מ-₪49</div>
        <div class="bundle-offer">חבילה: ₪4,500</div>
        """
        result = extractor.extract(html)
        assert result is not None
        assert result.price == 3499.0, "JSON-LD price should be preferred"
        assert result.source == "json_ld"


class TestNoStructuredDataFallback:
    """Tests for price extraction when NO structured data exists.

    These are the hardest cases - no JSON-LD, no microdata, no meta tags.
    The extractor must rely on CSS classes and regex, which is error-prone.
    """

    @pytest.fixture
    def extractor(self):
        return PriceExtractor()

    def test_installment_without_structured_data(self, extractor):
        """Should NOT extract installment price when no structured data exists."""
        # Real-world case: page shows installment first, total price later
        # No structured data available
        html = """
        <div class="product-page">
            <h1>MacBook Pro 14</h1>
            <div class="payment-options">
                <span class="installment-price">או ב-24 תשלומים של ₪350</span>
            </div>
            <div class="total-section">
                <span class="final-price">₪8,400</span>
                <button>הוסף לסל</button>
            </div>
        </div>
        """
        result = extractor.extract(html)
        assert result is not None
        # Should NOT extract 350 (installment), should extract 8400 (total)
        assert result.price == 8400.0, f"Should extract total 8400, not installment 350. Got {result.price}"

    def test_old_price_without_structured_data(self, extractor):
        """Should extract current price, not old price, without structured data."""
        html = """
        <div class="product">
            <span class="was-price">היה: ₪1,200</span>
            <span class="now-price">עכשיו: ₪899</span>
        </div>
        """
        result = extractor.extract(html)
        assert result is not None
        # Should extract 899 (current), not 1200 (old)
        assert result.price == 899.0, f"Should extract current 899, not old 1200. Got {result.price}"

    def test_shipping_vs_product_price(self, extractor):
        """Should extract product price, not shipping cost."""
        html = """
        <div class="product-details">
            <div class="shipping-info">משלוח: ₪35</div>
            <div class="product-price">מחיר: ₪2,500</div>
        </div>
        """
        result = extractor.extract(html)
        assert result is not None
        # Should extract 2500 (product), not 35 (shipping)
        assert result.price == 2500.0, f"Should extract product price 2500, not shipping 35. Got {result.price}"

    def test_discount_amount_vs_final_price(self, extractor):
        """Should extract final price, not discount amount."""
        html = """
        <div class="offer">
            <span class="discount">חסכו ₪500!</span>
            <span class="sale-price">₪1,999</span>
        </div>
        """
        result = extractor.extract(html)
        assert result is not None
        # Should extract 1999 (final), not 500 (discount)
        assert result.price == 1999.0, f"Should extract final price 1999, not discount 500. Got {result.price}"

    def test_bundle_vs_single_product(self, extractor):
        """Should extract single product price, not bundle/package price."""
        html = """
        <div class="product-buy">
            <div class="single-item">
                <span class="price">₪799</span>
                <button class="add-to-cart">הוסף לסל</button>
            </div>
            <div class="bundle-offer">
                <span>קנה 3 ב-₪2,000</span>
            </div>
        </div>
        """
        result = extractor.extract(html)
        assert result is not None
        # Should extract 799 (single), as it's near the buy button
        assert result.price == 799.0, f"Should extract single price 799. Got {result.price}"

    def test_first_price_on_page_is_not_always_correct(self, extractor):
        """The first price on page might be unrelated (promo, header, etc)."""
        html = """
        <header>
            <div class="top-banner">משלוח חינם מעל ₪200</div>
        </header>
        <main>
            <div class="product">
                <div class="price-display">₪3,499</div>
            </div>
        </main>
        """
        result = extractor.extract(html)
        assert result is not None
        # Should extract 3499 (product), not 200 (shipping threshold)
        assert result.price == 3499.0, f"Should extract product price 3499, not promo 200. Got {result.price}"


class TestSmallNumberFiltering:
    """Tests for filtering small non-price numbers like ratings, warranty years, etc.

    E-commerce pages often have small numbers like ratings (4.7), warranty periods (7 years),
    review counts (12 reviews) that appear before or near the actual price.
    These should NOT be extracted as prices.
    """

    @pytest.fixture
    def extractor(self):
        return PriceExtractor()

    def test_citydeal_warranty_vs_price(self, extractor):
        """Real-world case: citydeal.co.il showing warranty years near price.

        Page shows "7 שנות אחריות" (7 year warranty) and price "₪9,890".
        Should extract 9890, not 7.
        """
        html = """
        <div class="product-page">
            <h1>Samsung RF72DG9620B1 מקרר 4 דלתות</h1>
            <div class="product-info">
                <div class="warranty-badge">
                    <span class="warranty-years">7</span>
                    <span>שנות אחריות</span>
                </div>
                <div class="price-section">
                    <span class="product-price">₪9,890</span>
                </div>
            </div>
        </div>
        """
        result = extractor.extract(html)
        assert result is not None
        assert result.price == 9890.0, f"Should extract price 9890, not warranty years 7. Got {result.price}"

    def test_rating_near_price(self, extractor):
        """Should not extract rating as price."""
        html = """
        <div class="product">
            <div class="rating">
                <span class="stars">4.7</span>
                <span class="reviews">(125 ביקורות)</span>
            </div>
            <div class="price-box">
                <span class="price">₪2,499</span>
            </div>
        </div>
        """
        result = extractor.extract(html)
        assert result is not None
        assert result.price == 2499.0, f"Should extract price 2499, not rating 4.7. Got {result.price}"

    def test_quantity_selector_vs_price(self, extractor):
        """Should not extract quantity selector value as price."""
        html = """
        <div class="product-buy">
            <div class="quantity">
                <input type="number" value="1" min="1" max="10">
            </div>
            <div class="total-price">
                <span class="price">₪5,999</span>
            </div>
        </div>
        """
        result = extractor.extract(html)
        assert result is not None
        assert result.price == 5999.0, f"Should extract price 5999, not quantity 1. Got {result.price}"

    def test_review_count_vs_price(self, extractor):
        """Should not extract review count as price."""
        html = """
        <div class="product-header">
            <span class="review-count">23 ביקורות</span>
            <span class="product-price" data-price="1299">₪1,299</span>
        </div>
        """
        result = extractor.extract(html)
        assert result is not None
        assert result.price == 1299.0, f"Should extract price 1299, not review count 23. Got {result.price}"

    def test_small_number_with_shekel_symbol(self, extractor):
        """Small numbers with shekel should be filtered if too low for context."""
        # When page has both very small and reasonable prices, prefer reasonable
        html = """
        <div class="product">
            <div class="cashback-offer">קבלו ₪7 בחזרה</div>
            <div class="main-price">
                <span class="price" itemprop="price" content="9890">₪9,890</span>
            </div>
        </div>
        """
        result = extractor.extract(html)
        assert result is not None
        # Should use microdata (content="9890") not the cashback ₪7
        assert result.price == 9890.0, f"Should extract price 9890, not cashback 7. Got {result.price}"

    def test_warranty_pattern_hebrew(self, extractor):
        """Hebrew warranty pattern should be ignored."""
        html = """
        <div class="product-details">
            <ul class="features">
                <li>7 שנות אחריות יבואן</li>
                <li>משלוח חינם</li>
            </ul>
            <div class="price-container">
                <span class="final-price">₪12,500</span>
            </div>
        </div>
        """
        result = extractor.extract(html)
        assert result is not None
        assert result.price == 12500.0, f"Should extract price 12500, not warranty 7. Got {result.price}"

    def test_payment_count_vs_total_price(self, extractor):
        """Number of payments should not be extracted as price."""
        html = """
        <div class="payment-section">
            <span>12 תשלומים ללא ריבית</span>
            <span class="total">סה"כ: ₪6,000</span>
        </div>
        """
        result = extractor.extract(html)
        assert result is not None
        assert result.price == 6000.0, f"Should extract total 6000, not payment count 12. Got {result.price}"
