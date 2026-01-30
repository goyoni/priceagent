"""Google Shopping scraper using SerpAPI."""

import asyncio
import re
from datetime import datetime
from typing import Optional

import httpx
import structlog

from src.config.settings import settings
from src.state.models import PriceOption, SellerInfo
from src.tools.scraping.base_scraper import BaseScraper, ScraperConfig
from src.tools.scraping.filters import is_relevant_product
from src.tools.scraping.http_client import get_http_client
from src.tools.scraping.registry import ScraperRegistry

logger = structlog.get_logger()

SERPAPI_BASE_URL = "https://serpapi.com/search.json"
MAX_RETRIES = 5
INITIAL_RETRY_DELAY = 1.0  # seconds (will backoff: 1, 2, 4, 8, 16)


# NOTE: This SerpAPI-based scraper is deprecated.
# Use google_shopping_direct.py instead (no API key needed).
# Keeping this file for reference only.

class GoogleShoppingScraperSerpAPI(BaseScraper):
    """Scraper for Google Shopping results via SerpAPI."""

    def __init__(self, config: Optional[ScraperConfig] = None):
        if config is None:
            config = ScraperConfig(
                name="google_shopping",
                base_url="https://shopping.google.com",
                search_path="/search?q={query}",
                priority=5,  # Lower priority than ZAP
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
        if not settings.serpapi_key:
            logger.warning("SerpAPI key not configured, skipping Google Shopping")
            return []

        logger.info("Searching Google Shopping", query=query)

        params = {
            "engine": "google_shopping",
            "q": query,
            "location": "Israel",
            "gl": "il",
            "hl": "he",
            "api_key": settings.serpapi_key,
            "num": max_results * 2,  # Request more to account for filtering
        }

        results = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Retry loop for rate limits
            for attempt in range(MAX_RETRIES):
                try:
                    response = await client.get(SERPAPI_BASE_URL, params=params)

                    # Handle rate limiting with retry
                    if response.status_code == 429:
                        retry_delay = INITIAL_RETRY_DELAY * (2 ** attempt)
                        logger.warning(
                            "SerpAPI rate limited, retrying",
                            attempt=attempt + 1,
                            max_retries=MAX_RETRIES,
                            retry_in=retry_delay,
                        )
                        await asyncio.sleep(retry_delay)
                        continue

                    response.raise_for_status()
                    data = response.json()

                    shopping_results = data.get("shopping_results", [])
                    logger.info("Got Google Shopping results", count=len(shopping_results))

                    for item in shopping_results[:max_results * 2]:
                        try:
                            result = self._parse_shopping_result(item, query)
                            if result:
                                results.append(result)
                                if len(results) >= max_results:
                                    break
                        except Exception as e:
                            logger.warning("Failed to parse shopping result", error=str(e))

                    # Success - break out of retry loop
                    break

                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429 and attempt < MAX_RETRIES - 1:
                        retry_delay = INITIAL_RETRY_DELAY * (2 ** attempt)
                        logger.warning(
                            "SerpAPI rate limited (exception), retrying",
                            attempt=attempt + 1,
                            retry_in=retry_delay,
                        )
                        await asyncio.sleep(retry_delay)
                        continue
                    logger.error("SerpAPI HTTP error", status=e.response.status_code, error=str(e))
                    break
                except Exception as e:
                    logger.error("Google Shopping search failed", error=str(e))
                    break

        logger.info("Google Shopping search complete", query=query, results=len(results))
        return results

    def _parse_shopping_result(self, item: dict, query: str) -> Optional[PriceOption]:
        """Parse a single shopping result from SerpAPI.

        Args:
            item: Shopping result dict from SerpAPI
            query: Original search query for relevance checking

        Returns:
            PriceOption or None if not relevant
        """
        title = item.get("title", "")
        if not title:
            return None

        # Check relevance - filter out near-matches
        if not is_relevant_product(query, title, strict_model_match=True):
            logger.debug("Filtered irrelevant product", query=query, product=title)
            return None

        # Extract price
        price = None
        extracted_price = item.get("extracted_price")
        if extracted_price:
            price = float(extracted_price)
        elif item.get("price"):
            price = self._parse_price(item["price"])

        if not price:
            return None

        # Get seller info
        source = item.get("source", "Unknown")
        # Prefer product_link (direct to seller) over link (Google redirect)
        link = item.get("product_link") or item.get("link", "")

        # Skip results without proper URL
        if not link or not link.startswith("http"):
            logger.debug("Skipping result without valid link", source=source)
            return None

        # Extract rating if available (SerpAPI provides this)
        rating = None
        if item.get("rating"):
            try:
                rating = float(item["rating"])
            except (ValueError, TypeError):
                pass

        seller = SellerInfo(
            name=source,
            website=link,
            country="IL",
            source="google_shopping",
            reliability_score=rating,
        )

        return PriceOption(
            product_id=query,
            seller=seller,
            listed_price=price,
            currency="ILS",
            url=link,
            scraped_at=datetime.now(),
        )

    def _parse_price(self, price_text: str) -> Optional[float]:
        """Parse price from text like '₪1,234' or '1,234 ILS'."""
        if not price_text:
            return None

        # Remove currency symbols and whitespace
        cleaned = re.sub(r"[₪,\s]|ש\"ח|ILS", "", price_text)

        try:
            return float(cleaned)
        except ValueError:
            return None

    async def get_seller_details(self, seller_url: str) -> Optional[SellerInfo]:
        """Get detailed seller information."""
        # For Google Shopping, we don't have detailed seller info
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
        # Israeli phone patterns
        patterns = [
            r"05\d[\s-]?\d{3}[\s-]?\d{4}",  # Mobile: 05X-XXX-XXXX
            r"0[2-9][\s-]?\d{7}",  # Landline: 0X-XXXXXXX
            r"\+972[\s-]?5\d[\s-]?\d{3}[\s-]?\d{4}",  # International mobile
            r"\+972[\s-]?[2-9][\s-]?\d{7}",  # International landline
        ]

        for pattern in patterns:
            matches = re.findall(pattern, html)
            if matches:
                phone = re.sub(r"[\s-]", "", matches[0])
                if phone.startswith("0"):
                    phone = "+972" + phone[1:]
                return phone

        # Check for WhatsApp links
        wa_pattern = r'wa\.me/(\d+)'
        wa_matches = re.findall(wa_pattern, html)
        if wa_matches:
            return "+" + wa_matches[0]

        return None
