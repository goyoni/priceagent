"""Multi-strategy price extraction from web pages."""

import json
import re
from typing import NamedTuple, Optional

import structlog
from bs4 import BeautifulSoup

logger = structlog.get_logger()


class PriceResult(NamedTuple):
    """Price extraction result with confidence score."""

    price: float
    confidence: float  # 0.0 to 1.0
    source: str  # Strategy that found the price


class PriceExtractor:
    """Extract prices from HTML using multiple strategies.

    Strategies are tried in order of reliability:
    1. JSON-LD structured data (highest confidence)
    2. Schema.org microdata attributes
    3. OpenGraph/meta tags
    4. CSS class-based selectors
    5. Regex fallback (lowest confidence)
    """

    def extract(self, html: str, url: str = "") -> Optional[PriceResult]:
        """Extract price using multiple strategies, returning best result.

        Args:
            html: HTML content to parse
            url: Optional URL for logging context

        Returns:
            PriceResult with price, confidence, and source, or None if not found
        """
        strategies = [
            ("json_ld", self._extract_from_json_ld, 0.95),
            ("microdata", self._extract_from_microdata, 0.90),
            ("meta_tags", self._extract_from_meta_tags, 0.85),
            ("price_elements", self._extract_from_price_elements, 0.70),
            ("regex_fallback", self._extract_from_regex, 0.50),
        ]

        soup = BeautifulSoup(html, "lxml")

        for name, strategy, confidence in strategies:
            try:
                price = strategy(soup, html)
                if price and self._is_valid_price(price):
                    logger.debug(
                        "Price extracted",
                        strategy=name,
                        price=price,
                        confidence=confidence,
                    )
                    return PriceResult(price=price, confidence=confidence, source=name)
            except Exception as e:
                logger.debug("Strategy failed", strategy=name, error=str(e))

        return None

    def _extract_from_json_ld(
        self, soup: BeautifulSoup, html: str
    ) -> Optional[float]:
        """Extract from JSON-LD structured data (highest accuracy)."""
        scripts = soup.find_all("script", {"type": "application/ld+json"})
        for script in scripts:
            try:
                data = json.loads(script.string or "")
                price = self._find_price_in_json(data)
                if price:
                    return price
            except json.JSONDecodeError:
                continue
        return None

    def _find_price_in_json(self, data, depth: int = 0) -> Optional[float]:
        """Recursively search for price in JSON structure."""
        if depth > 5:
            return None

        if isinstance(data, dict):
            # Check for offers.price pattern (schema.org Product)
            if "offers" in data:
                offers = data["offers"]
                if isinstance(offers, dict):
                    price = offers.get("price") or offers.get("lowPrice")
                    if price:
                        try:
                            return float(price)
                        except (ValueError, TypeError):
                            pass
                elif isinstance(offers, list) and offers:
                    price = offers[0].get("price") or offers[0].get("lowPrice")
                    if price:
                        try:
                            return float(price)
                        except (ValueError, TypeError):
                            pass

            # Direct price field
            if "price" in data:
                try:
                    return float(data["price"])
                except (ValueError, TypeError):
                    pass

            # Recurse into nested objects
            for value in data.values():
                result = self._find_price_in_json(value, depth + 1)
                if result:
                    return result

        elif isinstance(data, list):
            for item in data:
                result = self._find_price_in_json(item, depth + 1)
                if result:
                    return result

        return None

    def _extract_from_microdata(
        self, soup: BeautifulSoup, html: str
    ) -> Optional[float]:
        """Extract from schema.org microdata attributes."""
        # itemprop="price" with content attribute
        price_elem = soup.find(attrs={"itemprop": "price"})
        if price_elem:
            content = price_elem.get("content")
            if content:
                try:
                    return float(content)
                except ValueError:
                    pass
            # Try text content
            return self._parse_price_text(price_elem.get_text())
        return None

    def _extract_from_meta_tags(
        self, soup: BeautifulSoup, html: str
    ) -> Optional[float]:
        """Extract from OpenGraph and product meta tags."""
        meta_names = [
            "product:price:amount",
            "og:price:amount",
            "twitter:data1",  # Sometimes contains price
        ]
        for name in meta_names:
            meta = soup.find("meta", {"property": name}) or soup.find(
                "meta", {"name": name}
            )
            if meta and meta.get("content"):
                try:
                    return float(meta["content"])
                except ValueError:
                    pass
        return None

    def _extract_from_price_elements(
        self, soup: BeautifulSoup, html: str
    ) -> Optional[float]:
        """Extract from common price CSS classes and elements.

        Prioritizes current/final prices over old/original prices.
        Filters out discounts, shipping costs, and installment prices.
        """
        # Priority selectors - most likely to be the actual product price
        priority_selectors = [
            # Current/final/sale price indicators (highest priority)
            "[class*='price'][class*='current']",
            "[class*='price'][class*='final']",
            "[class*='price'][class*='sale']",
            "[class*='price'][class*='now']",
            "[class*='price'][class*='special']",
            ".current-price",
            ".final-price",
            ".sale-price",
            ".now-price",
            ".special-price",
            # Product price containers
            "[class*='product-price']",
            ".price-box .price",
            ".product-info-price .price",
            # Data attributes (often reliable)
            "[data-price]",
            "[data-product-price]",
            "[data-final-price]",
        ]

        # General price selectors (fallback)
        general_selectors = [
            ".price",
            "[class*='price']",
        ]

        # Classes to exclude - these are NOT the main product price
        exclude_patterns = [
            "old", "was", "original", "before", "regular", "compare",  # Old prices
            "discount", "save", "off", "saving",  # Discount amounts
            "shipping", "delivery", "freight",  # Shipping costs
            "installment", "payment", "monthly", "תשלום",  # Installments
            "related", "recommend", "similar", "also",  # Related products
            "banner", "promo", "ad-", "advertisement",  # Ads/promos
        ]

        # Try priority selectors first
        for selector in priority_selectors:
            elements = soup.select(selector)
            for elem in elements:
                if self._should_skip_element(elem, exclude_patterns):
                    continue

                price = self._extract_price_from_element(elem)
                if price:
                    return price

        # Try general selectors, but be more careful
        for selector in general_selectors:
            elements = soup.select(selector)
            for elem in elements:
                if self._should_skip_element(elem, exclude_patterns):
                    continue

                # Additional check: skip if element text suggests it's not a product price
                text = elem.get_text().lower()
                if any(indicator in text for indicator in ["משלוח", "shipping", "תשלום", "payment", "חסכו", "save"]):
                    continue

                price = self._extract_price_from_element(elem)
                if price:
                    return price

        return None

    def _should_skip_element(self, elem, exclude_patterns: list) -> bool:
        """Check if element should be skipped based on class/id patterns.

        Uses word boundary matching to avoid false positives like 'off' matching 'offer'.
        """
        classes = elem.get("class", [])
        id_str = (elem.get("id") or "").lower()

        for pattern in exclude_patterns:
            # Check if pattern matches any class (word-level, not substring)
            for cls in classes:
                cls_lower = cls.lower()
                # Match if pattern is the class, or pattern is a word part separated by hyphen
                if pattern == cls_lower or f"-{pattern}" in cls_lower or f"{pattern}-" in cls_lower:
                    return True
            # Check id (same logic)
            if pattern == id_str or f"-{pattern}" in id_str or f"{pattern}-" in id_str:
                return True

        # Also check parent elements (2 levels up)
        parent_count = 0
        for parent in elem.parents:
            if parent.name in ["html", "body", "[document]"]:
                break
            parent_count += 1
            if parent_count > 2:
                break

            parent_classes = parent.get("class", [])
            parent_id = (parent.get("id") or "").lower()
            for pattern in exclude_patterns:
                for cls in parent_classes:
                    cls_lower = cls.lower()
                    if pattern == cls_lower or f"-{pattern}" in cls_lower or f"{pattern}-" in cls_lower:
                        return True
                if pattern == parent_id or f"-{pattern}" in parent_id or f"{pattern}-" in parent_id:
                    return True

        return False

    def _extract_price_from_element(self, elem) -> Optional[float]:
        """Extract price from a single element."""
        # Check data-price attribute first (most reliable)
        for attr in ["data-price", "data-product-price", "data-final-price", "content"]:
            value = elem.get(attr)
            if value:
                try:
                    price = float(value)
                    if self._is_valid_price(price):
                        return price
                except ValueError:
                    pass

        # Try text content
        return self._parse_price_text(elem.get_text())

    def _extract_from_regex(
        self, soup: BeautifulSoup, html: str
    ) -> Optional[float]:
        """Last resort: regex on page text."""
        text = soup.get_text()
        return self._parse_price_text(text)

    def _parse_price_text(self, text: str) -> Optional[float]:
        """Parse Israeli shekel price from text.

        Supports formats:
        - ₪1,234 or ₪1,234.00
        - 1,234₪
        - 1,234 ש"ח
        - ILS 1,234

        All prices must be >= 50 ILS to filter false positives.
        """
        if not text:
            return None

        # Price number pattern: handles both comma-formatted and plain numbers
        # Examples: 50, 999, 1234, 12345, 1,234, 12,345, 123,456
        price_num = r"([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)"

        patterns = [
            rf"₪\s*{price_num}",  # ₪1,234 or ₪1234
            rf"{price_num}\s*₪",  # 1,234₪ or 1234₪
            rf'{price_num}\s*ש["\']?ח',  # 1,234 ש"ח
            rf"ILS\s*{price_num}",  # ILS 1,234
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                price_str = match.group(1).replace(",", "")
                try:
                    price = float(price_str)
                    # Reject prices under 50 ILS (likely false positives)
                    if price >= 50:
                        return price
                except ValueError:
                    continue

        return None

    def _is_valid_price(self, price: float, min_price: float = 50.0) -> bool:
        """Check if price is reasonable for Israeli market.

        Args:
            price: Price value to validate
            min_price: Minimum valid price (default 50 ILS for appliances)

        Returns:
            True if price is between min_price and 500,000 ILS
        """
        return min_price <= price <= 500_000


# Global instance
_price_extractor: Optional[PriceExtractor] = None


def get_price_extractor() -> PriceExtractor:
    """Get or create the global price extractor instance."""
    global _price_extractor
    if _price_extractor is None:
        _price_extractor = PriceExtractor()
    return _price_extractor
