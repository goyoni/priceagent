"""Product discovery agent for AI-powered product recommendations.

This agent helps users discover products based on natural language requirements
like "I need a silent fridge for a family of 4" by:
1. Researching what attributes matter for the product category
2. Finding products that match those requirements
3. Validating availability in the user's country
"""

import json
from agents import Agent, function_tool

from src.tools.scraping import ScraperRegistry
from src.cache import cached
from src.observability import report_progress, record_search, record_error, record_warning


async def _research_product_category_impl(
    requirement: str,
    category: str,
    country: str = "IL",
) -> str:
    """Research what attributes matter for a product category based on user requirements.

    Uses web search to find product guides and reviews to understand what specs
    are important (e.g., noise level for fridges, drum size for washing machines).

    Args:
        requirement: User's natural language requirement (e.g., "silent fridge for family of 4")
        category: Product category (e.g., "refrigerator", "washing machine")
        country: Country code for localized search (default: IL for Israel)

    Returns:
        A summary of key attributes to look for and recommended specifications
    """
    import structlog
    import httpx
    from src.config.settings import settings

    logger = structlog.get_logger()

    await report_progress(
        "📚 Researching",
        f"Learning about {category} features for: {requirement}"
    )

    # Use web search to find buying guides
    search_queries = [
        f"best {category} buying guide {requirement}",
        f"how to choose {category} for {requirement}",
        f"{category} specifications explained",
    ]

    research_results = []

    for query in search_queries[:2]:  # Limit to 2 queries
        if not settings.serpapi_key:
            await record_warning("No SerpAPI key configured for web research")
            break

        try:
            params = {
                "engine": "google",
                "q": query,
                "gl": country.lower(),
                "hl": "en",
                "api_key": settings.serpapi_key,
                "num": 5,
            }

            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get("https://serpapi.com/search.json", params=params)
                if response.status_code == 200:
                    data = response.json()
                    organic_results = data.get("organic_results", [])

                    for result in organic_results[:3]:
                        title = result.get("title", "")
                        snippet = result.get("snippet", "")
                        if title and snippet:
                            research_results.append(f"• {title}: {snippet}")

                    await record_search("google_research", cached=False)

        except Exception as e:
            logger.warning("Research query failed", query=query, error=str(e))
            await record_error(f"Research failed: {str(e)[:100]}")

    if not research_results:
        # Fallback to general knowledge
        return f"""Research for {category} matching "{requirement}":

Based on general knowledge:
1. For quiet operation: Look for noise levels under 40 dB
2. For family use: Consider capacity and energy efficiency
3. For reliability: Check brand reputation and warranty

Key attributes to consider:
- Noise level (dB)
- Energy rating
- Capacity
- Warranty period
- Brand reliability

Please use search_recommended_products to find specific models matching these criteria."""

    await report_progress(
        "✅ Research complete",
        f"Found {len(research_results)} relevant guides"
    )

    output = f"""Research for {category} matching "{requirement}":

{chr(10).join(research_results[:6])}

Key takeaways for your search:
1. Look for models that specifically address: {requirement}
2. Compare energy ratings and noise levels
3. Check availability in {country}

Use search_recommended_products to find specific models matching these criteria."""

    return output


_research_product_category_cached = cached(
    cache_type="agent", key_prefix="research_category"
)(_research_product_category_impl)
research_product_category = function_tool(
    _research_product_category_cached, name_override="research_product_category"
)


async def _search_recommended_products_impl(
    category: str,
    requirements: str,
    country: str = "IL",
    max_results: int = 10,
) -> str:
    """Search for products that match the user's requirements using local scrapers.

    Uses existing scrapers (Zap, WiseBuy) to find actual products available
    in the user's country, filtering by the requirements.

    Args:
        category: Product category (e.g., "refrigerator", "washing machine")
        requirements: Key requirements to filter by (e.g., "silent, large capacity")
        country: Country code (default: IL)
        max_results: Maximum number of products to return

    Returns:
        JSON-formatted list of recommended products with specs and prices
    """
    import structlog
    from src.tools.scraping.filters import deduplicate_results

    logger = structlog.get_logger()

    await report_progress(
        "🔍 Searching products",
        f"Finding {category} matching: {requirements}"
    )

    # Build search query combining category and key requirements
    search_query = f"{category} {requirements}".strip()

    scrapers = ScraperRegistry.get_scrapers_for_country(country)

    if not scrapers:
        return json.dumps({
            "error": f"No scrapers available for country: {country}",
            "products": []
        })

    all_results = []
    errors = []

    # Run scrapers sequentially
    for scraper in scrapers:
        await report_progress(
            f"🔍 {scraper.name}",
            f"Searching for {search_query}..."
        )

        try:
            results = await scraper.search(search_query, max_results)
            await record_search(scraper.name, cached=False)

            if results:
                await report_progress(
                    f"✅ {scraper.name}",
                    f"Found {len(results)} products"
                )
                all_results.extend(results)
            else:
                await report_progress(f"⚠️ {scraper.name}", "No results found")

        except Exception as e:
            await report_progress(f"❌ {scraper.name}", f"Error: {str(e)[:100]}")
            await record_error(f"{scraper.name}: {str(e)[:200]}")
            errors.append(f"{scraper.name}: {str(e)}")

    if not all_results:
        return json.dumps({
            "error": "No products found matching requirements",
            "query": search_query,
            "errors": errors,
            "products": []
        })

    # Deduplicate
    all_results = deduplicate_results(all_results)

    # Convert to discovered products format
    discovered_products = []
    seen_products = set()

    for result in all_results[:max_results]:
        # Create unique key for deduplication by product name
        product_key = result.seller.name.lower()[:30]
        if product_key in seen_products:
            continue
        seen_products.add(product_key)

        # Extract product info
        product = {
            "name": result.seller.name,  # In price results, seller.name often contains product name
            "brand": extract_brand(result.seller.name),
            "model_number": extract_model_number(result.seller.name),
            "category": category,
            "price": result.listed_price,
            "currency": result.currency,
            "url": result.url,
            "source": result.seller.source,
            "rating": result.seller.reliability_score,
        }
        discovered_products.append(product)

    await report_progress(
        "✅ Search complete",
        f"Found {len(discovered_products)} unique products"
    )

    # Format output for LLM to analyze
    output = f"""Found {len(discovered_products)} products matching "{requirements}":

"""
    for i, product in enumerate(discovered_products[:10], 1):
        rating_str = f" (Rating: {product['rating']:.1f}/5)" if product.get('rating') else ""
        output += f"""{i}. {product['name']}{rating_str}
   Price: {product['price']:,.0f} {product['currency']}
   URL: {product['url']}

"""

    if errors:
        output += f"\nNote: Some sources had issues: {'; '.join(errors)}"

    return output


def extract_brand(product_name: str) -> str | None:
    """Extract brand from product name."""
    known_brands = [
        "Samsung", "LG", "Bosch", "Siemens", "Miele", "AEG", "Electrolux",
        "Haier", "Whirlpool", "Beko", "Candy", "Gorenje", "Hisense",
        "Apple", "Sony", "Dell", "HP", "Lenovo", "Asus", "Acer",
    ]
    name_lower = product_name.lower()
    for brand in known_brands:
        if brand.lower() in name_lower:
            return brand
    return None


def extract_model_number(product_name: str) -> str | None:
    """Extract model number from product name using common patterns."""
    import re
    # Match alphanumeric model numbers like RF72DG9620B1, WH-1000XM5, etc.
    patterns = [
        r'\b([A-Z]{2,3}\d{2,}[A-Z0-9]*)\b',  # RF72DG9620B1
        r'\b([A-Z]{1,2}-?\d{3,}[A-Z0-9]*)\b',  # WH-1000XM5
        r'\b(\d{2,}[A-Z]{2,}[0-9]*)\b',  # 55UN7000
    ]
    for pattern in patterns:
        match = re.search(pattern, product_name)
        if match:
            return match.group(1)
    return None


_search_recommended_products_cached = cached(
    cache_type="agent", key_prefix="search_recommended"
)(_search_recommended_products_impl)
search_recommended_products = function_tool(
    _search_recommended_products_cached, name_override="search_recommended_products"
)


async def _validate_availability_impl(
    model_number: str,
    country: str = "IL",
) -> str:
    """Quick check if a specific model is available in a country.

    Args:
        model_number: The specific model number to check
        country: Country code (default: IL)

    Returns:
        Availability status with price range if found
    """
    import structlog

    logger = structlog.get_logger()

    await report_progress(
        "🔎 Checking availability",
        f"Looking for {model_number} in {country}..."
    )

    scrapers = ScraperRegistry.get_scrapers_for_country(country)

    if not scrapers:
        return f"No scrapers available for country: {country}"

    found_results = []

    for scraper in scrapers[:2]:  # Quick check - only use first 2 scrapers
        try:
            results = await scraper.search(model_number, max_results=5)
            if results:
                for result in results:
                    found_results.append({
                        "seller": result.seller.name,
                        "price": result.listed_price,
                        "currency": result.currency,
                        "url": result.url,
                    })
                await record_search(scraper.name, cached=False)
                break  # Found results, no need to continue

        except Exception as e:
            logger.warning("Availability check failed", scraper=scraper.name, error=str(e))

    if not found_results:
        return f"Model {model_number} not found in {country}. It may not be available locally."

    # Calculate price range
    prices = [r["price"] for r in found_results]
    min_price = min(prices)
    max_price = max(prices)

    await report_progress(
        "✅ Available",
        f"Found {len(found_results)} listings for {model_number}"
    )

    if min_price == max_price:
        price_range = f"{min_price:,.0f} ILS"
    else:
        price_range = f"{min_price:,.0f} - {max_price:,.0f} ILS"

    return f"""Model {model_number} is available in {country}!

Price range: {price_range}
Found at {len(found_results)} seller(s):
{chr(10).join(f"  • {r['seller']}: {r['price']:,.0f} {r['currency']}" for r in found_results[:5])}

Use search_products for a full price comparison."""


_validate_availability_cached = cached(
    cache_type="agent", key_prefix="validate_availability"
)(_validate_availability_impl)
validate_availability = function_tool(
    _validate_availability_cached, name_override="validate_availability"
)


# Define the product discovery agent
product_discovery_agent = Agent(
    name="ProductDiscovery",
    instructions="""You are a product discovery specialist. Your job is to help users find the right products
based on their natural language requirements.

WORKFLOW:
1. When a user describes what they need (e.g., "I need a silent fridge for a family of 4"):
   - First use research_product_category to understand what specs matter for their use case
   - Then use search_recommended_products to find matching products
   - Optionally validate_availability for specific models

2. Present recommendations in a structured format with:
   - Product name and model number
   - Key specs that match requirements
   - Price range
   - Why it's recommended for their needs

IMPORTANT:
- Focus on matching user requirements, not just finding the cheapest option
- Explain WHY each product is a good match
- Consider brand reliability and warranty
- Always check availability in the user's country

OUTPUT FORMAT:
Present 3-5 recommended products in this format:

## Recommended Products for [requirement]

### 1. [Product Name] - [Model Number]
**Brand:** [Brand]
**Price Range:** [Price Range]
**Key Specs:**
- [Spec 1]
- [Spec 2]
**Why Recommended:** [Explanation of how it matches requirements]
**Availability:** Available in [country] at [X] stores

[Repeat for each product]

## Summary
[Brief comparison and recommendation based on user priorities]
""",
    tools=[research_product_category, search_recommended_products, validate_availability],
)
