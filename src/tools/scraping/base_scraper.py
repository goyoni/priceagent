"""Base scraper interface for price comparison sites."""

import asyncio
from abc import ABC, abstractmethod
from typing import Optional

import structlog
from pydantic import BaseModel

from src.state.models import PriceOption, SellerInfo

logger = structlog.get_logger()


class ScraperConfig(BaseModel):
    """Configuration for a scraper."""

    name: str
    base_url: str
    search_path: str
    priority: int = 1


class BaseScraper(ABC):
    """Abstract base class for price comparison scrapers."""

    def __init__(self, config: ScraperConfig):
        self.config = config
        self.name = config.name
        self.base_url = config.base_url

    @abstractmethod
    async def search(self, query: str, max_results: int = 10) -> list[PriceOption]:
        """Search for products matching the query.

        Args:
            query: Product search query
            max_results: Maximum number of results to return

        Returns:
            List of PriceOption objects with seller info
        """
        pass

    @abstractmethod
    async def get_seller_details(self, seller_url: str) -> Optional[SellerInfo]:
        """Get detailed information about a seller.

        Args:
            seller_url: URL of the seller's page

        Returns:
            SellerInfo object or None if not found
        """
        pass

    @abstractmethod
    async def extract_contact_info(self, seller_url: str) -> Optional[str]:
        """Extract contact information (phone/WhatsApp) from a seller's page.

        Args:
            seller_url: URL of the seller's website

        Returns:
            Phone number or None if not found
        """
        pass

    def build_search_url(self, query: str) -> str:
        """Build the search URL for a query."""
        return f"{self.base_url}{self.config.search_path.format(query=query)}"

    async def search_with_contacts(
        self, query: str, max_results: int = 10, progress_callback=None
    ) -> list[PriceOption]:
        """Search for products and automatically extract contact info.

        This method combines search() with sequential contact extraction,
        enriching each result with phone/WhatsApp contact information.

        Args:
            query: Product search query
            max_results: Maximum number of results to return
            progress_callback: Optional async callback(current, total, message) for progress updates

        Returns:
            List of PriceOption objects with contact info populated
        """
        # First, perform the search
        results = await self.search(query, max_results)

        if not results:
            return results

        # Extract contacts sequentially to avoid rate limiting
        for i, result in enumerate(results):
            try:
                # Skip if we already have contact info
                if result.seller.whatsapp_number:
                    continue

                # Report progress
                if progress_callback:
                    await progress_callback(
                        i + 1,
                        len(results),
                        f"Extracting contact for {result.seller.name}..."
                    )

                # Extract contact from the seller URL
                contact = await self.extract_contact_info(result.url)
                if contact:
                    result.seller.whatsapp_number = contact
                    logger.debug(
                        "Extracted contact",
                        seller=result.seller.name,
                        contact=contact,
                    )
            except Exception as e:
                logger.warning(
                    "Failed to extract contact",
                    seller=result.seller.name,
                    url=result.url,
                    error=str(e),
                )

        logger.info(
            "Search with contacts complete",
            query=query,
            results=len(results),
            with_contacts=sum(1 for r in results if r.seller.whatsapp_number),
        )

        return results
