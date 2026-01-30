"""Google Search scraper for organic results using SerpAPI."""

import asyncio
import re
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import httpx
import structlog

from playwright.async_api import async_playwright, Page

from src.config.settings import settings
from src.state.models import PriceOption, SellerInfo
from src.tools.scraping.base_scraper import BaseScraper, ScraperConfig
from src.tools.scraping.filters import is_relevant_product
from src.tools.scraping.http_client import get_http_client
from src.tools.scraping.price_extractor import get_price_extractor
from src.tools.scraping.registry import ScraperRegistry
from src.observability import record_scrape, record_price_extraction, record_contact_extraction

logger = structlog.get_logger()

SERPAPI_BASE_URL = "https://serpapi.com/search.json"
MAX_RETRIES = 5
INITIAL_RETRY_DELAY = 1.0  # seconds (will backoff: 1, 2, 4, 8, 16)


# NOTE: This SerpAPI-based scraper is deprecated.
# Use google_search_direct.py instead (no API key needed).
# Keeping this file for reference only.

class GoogleSearchScraperSerpAPI(BaseScraper):
    """Scraper for Google organic search results via SerpAPI."""

    def __init__(self, config: Optional[ScraperConfig] = None):
        if config is None:
            config = ScraperConfig(
                name="google_search",
                base_url="https://www.google.co.il",
                search_path="/search?q={query}",
                priority=10,  # Lowest priority, use as fallback
            )
        super().__init__(config)

    async def search(self, query: str, max_results: int = 10) -> list[PriceOption]:
        """Search Google for organic results from ecommerce sites.

        Args:
            query: Product search query
            max_results: Maximum number of results to return

        Returns:
            List of PriceOption objects from ecommerce sites
        """
        if not settings.serpapi_key:
            logger.warning("SerpAPI key not configured, skipping Google Search")
            return []

        # Enhance query to target ecommerce
        search_query = f"{query} buy israel price"
        logger.info("Searching Google", query=search_query)

        params = {
            "engine": "google",
            "q": search_query,
            "location": "Israel",
            "gl": "il",
            "hl": "he",
            "api_key": settings.serpapi_key,
            "num": 30,  # Request more to filter for ecommerce
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

                    organic_results = data.get("organic_results", [])
                    logger.info("Got Google organic results", count=len(organic_results))

                    for item in organic_results:
                        try:
                            result = await self._parse_organic_result(item, query)
                            if result:
                                results.append(result)
                                if len(results) >= max_results:
                                    break
                        except Exception as e:
                            logger.warning("Failed to parse organic result", error=str(e))

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
                    logger.error("Google Search failed", error=str(e))
                    break

        logger.info("Google Search complete", query=query, results=len(results))
        return results

    async def _parse_organic_result(
        self, item: dict, query: str
    ) -> Optional[PriceOption]:
        """Parse a single organic result from SerpAPI.

        Args:
            item: Organic result dict from SerpAPI
            query: Original search query for relevance checking

        Returns:
            PriceOption or None if not relevant
        """
        link = item.get("link", "")
        if not link or not link.startswith("http"):
            return None

        title = item.get("title", "")
        if not title:
            return None

        # Check relevance - filter out near-matches
        if not is_relevant_product(query, title, strict_model_match=True):
            logger.debug("Filtered irrelevant product", query=query, product=title)
            return None

        # Try to extract price from snippet or by fetching the page
        snippet = item.get("snippet", "")
        price = self._extract_price_from_text(snippet)

        # If no price in snippet, try to fetch the page
        if not price:
            try:
                price = await self._fetch_price_from_page(link)
            except Exception as e:
                logger.debug("Could not fetch price from page", url=link, error=str(e))

        # Skip results without price
        if not price:
            return None

        # Get seller name from domain
        parsed = urlparse(link)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        seller_name = domain.replace(".co.il", "").replace(".", " ").title()

        seller = SellerInfo(
            name=seller_name,
            website=link,
            country="IL",
            source="google_search",
        )

        return PriceOption(
            product_id=query,
            seller=seller,
            listed_price=price,
            currency="ILS",
            url=link,
            scraped_at=datetime.now(),
        )

    def _extract_price_from_text(self, text: str) -> Optional[float]:
        """Extract price from text content.

        When multiple prices are found, uses heuristics to select the most likely
        product price (not shipping costs, review counts, or warranty periods).

        All prices must be >= 50 ILS to filter false positives.
        """
        if not text:
            return None

        # Words that indicate the FOLLOWING number is NOT a product price
        # Only check these in the context BEFORE the price
        exclusion_keywords = [
            # Shipping/delivery (Hebrew and English)
            "משלוח", "שילוח", "delivery", "shipping", "הובלה",
            # Free threshold
            "מעל", "above", "over",
            # Up to
            "עד",
        ]

        # Price number pattern: handles both comma-formatted and plain numbers
        price_num = r"([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)"

        patterns = [
            rf"₪\s*{price_num}",  # ₪1,234 or ₪1234
            rf"{price_num}\s*₪",  # 1,234₪ or 1234₪
            rf'{price_num}\s*ש["\']?ח',  # 1,234 ש"ח
            rf"ILS\s*{price_num}",  # ILS 1,234
            rf"(?:ממחיר|החל מ|מחיר|price|במחיר)[:\s]*₪?\s*{price_num}",  # Hebrew/English prefixes
        ]

        # Collect all valid prices with their positions
        price_candidates = []
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                price_str = match.group(1).replace(",", "")
                try:
                    price = float(price_str)
                    # Sanity check: price should be reasonable (50-1,000,000 ILS)
                    if 50 <= price <= 1_000_000:
                        # Check context BEFORE the price (20 chars)
                        before_start = max(0, match.start() - 20)
                        before_context = text[before_start:match.start()].lower()

                        # Exclude if preceded by shipping/threshold keywords
                        prefix_excluded = any(kw in before_context for kw in exclusion_keywords)

                        if not prefix_excluded:
                            price_candidates.append(price)
                except ValueError:
                    continue

        # Also exclude bare numbers followed by specific keywords (not currency-marked)
        # Pattern for numbers NOT preceded by currency but followed by exclusion terms
        bare_number = r"(?<!₪)(?<!ILS)\s([0-9]+)\s*(?:תגובות|תגובה|ימי|ימים|תשלומים)"
        for match in re.finditer(bare_number, text, re.IGNORECASE):
            try:
                excluded_val = float(match.group(1))
                # Remove this value from candidates if present
                price_candidates = [p for p in price_candidates if abs(p - excluded_val) > 1]
            except ValueError:
                pass

        if not price_candidates:
            return None

        # If only one price found, return it
        if len(price_candidates) == 1:
            return price_candidates[0]

        # Multiple prices found - return the largest (usually the product price)
        return max(price_candidates)

    async def _fetch_price_from_page(self, url: str) -> Optional[float]:
        """Fetch page and extract price using multi-strategy extractor.

        First tries fast HTTP client. If that fails (common for JS-rendered SPAs),
        falls back to Playwright for full page rendering.

        Args:
            url: Page URL to fetch

        Returns:
            Extracted price or None
        """
        extractor = get_price_extractor()

        # First try fast HTTP client
        client = get_http_client()
        response = await client.get(url)

        if response:
            # Record the scrape
            await record_scrape(cached=False)

            result = extractor.extract(response.text, url)
            if result:
                await record_price_extraction(success=True)
                return result.price

        # Fallback to Playwright for JS-rendered pages
        logger.debug("HTTP extraction failed, trying Playwright", url=url)
        from src.tools.scraping.playwright_client import get_rendered_html

        html = await get_rendered_html(url)
        if html:
            await record_scrape(cached=False)
            result = extractor.extract(html, url)
            if result:
                await record_price_extraction(success=True)
                logger.info("Price extracted via Playwright", url=url, price=result.price)
                return result.price

        # Record failure
        await record_price_extraction(success=False)
        return None

    async def get_seller_details(self, seller_url: str) -> Optional[SellerInfo]:
        """Get detailed seller information."""
        return None

    async def extract_contact_info(
        self, seller_url: str, seller_name: Optional[str] = None
    ) -> Optional[str]:
        """Extract phone/WhatsApp number from seller's page.

        Handles both direct seller URLs and Google Shopping redirect URLs.
        For Google URLs, first extracts the actual seller URL, then scrapes that.

        Uses database cache to avoid re-scraping known sellers.

        Args:
            seller_url: URL to extract contact from
            seller_name: Optional seller name for caching

        Returns:
            Phone number in international format, or None
        """
        if not seller_url or not seller_url.startswith("http"):
            return None

        # Check if this is a Google Shopping URL - need to extract real seller URL first
        actual_url = seller_url
        if "google.com/search" in seller_url and "ibp=oshop" in seller_url:
            logger.info("Extracting seller URL from Google Shopping page", url=seller_url)
            actual_url = await self._extract_seller_url_from_google(seller_url)
            if not actual_url:
                logger.warning("Could not extract seller URL from Google page", url=seller_url)
                return None
            logger.info("Found actual seller URL", seller_url=actual_url)

        # Check database cache first
        cached_contact = await self._get_cached_contact(actual_url)
        if cached_contact:
            logger.info("Using cached contact", url=actual_url, contact=cached_contact)
            await record_scrape(cached=True)
            await record_contact_extraction(success=True)
            return cached_contact

        # Not in cache - scrape the page
        contact = await self._scrape_contact_from_page(actual_url)
        await record_scrape(cached=False)
        await record_contact_extraction(success=contact is not None)

        # Store in database cache if found
        if contact:
            await self._cache_contact(actual_url, contact, seller_name)

        return contact

    async def _get_cached_contact(self, url: str) -> Optional[str]:
        """Check database for cached contact info.

        Args:
            url: Website URL

        Returns:
            Cached contact or None
        """
        try:
            from src.db.session import get_db_session
            from src.db.repository.sellers import SellerRepository

            async with get_db_session() as session:
                repo = SellerRepository(session)
                return await repo.get_contact_by_url(url)
        except Exception as e:
            logger.debug("Failed to check contact cache", error=str(e))
            return None

    async def _cache_contact(
        self, url: str, contact: str, seller_name: Optional[str] = None
    ) -> None:
        """Store contact info in database cache.

        Args:
            url: Website URL
            contact: Phone/WhatsApp number
            seller_name: Optional seller name
        """
        try:
            from src.db.session import get_db_session
            from src.db.repository.sellers import SellerRepository

            # Extract seller name from domain if not provided
            if not seller_name:
                from urllib.parse import urlparse

                parsed = urlparse(url)
                domain = parsed.netloc.lower()
                if domain.startswith("www."):
                    domain = domain[4:]
                seller_name = domain.replace(".co.il", "").replace(".", " ").title()

            async with get_db_session() as session:
                repo = SellerRepository(session)
                await repo.create_or_update(
                    seller_name=seller_name,
                    website_url=url,
                    whatsapp_number=contact,
                )
                logger.info(
                    "Cached seller contact",
                    seller=seller_name,
                    contact=contact,
                )
        except Exception as e:
            logger.warning("Failed to cache contact", error=str(e))

    async def _scrape_contact_from_page(self, url: str) -> Optional[str]:
        """Scrape contact info from a seller page.

        Priority order:
        1. WhatsApp button/link (most reliable)
        2. Dynamic WhatsApp button (JS redirect - use Playwright click)
        3. Phone number patterns in HTML

        Args:
            url: Page URL to scrape

        Returns:
            Phone number or None
        """
        # Try Playwright first for JS-rendered pages and WhatsApp button clicks
        # Try multiple browsers in case one crashes
        browsers_to_try = ['chromium', 'firefox', 'webkit']

        for browser_type in browsers_to_try:
            try:
                logger.info("Extracting contact info with Playwright", url=url, browser=browser_type)
                async with async_playwright() as p:
                    browser_launcher = getattr(p, browser_type)
                    browser = await browser_launcher.launch(headless=True)
                    page = await browser.new_page()

                    try:
                        await page.goto(url, wait_until="networkidle", timeout=30000)

                        # Step 1: Try to find WhatsApp number from links/buttons (FIRST PRIORITY)
                        whatsapp_number = await self._extract_whatsapp_from_page(page)
                        if whatsapp_number:
                            logger.info("Found WhatsApp number from button/link", number=whatsapp_number)
                            return whatsapp_number

                        # Step 2: Try clicking WhatsApp buttons to get dynamic redirect
                        whatsapp_number = await self._click_whatsapp_button(page)
                        if whatsapp_number:
                            logger.info("Found WhatsApp number from button click", number=whatsapp_number)
                            return whatsapp_number

                        # Step 3: Fallback to phone patterns in HTML
                        result = await self._find_phone_on_page(page)
                        if result:
                            return result
                    finally:
                        await browser.close()

                    # If we got here without returning, try next browser
                    break

            except Exception as e:
                logger.debug("Playwright failed with browser", browser=browser_type, url=url, error=str(e))
                continue

        # Fallback to HTTP client
        try:
            logger.info("Extracting contact info with HTTP client", url=url)
            client = get_http_client()
            response = await client.get(url)
            if response:
                # Try WhatsApp patterns first, then phone patterns
                whatsapp = self._find_whatsapp_in_html(response.text)
                if whatsapp:
                    return whatsapp
                return self._find_phone_in_html(response.text)
        except Exception as e:
            logger.warning("HTTP client also failed", url=url, error=str(e))

        return None

    async def _extract_whatsapp_from_page(self, page: Page) -> Optional[str]:
        """Extract WhatsApp number from links and buttons on page.

        Looks for:
        - Direct wa.me links
        - api.whatsapp.com links
        - data-phone or data-whatsapp attributes
        - WhatsApp widget configurations

        Args:
            page: Playwright page object

        Returns:
            Phone number in international format, or None
        """
        try:
            # Method 1: Look for wa.me or api.whatsapp.com links
            whatsapp_links = await page.evaluate("""
                () => {
                    const links = [];

                    // Find all anchor tags with WhatsApp URLs
                    document.querySelectorAll('a[href*="wa.me"], a[href*="whatsapp.com"], a[href*="whatsapp"]').forEach(a => {
                        links.push(a.href);
                    });

                    // Find onclick handlers with WhatsApp URLs
                    document.querySelectorAll('[onclick*="wa.me"], [onclick*="whatsapp"]').forEach(el => {
                        links.push(el.getAttribute('onclick'));
                    });

                    // Find data attributes with phone numbers
                    document.querySelectorAll('[data-phone], [data-whatsapp], [data-number]').forEach(el => {
                        const phone = el.dataset.phone || el.dataset.whatsapp || el.dataset.number;
                        if (phone) links.push(phone);
                    });

                    // Look for WhatsApp widget scripts/configs
                    const scripts = document.querySelectorAll('script');
                    scripts.forEach(script => {
                        const content = script.textContent || '';
                        // Look for phone numbers in WhatsApp widget configs
                        const phoneMatch = content.match(/['"](\\+?972[0-9]{9}|05[0-9]{8})['"]/);
                        if (phoneMatch) links.push(phoneMatch[1]);

                        // Look for wa.me URLs in scripts
                        const waMatch = content.match(/wa\\.me\\/(\\d+)/);
                        if (waMatch) links.push(waMatch[1]);
                    });

                    return links;
                }
            """)

            # Extract phone numbers from the found links
            for link in whatsapp_links:
                phone = self._extract_phone_from_whatsapp_link(str(link))
                if phone:
                    return phone

        except Exception as e:
            logger.debug("Failed to extract WhatsApp from page", error=str(e))

        return None

    async def _click_whatsapp_button(self, page: Page) -> Optional[str]:
        """Click WhatsApp button and capture redirect URL.

        For sites with dynamic WhatsApp buttons that use JavaScript redirects.

        Args:
            page: Playwright page object

        Returns:
            Phone number extracted from redirect URL, or None
        """
        try:
            # Find WhatsApp button candidates
            whatsapp_selectors = [
                # Common WhatsApp button selectors
                '[class*="whatsapp"]',
                '[class*="Whatsapp"]',
                '[class*="WhatsApp"]',
                '[id*="whatsapp"]',
                '[id*="Whatsapp"]',
                'a[href*="whatsapp"]',
                'button[class*="whatsapp"]',
                # Image-based buttons
                'img[src*="whatsapp"]',
                'img[alt*="whatsapp"]',
                'img[alt*="WhatsApp"]',
                # Common widget classes
                '.wa-widget',
                '.whatsapp-widget',
                '.whatsapp-button',
                '.wa-button',
                '.floating-wpp',
                '#whatsapp-button',
                '.wh-widget',
            ]

            for selector in whatsapp_selectors:
                try:
                    button = page.locator(selector).first
                    if await button.count() > 0:
                        # Set up navigation listener
                        async with page.expect_popup(timeout=5000) as popup_info:
                            await button.click(timeout=3000)

                        popup = await popup_info.value
                        popup_url = popup.url

                        # Extract phone from the popup URL
                        phone = self._extract_phone_from_whatsapp_link(popup_url)
                        if phone:
                            await popup.close()
                            return phone
                        await popup.close()

                except Exception:
                    # Try next selector
                    continue

            # Try clicking and intercepting navigation instead of popup
            for selector in whatsapp_selectors:
                try:
                    button = page.locator(selector).first
                    if await button.count() > 0:
                        # Set up request interception
                        captured_url = None

                        async def capture_request(route):
                            nonlocal captured_url
                            url = route.request.url
                            if 'wa.me' in url or 'whatsapp.com' in url:
                                captured_url = url
                            await route.continue_()

                        await page.route('**/*', capture_request)

                        try:
                            await button.click(timeout=3000)
                            await page.wait_for_timeout(2000)  # Wait for redirect

                            if captured_url:
                                phone = self._extract_phone_from_whatsapp_link(captured_url)
                                if phone:
                                    return phone
                        finally:
                            await page.unroute('**/*')

                except Exception:
                    continue

        except Exception as e:
            logger.debug("Failed to click WhatsApp button", error=str(e))

        return None

    def _extract_phone_from_whatsapp_link(self, link: str) -> Optional[str]:
        """Extract phone number from WhatsApp link or URL.

        Handles:
        - wa.me/972501234567
        - api.whatsapp.com/send?phone=972501234567
        - whatsapp://send?phone=972501234567

        Args:
            link: WhatsApp URL or link text

        Returns:
            Phone in +XXX format, or None
        """
        if not link:
            return None

        # Pattern for wa.me links
        wa_me_match = re.search(r'wa\.me/(\d+)', link)
        if wa_me_match:
            phone = wa_me_match.group(1)
            if not phone.startswith('+'):
                phone = '+' + phone
            return phone

        # Pattern for api.whatsapp.com links
        api_match = re.search(r'whatsapp\.com/send\?phone=(\d+)', link)
        if api_match:
            phone = api_match.group(1)
            if not phone.startswith('+'):
                phone = '+' + phone
            return phone

        # Pattern for whatsapp:// protocol
        protocol_match = re.search(r'whatsapp://send\?phone=(\d+)', link)
        if protocol_match:
            phone = protocol_match.group(1)
            if not phone.startswith('+'):
                phone = '+' + phone
            return phone

        # Try to find bare phone number (if link is just a number)
        bare_match = re.match(r'^\+?(\d{10,15})$', link.strip())
        if bare_match:
            phone = bare_match.group(1)
            if not phone.startswith('+'):
                phone = '+' + phone
            return phone

        return None

    def _find_whatsapp_in_html(self, html: str) -> Optional[str]:
        """Find WhatsApp links in HTML content.

        Args:
            html: HTML content

        Returns:
            Phone number in international format, or None
        """
        # Look for wa.me links and common WhatsApp widget patterns
        wa_patterns = [
            # Direct WhatsApp links
            r'wa\.me/(\d+)',
            r'api\.whatsapp\.com/send\?phone=(\d+)',
            r'whatsapp://send\?phone=(\d+)',
            # Data attributes
            r'data-phone=["\'](\+?\d+)["\']',
            r'data-whatsapp=["\'](\+?\d+)["\']',
            r'data-number=["\'](\+?\d+)["\']',
            r'data-wa-number=["\'](\+?\d+)["\']',
            # Common WhatsApp widget configurations (in scripts)
            r'whatsapp["\']?\s*:\s*["\'](\+?\d+)["\']',
            r'phone["\']?\s*:\s*["\'](\+?972\d+)["\']',
            r'phoneNumber["\']?\s*:\s*["\'](\+?\d+)["\']',
            r'whatsappNumber["\']?\s*:\s*["\'](\+?\d+)["\']',
            # Hebrew site patterns
            r'href=["\']tel:(\+?972\d+)["\']',
            r'href=["\']tel:(05\d{8})["\']',
            # Widget scripts with phone in URL
            r'widget.*?(\d{10,12})',
            # JSON config in scripts
            r'"phone"\s*:\s*"(\+?972\d+)"',
            r'"whatsapp"\s*:\s*"(\+?972\d+)"',
        ]

        for pattern in wa_patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                phone = match.group(1)
                # Clean up the phone number
                phone = re.sub(r'[\s\-()]', '', phone)
                if not phone.startswith('+'):
                    # If it starts with 972, add +
                    if phone.startswith('972'):
                        phone = '+' + phone
                    # If it starts with 0, convert to +972
                    elif phone.startswith('0'):
                        phone = '+972' + phone[1:]
                    else:
                        phone = '+' + phone
                return phone

        return None

    async def _extract_seller_url_from_google(self, google_url: str) -> Optional[str]:
        """Extract the actual seller website URL from a Google Shopping page.

        Args:
            google_url: Google Shopping product URL

        Returns:
            The actual seller website URL, or None if not found
        """
        try:
            # Use direct httpx without compression to avoid decoding issues
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "he,en;q=0.9",
            }

            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(google_url, headers=headers)

                if response.status_code != 200:
                    logger.warning("Google Shopping page returned non-200", status=response.status_code)
                    return None

                html = response.text

                # Look for seller website links in the HTML
                # Pattern: href to non-google .co.il or .com domains
                pattern = r'href="(https?://(?:www\.)?(?!google)[a-zA-Z0-9-]+\.(?:co\.il|com|net)/[^"]*)"'
                matches = re.findall(pattern, html)

                if matches:
                    # Return the first valid seller URL (filter out tracking/ad URLs)
                    for url in matches:
                        # Skip Google URLs and common non-seller URLs
                        if "google" not in url and "gstatic" not in url and "youtube" not in url:
                            logger.info("Found seller URL from Google page", seller_url=url[:80])
                            return url

                logger.debug("No seller URL found in Google page", url_count=len(matches))

        except Exception as e:
            logger.warning("Failed to extract seller URL from Google", error=str(e))

        return None

    async def _find_phone_on_page(self, page: Page) -> Optional[str]:
        """Find phone numbers on the current page."""
        content = await page.content()
        return self._find_phone_in_html(content)

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
