"""HTTP-based scraper for wisebuy.co.il - Israeli price comparison site."""

import re
from datetime import datetime
from typing import Optional
from urllib.parse import quote

import httpx
from bs4 import BeautifulSoup
import structlog

from src.state.models import PriceOption, SellerInfo
from src.tools.scraping.base_scraper import BaseScraper, ScraperConfig
from src.tools.scraping.registry import ScraperRegistry

logger = structlog.get_logger()

# Headers optimized for wisebuy.co.il
WISEBUY_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "he,en;q=0.9",
}


@ScraperRegistry.register("IL", "wisebuy")
class WiseBuyScraper(BaseScraper):
    """HTTP-based scraper for wisebuy.co.il price comparison site."""

    def __init__(self, config: Optional[ScraperConfig] = None):
        if config is None:
            config = ScraperConfig(
                name="wisebuy",
                base_url="https://www.wisebuy.co.il",
                search_path="/search?q={query}",
                priority=1,  # After zap_http
            )
        super().__init__(config)

    async def search(self, query: str, max_results: int = 10) -> list[PriceOption]:
        """Search for products on wisebuy.co.il.

        Args:
            query: Product search query
            max_results: Maximum number of results to return

        Returns:
            List of PriceOption objects
        """
        search_url = f"{self.base_url}/search?q={quote(query)}"
        logger.info("Searching wisebuy.co.il", query=query, url=search_url)

        results = []

        async with httpx.AsyncClient(
            headers=WISEBUY_HEADERS,
            follow_redirects=True,
            timeout=30.0,
            verify=False,  # WiseBuy has SSL certificate issues
        ) as client:
            try:
                response = await client.get(search_url)
                response.raise_for_status()

                soup = BeautifulSoup(response.text, "lxml")

                # Check if we were redirected to a product detail page
                final_url = str(response.url)
                if "/product/" in final_url or "/item/" in final_url:
                    logger.info("Redirected to product page", url=final_url)
                    results = self._parse_product_page(soup, query, final_url, max_results)
                else:
                    # Regular search results page
                    results = self._parse_search_results(soup, query, max_results)

            except httpx.HTTPStatusError as e:
                logger.error("HTTP error searching wisebuy.co.il", status=e.response.status_code, error=str(e))
                raise
            except Exception as e:
                logger.error("Search failed on wisebuy.co.il", error=str(e))
                raise

        logger.info("Search complete (wisebuy)", query=query, results=len(results))
        return results

    def _parse_search_results(self, soup: BeautifulSoup, query: str, max_results: int) -> list[PriceOption]:
        """Parse search results page."""
        results = []

        # WiseBuy product selectors (may need adjustment based on actual structure)
        product_selectors = [
            ".product-item",
            ".product-card",
            ".search-result-item",
            ".item-box",
            "[data-product-id]",
        ]

        products = []
        for selector in product_selectors:
            products = soup.select(selector)[:max_results]
            if products:
                logger.debug("Found products with selector", selector=selector, count=len(products))
                break

        for product in products:
            try:
                result = self._parse_product_item(product, query)
                if result:
                    results.append(result)
            except Exception as e:
                logger.warning("Failed to parse product item", error=str(e))

        return results

    def _parse_product_page(self, soup: BeautifulSoup, query: str, page_url: str, max_results: int) -> list[PriceOption]:
        """Parse a product detail page with seller listings."""
        results = []

        # Look for seller/store listings on product page
        seller_selectors = [
            ".seller-item",
            ".store-item",
            ".price-item",
            ".offer-row",
            "[data-seller-id]",
            ".compare-row",
        ]

        sellers = []
        for selector in seller_selectors:
            sellers = soup.select(selector)[:max_results]
            if sellers:
                logger.debug("Found sellers with selector", selector=selector, count=len(sellers))
                break

        for seller_elem in sellers:
            try:
                result = self._parse_seller_item(seller_elem, query, page_url)
                if result:
                    results.append(result)
            except Exception as e:
                logger.warning("Failed to parse seller item", error=str(e))

        # Fallback: try to extract main price if no sellers found
        if not results:
            price_elem = soup.select_one(".price, .product-price, [data-price]")
            if price_elem:
                price = self._parse_price(price_elem.get_text())
                if price:
                    seller = SellerInfo(
                        name="WiseBuy.co.il",
                        website=page_url,
                        country="IL",
                        source="wisebuy",
                    )
                    results.append(PriceOption(
                        product_id=query,
                        seller=seller,
                        listed_price=price,
                        currency="ILS",
                        url=page_url,
                        scraped_at=datetime.now(),
                    ))

        return results

    def _parse_product_item(self, product_elem, query: str) -> Optional[PriceOption]:
        """Parse a product item from search results."""
        # Extract product name
        name_elem = product_elem.select_one(".product-name, .item-title, h2, h3, a")
        if not name_elem:
            return None

        product_name = name_elem.get_text(strip=True)
        if not product_name:
            return None

        # Extract price
        price_elem = product_elem.select_one(".price, .product-price, [data-price]")
        if not price_elem:
            return None

        price = self._parse_price(price_elem.get_text())
        if not price:
            return None

        # Extract URL
        link_elem = product_elem.select_one("a[href]")
        product_url = ""
        if link_elem and link_elem.get("href"):
            href = link_elem["href"]
            if href.startswith("/"):
                product_url = f"{self.base_url}{href}"
            elif href.startswith("http"):
                product_url = href

        # Extract seller name if available
        seller_elem = product_elem.select_one(".seller-name, .store-name, [data-seller]")
        seller_name = seller_elem.get_text(strip=True) if seller_elem else "WiseBuy.co.il"

        seller = SellerInfo(
            name=seller_name,
            website=product_url,
            country="IL",
            source="wisebuy",
        )

        return PriceOption(
            product_id=query,
            seller=seller,
            listed_price=price,
            currency="ILS",
            url=product_url,
            scraped_at=datetime.now(),
        )

    def _parse_seller_item(self, seller_elem, query: str, page_url: str) -> Optional[PriceOption]:
        """Parse a seller item from product detail page."""
        # Extract seller name
        name_elem = seller_elem.select_one(".seller-name, .store-name, [data-seller]")
        seller_name = name_elem.get_text(strip=True) if name_elem else None

        if not seller_name:
            # Try data attribute
            seller_name = seller_elem.get("data-seller-name") or seller_elem.get("data-store-name")

        if not seller_name:
            return None

        # Extract price
        price_elem = seller_elem.select_one(".price, .seller-price, [data-price]")
        price = None
        if price_elem:
            price = self._parse_price(price_elem.get_text())
        if not price:
            price_str = seller_elem.get("data-price")
            if price_str:
                price = self._parse_price(price_str)
        if not price:
            return None

        # Extract rating if available
        rating = None
        rating_elem = seller_elem.select_one(".rating, [data-rating]")
        if rating_elem:
            rating_str = rating_elem.get("data-rating") or rating_elem.get_text()
            try:
                rating = float(re.search(r"(\d+\.?\d*)", rating_str).group(1))
            except (AttributeError, ValueError):
                pass

        # Extract seller URL
        seller_url = page_url
        link_elem = seller_elem.select_one("a[href]")
        if link_elem and link_elem.get("href"):
            href = link_elem["href"]
            if href.startswith("/"):
                seller_url = f"{self.base_url}{href}"
            elif href.startswith("http"):
                seller_url = href

        seller = SellerInfo(
            name=seller_name,
            website=seller_url,
            country="IL",
            source="wisebuy",
            reliability_score=rating,
        )

        return PriceOption(
            product_id=query,
            seller=seller,
            listed_price=price,
            currency="ILS",
            url=seller_url,
            scraped_at=datetime.now(),
        )

    def _parse_price(self, price_text: str) -> Optional[float]:
        """Parse price from Hebrew text."""
        if not price_text:
            return None

        # Price patterns
        price_patterns = [
            r"₪?\s*([\d,]+(?:\.\d{1,2})?)",
            r"([\d,]+(?:\.\d{1,2})?)\s*(?:₪|ש[\"']?ח|ILS)",
            r"(?:מחיר|price)[:\s]*([\d,]+(?:\.\d{1,2})?)",
            r"([\d]{3,}(?:,\d{3})*(?:\.\d{1,2})?)",
        ]

        for pattern in price_patterns:
            match = re.search(pattern, price_text, re.IGNORECASE)
            if match:
                price_str = match.group(1).replace(",", "")
                try:
                    price = float(price_str)
                    if 1 <= price <= 1_000_000:
                        return price
                except ValueError:
                    continue

        return None

    async def extract_contact_info(self, seller_url: str) -> Optional[str]:
        """Extract phone/WhatsApp number from seller's page."""
        # Skip aggregator URLs
        if "wisebuy.co.il" in seller_url:
            return None

        logger.info("Extracting contact info from seller page", url=seller_url)

        try:
            async with httpx.AsyncClient(
                headers=WISEBUY_HEADERS,
                follow_redirects=True,
                timeout=15.0,
                verify=False,
            ) as client:
                response = await client.get(seller_url)
                if response.status_code != 200:
                    return None

                return self._find_phone_in_html(response.text)

        except Exception as e:
            logger.warning("Failed to extract contact", url=seller_url, error=str(e))
            return None

    async def get_seller_details(self, seller_url: str) -> Optional[SellerInfo]:
        """Get detailed seller information from their page."""
        logger.info("Getting seller details", url=seller_url)

        try:
            async with httpx.AsyncClient(
                headers=WISEBUY_HEADERS,
                follow_redirects=True,
                timeout=15.0,
                verify=False,
            ) as client:
                response = await client.get(seller_url)
                if response.status_code != 200:
                    return None

                soup = BeautifulSoup(response.text, "lxml")

                # Extract seller name
                name_elem = soup.select_one(".store-name, .seller-name, .merchant-name, h1")
                name = name_elem.get_text(strip=True) if name_elem else "Unknown"

                # Extract phone number
                phone = self._find_phone_in_html(response.text)

                return SellerInfo(
                    name=name,
                    website=seller_url,
                    whatsapp_number=phone,
                    country="IL",
                    source="wisebuy",
                )

        except Exception as e:
            logger.warning("Failed to get seller details", url=seller_url, error=str(e))
            return None

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

        # Check for WhatsApp links
        wa_pattern = r'wa\.me/(\d+)'
        wa_matches = re.findall(wa_pattern, html)
        if wa_matches:
            return "+" + wa_matches[0]

        return None
