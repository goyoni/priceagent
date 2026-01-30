"""API routes for geolocation."""

from fastapi import APIRouter, Request
from pydantic import BaseModel
import structlog

router = APIRouter(prefix="/api/geo", tags=["geo"])
logger = structlog.get_logger()


class CountryResponse(BaseModel):
    """Response for country detection."""
    country: str
    source: str  # "ip", "default", "header"


@router.get("/country")
async def get_country(request: Request) -> CountryResponse:
    """Detect user's country from IP address or headers.

    Priority:
    1. X-Country header (for proxies/CDNs)
    2. CF-IPCountry header (Cloudflare)
    3. X-Forwarded-For header with IP geolocation
    4. Default to IL (Israel)
    """
    # Check custom header
    country_header = request.headers.get("X-Country")
    if country_header:
        logger.info("country_detected", source="header", country=country_header)
        return CountryResponse(country=country_header.upper(), source="header")

    # Check Cloudflare country header
    cf_country = request.headers.get("CF-IPCountry")
    if cf_country and cf_country != "XX":  # XX means unknown
        logger.info("country_detected", source="cloudflare", country=cf_country)
        return CountryResponse(country=cf_country.upper(), source="cloudflare")

    # Get client IP
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else None

    # For local development or unknown IP, default to IL
    if not client_ip or client_ip in ("127.0.0.1", "localhost", "::1"):
        logger.info("country_default", reason="local_ip", ip=client_ip)
        return CountryResponse(country="IL", source="default")

    # In production, you could use an IP geolocation service here
    # For now, default to IL
    logger.info("country_default", reason="no_geolocation", ip=client_ip)
    return CountryResponse(country="IL", source="default")
