"""Product discovery agent for AI-powered product recommendations.

This agent helps users discover products based on natural language requirements
by performing deep research in the user's language, finding real product
recommendations, and validating they meet the criteria.

Approach:
1. Research criteria from multiple sources in user's language
2. Find specific product recommendations from reviews, social media, articles
3. Search for those specific products in local stores
4. Validate and score products against criteria
5. Always provide feedback about what was searched and why
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


# Country to language mapping
COUNTRY_LANGUAGES = {
    "IL": {
        "language": "Hebrew",
        "code": "he",
        "currency": "₪",
        "currency_name": "ILS",
        "metric_system": "metric",
        "volume_unit": "liters",
        "dimension_unit": "cm",
    },
    "US": {
        "language": "English",
        "code": "en",
        "currency": "$",
        "currency_name": "USD",
        "metric_system": "imperial",
        "volume_unit": "cubic feet",
        "dimension_unit": "inches",
    },
    "UK": {
        "language": "English",
        "code": "en",
        "currency": "£",
        "currency_name": "GBP",
        "metric_system": "metric",
        "volume_unit": "liters",
        "dimension_unit": "cm",
    },
    "DE": {
        "language": "German",
        "code": "de",
        "currency": "€",
        "currency_name": "EUR",
        "metric_system": "metric",
        "volume_unit": "liters",
        "dimension_unit": "cm",
    },
    "FR": {
        "language": "French",
        "code": "fr",
        "currency": "€",
        "currency_name": "EUR",
        "metric_system": "metric",
        "volume_unit": "liters",
        "dimension_unit": "cm",
    },
}

# Product type translations for common appliances
PRODUCT_TRANSLATIONS = {
    "he": {
        "refrigerator": "מקרר",
        "fridge": "מקרר",
        "washing machine": "מכונת כביסה",
        "dishwasher": "מדיח כלים",
        "air conditioner": "מזגן",
        "oven": "תנור",
        "dryer": "מייבש כביסה",
        "microwave": "מיקרוגל",
        "freezer": "מקפיא",
        "vacuum": "שואב אבק",
        "tv": "טלוויזיה",
        "television": "טלוויזיה",
        "laptop": "מחשב נייד",
        "phone": "טלפון",
        "quiet": "שקט",
        "silent": "שקט",
        "family": "משפחה",
        "large": "גדול",
        "small": "קטן",
        "energy efficient": "חסכוני באנרגיה",
    },
    "de": {
        "refrigerator": "Kühlschrank",
        "fridge": "Kühlschrank",
        "washing machine": "Waschmaschine",
        "dishwasher": "Geschirrspüler",
        "quiet": "leise",
        "silent": "leise",
    },
    "fr": {
        "refrigerator": "réfrigérateur",
        "fridge": "réfrigérateur",
        "washing machine": "lave-linge",
        "dishwasher": "lave-vaisselle",
        "quiet": "silencieux",
        "silent": "silencieux",
    },
}


def get_country_info(country: str) -> dict:
    """Get language and currency info for a country."""
    return COUNTRY_LANGUAGES.get(country.upper(), {
        "language": "English",
        "code": "en",
        "currency": "$",
        "currency_name": "USD",
        "metric_system": "metric",
        "volume_unit": "liters",
        "dimension_unit": "cm",
    })


def translate_query_to_native(query: str, lang_code: str) -> str:
    """Translate an English query to the native language using word-level translation.

    This ensures searches are performed in the local language even if
    the user typed in English.
    """
    if lang_code == "en" or lang_code not in PRODUCT_TRANSLATIONS:
        return query

    translations = PRODUCT_TRANSLATIONS[lang_code]
    translated = query.lower()

    # Sort by length (longest first) to avoid partial replacements
    sorted_terms = sorted(translations.keys(), key=len, reverse=True)

    for eng_term in sorted_terms:
        if eng_term in translated:
            translated = translated.replace(eng_term, translations[eng_term])

    return translated


def get_openai_client() -> AsyncOpenAI:
    """Get OpenAI client with API key from environment."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set")
    return AsyncOpenAI(api_key=api_key)


# ============================================================================
# Tool 1: Deep Research - Criteria and Product Discovery
# ============================================================================

async def _research_and_discover_impl(
    requirement: str,
    country: str = "IL",
) -> str:
    """Perform deep research to understand product criteria and find recommendations.

    This tool:
    1. Searches in the user's language for buying guides and expert recommendations
    2. Looks for specific product recommendations from reviews, social media, news
    3. Extracts realistic, research-backed criteria
    4. Returns both criteria AND specific product recommendations

    Args:
        requirement: User's natural language requirement
        country: User's country code for localized search

    Returns:
        JSON with researched criteria and product recommendations
    """
    import structlog
    import httpx
    from src.config.settings import settings

    logger = structlog.get_logger()
    country_info = get_country_info(country)
    language = country_info["language"]
    lang_code = country_info["code"]
    currency = country_info["currency"]

    await report_progress(
        "🔍 Researching",
        f"Searching for expert recommendations in {language}..."
    )

    # Collect research from web searches
    research_data = {
        "buying_guides": [],
        "product_recommendations": [],
        "expert_opinions": [],
        "social_mentions": [],
    }

    if not settings.serpapi_key:
        await record_warning("No SerpAPI key - using LLM knowledge only")
    else:
        # Search queries in user's language
        search_queries = _generate_research_queries(requirement, language, lang_code)

        for query_info in search_queries[:4]:  # Limit to 4 queries
            try:
                await report_progress(
                    "🔍 Searching",
                    f"{query_info['purpose']}: {query_info['query'][:50]}..."
                )

                params = {
                    "engine": "google",
                    "q": query_info["query"],
                    "gl": country.lower(),
                    "hl": lang_code,
                    "api_key": settings.serpapi_key,
                    "num": 8,
                }

                async with httpx.AsyncClient(timeout=15.0) as client:
                    response = await client.get("https://serpapi.com/search.json", params=params)
                    if response.status_code == 200:
                        data = response.json()
                        organic_results = data.get("organic_results", [])

                        for result in organic_results[:5]:
                            title = result.get("title", "")
                            snippet = result.get("snippet", "")
                            link = result.get("link", "")

                            if title and snippet:
                                research_data[query_info["category"]].append({
                                    "title": title,
                                    "snippet": snippet,
                                    "url": link,
                                    "source_type": query_info["purpose"],
                                })

                        await record_search("google_research", cached=False)

            except Exception as e:
                logger.warning("Research query failed", query=query_info["query"], error=str(e))
                await record_error(f"Research failed: {str(e)[:100]}")

    # Use LLM to analyze research and extract criteria + recommendations
    await report_progress(
        "🧠 Analyzing",
        "Extracting criteria and recommendations from research..."
    )

    try:
        client = get_openai_client()

        research_summary = json.dumps(research_data, indent=2, ensure_ascii=False)

        system_prompt = f"""You are a product research expert helping users in {country} find the right products.
Your task is to analyze research data and extract:
1. MARKET-REALISTIC criteria based on what's actually available in {country}
2. Specific product models that experts recommend
3. Price expectations in local currency ({currency})

CRITICAL - MARKET REALITY:
- Research what products are ACTUALLY AVAILABLE in {country}, not ideal specs
- For noise levels: Find the TYPICAL range in the local market. If most fridges in {country} are 42-46dB, then 42dB IS "quiet" for that market
- Set "ideal_value" as the user's wish and "market_value" as what's realistically available
- Include "market_context" explaining the local reality (e.g., "In Israel, refrigerators typically range 42-46dB, with 42dB being the quietest available")
- For capacity: Research actual recommendations for the use case (e.g., family size)
- Include specific model numbers when mentioned in research
- Prices must be in {currency} ({country_info['currency_name']})
- If research is insufficient, acknowledge uncertainty

UNITS - Use {country}'s measurement system:
- Volume: {country_info['volume_unit']} (NOT {('cubic feet' if country_info['volume_unit'] == 'liters' else 'liters')})
- Dimensions: {country_info['dimension_unit']} (NOT {('inches' if country_info['dimension_unit'] == 'cm' else 'cm')})
- Always convert to local units if source uses different system

Respond with valid JSON only."""

        user_prompt = f"""Analyze this research for: "{requirement}"
User country: {country} (currency: {currency})

RESEARCH DATA:
{research_summary}

Based on this research, provide:
{{
  "category": "product category",
  "criteria": [
    {{
      "attribute": "attribute name",
      "ideal_value": "what user ideally wants",
      "market_value": "what's realistically available in {country}",
      "market_context": "explanation of local market reality",
      "is_flexible": true/false,
      "source": "where this came from",
      "confidence": "high/medium/low"
    }}
  ],
  "recommended_models": [
    {{
      "model": "specific model name/number",
      "brand": "brand name",
      "source": "where recommended (article title, expert, etc.)",
      "why_recommended": "why this model fits the requirement"
    }}
  ],
  "search_terms": {{
    "native_language": ["search terms in {language} - ALWAYS include native language terms"],
    "model_searches": ["specific model searches"],
    "category_searches": ["category + feature searches in {language}"]
  }},
  "price_range": {{
    "min": number,
    "max": number,
    "currency": "{currency}",
    "source": "where this estimate comes from"
  }},
  "research_quality": "good/moderate/limited",
  "market_notes": "important notes about the {country} market for this product category"
}}"""

        response = await client.chat.completions.create(
            model="gpt-4o",  # Using GPT-4o for better research analysis
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

        # Add metadata
        result["country"] = country
        result["language"] = language
        result["original_requirement"] = requirement

        criteria_count = len(result.get("criteria", []))
        models_count = len(result.get("recommended_models", []))

        await report_progress(
            "✅ Research complete",
            f"Found {criteria_count} criteria, {models_count} recommended models"
        )

        logger.info("Research complete",
                   requirement=requirement,
                   criteria_count=criteria_count,
                   models_count=models_count,
                   research_quality=result.get("research_quality"))

        return json.dumps(result, indent=2, ensure_ascii=False)

    except json.JSONDecodeError as e:
        logger.error("Failed to parse research JSON", error=str(e))
        await record_error(f"Research JSON error: {str(e)}")
        return json.dumps({
            "category": "appliance",
            "criteria": [],
            "recommended_models": [],
            "search_terms": {"local_language": [requirement], "model_searches": [], "category_searches": []},
            "error": f"Research analysis failed: {str(e)}",
            "original_requirement": requirement,
            "country": country,
        }, ensure_ascii=False)

    except Exception as e:
        logger.error("Research failed", error=str(e))
        await record_error(f"Research failed: {str(e)[:100]}")
        return json.dumps({
            "category": "appliance",
            "criteria": [],
            "recommended_models": [],
            "search_terms": {"local_language": [requirement], "model_searches": [], "category_searches": []},
            "error": str(e),
            "original_requirement": requirement,
            "country": country,
        }, ensure_ascii=False)


def _generate_research_queries(requirement: str, language: str, lang_code: str) -> list:
    """Generate research queries in the user's native language.

    Always generates queries in the native language, even if user typed in English.
    """
    queries = []

    # Translate the requirement to native language
    native_requirement = translate_query_to_native(requirement, lang_code)

    # Hebrew-specific queries for Israel
    if lang_code == "he":
        # Extract product type from requirement
        product_hints = {
            "refrigerator": "מקרר",
            "fridge": "מקרר",
            "washing machine": "מכונת כביסה",
            "dishwasher": "מדיח כלים",
            "air conditioner": "מזגן",
            "oven": "תנור",
            "dryer": "מייבש כביסה",
        }

        hebrew_product = None
        for eng, heb in product_hints.items():
            if eng in requirement.lower():
                hebrew_product = heb
                break

        if hebrew_product:
            queries.extend([
                {
                    "query": f"{hebrew_product} שקט מומלץ 2024",
                    "purpose": "Finding quiet/recommended models",
                    "category": "product_recommendations"
                },
                {
                    "query": f"איזה {hebrew_product} מתאים למשפחה",
                    "purpose": "Family size recommendations",
                    "category": "buying_guides"
                },
                {
                    "query": f"{hebrew_product} ביקורות המלצות",
                    "purpose": "Reviews and recommendations",
                    "category": "expert_opinions"
                },
                {
                    "query": f"מדריך קניית {hebrew_product} מה חשוב",
                    "purpose": "Buying guide - what matters",
                    "category": "buying_guides"
                },
                # Market reality queries
                {
                    "query": f"רמת רעש {hebrew_product} בישראל טווח dB",
                    "purpose": "Market noise level range",
                    "category": "buying_guides"
                },
            ])
        else:
            # Use translated requirement
            queries.extend([
                {
                    "query": f"{native_requirement} מומלץ 2024",
                    "purpose": "Finding recommended models",
                    "category": "product_recommendations"
                },
                {
                    "query": f"{native_requirement} ביקורות המלצות",
                    "purpose": "Reviews and recommendations",
                    "category": "expert_opinions"
                },
            ])

        # Also add English queries for international research
        queries.append({
            "query": f"best quiet {requirement} specifications decibel range",
            "purpose": "International expert opinions",
            "category": "expert_opinions"
        })

    else:
        # English or other language queries
        queries.extend([
            {
                "query": f"best {requirement} 2024 reviews recommendations",
                "purpose": "Reviews and recommendations",
                "category": "product_recommendations"
            },
            {
                "query": f"{requirement} buying guide what to look for specifications",
                "purpose": "Buying guide criteria",
                "category": "buying_guides"
            },
            {
                "query": f"{requirement} noise level decibel range typical",
                "purpose": "Market noise level reality",
                "category": "buying_guides"
            },
            {
                "query": f"{requirement} expert recommendations reddit",
                "purpose": "Community recommendations",
                "category": "social_mentions"
            },
        ])

    return queries


_research_and_discover_cached = cached(
    cache_type="agent", key_prefix="research_discover"
)(_research_and_discover_impl)
research_and_discover = function_tool(
    _research_and_discover_cached, name_override="research_and_discover"
)


# ============================================================================
# Tool 2: Smart Product Search
# ============================================================================

async def _search_products_smart_impl(
    research_json: str,
    country: str = "IL",
    max_results: int = 20,
) -> str:
    """Search for products using smart strategies based on research.

    Search strategies (in order):
    1. Search for specific recommended models (highest priority)
    2. Search using local language terms
    3. Search category + key features

    Args:
        research_json: JSON from research_and_discover with criteria and recommendations
        country: Country code
        max_results: Maximum products to return

    Returns:
        JSON with search results and metadata about what was searched
    """
    import structlog
    from src.tools.scraping.filters import deduplicate_results

    logger = structlog.get_logger()

    try:
        research = json.loads(research_json)
    except json.JSONDecodeError:
        return json.dumps({
            "error": "Invalid research JSON",
            "products": [],
            "search_attempts": [],
        })

    search_terms = research.get("search_terms", {})
    recommended_models = research.get("recommended_models", [])
    category = research.get("category", "product")

    scrapers = ScraperRegistry.get_scrapers_for_country(country)

    if not scrapers:
        return json.dumps({
            "error": f"No scrapers available for country: {country}",
            "products": [],
            "search_attempts": [],
        })

    all_results = []
    search_attempts = []

    # Strategy 1: Search for specific recommended models
    model_searches = [m.get("model") for m in recommended_models if m.get("model")]
    model_searches.extend(search_terms.get("model_searches", []))

    for model in model_searches[:5]:  # Limit model searches
        await report_progress(
            "🔍 Model search",
            f"Looking for: {model}"
        )

        attempt = {"query": model, "strategy": "specific_model", "results": 0, "scrapers": []}

        for scraper in scrapers:
            try:
                results = await scraper.search(model, max_results=5)
                await record_search(scraper.name, cached=False)

                if results:
                    await report_progress(
                        f"✅ {scraper.name}",
                        f"Found {len(results)} for '{model}'"
                    )
                    all_results.extend(results)
                    attempt["results"] += len(results)
                    attempt["scrapers"].append({"name": scraper.name, "count": len(results)})

            except Exception as e:
                logger.warning("Model search failed", model=model, scraper=scraper.name, error=str(e))

        search_attempts.append(attempt)

    # Strategy 2: Search using native language terms
    native_terms = search_terms.get("native_language", search_terms.get("local_language", []))

    for term in native_terms[:3]:
        await report_progress(
            "🔍 Local search",
            f"Searching: {term}"
        )

        attempt = {"query": term, "strategy": "local_language", "results": 0, "scrapers": []}

        for scraper in scrapers:
            try:
                results = await scraper.search(term, max_results=max_results // 3)
                await record_search(scraper.name, cached=False)

                if results:
                    await report_progress(
                        f"✅ {scraper.name}",
                        f"Found {len(results)} for '{term}'"
                    )
                    all_results.extend(results)
                    attempt["results"] += len(results)
                    attempt["scrapers"].append({"name": scraper.name, "count": len(results)})

            except Exception as e:
                logger.warning("Local search failed", term=term, scraper=scraper.name, error=str(e))

        search_attempts.append(attempt)

    # Strategy 3: Category searches
    category_terms = search_terms.get("category_searches", [])

    for term in category_terms[:2]:
        await report_progress(
            "🔍 Category search",
            f"Searching: {term}"
        )

        attempt = {"query": term, "strategy": "category", "results": 0, "scrapers": []}

        for scraper in scrapers:
            try:
                results = await scraper.search(term, max_results=max_results // 3)
                await record_search(scraper.name, cached=False)

                if results:
                    all_results.extend(results)
                    attempt["results"] += len(results)
                    attempt["scrapers"].append({"name": scraper.name, "count": len(results)})

            except Exception as e:
                logger.warning("Category search failed", term=term, scraper=scraper.name, error=str(e))

        search_attempts.append(attempt)

    # Deduplicate results
    if all_results:
        all_results = deduplicate_results(all_results)

    # Convert to simple format
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

    total_attempts = len(search_attempts)
    successful_attempts = sum(1 for a in search_attempts if a["results"] > 0)

    await report_progress(
        "✅ Search complete",
        f"Found {len(products)} products from {successful_attempts}/{total_attempts} searches"
    )

    return json.dumps({
        "category": category,
        "products": products,
        "total_found": len(products),
        "search_attempts": search_attempts,
        "country": country,
    }, indent=2, ensure_ascii=False)


_search_products_smart_cached = cached(
    cache_type="agent", key_prefix="search_smart"
)(_search_products_smart_impl)
search_products_smart = function_tool(
    _search_products_smart_cached, name_override="search_products_smart"
)


# ============================================================================
# Tool 3: Analyze, Score, and Format Results
# ============================================================================

async def _analyze_and_format_results_impl(
    research_json: str,
    products_json: str,
) -> str:
    """Analyze products against criteria and format for display.

    This tool ALWAYS returns useful information, even if no products were found.
    It includes:
    - Criteria that were used
    - Products found (if any) with match scores
    - Explanation of what was searched
    - Suggestions if search was unsuccessful

    Args:
        research_json: JSON from research_and_discover
        products_json: JSON from search_products_smart

    Returns:
        JSON with products array and search summary for frontend
    """
    import structlog
    logger = structlog.get_logger()

    await report_progress(
        "📊 Analyzing",
        "Scoring products against criteria..."
    )

    try:
        research = json.loads(research_json)
        search_results = json.loads(products_json)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse input JSON", error=str(e))
        return json.dumps({
            "products": [],
            "search_summary": {"error": f"Invalid input: {str(e)}"},
        })

    products = search_results.get("products", [])
    criteria = research.get("criteria", [])
    recommended_models = research.get("recommended_models", [])
    original_requirement = research.get("original_requirement", "")
    category = research.get("category", "product")
    country = research.get("country", "IL")
    country_info = get_country_info(country)

    # Build search summary (always included)
    # Include market context from criteria
    market_notes = research.get("market_notes", "")
    criteria_with_context = []
    for c in criteria:
        criterion_text = f"• {c.get('attribute')}: "
        if c.get('market_value'):
            criterion_text += f"{c.get('market_value')} (market reality)"
            if c.get('market_context'):
                criterion_text += f" - {c.get('market_context')}"
        elif c.get('value'):
            criterion_text += f"{c.get('value')} ({c.get('source', 'research')})"
        else:
            criterion_text += f"{c.get('ideal_value', 'N/A')}"
        criteria_with_context.append(criterion_text)

    search_summary = {
        "original_requirement": original_requirement,
        "category": category,
        "country": country,
        "criteria_used": criteria,
        "recommended_models_searched": [m.get("model") for m in recommended_models],
        "search_attempts": search_results.get("search_attempts", []),
        "total_products_found": len(products),
        "research_quality": research.get("research_quality", "unknown"),
        "market_notes": market_notes,
    }

    # If no products found, return helpful response
    if not products:
        await report_progress(
            "⚠️ No products found",
            "Preparing search summary..."
        )

        suggestions = []
        if criteria:
            suggestions.append("Try relaxing some criteria")
        if recommended_models:
            suggestions.append(f"Search directly for: {', '.join([m.get('model', '') for m in recommended_models[:3]])}")
        suggestions.append("Try different keywords or product description")

        return json.dumps({
            "products": [],
            "search_summary": search_summary,
            "no_results_message": f"No products found matching '{original_requirement}'",
            "suggestions": suggestions,
            "criteria_feedback": criteria_with_context,
            "market_notes": market_notes,
        }, indent=2, ensure_ascii=False)

    # Analyze products with LLM - using ADAPTIVE FILTERING
    try:
        client = get_openai_client()

        system_prompt = f"""You are a product analyst using ADAPTIVE FILTERING.

Your job is to:
1. Score ALL products against criteria
2. If strict criteria eliminate all products, RELAX criteria based on market reality
3. Always return the BEST AVAILABLE products, even if they don't perfectly match

ADAPTIVE FILTERING RULES:
- If criteria specify "< 40dB" but best available is 42dB, accept 42dB as "best in market"
- Explain the adaptation: "While you requested <40dB, the quietest available in {country} is 42dB"
- Prioritize products that are relatively best, not just those matching absolute criteria
- Include market_reality_note explaining any adaptations made

UNITS - Use {country}'s measurement system:
- Volume: {country_info['volume_unit']} (NOT {('cubic feet' if country_info['volume_unit'] == 'liters' else 'liters')})
- Dimensions: {country_info['dimension_unit']}
- Currency for prices: {country_info['currency']} ({country_info['currency_name']})

Respond with valid JSON only."""

        user_prompt = f"""Analyze these products for: "{original_requirement}"

CRITERIA (may include market context):
{json.dumps(criteria, indent=2, ensure_ascii=False)}

MARKET NOTES:
{market_notes}

RECOMMENDED MODELS FROM RESEARCH:
{json.dumps(recommended_models, indent=2, ensure_ascii=False)}

PRODUCTS FOUND ({len(products)} total):
{json.dumps(products[:20], indent=2, ensure_ascii=False)}

Use ADAPTIVE FILTERING - return best available products even if they don't perfectly match criteria.

Output:
{{
  "products": [
    {{
      "id": "prod_<timestamp>_<index>",
      "name": "full product name",
      "brand": "brand",
      "model_number": "model if found",
      "category": "{category}",
      "key_specs": ["inferred specs based on model/brand knowledge"],
      "price_range": "{country_info['currency']}X,XXX",
      "criteria_match": {{
        "matched": ["which criteria this product meets"],
        "adapted": ["criteria relaxed due to market reality"],
        "unknown": ["criteria that can't be verified"],
        "unmet": ["criteria definitely not met"]
      }},
      "match_score": "high/medium/low",
      "why_recommended": "explanation - if adapted, explain why this is the best available option",
      "market_reality_note": "optional - explain any criteria adaptation (e.g., 'Quietest available in Israel at 42dB')"
    }}
  ],
  "filtering_notes": "explain any adaptive filtering applied (e.g., 'Relaxed noise criteria from <40dB to <43dB as no products under 40dB available in Israel')"
}}

IMPORTANT:
- Include 5 best matching products (or all available if fewer than 5)
- NEVER return empty products if there are products available - adapt criteria instead
- If a product matches a recommended model, prioritize it
- Be honest about what can't be verified from the product name
- Price should use {country_info['currency']} symbol
- Add market_reality_note when criteria were adapted"""

        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=2500,
        )

        result_text = response.choices[0].message.content.strip()

        if result_text.startswith("```"):
            result_text = re.sub(r'^```(?:json)?\n?', '', result_text)
            result_text = re.sub(r'\n?```$', '', result_text)

        result = json.loads(result_text)

        # Ensure products have valid IDs
        timestamp = int(time.time() * 1000)
        for i, product in enumerate(result.get("products", [])):
            if not product.get("id") or not product["id"].startswith("prod_"):
                product["id"] = f"prod_{timestamp}_{i}"
            # Ensure key_specs is a list
            if not isinstance(product.get("key_specs"), list):
                product["key_specs"] = []

        # Add filtering notes to search summary if criteria were adapted
        if result.get("filtering_notes"):
            search_summary["filtering_notes"] = result["filtering_notes"]

        result["search_summary"] = search_summary

        await report_progress(
            "✅ Analysis complete",
            f"Scored {len(result.get('products', []))} products"
        )

        return json.dumps(result, indent=2, ensure_ascii=False)

    except Exception as e:
        logger.error("Product analysis failed", error=str(e))
        await record_error(f"Analysis failed: {str(e)[:100]}")

        # Fallback: return products with basic formatting
        timestamp = int(time.time() * 1000)
        fallback_products = []

        for i, p in enumerate(products[:5]):
            fallback_products.append({
                "id": f"prod_{timestamp}_{i}",
                "name": p.get("name", "Unknown"),
                "brand": p.get("brand"),
                "model_number": p.get("model_number"),
                "category": category,
                "key_specs": [],
                "price_range": f"{country_info['currency']}{p.get('price', 0):,.0f}",
                "why_recommended": "Found matching your search",
                "match_score": "unknown",
            })

        return json.dumps({
            "products": fallback_products,
            "search_summary": search_summary,
        }, indent=2, ensure_ascii=False)


_analyze_and_format_results_cached = cached(
    cache_type="agent", key_prefix="analyze_format"
)(_analyze_and_format_results_impl)
analyze_and_format_results = function_tool(
    _analyze_and_format_results_cached, name_override="analyze_and_format_results"
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
        "Amcor", "Tadiran", "Tornado", "Crystal", "General Electric", "GE",
    ]
    name_lower = product_name.lower()
    for brand in known_brands:
        if brand.lower() in name_lower:
            return brand
    return None


def extract_model_number(product_name: str) -> Optional[str]:
    """Extract model number from product name."""
    patterns = [
        r'\b([A-Z]{2,3}\d{2,}[A-Z0-9]*)\b',
        r'\b([A-Z]{1,2}-?\d{3,}[A-Z0-9]*)\b',
        r'\b(\d{2,}[A-Z]{2,}[0-9]*)\b',
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
    instructions="""You are a product discovery specialist that performs deep research to help users find the right products.

## EXTRACTING COUNTRY FROM PROMPT

The user's prompt will contain "User country: XX" where XX is the country code (IL, US, UK, DE, FR, etc.).
ALWAYS extract this country code and pass it to all tool calls.

Example prompt: "Find products matching: silent refrigerator for family of 4\nUser country: IL"
- Extract country = "IL" (Israel)
- Pass country="IL" to all tools

If no country is specified, default to "IL".

## WORKFLOW (Follow these steps in order):

### Step 1: RESEARCH AND DISCOVER
Use `research_and_discover` with the user's requirement and country.
This tool:
- Searches in the user's language for buying guides and recommendations
- Finds specific product models recommended by experts
- Extracts research-backed criteria (not arbitrary numbers)
- Returns both criteria AND specific model recommendations
- Uses the country's measurement system (metric for IL/EU, imperial for US)

### Step 2: SMART SEARCH
Use `search_products_smart` with the research JSON and country.
This tool:
- First searches for specific recommended models (highest priority)
- Then searches using local language terms
- Finally searches by category if needed
- Returns products AND details of what was searched

### Step 3: ANALYZE AND FORMAT
Use `analyze_and_format_results` with research JSON and products JSON.
This tool:
- Scores products against criteria
- ALWAYS provides feedback about what was searched
- Returns structured JSON for the frontend
- If no products found, explains why and gives suggestions

## OUTPUT FORMAT

Your final response must be the JSON from step 3. It includes:
- "products": Array of matched products (may be empty)
- "search_summary": Details of criteria used and searches performed
- If no products: "no_results_message", "suggestions", "criteria_feedback"

```json
{
  "products": [...],
  "search_summary": {
    "original_requirement": "what user asked for",
    "criteria_used": [...],
    "search_attempts": [...]
  }
}
```

## IMPORTANT RULES

1. ALWAYS extract the country from the prompt first
2. ALWAYS complete all 3 steps
3. ALWAYS return valid JSON (no markdown, no explanations outside JSON)
4. NEVER guess criteria - base them on research
5. Use correct currency and units for user's country (IL uses ₪, liters, cm)
6. If no products found, still return the search_summary so user knows what was tried
7. Prioritize finding specific recommended models over generic searches
""",
    tools=[research_and_discover, search_products_smart, analyze_and_format_results],
)
