"""Product discovery agent for AI-powered product recommendations.

This agent helps users discover products based on natural language requirements
like "I need a silent fridge for a family of 4" by:
1. Extracting specific criteria using LLM (dB levels, capacity, etc.)
2. Searching for products that match those criteria
3. Analyzing and formatting results as structured JSON
"""

import json
import os
import re
import time
from typing import Optional

from agents import Agent, function_tool
from openai import AsyncOpenAI

from src.tools.scraping import ScraperRegistry
from src.cache import cached
from src.observability import report_progress, record_search, record_error, record_warning


# Initialize OpenAI client for LLM calls within tools
def get_openai_client() -> AsyncOpenAI:
    """Get OpenAI client with API key from environment."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set")
    return AsyncOpenAI(api_key=api_key)


# ============================================================================
# Tool 1: Extract Product Criteria
# ============================================================================

async def _extract_product_criteria_impl(
    requirement: str,
) -> str:
    """Extract specific, searchable criteria from user's natural language requirement.

    Uses LLM to analyze the requirement and determine concrete specifications
    like noise level thresholds, capacity requirements, energy ratings, etc.

    Args:
        requirement: User's natural language requirement (e.g., "silent fridge for family of 4")

    Returns:
        JSON with extracted criteria, search terms, and recommended brands
    """
    import structlog
    logger = structlog.get_logger()

    await report_progress(
        "🧠 Analyzing requirements",
        f"Extracting criteria from: {requirement}"
    )

    # Use LLM to extract structured criteria
    try:
        client = get_openai_client()

        system_prompt = """You are a product specification expert. Your task is to analyze a user's natural language
product requirement and extract specific, measurable criteria for product selection.

For each requirement, determine:
1. The product category
2. Specific numeric criteria (e.g., noise < 40 dB, capacity > 400L)
3. Effective search terms to find matching products
4. Recommended brands known for these features

You MUST respond with valid JSON only, no other text."""

        user_prompt = f"""Analyze this product requirement and extract specific criteria:

"{requirement}"

Respond with this exact JSON structure:
{{
  "category": "the product category (e.g., refrigerator, washing machine)",
  "criteria": [
    {{
      "attribute": "attribute name (e.g., noise_level, capacity, energy_rating)",
      "value": "specific threshold (e.g., <40, >400, A++)",
      "unit": "unit of measurement (e.g., dB, liters, rating)",
      "reason": "why this matters for the user's needs"
    }}
  ],
  "search_terms": ["list of effective search queries"],
  "recommended_brands": ["brands known for these features"],
  "price_range_estimate": "estimated price range in local currency"
}}"""

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=1000,
        )

        result_text = response.choices[0].message.content.strip()

        # Clean up response - remove markdown code blocks if present
        if result_text.startswith("```"):
            result_text = re.sub(r'^```(?:json)?\n?', '', result_text)
            result_text = re.sub(r'\n?```$', '', result_text)

        # Validate JSON
        criteria = json.loads(result_text)

        await report_progress(
            "✅ Criteria extracted",
            f"Found {len(criteria.get('criteria', []))} specific criteria"
        )

        # Log extracted criteria for debugging
        logger.info("Extracted criteria", requirement=requirement, criteria=criteria)

        return json.dumps(criteria, indent=2)

    except json.JSONDecodeError as e:
        logger.error("Failed to parse criteria JSON", error=str(e), response=result_text[:500])
        await record_error(f"Criteria extraction JSON error: {str(e)}")
        # Return fallback criteria
        return json.dumps({
            "category": "appliance",
            "criteria": [{"attribute": "general", "value": "high quality", "unit": "", "reason": "Based on user requirements"}],
            "search_terms": [requirement],
            "recommended_brands": [],
            "price_range_estimate": "varies"
        })

    except Exception as e:
        logger.error("Criteria extraction failed", error=str(e))
        await record_error(f"Criteria extraction failed: {str(e)[:100]}")
        return json.dumps({
            "category": "appliance",
            "criteria": [],
            "search_terms": [requirement],
            "recommended_brands": [],
            "error": str(e)
        })


_extract_product_criteria_cached = cached(
    cache_type="agent", key_prefix="extract_criteria"
)(_extract_product_criteria_impl)
extract_product_criteria = function_tool(
    _extract_product_criteria_cached, name_override="extract_product_criteria"
)


# ============================================================================
# Tool 2: Search Products (Improved)
# ============================================================================

async def _search_products_with_criteria_impl(
    search_terms: str,
    category: str,
    country: str = "IL",
    max_results: int = 15,
) -> str:
    """Search for products using targeted search terms.

    Args:
        search_terms: Comma-separated search terms from criteria extraction
        category: Product category for context
        country: Country code (default: IL)
        max_results: Maximum number of products to return

    Returns:
        JSON list of raw product results with names, prices, URLs
    """
    import structlog
    from src.tools.scraping.filters import deduplicate_results

    logger = structlog.get_logger()

    # Parse search terms
    terms = [t.strip() for t in search_terms.split(",")]

    await report_progress(
        "🔍 Searching products",
        f"Running {len(terms)} targeted searches for {category}"
    )

    scrapers = ScraperRegistry.get_scrapers_for_country(country)

    if not scrapers:
        return json.dumps({
            "error": f"No scrapers available for country: {country}",
            "products": []
        })

    all_results = []
    errors = []

    # Search with each term
    for term in terms[:3]:  # Limit to 3 search terms
        for scraper in scrapers:
            await report_progress(
                f"🔍 {scraper.name}",
                f"Searching: {term}"
            )

            try:
                results = await scraper.search(term, max_results=max_results // len(terms))
                await record_search(scraper.name, cached=False)

                if results:
                    await report_progress(
                        f"✅ {scraper.name}",
                        f"Found {len(results)} results for '{term}'"
                    )
                    all_results.extend(results)
                else:
                    await report_progress(f"⚠️ {scraper.name}", f"No results for '{term}'")

            except Exception as e:
                await report_progress(f"❌ {scraper.name}", f"Error: {str(e)[:100]}")
                await record_error(f"{scraper.name}: {str(e)[:200]}")
                errors.append(f"{scraper.name}: {str(e)[:50]}")

    if not all_results:
        return json.dumps({
            "error": "No products found",
            "search_terms": terms,
            "errors": errors,
            "products": []
        })

    # Deduplicate
    all_results = deduplicate_results(all_results)

    # Convert to simple format for LLM analysis
    products = []
    seen_names = set()

    for result in all_results[:max_results]:
        name = result.seller.name
        name_key = name.lower()[:40]

        if name_key in seen_names:
            continue
        seen_names.add(name_key)

        products.append({
            "name": name,
            "brand": extract_brand(name),
            "model_number": extract_model_number(name),
            "price": result.listed_price,
            "currency": result.currency,
            "url": result.url,
            "source": result.seller.source,
            "rating": result.seller.reliability_score,
        })

    await report_progress(
        "✅ Search complete",
        f"Found {len(products)} unique products"
    )

    return json.dumps({
        "category": category,
        "products": products,
        "search_terms_used": terms[:3],
        "total_found": len(products),
    }, indent=2)


_search_products_with_criteria_cached = cached(
    cache_type="agent", key_prefix="search_with_criteria"
)(_search_products_with_criteria_impl)
search_products_with_criteria = function_tool(
    _search_products_with_criteria_cached, name_override="search_products_with_criteria"
)


# ============================================================================
# Tool 3: Analyze and Format Products
# ============================================================================

async def _analyze_and_format_products_impl(
    products_json: str,
    criteria_json: str,
    original_requirement: str,
) -> str:
    """Analyze products against criteria and format for frontend display.

    Uses LLM to:
    1. Extract specs from product names/descriptions
    2. Score products against criteria
    3. Generate "why recommended" explanations
    4. Format as DiscoveredProduct[] JSON

    Args:
        products_json: JSON string of raw products from search
        criteria_json: JSON string of criteria from extraction
        original_requirement: Original user requirement for context

    Returns:
        JSON with products array matching frontend DiscoveredProduct type
    """
    import structlog
    logger = structlog.get_logger()

    await report_progress(
        "📊 Analyzing products",
        "Matching products to your criteria..."
    )

    try:
        products = json.loads(products_json)
        criteria = json.loads(criteria_json)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse input JSON", error=str(e))
        return json.dumps({"products": [], "error": f"Invalid input: {str(e)}"})

    product_list = products.get("products", [])
    criteria_list = criteria.get("criteria", [])
    category = criteria.get("category", "product")

    if not product_list:
        return json.dumps({"products": [], "error": "No products to analyze"})

    try:
        client = get_openai_client()

        system_prompt = """You are a product analyst. Given a list of products and selection criteria,
analyze each product and determine how well it matches the criteria.

For each product, extract any visible specs from the product name and determine:
1. Which criteria it likely meets (based on brand reputation, model patterns, etc.)
2. A clear "why recommended" explanation

You MUST respond with valid JSON only, no other text."""

        user_prompt = f"""Analyze these products for a customer looking for: "{original_requirement}"

CRITERIA TO MATCH:
{json.dumps(criteria_list, indent=2)}

PRODUCTS FOUND:
{json.dumps(product_list[:15], indent=2)}

For each product that matches the criteria well, output in this exact JSON format:
{{
  "products": [
    {{
      "id": "prod_<timestamp>_<index>",
      "name": "full product name",
      "brand": "brand name",
      "model_number": "model if found",
      "category": "{category}",
      "key_specs": ["spec 1", "spec 2", "spec 3"],
      "price_range": "₪X,XXX - ₪X,XXX",
      "why_recommended": "Clear explanation of how this product meets the user's specific requirements"
    }}
  ]
}}

IMPORTANT:
- Include only products that likely meet the criteria (3-5 best matches)
- For key_specs, include specific specs like "Noise: ~38 dB", "Capacity: 600L" if inferable
- Price range should use the product's actual price
- why_recommended should directly reference the user's requirements
- Generate unique IDs using current timestamp"""

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=2000,
        )

        result_text = response.choices[0].message.content.strip()

        # Clean up response
        if result_text.startswith("```"):
            result_text = re.sub(r'^```(?:json)?\n?', '', result_text)
            result_text = re.sub(r'\n?```$', '', result_text)

        result = json.loads(result_text)

        # Ensure products have valid IDs
        timestamp = int(time.time() * 1000)
        for i, product in enumerate(result.get("products", [])):
            if not product.get("id") or not product["id"].startswith("prod_"):
                product["id"] = f"prod_{timestamp}_{i}"

        await report_progress(
            "✅ Analysis complete",
            f"Found {len(result.get('products', []))} matching products"
        )

        logger.info("Product analysis complete",
                   input_count=len(product_list),
                   output_count=len(result.get("products", [])))

        return json.dumps(result, indent=2)

    except json.JSONDecodeError as e:
        logger.error("Failed to parse analysis JSON", error=str(e), response=result_text[:500])
        await record_error(f"Product analysis JSON error: {str(e)}")

        # Fallback: format products without LLM analysis
        fallback_products = []
        timestamp = int(time.time() * 1000)
        for i, p in enumerate(product_list[:5]):
            fallback_products.append({
                "id": f"prod_{timestamp}_{i}",
                "name": p.get("name", "Unknown"),
                "brand": p.get("brand"),
                "model_number": p.get("model_number"),
                "category": category,
                "key_specs": [],
                "price_range": f"₪{p.get('price', 0):,.0f}",
                "why_recommended": "Found matching your search criteria"
            })

        return json.dumps({"products": fallback_products})

    except Exception as e:
        logger.error("Product analysis failed", error=str(e))
        await record_error(f"Product analysis failed: {str(e)[:100]}")
        return json.dumps({"products": [], "error": str(e)})


_analyze_and_format_products_cached = cached(
    cache_type="agent", key_prefix="analyze_products"
)(_analyze_and_format_products_impl)
analyze_and_format_products = function_tool(
    _analyze_and_format_products_cached, name_override="analyze_and_format_products"
)


# ============================================================================
# Helper Functions
# ============================================================================

def extract_brand(product_name: str) -> Optional[str]:
    """Extract brand from product name."""
    known_brands = [
        "Samsung", "LG", "Bosch", "Siemens", "Miele", "AEG", "Electrolux",
        "Haier", "Whirlpool", "Beko", "Candy", "Gorenje", "Hisense",
        "Apple", "Sony", "Dell", "HP", "Lenovo", "Asus", "Acer",
        "Panasonic", "Sharp", "Toshiba", "Hitachi", "Frigidaire",
    ]
    name_lower = product_name.lower()
    for brand in known_brands:
        if brand.lower() in name_lower:
            return brand
    return None


def extract_model_number(product_name: str) -> Optional[str]:
    """Extract model number from product name using common patterns."""
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


# ============================================================================
# Product Discovery Agent
# ============================================================================

product_discovery_agent = Agent(
    name="ProductDiscovery",
    instructions="""You are a product discovery specialist that helps users find products matching their requirements.

## WORKFLOW (Follow these steps in order):

1. **EXTRACT CRITERIA** - Use `extract_product_criteria` with the user's requirement
   - This extracts specific specs (e.g., noise < 40 dB, capacity > 400L)
   - Returns search terms and recommended brands

2. **SEARCH PRODUCTS** - Use `search_products_with_criteria`
   - Pass the search_terms from step 1 (comma-separated)
   - Pass the category from step 1
   - Returns raw product listings

3. **ANALYZE & FORMAT** - Use `analyze_and_format_products`
   - Pass the products JSON from step 2
   - Pass the criteria JSON from step 1
   - Pass the original user requirement
   - Returns formatted products matching frontend expectations

## OUTPUT FORMAT:

After completing all 3 steps, return ONLY the JSON from step 3.
The JSON must have this structure:
```json
{
  "products": [
    {
      "id": "prod_...",
      "name": "Product Name",
      "brand": "Brand",
      "model_number": "MODEL123",
      "category": "refrigerator",
      "key_specs": ["Noise: 38 dB", "Capacity: 640L"],
      "price_range": "₪12,000 - ₪14,000",
      "why_recommended": "Explanation of why this matches requirements"
    }
  ]
}
```

## IMPORTANT:
- Always complete all 3 steps
- Your final response must be ONLY valid JSON (no markdown, no explanation)
- Include 3-5 products that best match the criteria
- Each product must have why_recommended explaining the match
""",
    tools=[extract_product_criteria, search_products_with_criteria, analyze_and_format_products],
)
