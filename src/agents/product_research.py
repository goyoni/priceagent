"""Product research agent for finding best purchase options."""

import asyncio
from agents import Agent, function_tool
from typing import Optional

# Import from scraping module to ensure scrapers are registered
from src.tools.scraping import ScraperRegistry
from src.tools.scraping.filters import deduplicate_results
from src.tools.aggregation import aggregate_by_seller, SELLER_DOMAINS
from src.state.models import PriceOption, SellerInfo
from src.cache import cached
from src.observability import report_progress, record_search, record_error, record_warning


# List of aggregator scraper names (prioritized for appliance/electronics searches)
AGGREGATOR_SCRAPERS = ["zap_http", "wisebuy"]


async def _search_products_impl(query: str, country: str = "IL", max_results: int = 10) -> str:
    """Search for products across price comparison sites with contact info.

    Runs all scrapers in parallel and automatically extracts contact information.

    Args:
        query: The product to search for (e.g., "iPhone 15 Pro 256GB")
        country: Country code for localized search (default: IL for Israel)
        max_results: Maximum number of results per site

    Returns:
        A formatted list of products with prices, sellers, ratings, and contact info
    """
    import structlog
    logger = structlog.get_logger()

    scrapers = ScraperRegistry.get_scrapers_for_country(country)

    if not scrapers:
        return f"No scrapers available for country: {country}"

    all_results: list[PriceOption] = []
    errors: list[str] = []

    # Run scrapers sequentially to avoid rate limiting
    for scraper_idx, scraper in enumerate(scrapers):
        # Report which scraper is running
        await report_progress(
            f"🔍 {scraper.name}",
            f"Searching {scraper.name} for {query}..."
        )

        try:
            # Just do the search (fast, no contact extraction)
            results = await scraper.search(query, max_results)

            # Record search operation
            await record_search(scraper.name, cached=False)

            if results:
                # Report results immediately
                progress_output = f"✅ Found {len(results)} results:\n"
                for r in results[:5]:
                    price_str = f"{r.listed_price:,.0f} {r.currency}"
                    progress_output += f"  • {r.seller.name}: {price_str}\n"
                if len(results) > 5:
                    progress_output += f"  ... and {len(results) - 5} more"
                await report_progress(f"✅ {scraper.name}", progress_output)
                all_results.extend(results)
            else:
                await report_progress(f"⚠️ {scraper.name}", "No results found")
                await record_warning(f"{scraper.name}: No results for {query}")
        except Exception as e:
            await report_progress(f"❌ {scraper.name}", f"Error: {str(e)[:100]}")
            await record_error(f"{scraper.name}: {str(e)[:200]}")
            errors.append(f"{scraper.__class__.__name__}: {str(e)}")

    if not all_results:
        if errors:
            return f"No products found for '{query}' in {country}. Scraper errors: {'; '.join(errors)}"
        return f"No products found for '{query}' in {country}"

    # Deduplicate results by seller + price bucket
    all_results = deduplicate_results(all_results)

    # Rank results by combined score (price and reputation)
    def rank_score(result: PriceOption) -> float:
        """Lower score = better. Combines price rank with reputation penalty."""
        # Normalize price (assuming most products are 100-50000 ILS)
        price_score = result.listed_price

        # Apply reputation bonus/penalty (rating is 0-5, default to 3 if unknown)
        rating = result.seller.reliability_score or 3.0
        # Higher rating = lower score (better). Max bonus is 20% discount for 5-star
        reputation_multiplier = 1.0 - ((rating - 3.0) / 10.0)  # 5-star = 0.8x, 1-star = 1.2x

        return price_score * reputation_multiplier

    all_results.sort(key=rank_score)

    # Limit to top 5 results
    top_results = all_results[:5]

    # Format results with ratings and contact info
    # NOTE: Format must match dashboard's parseSearchResults() regex patterns:
    # - Rating: "(Rating: X/5)"
    # - Price: "Price: X,XXX ILS"
    # - URL: "URL: https://..."
    # - Contact: "Contact: +972..."
    output = [f"Top {len(top_results)} results for '{query}' (ranked by price + reputation):\n"]

    for i, result in enumerate(top_results, 1):
        rating_str = ""
        if result.seller.reliability_score:
            rating_str = f" (Rating: {result.seller.reliability_score:.1f}/5)"

        source_str = ""
        if result.seller.source:
            source_str = f" [{result.seller.source}]"

        contact_str = ""
        if result.seller.whatsapp_number:
            contact_str = f"   Contact: {result.seller.whatsapp_number}\n"

        output.append(
            f"{i}. {result.seller.name}{rating_str}{source_str}\n"
            f"   Price: {result.listed_price:,.0f} {result.currency}\n"
            f"   URL: {result.url}\n"
            f"{contact_str}"
        )

    if errors:
        output.append(f"\nNote: Some scrapers had issues: {'; '.join(errors)}")

    return "\n".join(output)


# Create cached version (for testing) and tool version (for agents)
_search_products_cached = cached(cache_type="agent", key_prefix="search_products")(
    _search_products_impl
)
search_products = function_tool(_search_products_cached, name_override="search_products")


async def _get_seller_contact_impl(seller_url: str, country: str = "IL") -> str:
    """Get contact information for a seller from their website.

    Args:
        seller_url: URL of the seller's page or website
        country: Country code for selecting appropriate scraper

    Returns:
        Contact information including phone/WhatsApp if found
    """
    scrapers = ScraperRegistry.get_scrapers_for_country(country)

    for scraper in scrapers:
        try:
            phone = await scraper.extract_contact_info(seller_url)
            if phone:
                return f"Found contact: {phone}"
        except Exception:
            continue

    return "No contact information found. Please provide manually."


# Create cached version (for testing) and tool version (for agents)
_get_seller_contact_cached = cached(cache_type="contact", key_prefix="get_seller_contact")(
    _get_seller_contact_impl
)
get_seller_contact = function_tool(_get_seller_contact_cached, name_override="get_seller_contact")


async def _search_multiple_products_impl(
    queries: list[str],
    country: str = "IL",
    max_results_per_product: int = 20,
    top_stores: int = 10,
) -> str:
    """Search for multiple products and aggregate by seller for bundle deals.

    Args:
        queries: List of product search queries
        country: Country code (default: IL)
        max_results_per_product: Max results per product search
        top_stores: Number of top stores to show in aggregated view

    Returns:
        Formatted string with bundle opportunities and individual results
    """
    import structlog
    logger = structlog.get_logger()

    scrapers = ScraperRegistry.get_scrapers_for_country(country)

    if not scrapers:
        return f"No scrapers available for country: {country}"

    # Search products sequentially to avoid rate limiting
    results_by_query: dict[str, list[PriceOption]] = {}
    total_queries = len(queries)

    for query_idx, query in enumerate(queries):
        # Report starting this product search
        await report_progress(
            f"📦 Product {query_idx + 1}/{total_queries}",
            f"Starting search for: {query}"
        )

        logger.info(
            "Searching product",
            query=query,
            progress=f"{query_idx + 1}/{total_queries}",
        )

        all_results: list[PriceOption] = []

        # Run scrapers sequentially for this query
        for scraper_idx, scraper in enumerate(scrapers):
            # Report which scraper is running
            await report_progress(
                f"🔍 {scraper.name}",
                f"Searching {scraper.name} for {query}..."
            )

            logger.info(
                "Running scraper",
                scraper=scraper.name,
                query=query,
                progress=f"Scraper {scraper_idx + 1}/{len(scrapers)}",
            )
            try:
                # First just do the search (fast)
                results = await scraper.search(query, max_results_per_product)
                if results:
                    # Report results found
                    progress_output = f"✅ Found {len(results)} results for {query}:\n"
                    for r in results[:5]:  # Show top 5
                        price_str = f"{r.listed_price:,.0f} {r.currency}"
                        progress_output += f"  • {r.seller.name}: {price_str}\n"
                    if len(results) > 5:
                        progress_output += f"  ... and {len(results) - 5} more"
                    await report_progress(f"✅ {scraper.name}: {query}", progress_output)

                    all_results.extend(results)
                    logger.info(
                        "Scraper complete",
                        scraper=scraper.name,
                        results=len(results),
                    )
                else:
                    await report_progress(
                        f"⚠️ {scraper.name}: {query}",
                        f"No results found"
                    )
            except Exception as e:
                await report_progress(
                    f"❌ {scraper.name}: {query}",
                    f"Error: {str(e)[:100]}"
                )
                logger.warning(
                    "Scraper failed",
                    scraper=scraper.name,
                    error=str(e),
                )

        # After all scrapers complete for this query, deduplicate
        results_by_query[query] = deduplicate_results(all_results)

        await report_progress(
            f"📊 {query} complete",
            f"Found {len(results_by_query[query])} unique results after deduplication"
        )
        logger.info(
            "Product search complete",
            query=query,
            total_results=len(results_by_query[query]),
        )

    # Report starting aggregation
    await report_progress(
        "🔄 Aggregating results",
        f"Finding bundle opportunities across {len(results_by_query)} products..."
    )

    # Aggregate by seller
    aggregations = aggregate_by_seller(results_by_query, top_stores)

    # Step 2: Check availability of missing products at promising sellers
    bundle_sellers = [a for a in aggregations if a.product_count >= 2]
    all_queries = set(queries)

    # Helper: get expected price range for a product based on existing results
    def get_price_range(query: str) -> tuple[float, float]:
        """Get min/max reasonable price for a product based on existing results."""
        prices = [r.listed_price for r in results_by_query.get(query, []) if r.listed_price > 50]
        if not prices:
            return (100, 50000)  # Default range if no reference
        min_price = min(prices) * 0.5  # Allow 50% below min
        max_price = max(prices) * 2.0  # Allow 2x above max
        return (min_price, max_price)

    for agg in bundle_sellers:
        missing_queries = all_queries - set(agg.product_queries)
        if not missing_queries:
            continue  # Seller already has all products

        # Get seller's website domain from SELLER_DOMAINS mapping or product URL
        seller_domain = None

        # First try the normalized name -> domain mapping
        if agg.normalized_name in SELLER_DOMAINS:
            seller_domain = SELLER_DOMAINS[agg.normalized_name]
        else:
            # Fallback: try to extract from seller.website or product URL
            for product in agg.products:
                # Prefer seller.website over product.url (product.url might be Zap/Google)
                url_to_check = product.seller.website or product.url
                if url_to_check:
                    from urllib.parse import urlparse
                    parsed = urlparse(url_to_check)
                    domain = parsed.netloc
                    if domain.startswith("www."):
                        domain = domain[4:]
                    # Skip aggregator domains
                    if domain and not any(agg_domain in domain for agg_domain in ["google.com", "zap.co.il", "pricez"]):
                        seller_domain = domain
                        break

        if not seller_domain or "google.com" in seller_domain:
            logger.debug(
                "Skipping seller - no valid domain found",
                seller=agg.seller_name,
                normalized_name=agg.normalized_name,
            )
            continue  # Skip if no valid domain

        logger.info(
            "Site-search for missing products",
            seller=agg.seller_name,
            normalized_name=agg.normalized_name,
            seller_domain=seller_domain,
            domain_source="mapping" if agg.normalized_name in SELLER_DOMAINS else "fallback",
            missing_products=list(missing_queries),
        )

        await report_progress(
            f"🔎 Checking {agg.seller_name}",
            f"Looking for {len(missing_queries)} missing products at {seller_domain}..."
        )

        # Search for missing products at this seller's site
        import httpx
        from src.config.settings import settings

        for missing_query in missing_queries:
            if not settings.serpapi_key:
                break

            try:
                # Use Google site-specific search
                search_query = f"site:{seller_domain} {missing_query}"

                params = {
                    "engine": "google",
                    "q": search_query,
                    "gl": "il",
                    "hl": "he",
                    "api_key": settings.serpapi_key,
                    "num": 5,
                }

                async with httpx.AsyncClient(timeout=15.0) as client:
                    response = await client.get("https://serpapi.com/search.json", params=params)
                    if response.status_code == 200:
                        data = response.json()
                        organic_results = data.get("organic_results", [])

                        if organic_results:
                            # Found the product at this seller!
                            result_url = organic_results[0].get("link", "")
                            logger.info(
                                "Found missing product at seller",
                                seller=agg.seller_name,
                                query=missing_query,
                                url=result_url[:80],
                            )

                            # Try to get price from the page
                            from src.tools.scraping.http_client import get_http_client
                            from src.tools.scraping.price_extractor import get_price_extractor

                            http_client = get_http_client()
                            page_response = await http_client.get(result_url)
                            price = None
                            if page_response:
                                extractor = get_price_extractor()
                                price_result = extractor.extract(page_response.text, result_url)
                                if price_result:
                                    price = price_result.price

                            # Validate price against expected range
                            min_price, max_price = get_price_range(missing_query)

                            if price and min_price <= price <= max_price:
                                # Price is reasonable - add to results
                                from datetime import datetime

                                new_result = PriceOption(
                                    product_id=missing_query,
                                    seller=SellerInfo(
                                        name=agg.seller_name,
                                        website=result_url,
                                        country="IL",
                                        source="site_search",
                                    ),
                                    listed_price=price,
                                    currency="ILS",
                                    url=result_url,
                                    scraped_at=datetime.now(),
                                )

                                if missing_query not in results_by_query:
                                    results_by_query[missing_query] = []
                                results_by_query[missing_query].append(new_result)

                                await report_progress(
                                    f"✅ Found at {agg.seller_name}",
                                    f"{missing_query}: {price:,.0f} ILS"
                                )
                            elif price:
                                # Price extracted but out of expected range
                                logger.warning(
                                    "Price out of expected range",
                                    seller=agg.seller_name,
                                    query=missing_query,
                                    price=price,
                                    expected_range=(min_price, max_price),
                                )
                                await report_progress(
                                    f"⚠️ {agg.seller_name}",
                                    f"{missing_query}: price {price:,.0f} ILS seems wrong (expected {min_price:,.0f}-{max_price:,.0f})"
                                )
                            else:
                                await report_progress(
                                    f"⚠️ {agg.seller_name}",
                                    f"Found {missing_query} but couldn't extract price"
                                )
                        else:
                            logger.debug(
                                "Product not found at seller site",
                                seller=agg.seller_name,
                                query=missing_query,
                            )

            except Exception as e:
                logger.warning(
                    "Site search failed",
                    seller=agg.seller_name,
                    query=missing_query,
                    error=str(e),
                )

    # Re-aggregate with any newly found products
    if bundle_sellers:
        await report_progress(
            "🔄 Re-aggregating",
            "Updating bundle opportunities with newly found products..."
        )
        aggregations = aggregate_by_seller(results_by_query, top_stores)

    # Report final aggregation results
    bundle_sellers = [a for a in aggregations if a.product_count >= 2]
    if bundle_sellers:
        bundle_summary = f"Found {len(bundle_sellers)} stores with bundle opportunities:\n"
        for agg in bundle_sellers[:5]:
            bundle_summary += f"  • {agg.seller_name}: {agg.product_count}/{len(queries)} products, {agg.total_price:,.0f} ILS total\n"
        await report_progress("🎯 Final bundle opportunities", bundle_summary)
    else:
        await report_progress("ℹ️ No bundles", "No stores found selling multiple products")

    # Format output
    output = []

    # Section 1: Bundle opportunities (sellers with 2+ products)
    bundle_sellers = [a for a in aggregations if a.product_count >= 2]
    if bundle_sellers:
        output.append(f"=== BUNDLE OPPORTUNITIES ({len(bundle_sellers)} stores) ===\n")

        for i, agg in enumerate(bundle_sellers, 1):
            rating_str = f" (Rating: {agg.average_rating:.1f}/5)" if agg.average_rating else ""
            output.append(f"{i}. {agg.seller_name}{rating_str}")
            output.append(f"   Offers {agg.product_count}/{len(queries)} products:")

            for product in agg.products:
                # Find which query this product matched
                query_match = ""
                for query, price_option in zip(agg.product_queries, agg.products):
                    if price_option == product:
                        query_match = query
                        break
                output.append(f"   - {query_match}: {product.listed_price:,.0f} {product.currency} | {product.url}")

            output.append(f"   Total: {agg.total_price:,.0f} ILS")

            if agg.contact:
                output.append(f"   Contact: {agg.contact}")

            output.append("   Negotiation: Ask for bundle discount")
            output.append("")

    # Section 2: Full results per product (same format as single product search)
    for query in queries:
        results = results_by_query.get(query, [])
        output.append(f"\n=== {query} ===\n")

        if not results:
            output.append("No results found\n")
            continue

        # Rank results by combined score (price and reputation)
        def rank_score(result: PriceOption) -> float:
            """Lower score = better. Combines price rank with reputation penalty."""
            price_score = result.listed_price
            rating = result.seller.reliability_score or 3.0
            reputation_multiplier = 1.0 - ((rating - 3.0) / 10.0)
            return price_score * reputation_multiplier

        results_sorted = sorted(results, key=rank_score)
        top_results = results_sorted[:5]

        output.append(f"Top {len(top_results)} results (ranked by price + reputation):\n")

        for i, result in enumerate(top_results, 1):
            rating_str = ""
            if result.seller.reliability_score:
                rating_str = f" (Rating: {result.seller.reliability_score:.1f}/5)"

            source_str = ""
            if result.seller.source:
                source_str = f" [{result.seller.source}]"

            contact_str = ""
            if result.seller.whatsapp_number:
                contact_str = f"   Contact: {result.seller.whatsapp_number}\n"

            output.append(
                f"{i}. {result.seller.name}{rating_str}{source_str}\n"
                f"   Price: {result.listed_price:,.0f} {result.currency}\n"
                f"   URL: {result.url}\n"
                f"{contact_str}"
            )

    return "\n".join(output)


# Create cached version and tool version for multi-product search
_search_multiple_products_cached = cached(
    cache_type="agent", key_prefix="search_multiple_products"
)(_search_multiple_products_impl)
search_multiple_products = function_tool(
    _search_multiple_products_cached, name_override="search_multiple_products"
)


async def _search_aggregators_impl(
    query: str,
    country: str = "IL",
    max_results: int = 15,
) -> str:
    """Search specifically on aggregator sites (Zap, WiseBuy) for better price discovery.

    Aggregator sites like Zap.co.il often have better coverage for appliances and
    electronics that may not rank highly in regular Google search. This function
    prioritizes these sources for finding sellers with competitive prices.

    Args:
        query: Product search query (model number works best)
        country: Country code (default: IL)
        max_results: Max results per aggregator

    Returns:
        Formatted string with results from aggregator sites
    """
    import structlog
    logger = structlog.get_logger()

    await report_progress(
        "🔍 Aggregator Search",
        f"Searching price comparison sites for: {query}"
    )

    all_scrapers = ScraperRegistry.get_scrapers_for_country(country)

    # Filter to only aggregator scrapers
    aggregator_scrapers = [s for s in all_scrapers if s.name in AGGREGATOR_SCRAPERS]

    if not aggregator_scrapers:
        return f"No aggregator scrapers available for country: {country}"

    all_results: list[PriceOption] = []
    errors: list[str] = []

    for scraper in aggregator_scrapers:
        await report_progress(
            f"🔍 {scraper.name}",
            f"Deep search on {scraper.name} for {query}..."
        )

        try:
            results = await scraper.search(query, max_results)
            await record_search(scraper.name, cached=False)

            if results:
                progress_output = f"✅ Found {len(results)} listings:\n"
                for r in results[:5]:
                    price_str = f"{r.listed_price:,.0f} {r.currency}"
                    rating_str = f" ({r.seller.reliability_score:.1f}★)" if r.seller.reliability_score else ""
                    progress_output += f"  • {r.seller.name}{rating_str}: {price_str}\n"
                if len(results) > 5:
                    progress_output += f"  ... and {len(results) - 5} more"
                await report_progress(f"✅ {scraper.name}", progress_output)
                all_results.extend(results)
            else:
                await report_progress(f"⚠️ {scraper.name}", "No results found")
                await record_warning(f"{scraper.name}: No results for {query}")

        except Exception as e:
            await report_progress(f"❌ {scraper.name}", f"Error: {str(e)[:100]}")
            await record_error(f"{scraper.name}: {str(e)[:200]}")
            errors.append(f"{scraper.__class__.__name__}: {str(e)}")

    if not all_results:
        if errors:
            return f"No products found on aggregator sites for '{query}'. Errors: {'; '.join(errors)}"
        return f"No products found on aggregator sites for '{query}'"

    # Deduplicate results
    all_results = deduplicate_results(all_results)

    # Sort by price (ascending), with rating as tiebreaker
    def sort_key(result: PriceOption) -> tuple:
        price = result.listed_price
        # Higher rating = lower sort value (better)
        rating = -(result.seller.reliability_score or 0)
        return (price, rating)

    all_results.sort(key=sort_key)

    # Limit to top results
    top_results = all_results[:10]

    # Format output
    output = [f"Aggregator Search Results for '{query}' ({len(top_results)} listings from price comparison sites):\n"]

    for i, result in enumerate(top_results, 1):
        rating_str = ""
        if result.seller.reliability_score:
            rating_str = f" (Rating: {result.seller.reliability_score:.1f}/5)"

        source_str = f" [{result.seller.source}]" if result.seller.source else ""

        contact_str = ""
        if result.seller.whatsapp_number:
            contact_str = f"   Contact: {result.seller.whatsapp_number}\n"

        output.append(
            f"{i}. {result.seller.name}{rating_str}{source_str}\n"
            f"   Price: {result.listed_price:,.0f} {result.currency}\n"
            f"   URL: {result.url}\n"
            f"{contact_str}"
        )

    if errors:
        output.append(f"\nNote: Some aggregators had issues: {'; '.join(errors)}")

    return "\n".join(output)


# Create cached version and tool version for aggregator search
_search_aggregators_cached = cached(
    cache_type="agent", key_prefix="search_aggregators"
)(_search_aggregators_impl)
search_aggregators = function_tool(
    _search_aggregators_cached, name_override="search_aggregators"
)


@function_tool
def rank_options(options_summary: str, criteria: str = "price") -> str:
    """Analyze and rank purchase options based on criteria.

    Args:
        options_summary: Summary of available options
        criteria: Ranking criteria (price, reliability, or balanced)

    Returns:
        Analysis and recommendations
    """
    # This is a helper tool for the agent to structure its thinking
    return f"Analyze and rank the following options by {criteria}:\n{options_summary}"


# Define the product research agent
product_research_agent = Agent(
    name="ProductResearch",
    instructions="""You are a product research specialist. Your job is to find the best purchase options for products.

IMPORTANT - Search Query Formatting:
Price comparison sites work best with simple, concise search queries. Before searching:
- Extract just the model number or brand + model (e.g., "RF72DG9620B1" or "Samsung RF72DG9620B1")
- Remove descriptive words like "fridge", "refrigerator", "phone", etc.
- Remove formatting like "(Model: ...)" or brackets
- If the model number is specific, search by model number alone first
- If that returns no results, try brand + simplified product name

Examples of query transformation:
- "Samsung fridge (Model: RF72DG9620B1)" → "RF72DG9620B1"
- "Apple iPhone 15 Pro Max 256GB smartphone" → "iPhone 15 Pro Max 256GB"
- "Sony WH-1000XM5 headphones" → "WH-1000XM5"

SINGLE PRODUCT SEARCH:
When given a single product to research:
1. Transform the search query to a simple, search-friendly format
2. Use search_products to find available options - it returns the TOP 5 sellers ranked by price + reputation
3. If no results, try alternative query formats (just model number, or brand + category)

The search_products tool automatically:
- Searches multiple sources (Zap, WiseBuy, Google Shopping, Google Search)
- Extracts contact info (phone/WhatsApp) when available
- Ranks results by combining price and seller reputation
- Returns only the top 5 options ready for negotiation

AGGREGATOR-FOCUSED SEARCH (Better Price Discovery):
For appliances and electronics, use search_aggregators to search specifically on price comparison sites (Zap, WiseBuy):
- These aggregators often have better coverage for appliances/electronics than general Google search
- Returns up to 10 listings from aggregator sites, sorted by price
- Use when: (1) Initial search returned few results, (2) User wants best prices for appliances/electronics
- Example: search_aggregators("RF72DG9620B1") finds all Zap + WiseBuy listings

MULTI-PRODUCT SEARCH (Bundle Deals):
When the user wants to buy multiple products:
1. Use search_multiple_products with a list of product queries (transformed as above)
2. The tool automatically finds stores selling multiple products
3. Prioritizes bundle opportunities with negotiation tips

Example: User says "I need a fridge, oven, and washing machine"
→ search_multiple_products(["RF72DG9620B1", "BFL523MB1F", "LG F4V5"])

NEGOTIATION STRATEGY:
- Stores offering multiple products = bundle discount opportunity
- Always mention competitor prices as leverage
- Bundle purchases have stronger negotiating power

Present the results to the user as-is. Each result includes:
- Seller name and rating
- Price
- Contact info if available
- Direct link to the seller's page

Always search in the correct country based on the user's location.
""",
    tools=[search_products, get_seller_contact, search_multiple_products, search_aggregators, rank_options],
)
