"""Playwright-based client for JavaScript-rendered pages."""

import asyncio
from typing import Optional

import structlog
from playwright.async_api import async_playwright

logger = structlog.get_logger()

# Browser fallback order
BROWSERS = ["chromium", "firefox", "webkit"]

# Timeout for page load
PAGE_TIMEOUT = 30000  # 30 seconds


async def get_rendered_html(url: str, wait_for_selector: Optional[str] = None) -> Optional[str]:
    """Fetch page and return fully rendered HTML using Playwright.

    This is used for JavaScript-rendered Single Page Applications (SPAs)
    where prices and other content are loaded dynamically.

    Args:
        url: URL to fetch
        wait_for_selector: Optional CSS selector to wait for before capturing HTML

    Returns:
        Rendered HTML content, or None on failure
    """
    for browser_type in BROWSERS:
        try:
            logger.debug("Fetching with Playwright", url=url, browser=browser_type)
            async with async_playwright() as p:
                browser_launcher = getattr(p, browser_type)
                browser = await browser_launcher.launch(headless=True)

                try:
                    context = await browser.new_context(
                        locale="he-IL",
                        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    )
                    page = await context.new_page()

                    await page.goto(url, wait_until="networkidle", timeout=PAGE_TIMEOUT)

                    # Wait for specific selector if provided
                    if wait_for_selector:
                        try:
                            await page.wait_for_selector(wait_for_selector, timeout=5000)
                        except Exception:
                            pass  # Continue even if selector not found

                    # Wait a bit for any late JS execution
                    await page.wait_for_timeout(1000)

                    html = await page.content()
                    logger.debug("Page rendered successfully", url=url, size=len(html))
                    return html

                finally:
                    await browser.close()

        except Exception as e:
            logger.debug("Playwright failed", browser=browser_type, url=url, error=str(e))
            continue

    logger.warning("All browsers failed to render page", url=url)
    return None


async def extract_price_with_playwright(url: str) -> Optional[float]:
    """Extract price from a JavaScript-rendered page.

    Fetches the page with Playwright, then uses the PriceExtractor
    on the rendered HTML.

    Args:
        url: URL to fetch and extract price from

    Returns:
        Extracted price, or None
    """
    from src.tools.scraping.price_extractor import get_price_extractor

    html = await get_rendered_html(url)
    if not html:
        return None

    extractor = get_price_extractor()
    result = extractor.extract(html, url)

    if result:
        logger.info("Price extracted via Playwright", url=url, price=result.price, method=result.source)
        return result.price

    return None
