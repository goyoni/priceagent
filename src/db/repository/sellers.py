"""Seller repository for database operations."""

from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Seller

logger = structlog.get_logger()


class SellerRepository:
    """CRUD operations for sellers."""

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def extract_domain(url: str) -> Optional[str]:
        """Extract domain from URL.

        Args:
            url: Full URL string

        Returns:
            Domain without www prefix, or None if invalid
        """
        if not url:
            return None
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            if domain.startswith("www."):
                domain = domain[4:]
            return domain if domain else None
        except Exception:
            return None

    async def get_by_id(self, seller_id: int) -> Optional[Seller]:
        """Get seller by ID.

        Args:
            seller_id: Seller primary key

        Returns:
            Seller or None
        """
        stmt = select(Seller).where(Seller.id == seller_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_domain(self, domain: str) -> Optional[Seller]:
        """Get seller by domain.

        Args:
            domain: Domain name (e.g., "p1000.co.il")

        Returns:
            Seller or None
        """
        if not domain:
            return None
        stmt = select(Seller).where(Seller.domain == domain.lower())
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_website_url(self, url: str) -> Optional[Seller]:
        """Get seller by website URL (extracts domain).

        Args:
            url: Full website URL

        Returns:
            Seller or None
        """
        domain = self.extract_domain(url)
        if not domain:
            return None
        return await self.get_by_domain(domain)

    async def get_by_name(self, seller_name: str) -> Optional[Seller]:
        """Get seller by name (exact match).

        Args:
            seller_name: Seller display name

        Returns:
            Seller or None
        """
        stmt = select(Seller).where(Seller.seller_name == seller_name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_contact_by_url(self, url: str) -> Optional[str]:
        """Get cached contact info by URL.

        Args:
            url: Website URL

        Returns:
            WhatsApp number if available, otherwise phone number, or None
        """
        seller = await self.get_by_website_url(url)
        if seller:
            return seller.contact
        return None

    async def get_contact_by_domain(self, domain: str) -> Optional[str]:
        """Get cached contact info by domain.

        Args:
            domain: Domain name

        Returns:
            WhatsApp number if available, otherwise phone number, or None
        """
        seller = await self.get_by_domain(domain)
        if seller:
            return seller.contact
        return None

    async def create(
        self,
        seller_name: str,
        domain: Optional[str] = None,
        phone_number: Optional[str] = None,
        whatsapp_number: Optional[str] = None,
        website_url: Optional[str] = None,
        country: str = "IL",
        rating: Optional[float] = None,
        reliability_score: Optional[float] = None,
    ) -> Seller:
        """Create a new seller.

        Args:
            seller_name: Display name
            domain: Domain name (extracted from URL if not provided)
            phone_number: Phone number
            whatsapp_number: WhatsApp number (preferred for contact)
            website_url: Full website URL
            country: Country code
            rating: Seller rating
            reliability_score: Reliability score

        Returns:
            Created Seller instance
        """
        if domain is None and website_url:
            domain = self.extract_domain(website_url)

        seller = Seller(
            seller_name=seller_name,
            domain=domain,
            phone_number=phone_number,
            whatsapp_number=whatsapp_number,
            website_url=website_url,
            country=country,
            rating=rating,
            reliability_score=reliability_score,
            last_scraped_at=datetime.now(),
        )

        self.session.add(seller)
        await self.session.flush()
        await self.session.refresh(seller)

        logger.info(
            "Created seller",
            seller_id=seller.id,
            name=seller_name,
            domain=domain,
        )

        return seller

    async def update(
        self,
        seller: Seller,
        phone_number: Optional[str] = None,
        whatsapp_number: Optional[str] = None,
        website_url: Optional[str] = None,
        rating: Optional[float] = None,
        reliability_score: Optional[float] = None,
    ) -> Seller:
        """Update an existing seller.

        Only updates non-None values.

        Args:
            seller: Seller to update
            phone_number: New phone number
            whatsapp_number: New WhatsApp number
            website_url: New website URL
            rating: New rating
            reliability_score: New reliability score

        Returns:
            Updated Seller instance
        """
        if phone_number is not None:
            seller.phone_number = phone_number
        if whatsapp_number is not None:
            seller.whatsapp_number = whatsapp_number
        if website_url is not None:
            seller.website_url = website_url
        if rating is not None:
            seller.rating = rating
        if reliability_score is not None:
            seller.reliability_score = reliability_score

        seller.last_scraped_at = datetime.now()
        seller.updated_at = datetime.now()

        await self.session.flush()

        logger.info(
            "Updated seller",
            seller_id=seller.id,
            name=seller.seller_name,
        )

        return seller

    async def create_or_update(
        self,
        seller_name: str,
        website_url: Optional[str] = None,
        phone_number: Optional[str] = None,
        whatsapp_number: Optional[str] = None,
        country: str = "IL",
        rating: Optional[float] = None,
        reliability_score: Optional[float] = None,
    ) -> Seller:
        """Create or update a seller by domain.

        If a seller with the same domain exists, updates it.
        Otherwise creates a new seller.

        Args:
            seller_name: Display name
            website_url: Website URL (domain extracted)
            phone_number: Phone number
            whatsapp_number: WhatsApp number
            country: Country code
            rating: Seller rating
            reliability_score: Reliability score

        Returns:
            Created or updated Seller instance
        """
        domain = self.extract_domain(website_url) if website_url else None

        # Try to find existing seller by domain
        existing = await self.get_by_domain(domain) if domain else None

        if existing:
            return await self.update(
                existing,
                phone_number=phone_number,
                whatsapp_number=whatsapp_number,
                website_url=website_url,
                rating=rating,
                reliability_score=reliability_score,
            )
        else:
            return await self.create(
                seller_name=seller_name,
                domain=domain,
                phone_number=phone_number,
                whatsapp_number=whatsapp_number,
                website_url=website_url,
                country=country,
                rating=rating,
                reliability_score=reliability_score,
            )

    async def list_all(self, limit: int = 100) -> list[Seller]:
        """List all sellers.

        Args:
            limit: Maximum number to return

        Returns:
            List of Seller instances
        """
        stmt = select(Seller).order_by(Seller.updated_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def search_by_name(self, query: str, limit: int = 10) -> list[Seller]:
        """Search sellers by name (partial match).

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of matching Seller instances
        """
        stmt = (
            select(Seller)
            .where(Seller.seller_name.ilike(f"%{query}%"))
            .order_by(Seller.seller_name)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
