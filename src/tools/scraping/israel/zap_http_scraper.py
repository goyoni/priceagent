"""HTTP-based scraper for zap.co.il - no browser required."""

import asyncio
import re
from datetime import datetime
from typing import Optional
from urllib.parse import quote, urljoin

import httpx
from bs4 import BeautifulSoup
import structlog

from src.state.models import PriceOption, SellerInfo
from src.tools.scraping.base_scraper import BaseScraper, ScraperConfig
from src.tools.scraping.http_client import get_http_client, BROWSER_HEADERS
from src.tools.scraping.registry import ScraperRegistry

logger = structlog.get_logger()

# Known aggregator/affiliate domains that should be followed through to the actual seller
AGGREGATOR_DOMAINS = {
    "zap.co.il",  # Israel's main price comparison site
}

# Simpler headers that work better with zap.co.il (avoids anti-bot triggers)
ZAP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "he,en;q=0.9",
}


@ScraperRegistry.register("IL", "zap_http")
class ZapHttpScraper(BaseScraper):
    """HTTP-based scraper for zap.co.il - more reliable than Playwright."""

    def __init__(self, config: Optional[ScraperConfig] = None):
        if config is None:
            config = ScraperConfig(
                name="zap_http",
                base_url="https://www.zap.co.il",
                search_path="/search.aspx?keyword={query}",
                priority=0,  # Higher priority than Playwright version
            )
        super().__init__(config)

    async def search(self, query: str, max_results: int = 10) -> list[PriceOption]:
        """Search for products on zap.co.il using HTTP requests.

        Args:
            query: Product search query
            max_results: Maximum number of results to return

        Returns:
            List of PriceOption objects
        """
        search_url = f"{self.base_url}/search.aspx?keyword={quote(query)}"
        logger.info("Searching zap.co.il (HTTP)", query=query, url=search_url)

        results = []

        async with httpx.AsyncClient(
            headers=ZAP_HEADERS,
            follow_redirects=True,
            timeout=30.0,
        ) as client:
            try:
                response = await client.get(search_url)
                response.raise_for_status()

                soup = BeautifulSoup(response.text, "lxml")

                # Check if we were redirected to a product detail page
                final_url = str(response.url)
                if "model.aspx" in final_url:
                    logger.info("Redirected to product page", url=final_url)
                    results = self._parse_product_page(soup, query, final_url, max_results)
                else:
                    # Regular search results page
                    products = soup.select(".product-box.ModelRow.Product")[:max_results]
                    logger.info("Found product elements", count=len(products))

                    for product in products:
                        try:
                            result = self._parse_product(product, query)
                            if result:
                                results.append(result)
                        except Exception as e:
                            logger.warning("Failed to parse product", error=str(e))

                    # If no products found with primary selectors, try API
                    if not results:
                        results = await self._try_api_search(client, query, max_results)

                # Resolve all ZAP redirect URLs to actual seller URLs
                if results:
                    results = await self._batch_resolve_urls(client, results)

            except httpx.HTTPStatusError as e:
                logger.error("HTTP error searching zap.co.il", status=e.response.status_code, error=str(e))
                raise
            except Exception as e:
                logger.error("Search failed", error=str(e))
                raise

        logger.info("Search complete (HTTP)", query=query, results=len(results))
        return results

    def _parse_product_page(self, soup: BeautifulSoup, query: str, page_url: str, max_results: int) -> list[PriceOption]:
        """Parse a product detail page with seller listings."""
        results = []

        # Extract product name from title
        title_elem = soup.select_one("title")
        product_name = title_elem.get_text().split(" - ")[0] if title_elem else query

        # Primary: Find seller listings from compare table (has all stores with prices)
        compare_rows = soup.select(".compare-item-row.product-item")
        if compare_rows:
            logger.info("Found compare-item rows", count=len(compare_rows))
            for row in compare_rows[:max_results]:
                try:
                    result = self._parse_compare_row(row, query, page_url)
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.warning("Failed to parse compare row", error=str(e))

        # Fallback: Try bid-row elements (featured sellers)
        if not results:
            bid_rows = soup.select(".bid-row")[:max_results]
            logger.info("Found seller listings (bid-row)", count=len(bid_rows))

            for bid in bid_rows:
                try:
                    result = self._parse_bid_row(bid, query, page_url)
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.warning("Failed to parse bid row", error=str(e))

        # Last fallback: BuyBox for main price
        if not results:
            buybox = soup.select_one(".BuyBox")
            if buybox:
                price_elem = buybox.select_one("[class*='price']")
                if price_elem:
                    price = self._parse_price(price_elem.get_text())
                    if price:
                        store_elem = buybox.select_one("[class*='store'], [class*='Shop']")
                        store_name = store_elem.get_text(strip=True)[:50] if store_elem else "Zap.co.il"

                        seller = SellerInfo(
                            name=store_name,
                            website=page_url,
                            country="IL",
                            source="zap",
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

    def _parse_compare_row(self, row, query: str, page_url: str) -> Optional[PriceOption]:
        """Parse a compare-item-row element."""
        # Get store name - check row attributes first, then child elements
        store_name = row.get("data-site-name")
        if not store_name:
            store_elem = row.select_one("[data-site-name]")
            store_name = store_elem.get("data-site-name") if store_elem else None
        if not store_name:
            return None

        # Get store rating - check row attributes first
        rating = None
        rating_str = row.get("data-site-rate")
        if rating_str:
            try:
                rating = float(rating_str)
            except ValueError:
                pass

        # Get price - try data attribute first (most reliable), then .price element
        price = None
        price_str = row.get("data-product-price") or row.get("data-min-price")
        if price_str:
            price = self._parse_price(price_str)

        if not price:
            price_elem = row.select_one(".price")
            if price_elem:
                price = self._parse_price(price_elem.get_text())

        if not price:
            return None

        # Try to extract the actual seller link
        seller_url = page_url  # Fallback to product page

        # First, look for the "לפרטים נוספים" (For more details) button - this leads to actual product page
        all_links = row.select("a[href]")
        for link in all_links:
            link_text = link.get_text(strip=True)
            if "לפרטים נוספים" in link_text or "פרטים נוספים" in link_text:
                href = link.get("href", "")
                if href.startswith("/"):
                    seller_url = f"{self.base_url}{href}"
                elif href.startswith("http"):
                    seller_url = href
                if seller_url != page_url:
                    logger.debug("Found 'לפרטים נוספים' button", url=seller_url)
                    break

        # If not found, look for buy/redirect links (common patterns on zap.co.il)
        if seller_url == page_url:
            link_selectors = [
                "a.go-to-store",
                "a.buy-btn",
                "a.store-link",
                "a[href*='/redir/']",  # Zap redirect links
                "a[href*='redirect']",
                ".store-name a",
                ".StoreName a",
                "a[data-site-name]",
                "a.btn",  # Generic button links
                "a[onclick*='redir']",  # Links with onclick handlers
            ]

            for selector in link_selectors:
                link_elem = row.select_one(selector)
                if link_elem and link_elem.get("href"):
                    href = link_elem["href"]
                    if href.startswith("/"):
                        seller_url = f"{self.base_url}{href}"
                        break
                    elif href.startswith("http"):
                        seller_url = href
                        break

        # If no link found, check for data attributes that might contain URLs
        if seller_url == page_url:
            # Check for data-url, data-redirect, data-href attributes
            for attr in ["data-url", "data-redirect", "data-href", "data-link"]:
                url_val = row.get(attr)
                if url_val:
                    if url_val.startswith("/"):
                        seller_url = f"{self.base_url}{url_val}"
                        break
                    elif url_val.startswith("http"):
                        seller_url = url_val
                        break

        # If still no link found, try any link in the row
        if seller_url == page_url:
            any_link = row.select_one("a[href]")
            if any_link and any_link.get("href"):
                href = any_link["href"]
                if href.startswith("/") and not href.startswith("/search"):
                    seller_url = f"{self.base_url}{href}"
                elif href.startswith("http"):
                    seller_url = href

        seller = SellerInfo(
            name=store_name,
            website=seller_url,
            country="IL",
            source="zap",
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

    def _parse_bid_row(self, bid, query: str, page_url: str) -> Optional[PriceOption]:
        """Parse a bid-row element (featured seller)."""
        # Extract store name - check element attributes first, then data attribute
        store_name = bid.get("data-site-name")
        if not store_name:
            store_elem = bid.select_one("[data-site-name]")
            store_name = store_elem.get("data-site-name") if store_elem else "Unknown"

        # Get store rating - check element attributes first
        rating = None
        rating_str = bid.get("data-site-rate")
        if rating_str:
            try:
                rating = float(rating_str)
            except ValueError:
                pass

        # Extract price - try data attribute first, then .price element
        price = None
        price_str = bid.get("data-product-price") or bid.get("data-min-price")
        if price_str:
            price = self._parse_price(price_str)

        if not price:
            price_elem = bid.select_one(".price")
            if price_elem:
                price = self._parse_price(price_elem.get_text())

        if not price:
            # Fallback: search in text
            all_text = bid.get_text()
            price_match = re.search(r"₪?([\d,]+)", all_text)
            if price_match:
                price = self._parse_price(price_match.group(1))

        if not price or not store_name:
            return None

        # Try to extract the actual seller link
        seller_url = page_url  # Fallback to product page

        # First, look for the "לפרטים נוספים" (For more details) button - this leads to actual product page
        all_links = bid.select("a[href]")
        for link in all_links:
            link_text = link.get_text(strip=True)
            if "לפרטים נוספים" in link_text or "פרטים נוספים" in link_text:
                href = link.get("href", "")
                if href.startswith("/"):
                    seller_url = f"{self.base_url}{href}"
                elif href.startswith("http"):
                    seller_url = href
                if seller_url != page_url:
                    logger.debug("Found 'לפרטים נוספים' button in bid row", url=seller_url)
                    break

        # If not found, look for buy/redirect links
        if seller_url == page_url:
            link_selectors = [
                "a.go-to-store",
                "a.buy-btn",
                "a.store-link",
                "a[href*='/redir/']",
                "a[href*='redirect']",
                ".store-name a",
                "a[data-site-name]",
                "a.btn",
                "a[onclick*='redir']",
            ]

            for selector in link_selectors:
                link_elem = bid.select_one(selector)
                if link_elem and link_elem.get("href"):
                    href = link_elem["href"]
                    if href.startswith("/"):
                        seller_url = f"{self.base_url}{href}"
                        break
                    elif href.startswith("http"):
                        seller_url = href
                        break

        # If no link found, check for data attributes that might contain URLs
        if seller_url == page_url:
            for attr in ["data-url", "data-redirect", "data-href", "data-link"]:
                url_val = bid.get(attr)
                if url_val:
                    if url_val.startswith("/"):
                        seller_url = f"{self.base_url}{url_val}"
                        break
                    elif url_val.startswith("http"):
                        seller_url = url_val
                        break

        # If still no link found, try any link in the row
        if seller_url == page_url:
            any_link = bid.select_one("a[href]")
            if any_link and any_link.get("href"):
                href = any_link["href"]
                if href.startswith("/") and not href.startswith("/search"):
                    seller_url = f"{self.base_url}{href}"
                elif href.startswith("http"):
                    seller_url = href

        seller = SellerInfo(
            name=store_name,
            website=seller_url,
            country="IL",
            source="zap",
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

    async def _try_api_search(self, client: httpx.AsyncClient, query: str, max_results: int) -> list[PriceOption]:
        """Try searching via Zap's API endpoint."""
        results = []

        # Zap sometimes uses an API for search suggestions/results
        api_url = f"https://www.zap.co.il/searchAPI/searchResults?keyword={quote(query)}&pageNo=1"

        try:
            response = await client.get(api_url)
            if response.status_code == 200:
                data = response.json()

                # Parse API response if it's in expected format
                items = data.get("products", data.get("items", []))
                for item in items[:max_results]:
                    try:
                        result = self._parse_api_product(item, query)
                        if result:
                            results.append(result)
                    except Exception as e:
                        logger.warning("Failed to parse API product", error=str(e))
        except Exception as e:
            logger.debug("API search failed, falling back to HTML", error=str(e))

        return results

    def _parse_product(self, product_elem, query: str) -> Optional[PriceOption]:
        """Parse a product element from zap.co.il search results."""
        # Extract product name from img alt or link text
        product_name = None
        img = product_elem.select_one("img[alt]")
        if img and img.get("alt"):
            product_name = img.get("alt").strip()

        if not product_name:
            # Try link text
            link = product_elem.select_one("a[href]")
            if link:
                product_name = link.get_text(strip=True)

        if not product_name:
            return None

        # Validate product relevance - check if query terms appear in product name
        if not self._is_relevant_product(query, product_name):
            logger.debug("Skipping irrelevant product", query=query, product=product_name)
            return None

        # Extract price from .price-wrapper
        price = None
        price_elem = product_elem.select_one(".price-wrapper.product.total, .price-wrapper")
        if price_elem:
            price_text = price_elem.get_text(strip=True)
            price = self._parse_price(price_text)

        if not price:
            return None

        # Extract product URL - the main link in the product box
        product_url = ""
        link_elem = product_elem.select_one("a[href]")
        if link_elem and link_elem.get("href"):
            href = link_elem["href"]
            if href.startswith("/"):
                product_url = f"{self.base_url}{href}"
            elif href.startswith("http"):
                product_url = href
            else:
                product_url = f"{self.base_url}/{href}"

        # Use Zap.co.il as the seller (it aggregates prices)
        seller = SellerInfo(
            name="Zap.co.il",
            website=product_url,
            country="IL",
            source="zap",
        )

        return PriceOption(
            product_id=query,
            seller=seller,
            listed_price=price,
            currency="ILS",
            url=product_url,
            scraped_at=datetime.now(),
        )

    def _parse_api_product(self, item: dict, query: str) -> Optional[PriceOption]:
        """Parse a product from API response."""
        name = item.get("name") or item.get("productName") or item.get("title")
        if not name:
            return None

        price = item.get("price") or item.get("minPrice") or item.get("lowPrice")
        if not price:
            return None

        if isinstance(price, str):
            price = self._parse_price(price)
        if not price:
            return None

        seller_name = item.get("storeName") or item.get("merchantName") or "Unknown Seller"
        product_url = item.get("url") or item.get("productUrl") or ""
        if product_url and product_url.startswith("/"):
            product_url = f"{self.base_url}{product_url}"

        seller = SellerInfo(
            name=seller_name,
            website=product_url,
            country="IL",
            source="zap",
        )

        return PriceOption(
            product_id=query,
            seller=seller,
            listed_price=float(price),
            currency="ILS",
            url=product_url,
            scraped_at=datetime.now(),
        )

    def _parse_price(self, price_text: str) -> Optional[float]:
        """Parse price from text like '₪1,234' or '1234 ש"ח' or 'ממחיר 1,234'."""
        if not price_text:
            return None

        # First try to extract just the numeric part with regex
        # This handles Hebrew prefixes like "ממחיר" (from price), "החל מ" (starting from), etc.
        # Match pattern: optional currency, then digits with optional comma/period separators
        price_patterns = [
            r"₪?\s*([\d,]+(?:\.\d{1,2})?)",  # ₪1,234 or ₪1,234.99
            r"([\d,]+(?:\.\d{1,2})?)\s*(?:₪|ש[\"']?ח|ILS)",  # 1,234₪ or 1,234 ש"ח
            r"(?:ממחיר|החל מ|מחיר|price)[:\s]*([\d,]+(?:\.\d{1,2})?)",  # Hebrew/English prefixes
            r"([\d]{3,}(?:,\d{3})*(?:\.\d{1,2})?)",  # Just numbers with optional commas/decimals
        ]

        for pattern in price_patterns:
            match = re.search(pattern, price_text, re.IGNORECASE)
            if match:
                price_str = match.group(1).replace(",", "")
                try:
                    price = float(price_str)
                    # Sanity check: price should be reasonable (1-1,000,000 ILS)
                    if 1 <= price <= 1_000_000:
                        return price
                except ValueError:
                    continue

        # Fallback: try original simple approach
        cleaned = re.sub(r"[₪,\s]|ש\"ח|ILS", "", price_text)
        try:
            price = float(cleaned)
            if 1 <= price <= 1_000_000:
                return price
        except ValueError:
            pass

        return None

    def _is_aggregator_domain(self, url: str) -> bool:
        """Check if URL belongs to a known aggregator/affiliate domain."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            if domain.startswith("www."):
                domain = domain[4:]
            return any(agg in domain for agg in AGGREGATOR_DOMAINS)
        except Exception:
            return False

    async def _resolve_redirect_url(self, client: httpx.AsyncClient, url: str, max_depth: int = 5) -> str:
        """Follow redirect chains to get actual seller URL.

        Follows through known aggregators (zap.co.il, wisebuy.co.il, etc.)
        until reaching the actual seller website.

        Args:
            client: HTTP client to use for requests
            url: URL that may be a redirect link
            max_depth: Maximum number of redirects to follow

        Returns:
            The actual seller URL after following redirects, or original if can't resolve
        """
        if max_depth <= 0:
            logger.warning("Max redirect depth reached", url=url)
            return url

        current_url = url

        # Keep following redirects until we hit a non-aggregator domain
        for depth in range(max_depth):
            # If current URL is not from an aggregator, we're done
            if not self._is_aggregator_domain(current_url):
                if depth > 0:
                    logger.debug("Resolved to seller URL", from_url=url, to_url=current_url, depth=depth)
                return current_url

            try:
                # For /redir/ style links, use HEAD to get redirect without downloading
                if "/redir/" in current_url or "/redirect" in current_url.lower():
                    response = await client.head(current_url, follow_redirects=False, timeout=10.0)
                    if response.status_code in (301, 302, 303, 307, 308):
                        location = response.headers.get("location", "")
                        if location:
                            if not location.startswith("http"):
                                location = urljoin(current_url, location)
                            logger.debug("Following redirect", from_url=current_url, to_url=location)
                            current_url = location
                            continue

                # Try GET with follow_redirects to handle JavaScript redirects etc.
                response = await client.get(current_url, follow_redirects=True, timeout=10.0)
                final_url = str(response.url)

                # If we ended up at a different URL, check if it's a seller
                if final_url != current_url:
                    if not self._is_aggregator_domain(final_url):
                        logger.debug("Resolved via GET follow", from_url=url, to_url=final_url)
                        return final_url
                    current_url = final_url
                    continue

                # Parse page content to find seller links
                soup = BeautifulSoup(response.text, "lxml")

                # Look for "go to store" type links
                link_selectors = [
                    "a.go-to-store",
                    "a.buy-btn",
                    "a.store-link",
                    "a[href*='/redir/']",
                    "a[href*='/redirect']",
                    ".BuyBox a[href]",
                    ".price-wrapper a[href]",
                    "a.btn-primary",
                    "a.cta-button",
                ]

                for selector in link_selectors:
                    link_elem = soup.select_one(selector)
                    if link_elem and link_elem.get("href"):
                        href = link_elem["href"]
                        if href.startswith("/"):
                            from urllib.parse import urlparse
                            parsed = urlparse(current_url)
                            href = f"{parsed.scheme}://{parsed.netloc}{href}"
                        elif not href.startswith("http"):
                            continue

                        # If this is a new URL, follow it
                        if href != current_url:
                            logger.debug("Found link in page", selector=selector, url=href)
                            current_url = href
                            break
                else:
                    # No links found, check for meta refresh or JavaScript redirects
                    meta_refresh = soup.select_one('meta[http-equiv="refresh"]')
                    if meta_refresh:
                        content = meta_refresh.get("content", "")
                        # Parse: "0;url=https://..."
                        if "url=" in content.lower():
                            redirect_url = content.split("url=", 1)[-1].strip().strip("'\"")
                            if redirect_url.startswith("http"):
                                logger.debug("Found meta refresh", url=redirect_url)
                                current_url = redirect_url
                                continue

                    # Look for any external seller link
                    external_links = soup.select("a[href^='http']")
                    for link in external_links:
                        href = link.get("href", "")
                        if self._is_aggregator_domain(href):
                            continue
                        # Skip common non-seller links
                        skip_domains = ["google.com", "facebook.com", "twitter.com", "youtube.com", "instagram.com", "linkedin.com"]
                        if any(domain in href for domain in skip_domains):
                            continue
                        # Check if this looks like a seller/store link
                        link_text = link.get_text().lower()
                        if any(keyword in link_text for keyword in ["חנות", "store", "buy", "קנה", "לרכישה", "לאתר", "go to"]):
                            logger.debug("Found seller link via text match", url=href)
                            return href

                    # No more redirects found
                    logger.debug("No further redirects found", url=current_url)
                    break

            except Exception as e:
                logger.warning("Failed to resolve redirect", url=current_url, error=str(e))
                break

        return current_url

    async def _batch_resolve_urls(self, client: httpx.AsyncClient, results: list[PriceOption]) -> list[PriceOption]:
        """Batch resolve all redirect URLs in parallel.

        Args:
            client: HTTP client to use for requests
            results: List of PriceOption objects with potential redirect URLs

        Returns:
            List of PriceOption objects with resolved seller URLs
        """

        async def resolve_result(result: PriceOption) -> PriceOption:
            """Resolve a single result's URL."""
            # Resolve any URL from aggregator domains
            if self._is_aggregator_domain(result.url):
                resolved_url = await self._resolve_redirect_url(client, result.url)
                # Only update if we got an actual seller URL (not an aggregator)
                if resolved_url and not self._is_aggregator_domain(resolved_url):
                    result.url = resolved_url
                    result.seller.website = resolved_url
                    logger.debug("Resolved to seller URL", seller=result.seller.name, url=resolved_url)
            return result

        # Resolve all URLs in parallel
        tasks = [resolve_result(result) for result in results]
        resolved_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out failed resolutions, keep original on error
        final_results = []
        for i, resolved in enumerate(resolved_results):
            if isinstance(resolved, Exception):
                logger.warning("URL resolution failed", error=str(resolved))
                final_results.append(results[i])  # Keep original
            else:
                final_results.append(resolved)

        logger.info("Batch URL resolution complete", total=len(results), resolved=len(final_results))
        return final_results

    def _is_relevant_product(self, query: str, product_name: str) -> bool:
        """Check if product name is relevant to the search query.

        This helps filter out "related" products that don't actually match.
        """
        query_lower = query.lower()
        product_lower = product_name.lower()

        # Extract potential model numbers from query (alphanumeric sequences)
        model_patterns = re.findall(r'[a-z0-9]{4,}', query_lower)

        # Check if any significant part of the query appears in product name
        for pattern in model_patterns:
            # For model numbers, require at least first 4-5 chars to match
            if len(pattern) >= 6:
                # Check if first 6 chars of model appear in product
                if pattern[:6] in product_lower:
                    return True
            elif len(pattern) >= 4:
                if pattern in product_lower:
                    return True

        # Check brand names
        brands = ['samsung', 'סמסונג', 'apple', 'אפל', 'sony', 'lg', 'philips', 'bosch']
        query_brands = [b for b in brands if b in query_lower]
        if query_brands:
            # If brand specified in query, it must appear in product
            for brand in query_brands:
                if brand in product_lower:
                    return True
            return False

        # If we had model patterns but none matched, reject the product
        if model_patterns:
            return False

        # If no specific model/brand patterns found, accept the product
        # (this handles generic searches like "מקרר")
        return True

    async def extract_contact_info(self, seller_url: str) -> Optional[str]:
        """Extract phone/WhatsApp number from seller's page."""
        # Validate URL before attempting to fetch
        if not seller_url or not seller_url.startswith("http"):
            logger.debug("Skipping invalid URL for contact extraction", url=seller_url)
            return None

        # Skip aggregator URLs - we need actual seller pages for contact info
        if self._is_aggregator_domain(seller_url):
            logger.debug("Skipping aggregator URL for contact extraction", url=seller_url)
            return None

        logger.info("Extracting contact info (HTTP)", url=seller_url)

        client = get_http_client()
        response = await client.get(seller_url)
        if not response:
            return None

        return self._find_phone_in_html(response.text)

    async def get_seller_details(self, seller_url: str) -> Optional[SellerInfo]:
        """Get detailed seller information from their page."""
        logger.info("Getting seller details (HTTP)", url=seller_url)

        client = get_http_client()
        response = await client.get(seller_url)
        if not response:
            return None

        soup = BeautifulSoup(response.text, "lxml")

        # Extract seller name
        name_elem = soup.select_one(".StoreName, .merchant-name, h1, .shop-name")
        name = name_elem.get_text(strip=True) if name_elem else "Unknown"

        # Extract seller website
        website_elem = soup.select_one('a[href*="http"]:not([href*="zap.co.il"])')
        website = website_elem.get("href") if website_elem else None

        # Extract phone number
        phone = self._find_phone_in_html(response.text)

        return SellerInfo(
            name=name,
            website=website,
            whatsapp_number=phone,
            country="IL",
            source="zap",
        )

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
