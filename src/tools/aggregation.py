"""Seller normalization and aggregation logic for multi-product searches."""

import re
from collections import defaultdict
from typing import Optional
from urllib.parse import urlparse

from src.state.models import PriceOption, SellerAggregation


# Known seller name aliases (map variants to canonical name)
SELLER_ALIASES = {
    # Hebrew to English mappings
    "אבי סופר": "soferavi",
    "סופראבי": "soferavi",
    "soferavi": "soferavi",  # English variant
    "באג": "bug",
    "bug": "bug",
    "קיי אס פי": "ksp",
    "ksp": "ksp",
    "סיטי דיל": "citydeal",
    "citydeal": "citydeal",
    "חשמל נטו": "chashmal-neto",
    "גלדיאטור": "gladiator",
    "גלדיאטור מוצרי חשמל": "gladiator",
    "gladiator": "gladiator",
    "ליאור מוצרי חשמל": "lior-electric",
    "lior electric": "lior-electric",
    "אלקטריק סייל": "electricsale",
    "electricsale": "electricsale",
    "פירסט פרייס": "firstprice",
    "firstprice": "firstprice",
    # Domain-based normalization
    "zap.co.il": "zap",
    "x-press.co.il": "xpress",
    # Common variations
    "citydeal | סיטי דיל": "citydeal",
    "א.ל.מ": "alm",
    "p1000": "p1000",
    "ivory": "ivory",
    "mahsanei hashmal": "mahsanei-hashmal",
    "מחסני חשמל": "mahsanei-hashmal",
}

# Reverse mapping from canonical name to domain (for site-search)
SELLER_DOMAINS = {
    "soferavi": "soferavi.co.il",
    "bug": "bug.co.il",
    "ksp": "ksp.co.il",
    "citydeal": "citydeal.co.il",
    "gladiator": "gladiator.co.il",
    "lior-electric": "lior-electric.co.il",
    "electricsale": "electricsale.co.il",
    "firstprice": "firstprice.co.il",
    "p1000": "p1000.co.il",
    "ivory": "ivory.co.il",
    "mahsanei-hashmal": "mahsanei-hashmal.co.il",
    "chashmal-neto": "chashmal-neto.co.il",
}


def extract_domain_name(url: str) -> Optional[str]:
    """Extract clean domain name from URL for matching."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        # Remove TLD
        domain = domain.replace(".co.il", "").replace(".com", "").replace(".net", "")
        return domain
    except Exception:
        return None


def normalize_seller_name(name: str, url: Optional[str] = None) -> str:
    """Normalize seller name for matching across sources.

    Args:
        name: Original seller name
        url: Optional URL to extract domain for better matching

    Returns:
        Normalized name for grouping

    Note:
        For comparison sites like Zap, we use the ACTUAL seller name (not "zap")
        so that products from different sellers don't incorrectly aggregate.
        Only use "zap" if the seller is actually Zap itself.
    """
    name_lower = name.lower().strip()

    # Check known aliases first - require word boundary matching, not substring
    # This prevents "BUG Electric" matching the "bug" alias incorrectly
    for alias, canonical in SELLER_ALIASES.items():
        alias_lower = alias.lower()
        # Check for exact match or word boundary match
        if name_lower == alias_lower:
            return canonical
        # Check if alias appears as a complete word (with word boundaries)
        # This handles "KSP Computers" → "ksp" but not "AKSP Store"
        words = re.split(r'[\s|,.\-]+', name_lower)
        if alias_lower in words:
            return canonical

    # If name is generic/unknown, try domain-based matching
    # But skip if URL is from a comparison/aggregator site (zap, wisebuy, etc.)
    if url:
        domain = extract_domain_name(url)
        if domain:
            # Skip domain matching for aggregator sites - use name instead
            aggregator_domains = {"zap", "wisebuy", "pricewatch"}
            if domain not in aggregator_domains:
                # Check if domain matches any known alias
                for alias, canonical in SELLER_ALIASES.items():
                    if alias.lower() in domain:
                        return canonical
                return domain

    # Generic normalization: keep alphanumeric + Hebrew chars
    # Hebrew unicode range: \u0590-\u05FF
    normalized = re.sub(r"[^a-z0-9\u0590-\u05ff\s]", "", name_lower)
    normalized = re.sub(r"\s+", " ", normalized).strip()

    return normalized


def aggregate_by_seller(
    results_by_query: dict[str, list[PriceOption]],
    top_stores: int = 10,
) -> list[SellerAggregation]:
    """Aggregate search results by seller across multiple product queries.

    Args:
        results_by_query: Dict mapping query string to list of PriceOptions
        top_stores: Max number of stores to return

    Returns:
        List of SellerAggregation, sorted by:
        1. Number of products (descending)
        2. Total price (ascending)
    """
    # Group by normalized seller name
    seller_groups: dict[str, list[tuple[str, PriceOption]]] = defaultdict(list)

    for query, results in results_by_query.items():
        for result in results:
            # Use URL for better matching
            key = normalize_seller_name(result.seller.name, result.url)
            seller_groups[key].append((query, result))

    # Build aggregations
    aggregations = []
    for normalized_name, items in seller_groups.items():
        # Get unique products (one per query, lowest price)
        best_per_query: dict[str, PriceOption] = {}
        for query, result in items:
            if (
                query not in best_per_query
                or result.listed_price < best_per_query[query].listed_price
            ):
                best_per_query[query] = result

        products = list(best_per_query.values())

        # Calculate aggregates
        total_price = sum(p.listed_price for p in products)
        ratings = [
            p.seller.reliability_score
            for p in products
            if p.seller.reliability_score is not None
        ]
        avg_rating = sum(ratings) / len(ratings) if ratings else None

        # Get contact (prefer WhatsApp)
        contacts = [
            p.seller.whatsapp_number for p in products if p.seller.whatsapp_number
        ]
        contact = contacts[0] if contacts else None

        # Get sources
        sources = list(set(p.seller.source for p in products if p.seller.source))

        aggregations.append(
            SellerAggregation(
                seller_name=products[0].seller.name,  # Use first occurrence
                normalized_name=normalized_name,
                products=products,
                product_queries=list(best_per_query.keys()),
                total_price=total_price,
                average_rating=avg_rating,
                contact=contact,
                sources=sources,
            )
        )

    # Sort: most products first, then lowest total price
    aggregations.sort(key=lambda a: (-a.product_count, a.total_price))

    return aggregations[:top_stores]
