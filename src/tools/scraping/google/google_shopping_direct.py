"""Direct Google Shopping scraper without SerpAPI.

Scrapes Google Shopping directly using HTTP requests.
"""

import asyncio
import re
import json
from datetime import datetime
from typing import Optional
from urllib.parse import quote_plus, urljoin

import httpx
import structlog

from src.state.models import PriceOption, SellerInfo
from src.tools.scraping.base_scraper import BaseScraper, ScraperConfig
from src.tools.scraping.filters import is_relevant_product
from src.tools.scraping.http_client import get_http_client
from src.tools.scraping.registry import ScraperRegistry

logger = structlog.get_logger()

# Google Shopping URL for Israel
GOOGLE_SHOPPING_URL = "https://www.google.com/search"

# Headers that mimic a real browser
GOOGLE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


@ScraperRegistry.register("IL", "google_shopping")
class GoogleShoppingDirectScraper(BaseScraper):
    """Scraper for Google Shopping results via direct HTTP requests."""

    def __init__(self, config: Optional[ScraperConfig] = None):
        if config is None:
            config = ScraperConfig(
                name="google_shopping",
                base_url="https://www.google.com",
                search_path="/search?tbm=shop&q={query}",
                priority=5,
            )
        super().__init__(config)

    async def search(self, query: str, max_results: int = 10) -> list[PriceOption]:
        """Search Google Shopping for products.

        Args:
            query: Product search query
            max_results: Maximum number of results to return

        Returns:
            List of PriceOption objects
        """
        logger.info("Searching Google Shopping (direct)", query=query)

        # Build the search URL
        params = {
            "q": query,
            "tbm": "shop",  # Shopping tab
            "gl": "il",     # Country: Israel
            "hl": "he",     # Language: Hebrew
        }

        results = []

        try:
            async with httpx.AsyncClient(
                timeout=20.0,
                follow_redirects=True,
                headers=GOOGLE_HEADERS,
            ) as client:
                response = await client.get(GOOGLE_SHOPPING_URL, params=params)

                if response.status_code != 200:
                    logger.warning(
                        "Google Shopping returned non-200",
                        status=response.status_code,
                    )
                    return []

                html = response.text

                # Try multiple parsing strategies
                results = self._parse_shopping_html(html, query, max_results)

                if not results:
                    # Try parsing as JSON embedded in HTML
                    results = self._parse_shopping_json(html, query, max_results)

        except Exception as e:
            logger.error("Google Shopping search failed", error=str(e))

        logger.info("Google Shopping search complete", query=query, results=len(results))
        return results

    def _parse_shopping_html(self, html: str, query: str, max_results: int) -> list[PriceOption]:
        """Parse shopping results from HTML.

        Google Shopping embeds product data in various formats.
        This method tries to extract products from the HTML structure.
        """
        results = []

        # Pattern 1: Look for product cards with prices
        # Google uses data attributes and specific class patterns

        # Find price patterns: ₪X,XXX or X,XXX ש"ח
        price_pattern = r'(?:₪|ש"ח\s*)?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?)\s*(?:₪|ש"ח)?'

        # Look for product blocks - Google often uses specific div structures
        # Try to find product containers
        product_blocks = re.findall(
            r'<div[^>]*class="[^"]*sh-dgr__content[^"]*"[^>]*>(.*?)</div>\s*</div>\s*</div>',
            html,
            re.DOTALL | re.IGNORECASE,
        )

        if not product_blocks:
            # Alternative pattern for different Google Shopping layout
            product_blocks = re.findall(
                r'<div[^>]*data-docid="[^"]*"[^>]*>(.*?)</div>\s*</a>',
                html,
                re.DOTALL | re.IGNORECASE,
            )

        for block in product_blocks[:max_results * 2]:
            try:
                result = self._extract_product_from_block(block, query)
                if result:
                    results.append(result)
                    if len(results) >= max_results:
                        break
            except Exception as e:
                logger.debug("Failed to parse product block", error=str(e))

        return results

    def _parse_shopping_json(self, html: str, query: str, max_results: int) -> list[PriceOption]:
        """Parse shopping results from embedded JSON data.

        Google often embeds product data as JSON in script tags.
        """
        results = []

        # Look for JSON data in script tags
        json_patterns = [
            r'AF_initDataCallback\([^)]*data:(\[.*?\])\s*,\s*sideChannel',
            r'data:(\[\[.*?\]\])',
            r'"products":\s*(\[.*?\])',
        ]

        for pattern in json_patterns:
            matches = re.findall(pattern, html, re.DOTALL)
            for match in matches:
                try:
                    data = json.loads(match)
                    products = self._extract_products_from_json(data, query)
                    results.extend(products)
                except (json.JSONDecodeError, TypeError):
                    continue

            if results:
                break

        return results[:max_results]

    def _extract_product_from_block(self, block: str, query: str) -> Optional[PriceOption]:
        """Extract product info from an HTML block."""
        # Extract title
        title_match = re.search(r'<(?:h3|h4|span)[^>]*>([^<]+)</(?:h3|h4|span)>', block)
        if not title_match:
            return None

        title = title_match.group(1).strip()

        # Check relevance
        if not is_relevant_product(query, title, strict_model_match=True):
            return None

        # Extract price
        price_match = re.search(
            r'(?:₪|ש"ח\s*)?\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?)\s*(?:₪|ש"ח)?',
            block,
        )
        if not price_match:
            return None

        price_str = price_match.group(1).replace(",", "")
        try:
            price = float(price_str)
        except ValueError:
            return None

        if price <= 0:
            return None

        # Extract seller/source
        seller_match = re.search(r'<(?:span|div)[^>]*class="[^"]*merchant[^"]*"[^>]*>([^<]+)</', block)
        seller_name = seller_match.group(1).strip() if seller_match else "Google Shopping"

        # Extract URL
        url_match = re.search(r'href="(/url\?[^"]+|https?://[^"]+)"', block)
        url = ""
        if url_match:
            url = url_match.group(1)
            if url.startswith("/"):
                url = "https://www.google.com" + url

        # Extract rating if available
        rating = None
        rating_match = re.search(r'(\d+\.?\d*)\s*(?:כוכבים|stars|★)', block, re.IGNORECASE)
        if rating_match:
            try:
                rating = float(rating_match.group(1))
            except ValueError:
                pass

        seller = SellerInfo(
            name=seller_name,
            website=url,
            country="IL",
            source="google_shopping",
            reliability_score=rating,
        )

        return PriceOption(
            product_id=query,
            seller=seller,
            listed_price=price,
            currency="ILS",
            url=url,
            scraped_at=datetime.now(),
        )

    def _extract_products_from_json(self, data: list, query: str) -> list[PriceOption]:
        """Extract products from JSON data structure."""
        results = []

        def traverse(obj):
            """Recursively traverse JSON to find product data."""
            if isinstance(obj, dict):
                # Look for product-like structures
                if "title" in obj and "price" in obj:
                    try:
                        title = str(obj.get("title", ""))
                        if not is_relevant_product(query, title, strict_model_match=True):
                            return

                        price_val = obj.get("price")
                        if isinstance(price_val, dict):
                            price = float(price_val.get("value", 0))
                        else:
                            price = float(price_val) if price_val else 0

                        if price <= 0:
                            return

                        seller_name = obj.get("merchant", obj.get("seller", "Google Shopping"))
                        url = obj.get("link", obj.get("url", ""))

                        seller = SellerInfo(
                            name=str(seller_name),
                            website=str(url),
                            country="IL",
                            source="google_shopping",
                        )

                        results.append(PriceOption(
                            product_id=query,
                            seller=seller,
                            listed_price=price,
                            currency="ILS",
                            url=str(url),
                            scraped_at=datetime.now(),
                        ))
                    except (ValueError, TypeError):
                        pass

                for value in obj.values():
                    traverse(value)

            elif isinstance(obj, list):
                for item in obj:
                    traverse(item)

        traverse(data)
        return results

    async def get_seller_details(self, seller_url: str) -> Optional[SellerInfo]:
        """Get detailed seller information."""
        return None

    async def extract_contact_info(self, seller_url: str) -> Optional[str]:
        """Extract phone/WhatsApp number from seller's page."""
        if not seller_url or not seller_url.startswith("http"):
            return None

        logger.info("Extracting contact info", url=seller_url)

        client = get_http_client()
        response = await client.get(seller_url)
        if not response:
            return None

        return self._find_phone_in_html(response.text)

    def _find_phone_in_html(self, html: str) -> Optional[str]:
        """Find phone numbers in HTML content."""
        patterns = [
            r"05\d[\s-]?\d{3}[\s-]?\d{4}",
            r"0[2-9][\s-]?\d{7}",
            r"\+972[\s-]?5\d[\s-]?\d{3}[\s-]?\d{4}",
            r"\+972[\s-]?[2-9][\s-]?\d{7}",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, html)
            if matches:
                phone = re.sub(r"[\s-]", "", matches[0])
                if phone.startswith("0"):
                    phone = "+972" + phone[1:]
                return phone

        wa_pattern = r'wa\.me/(\d+)'
        wa_matches = re.findall(wa_pattern, html)
        if wa_matches:
            return "+" + wa_matches[0]

        return None
