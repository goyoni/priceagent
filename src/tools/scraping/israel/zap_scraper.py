"""Scraper for zap.co.il - Israeli price comparison site."""

import re
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin, quote

from playwright.async_api import async_playwright, Page
from bs4 import BeautifulSoup
import structlog

from src.state.models import PriceOption, SellerInfo
from src.tools.scraping.base_scraper import BaseScraper, ScraperConfig
from src.tools.scraping.registry import ScraperRegistry

logger = structlog.get_logger()


@ScraperRegistry.register("IL", "zap")
class ZapScraper(BaseScraper):
    """Scraper for zap.co.il price comparison site."""

    def __init__(self, config: Optional[ScraperConfig] = None):
        if config is None:
            config = ScraperConfig(
                name="zap",
                base_url="https://www.zap.co.il",
                search_path="/search.aspx?keyword={query}",
                priority=1,
            )
        super().__init__(config)

    async def search(self, query: str, max_results: int = 10) -> list[PriceOption]:
        """Search for products on zap.co.il.

        Args:
            query: Product search query
            max_results: Maximum number of results to return

        Returns:
            List of PriceOption objects
        """
        search_url = f"{self.base_url}/search.aspx?keyword={quote(query)}"
        logger.info("Searching zap.co.il", query=query, url=search_url)

        results = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            try:
                await page.goto(search_url, wait_until="networkidle", timeout=30000)

                # Wait for results to load
                await page.wait_for_selector(".ProductBox, .product-item", timeout=10000)

                # Get page content
                content = await page.content()
                soup = BeautifulSoup(content, "lxml")

                # Find product items (zap.co.il structure)
                products = soup.select(".ProductBox, .product-item")[:max_results]

                for product in products:
                    try:
                        result = self._parse_product(product, query)
                        if result:
                            results.append(result)
                    except Exception as e:
                        logger.warning("Failed to parse product", error=str(e))

            except Exception as e:
                logger.error("Search failed", error=str(e))
            finally:
                await browser.close()

        logger.info("Search complete", query=query, results=len(results))
        return results

    def _parse_product(self, product_elem, query: str) -> Optional[PriceOption]:
        """Parse a product element from search results."""
        # Extract product name
        name_elem = product_elem.select_one(".ProductName, .product-name, h3 a")
        if not name_elem:
            return None

        product_name = name_elem.get_text(strip=True)

        # Extract price
        price_elem = product_elem.select_one(".ProductPrice, .price, .PriceNum")
        if not price_elem:
            return None

        price_text = price_elem.get_text(strip=True)
        price = self._parse_price(price_text)
        if not price:
            return None

        # Extract seller info
        seller_elem = product_elem.select_one(".StoreName, .seller-name, .merchant")
        seller_name = seller_elem.get_text(strip=True) if seller_elem else "Unknown Seller"

        # Extract product URL
        link_elem = product_elem.select_one("a[href]")
        product_url = ""
        if link_elem and link_elem.get("href"):
            product_url = urljoin(self.base_url, link_elem["href"])

        # Create seller info
        seller = SellerInfo(
            name=seller_name,
            website=product_url,
            country="IL",
            source="scraped",
        )

        return PriceOption(
            product_id=query,  # Will be updated later
            seller=seller,
            listed_price=price,
            currency="ILS",
            url=product_url,
            scraped_at=datetime.now(),
        )

    def _parse_price(self, price_text: str) -> Optional[float]:
        """Parse price from text like '₪1,234' or '1234 ש"ח'."""
        # Remove currency symbols and whitespace
        cleaned = re.sub(r"[₪,\s]|ש\"ח", "", price_text)

        try:
            return float(cleaned)
        except ValueError:
            return None

    async def get_seller_details(self, seller_url: str) -> Optional[SellerInfo]:
        """Get detailed seller information from their page on zap."""
        logger.info("Getting seller details", url=seller_url)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            try:
                await page.goto(seller_url, wait_until="networkidle", timeout=30000)
                content = await page.content()
                soup = BeautifulSoup(content, "lxml")

                # Try to find seller name
                name_elem = soup.select_one(".StoreName, .merchant-name, h1")
                name = name_elem.get_text(strip=True) if name_elem else "Unknown"

                # Try to find seller website
                website_elem = soup.select_one('a[href*="http"]:not([href*="zap.co.il"])')
                website = website_elem.get("href") if website_elem else None

                # Try to find phone number
                phone = await self._find_phone_on_page(page)

                return SellerInfo(
                    name=name,
                    website=website,
                    whatsapp_number=phone,
                    country="IL",
                    source="scraped",
                )

            except Exception as e:
                logger.error("Failed to get seller details", error=str(e))
                return None
            finally:
                await browser.close()

    async def extract_contact_info(self, seller_url: str) -> Optional[str]:
        """Extract phone/WhatsApp number from seller's website."""
        logger.info("Extracting contact info", url=seller_url)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            try:
                await page.goto(seller_url, wait_until="networkidle", timeout=30000)
                return await self._find_phone_on_page(page)

            except Exception as e:
                logger.error("Failed to extract contact", error=str(e))
                return None
            finally:
                await browser.close()

    async def _find_phone_on_page(self, page: Page) -> Optional[str]:
        """Find phone numbers on the current page."""
        content = await page.content()

        # Israeli phone patterns
        patterns = [
            r"05\d[\s-]?\d{3}[\s-]?\d{4}",  # Mobile: 05X-XXX-XXXX
            r"0[2-9][\s-]?\d{7}",  # Landline: 0X-XXXXXXX
            r"\+972[\s-]?5\d[\s-]?\d{3}[\s-]?\d{4}",  # International mobile
            r"\+972[\s-]?[2-9][\s-]?\d{7}",  # International landline
        ]

        for pattern in patterns:
            matches = re.findall(pattern, content)
            if matches:
                # Clean up the first match
                phone = re.sub(r"[\s-]", "", matches[0])
                # Normalize to international format
                if phone.startswith("0"):
                    phone = "+972" + phone[1:]
                return phone

        # Also check for WhatsApp links
        wa_pattern = r'wa\.me/(\d+)'
        wa_matches = re.findall(wa_pattern, content)
        if wa_matches:
            return "+" + wa_matches[0]

        return None
