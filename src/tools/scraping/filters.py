"""Shared filters for product relevance matching across scrapers."""

import re
from typing import Optional

import structlog

logger = structlog.get_logger()


def is_relevant_product(query: str, product_name: str, strict_model_match: bool = True) -> bool:
    """Check if product name is relevant to the search query.

    This helps filter out "related" products that don't actually match,
    especially important for Google results which tend to return near-matches.

    Args:
        query: The search query (may include brand and model number)
        product_name: The product name from search results
        strict_model_match: If True, requires exact model number matching

    Returns:
        True if product is relevant, False otherwise
    """
    query_lower = query.lower()
    product_lower = product_name.lower()

    # Extract potential model numbers from query (alphanumeric sequences)
    model_patterns = re.findall(r'[a-z0-9]{4,}', query_lower)

    # Check if any significant part of the query appears in product name
    for pattern in model_patterns:
        if strict_model_match:
            # For model numbers, require exact match or very close match
            if len(pattern) >= 8:
                # Long model numbers: require first 8 chars to match
                if pattern[:8] in product_lower:
                    return True
            elif len(pattern) >= 6:
                # Medium model numbers: require first 6 chars to match
                if pattern[:6] in product_lower:
                    return True
            elif len(pattern) >= 4:
                # Short patterns: require exact match
                if pattern in product_lower:
                    return True
        else:
            # Less strict matching
            if len(pattern) >= 4:
                if pattern in product_lower:
                    return True

    # Check brand names
    brands = [
        'samsung', 'סמסונג',
        'apple', 'אפל',
        'sony', 'סוני',
        'lg', 'אל ג\'י',
        'philips', 'פיליפס',
        'bosch', 'בוש',
        'siemens', 'סימנס',
        'electra', 'אלקטרה',
        'tadiran', 'תדיראן',
        'amcor', 'אמקור',
    ]
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


def extract_model_number(text: str) -> Optional[str]:
    """Extract a model number from text.

    Args:
        text: Text that may contain a model number

    Returns:
        Extracted model number or None
    """
    # Common model number patterns
    patterns = [
        r'[A-Z]{2,3}[-]?\d{2,}[A-Z]{0,3}\d*[A-Z]*',  # Samsung: RF72DG9620B1
        r'[A-Z]\d{2,}[A-Z]{0,2}\d*',  # Short codes: A2345XY
        r'\d{2,}[A-Z]{2,}\d*',  # Number first: 55UQ8000
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0).upper()

    return None


def normalize_price_for_comparison(price: float, currency: str = "ILS") -> float:
    """Normalize price for comparison across different listings.

    Args:
        price: Price value
        currency: Currency code

    Returns:
        Normalized price value
    """
    # For now, just return the price as-is
    # Future: could add currency conversion
    return price


def deduplicate_results(
    results: list, price_bucket_size: float = 50.0, min_price: float = 50.0
) -> list:
    """Deduplicate search results by seller and price bucket.

    Also filters out unreasonably low prices that are likely extraction errors.

    Args:
        results: List of PriceOption objects
        price_bucket_size: Size of price buckets for grouping similar prices
        min_price: Minimum valid price (filters likely extraction errors)

    Returns:
        Deduplicated list of PriceOption objects
    """
    seen = set()
    unique_results = []

    for result in results:
        # Filter unreasonably low prices (likely extraction errors)
        if result.listed_price < min_price:
            logger.warning(
                "Filtered unreasonably low price",
                seller=result.seller.name,
                price=result.listed_price,
                url=result.url[:80] if result.url else None,
            )
            continue

        # Create deduplication key: seller name + price bucket
        seller_name = result.seller.name.lower().strip()
        price_bucket = int(result.listed_price / price_bucket_size)
        key = (seller_name, price_bucket)

        if key not in seen:
            seen.add(key)
            unique_results.append(result)
        else:
            logger.debug(
                "Duplicate filtered",
                seller=seller_name,
                price=result.listed_price,
            )

    logger.info(
        "Deduplication complete",
        original=len(results),
        unique=len(unique_results),
    )
    return unique_results
