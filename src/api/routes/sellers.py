"""FastAPI routes for seller data."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from typing import List, Optional
from pydantic import BaseModel

from src.db.session import get_db_session
from src.db.repository.sellers import SellerRepository

router = APIRouter(prefix="/sellers", tags=["sellers"])


class ContactLookupRequest(BaseModel):
    """Request to look up contacts for multiple domains."""
    domains: List[str]


class ContactInfo(BaseModel):
    """Contact information for a seller."""
    domain: str
    seller_name: Optional[str] = None
    phone_number: Optional[str] = None
    whatsapp_number: Optional[str] = None


@router.post("/contacts")
async def lookup_contacts(request: ContactLookupRequest) -> dict:
    """Look up contact information for multiple domains.

    Args:
        request: List of domains to look up

    Returns:
        Dictionary mapping domain to contact info
    """
    contacts = {}

    try:
        async with get_db_session() as session:
            repo = SellerRepository(session)

            for domain in request.domains:
                # Clean up domain
                clean_domain = domain.lower().strip()
                if clean_domain.startswith("www."):
                    clean_domain = clean_domain[4:]

                seller = await repo.get_by_domain(clean_domain)
                if seller:
                    contacts[domain] = {
                        "domain": clean_domain,
                        "seller_name": seller.seller_name,
                        "phone_number": seller.phone_number,
                        "whatsapp_number": seller.whatsapp_number,
                    }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to lookup contacts: {str(e)}"}
        )

    return {"contacts": contacts}


@router.get("/")
async def list_sellers(limit: int = 100) -> dict:
    """List all sellers in the database."""
    try:
        async with get_db_session() as session:
            repo = SellerRepository(session)
            sellers = await repo.list_all()

            return {
                "sellers": [
                    {
                        "id": s.id,
                        "seller_name": s.seller_name,
                        "domain": s.domain,
                        "phone_number": s.phone_number,
                        "whatsapp_number": s.whatsapp_number,
                        "website_url": s.website_url,
                        "rating": s.rating,
                    }
                    for s in sellers[:limit]
                ]
            }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to list sellers: {str(e)}"}
        )


@router.get("/{domain}")
async def get_seller(domain: str) -> dict:
    """Get seller info by domain."""
    try:
        async with get_db_session() as session:
            repo = SellerRepository(session)

            # Clean up domain
            clean_domain = domain.lower().strip()
            if clean_domain.startswith("www."):
                clean_domain = clean_domain[4:]

            seller = await repo.get_by_domain(clean_domain)
            if not seller:
                return JSONResponse(
                    status_code=404,
                    content={"error": "Seller not found"}
                )

            return {
                "id": seller.id,
                "seller_name": seller.seller_name,
                "domain": seller.domain,
                "phone_number": seller.phone_number,
                "whatsapp_number": seller.whatsapp_number,
                "website_url": seller.website_url,
                "rating": seller.rating,
            }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to get seller: {str(e)}"}
        )
