"""HTTP-based scraper for alm.co.il using GraphQL API.

ALM uses a React/PWA frontend with Magento GraphQL backend.
Static HTML doesn't contain prices, so we must use the API.
"""

import re
from datetime import datetime
from typing import Optional
from urllib.parse import quote

import httpx
import structlog

from src.state.models import PriceOption, SellerInfo
from src.tools.scraping.base_scraper import BaseScraper, ScraperConfig
from src.tools.scraping.registry import ScraperRegistry

logger = structlog.get_logger()

# ALM GraphQL endpoint
ALM_GRAPHQL_URL = "https://www.alm.co.il/graphql"

# Headers for ALM requests
ALM_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "he,en;q=0.9",
    "Content-Type": "application/json",
    "Store": "default",
}


@ScraperRegistry.register("IL", "alm")
class AlmScraper(BaseScraper):
    """HTTP-based scraper for alm.co.il using GraphQL API."""

    def __init__(self, config: Optional[ScraperConfig] = None):
        if config is None:
            config = ScraperConfig(
                name="alm",
                base_url="https://www.alm.co.il",
                search_path="/catalogsearch/result/?q={query}",
                priority=2,  # After Zap and WiseBuy
            )
        super().__init__(config)

    async def search(self, query: str, max_results: int = 10) -> list[PriceOption]:
        """Search for products on alm.co.il using GraphQL API.

        Args:
            query: Product search query (SKU or product name)
            max_results: Maximum number of results to return

        Returns:
            List of PriceOption objects
        """
        logger.info("Searching alm.co.il", query=query)

        results = []

        async with httpx.AsyncClient(
            headers=ALM_HEADERS,
            timeout=30.0,
        ) as client:
            try:
                # First try exact SKU match
                sku_results = await self._search_by_sku(client, query)
                if sku_results:
                    results.extend(sku_results)

                # If no SKU match, try text search
                if not results:
                    text_results = await self._search_by_text(client, query, max_results)
                    results.extend(text_results)

            except httpx.HTTPStatusError as e:
                logger.error("HTTP error searching alm.co.il", status=e.response.status_code, error=str(e))
            except Exception as e:
                logger.error("Error searching alm.co.il", error=str(e))

        logger.info("ALM search completed", query=query, results=len(results))
        return results[:max_results]

    async def _search_by_sku(self, client: httpx.AsyncClient, sku: str) -> list[PriceOption]:
        """Search for a product by exact SKU match."""
        graphql_query = """
        query ProductsBySku($sku: String!) {
            products(filter: {sku: {eq: $sku}}) {
                items {
                    id
                    name
                    sku
                    url_key
                    price_range {
                        minimum_price {
                            regular_price { value currency }
                            final_price { value currency }
                            discount { amount_off percent_off }
                        }
                    }
                    stock_status
                    small_image { url }
                }
            }
        }
        """

        try:
            response = await client.post(
                ALM_GRAPHQL_URL,
                json={"query": graphql_query, "variables": {"sku": sku}},
            )
            response.raise_for_status()
            data = response.json()

            items = data.get("data", {}).get("products", {}).get("items", [])
            return [self._parse_graphql_item(item) for item in items if item]

        except Exception as e:
            logger.debug("SKU search failed", sku=sku, error=str(e))
            return []

    async def _search_by_text(self, client: httpx.AsyncClient, query: str, max_results: int) -> list[PriceOption]:
        """Search for products by text query."""
        graphql_query = """
        query ProductsBySearch($search: String!, $pageSize: Int!) {
            products(search: $search, pageSize: $pageSize) {
                items {
                    id
                    name
                    sku
                    url_key
                    price_range {
                        minimum_price {
                            regular_price { value currency }
                            final_price { value currency }
                            discount { amount_off percent_off }
                        }
                    }
                    stock_status
                    small_image { url }
                }
                total_count
            }
        }
        """

        try:
            response = await client.post(
                ALM_GRAPHQL_URL,
                json={
                    "query": graphql_query,
                    "variables": {"search": query, "pageSize": max_results},
                },
            )
            response.raise_for_status()
            data = response.json()

            items = data.get("data", {}).get("products", {}).get("items", [])
            return [self._parse_graphql_item(item) for item in items if item]

        except Exception as e:
            logger.debug("Text search failed", query=query, error=str(e))
            return []

    def _parse_graphql_item(self, item: dict) -> PriceOption:
        """Parse a GraphQL product item into a PriceOption."""
        price_range = item.get("price_range", {}).get("minimum_price", {})
        final_price = price_range.get("final_price", {})
        regular_price = price_range.get("regular_price", {})

        price = final_price.get("value", 0) or regular_price.get("value", 0)
        currency = final_price.get("currency", "ILS")

        sku = item.get("sku", "")
        url_key = item.get("url_key", sku)
        product_url = f"{self.base_url}/{url_key}.html"
        product_name = item.get("name", sku)  # Use product name from API

        return PriceOption(
            id=f"alm_{sku}",
            product_id=sku,
            product_name=product_name,
            seller=SellerInfo(
                id="alm",
                name="א.ל.מ",
                website="https://www.alm.co.il",
                whatsapp_number="+972506688740",  # From their JSON-LD data
                country="IL",
                source="alm",
            ),
            listed_price=float(price),
            currency=currency,
            url=product_url,
            scraped_at=datetime.utcnow(),
        )

    async def get_seller_details(self, seller_url: str) -> Optional[SellerInfo]:
        """Get seller details for ALM (always returns ALM info)."""
        return SellerInfo(
            id="alm",
            name="א.ל.מ",
            website="https://www.alm.co.il",
            whatsapp_number="+972506688740",
            country="IL",
            source="alm",
        )

    async def extract_contact_info(self, seller_url: str) -> Optional[str]:
        """Extract contact info for ALM (fixed WhatsApp number)."""
        return "+972506688740"


async def get_alm_price(url: str) -> Optional[float]:
    """Get the correct price for an ALM product URL.

    This function can be used by other scrapers to verify/correct
    ALM prices when they encounter an alm.co.il URL.

    Args:
        url: ALM product URL (e.g., https://www.alm.co.il/114600021.html)

    Returns:
        The correct price from ALM's GraphQL API, or None if not found
    """
    # Extract SKU from URL
    # URL patterns: /114600021.html or /product-name-114600021.html
    match = re.search(r"/([^/]+)\.html", url)
    if not match:
        return None

    url_key = match.group(1)

    # Try to extract numeric SKU from url_key
    # Could be just "114600021" or "product-name-114600021"
    sku_match = re.search(r"(\d{6,})", url_key)
    sku = sku_match.group(1) if sku_match else url_key

    async with httpx.AsyncClient(headers=ALM_HEADERS, timeout=30.0) as client:
        # First try by SKU
        graphql_query = """
        query GetPrice($sku: String!) {
            products(filter: {sku: {eq: $sku}}) {
                items {
                    sku
                    price_range {
                        minimum_price {
                            final_price { value }
                        }
                    }
                }
            }
        }
        """

        try:
            response = await client.post(
                ALM_GRAPHQL_URL,
                json={"query": graphql_query, "variables": {"sku": sku}},
            )
            response.raise_for_status()
            data = response.json()

            items = data.get("data", {}).get("products", {}).get("items", [])
            if items:
                price = items[0].get("price_range", {}).get("minimum_price", {}).get("final_price", {}).get("value")
                if price:
                    logger.info("Got ALM price via GraphQL", sku=sku, price=price)
                    return float(price)

            # If SKU didn't work, try URL resolver
            url_query = """
            query ResolveUrl($url: String!) {
                urlResolver(url: $url) {
                    id
                    type
                }
            }
            """

            response = await client.post(
                ALM_GRAPHQL_URL,
                json={"query": url_query, "variables": {"url": f"{url_key}.html"}},
            )
            response.raise_for_status()
            data = response.json()

            resolver = data.get("data", {}).get("urlResolver")
            if resolver and resolver.get("type") == "PRODUCT":
                product_id = resolver.get("id")

                # Get price by product ID
                id_query = """
                query GetPriceById($id: Int!) {
                    products(filter: {id: {eq: $id}}) {
                        items {
                            price_range {
                                minimum_price {
                                    final_price { value }
                                }
                            }
                        }
                    }
                }
                """

                response = await client.post(
                    ALM_GRAPHQL_URL,
                    json={"query": id_query, "variables": {"id": int(product_id)}},
                )
                response.raise_for_status()
                data = response.json()

                items = data.get("data", {}).get("products", {}).get("items", [])
                if items:
                    price = items[0].get("price_range", {}).get("minimum_price", {}).get("final_price", {}).get("value")
                    if price:
                        logger.info("Got ALM price via URL resolver", url_key=url_key, price=price)
                        return float(price)

        except Exception as e:
            logger.warning("Failed to get ALM price", url=url, error=str(e))

    return None


def is_alm_url(url: str) -> bool:
    """Check if a URL is from ALM."""
    return "alm.co.il" in url.lower()
