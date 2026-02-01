"""Direct Google Search scraper without SerpAPI.

Scrapes Google organic search results directly using HTTP requests.
"""

import re
import json
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse, quote_plus

import httpx
import structlog

from src.state.models import PriceOption, SellerInfo
from src.tools.scraping.base_scraper import BaseScraper, ScraperConfig
from src.tools.scraping.filters import is_relevant_product
from src.tools.scraping.http_client import get_http_client
from src.tools.scraping.price_extractor import get_price_extractor
from src.tools.scraping.registry import ScraperRegistry
from src.observability import record_scrape, record_price_extraction, record_contact_extraction

logger = structlog.get_logger()

# Known Israeli ecommerce domains
IL_ECOMMERCE_DOMAINS = {
    "zap.co.il", "www.zap.co.il",
    "ksp.co.il", "www.ksp.co.il",
    "bug.co.il", "www.bug.co.il",
    "ivory.co.il", "www.ivory.co.il",
    "machsanei-hashmal.co.il", "www.machsanei-hashmal.co.il",
    "electra.co.il", "www.electra.co.il",
    "ace.co.il", "www.ace.co.il",
    "homedepot.co.il", "www.homedepot.co.il",
    "p1000.co.il", "www.p1000.co.il",
    "1pc.co.il", "www.1pc.co.il",
    "allphones.co.il", "www.allphones.co.il",
}

GOOGLE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
}


@ScraperRegistry.register("IL", "google_search")
class GoogleSearchDirectScraper(BaseScraper):
    """Scraper for Google organic search results via direct HTTP requests."""

    def __init__(self, config: Optional[ScraperConfig] = None):
        if config is None:
            config = ScraperConfig(
                name="google_search",
                base_url="https://www.google.co.il",
                search_path="/search?q={query}",
                priority=10,  # Lowest priority, use as fallback
            )
        super().__init__(config)
        self._price_extractor = get_price_extractor()

    async def search(self, query: str, max_results: int = 10) -> list[PriceOption]:
        """Search Google for organic results from ecommerce sites.

        Args:
            query: Product search query
            max_results: Maximum number of results to return

        Returns:
            List of PriceOption objects from ecommerce sites
        """
        # Enhance query to target ecommerce
        search_query = f"{query} buy israel price"
        logger.info("Searching Google (direct)", query=search_query)

        params = {
            "q": search_query,
            "gl": "il",
            "hl": "he",
            "num": 30,  # Request more to filter for ecommerce
        }

        results = []
        ecommerce_urls = []

        try:
            async with httpx.AsyncClient(
                timeout=20.0,
                follow_redirects=True,
                headers=GOOGLE_HEADERS,
            ) as client:
                response = await client.get("https://www.google.com/search", params=params)

                if response.status_code != 200:
                    logger.warning(
                        "Google Search returned non-200",
                        status=response.status_code,
                    )
                    return []

                html = response.text

                # Extract URLs from search results
                ecommerce_urls = self._extract_ecommerce_urls(html, query)

        except Exception as e:
            logger.error("Google Search failed", error=str(e))
            return []

        # Scrape each ecommerce URL for price
        for url, title in ecommerce_urls[:max_results * 2]:
            try:
                result = await self._scrape_product_page(url, title, query)
                if result:
                    results.append(result)
                    if len(results) >= max_results:
                        break
            except Exception as e:
                logger.debug("Failed to scrape product page", url=url, error=str(e))

        logger.info("Google Search complete", query=query, results=len(results))
        return results

    def _extract_ecommerce_urls(self, html: str, query: str) -> list[tuple[str, str]]:
        """Extract ecommerce URLs from Google search results.

        Returns list of (url, title) tuples.
        """
        results = []

        # Pattern to find search result links
        # Google uses various formats, try multiple patterns
        patterns = [
            r'<a[^>]*href="(https?://[^"]+)"[^>]*>.*?<h3[^>]*>([^<]+)</h3>',
            r'<a[^>]*href="/url\?q=(https?://[^&"]+)[^"]*"[^>]*>.*?<h3[^>]*>([^<]+)</h3>',
            r'href="(https?://(?:www\.)?[a-z0-9-]+\.co\.il[^"]*)"[^>]*>([^<]+)<',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)
            for url, title in matches:
                # Check if it's an ecommerce domain
                try:
                    domain = urlparse(url).netloc.lower()
                    if domain in IL_ECOMMERCE_DOMAINS or domain.endswith(".co.il"):
                        # Skip Google's own URLs
                        if "google.com" in domain or "google.co.il" in domain:
                            continue
                        results.append((url, title.strip()))
                except Exception:
                    continue

        # Deduplicate by URL
        seen = set()
        unique_results = []
        for url, title in results:
            if url not in seen:
                seen.add(url)
                unique_results.append((url, title))

        return unique_results

    async def _scrape_product_page(
        self,
        url: str,
        title: str,
        query: str,
    ) -> Optional[PriceOption]:
        """Scrape a product page for price information."""
        # Check relevance first
        if not is_relevant_product(query, title, strict_model_match=False):
            return None

        client = get_http_client()
        response = await client.get(url)

        if not response:
            return None

        # Record scrape
        await record_scrape(url, cached=False)

        html = response.text

        # Extract price using the price extractor
        price_result = await self._price_extractor.extract_price(html, url)

        if not price_result or price_result.price <= 0:
            await record_price_extraction(url, success=False)
            return None

        await record_price_extraction(url, success=True, price=price_result.price)

        # Extract domain for seller name
        domain = urlparse(url).netloc
        seller_name = domain.replace("www.", "").split(".")[0].upper()

        seller = SellerInfo(
            name=seller_name,
            website=url,
            country="IL",
            source="google_search",
        )

        return PriceOption(
            product_id=query,
            seller=seller,
            listed_price=price_result.price,
            currency=price_result.currency,
            url=url,
            scraped_at=datetime.now(),
        )

    async def get_seller_details(self, seller_url: str) -> Optional[SellerInfo]:
        """Get detailed seller information."""
        return None

    async def extract_contact_info(self, seller_url: str) -> Optional[str]:
        """Extract phone/WhatsApp number from seller's page."""
        if not seller_url or not seller_url.startswith("http"):
            return None

        client = get_http_client()
        response = await client.get(seller_url)
        if not response:
            return None

        return self._find_phone_in_html(response.text)

    def _find_phone_in_html(self, html: str) -> Optional[str]:
        """Find phone numbers in HTML content.

        Prioritizes phone numbers from:
        1. WhatsApp links (most reliable)
        2. Footer and contact sections
        3. Page body (fallback)
        """
        from bs4 import BeautifulSoup

        # Check for WhatsApp API links first - most reliable
        # Matches: api.whatsapp.com/send/?phone=972545472406 or api.whatsapp.com/send?phone=...
        wa_api_pattern = r'api\.whatsapp\.com/send/?\?phone=(\d+)'
        wa_api_matches = re.findall(wa_api_pattern, html)
        if wa_api_matches:
            phone = wa_api_matches[0]
            if not phone.startswith('+'):
                phone = '+' + phone
            return phone

        # Check for wa.me links
        wa_pattern = r'wa\.me/(\d+)'
        wa_matches = re.findall(wa_pattern, html)
        if wa_matches:
            phone = wa_matches[0]
            if not phone.startswith('+'):
                phone = '+' + phone
            return phone

        # Also check for whatsapp:// protocol
        wa_protocol_pattern = r'whatsapp://send\?phone=(\d+)'
        wa_protocol_matches = re.findall(wa_protocol_pattern, html)
        if wa_protocol_matches:
            phone = wa_protocol_matches[0]
            if not phone.startswith('+'):
                phone = '+' + phone
            return phone

        # Israeli phone patterns
        phone_patterns = [
            r"05\d[\s-]?\d{3}[\s-]?\d{4}",
            r"0[2-9][\s-]?\d{7}",
            r"\+972[\s-]?5\d[\s-]?\d{3}[\s-]?\d{4}",
            r"\+972[\s-]?[2-9][\s-]?\d{7}",
            r"972[\s-]?5\d[\s-]?\d{3}[\s-]?\d{4}",
        ]

        # Parse HTML to look in specific sections first
        soup = BeautifulSoup(html, "lxml")

        # Priority sections to search for phone numbers
        priority_selectors = [
            "footer",
            ".footer",
            "#footer",
            "[class*='contact']",
            "[id*='contact']",
            "[class*='phone']",
            "[id*='phone']",
            "[class*='whatsapp']",
            ".about",
            "#about",
        ]

        # Search in priority sections first
        for selector in priority_selectors:
            elements = soup.select(selector)
            for element in elements:
                text = element.get_text()
                for pattern in phone_patterns:
                    matches = re.findall(pattern, text)
                    if matches:
                        phone = re.sub(r"[\s-]", "", matches[0])
                        if phone.startswith("972") and not phone.startswith("+"):
                            phone = "+" + phone
                        elif phone.startswith("0"):
                            phone = "+972" + phone[1:]
                        return phone

        # Fallback: search bottom half of page first
        lines = html.split('\n')
        bottom_half = '\n'.join(lines[len(lines)//2:])

        for pattern in phone_patterns:
            matches = re.findall(pattern, bottom_half)
            if matches:
                phone = re.sub(r"[\s-]", "", matches[0])
                if phone.startswith("972") and not phone.startswith("+"):
                    phone = "+" + phone
                elif phone.startswith("0"):
                    phone = "+972" + phone[1:]
                return phone

        # Final fallback: search entire page
        for pattern in phone_patterns:
            matches = re.findall(pattern, html)
            if matches:
                phone = re.sub(r"[\s-]", "", matches[0])
                if phone.startswith("972") and not phone.startswith("+"):
                    phone = "+" + phone
                elif phone.startswith("0"):
                    phone = "+972" + phone[1:]
                return phone

        return None
