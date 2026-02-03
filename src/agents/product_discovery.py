"""Product discovery agent for AI-powered product recommendations.

This agent helps users discover products based on natural language requirements
by performing deep research in the user's language, finding real product
recommendations, and validating they meet the criteria.

Approach:
1. Detect product category and load/discover criteria from persistent store
2. Research criteria from multiple sources in user's language
3. Find specific product recommendations from reviews, social media, articles
4. Search for those specific products in local stores
5. Validate and score products against criteria
6. Always provide feedback about what was searched and why

The criteria store learns over time - when a new product category is encountered,
the agent discovers relevant criteria and saves them for future use.
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
from src.db.criteria_store import get_criteria_store
from src.agents.product_matching import (
    parse_multi_product_query,
    find_matched_sets,
    extract_product_attributes,
    normalize_product_type,
)


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


def get_openai_client() -> AsyncOpenAI:
    """Get OpenAI client with API key from environment."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set")
    return AsyncOpenAI(api_key=api_key)


async def detect_category_with_llm(requirement: str) -> str:
    """Use LLM to detect the product category from a user requirement.

    Returns a normalized category name (e.g., "refrigerator", "car", "laptop").
    """
    client = get_openai_client()

    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": """You are a product category classifier.
Given a user's product requirement, identify the main product category.
Return ONLY the category name in lowercase English, nothing else.
Examples:
- "quiet fridge for family" -> refrigerator
- "מזגן שקט לחדר שינה" -> air_conditioner
- "looking for a Tesla Model 3" -> car
- "best laptop for programming" -> laptop
- "תנור בילט אין" -> oven
Use underscores for multi-word categories (e.g., washing_machine, air_conditioner)."""},
            {"role": "user", "content": requirement}
        ],
        temperature=0,
        max_tokens=50,
    )

    category = response.choices[0].message.content.strip().lower()
    # Normalize: remove quotes, extra spaces
    category = category.strip('"\'').replace(" ", "_")
    return category


async def discover_category_criteria(category: str) -> list[dict]:
    """Use LLM to discover important criteria for a product category.

    This is called when we encounter a new category not in our store.
    The discovered criteria are saved for future use.
    """
    client = get_openai_client()

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": """You are a product expert.
Given a product category, list the 6-10 most important criteria that buyers should consider.
For each criterion, provide:
- name: short English name (snake_case)
- description: what this criterion measures/means
- unit: measurement unit if applicable (e.g., "liters", "dB", "kg", "count")
- options: array of common options if it's a choice (e.g., ["yes", "no"], ["A+++", "A++", "A+"])

Focus on criteria that:
1. Significantly impact user satisfaction
2. Vary meaningfully between products
3. Can be compared objectively

Return valid JSON array only, no markdown."""},
            {"role": "user", "content": f"What are the most important criteria for buying a {category}?"}
        ],
        temperature=0.3,
        max_tokens=1500,
    )

    result_text = response.choices[0].message.content.strip()

    # Clean up response
    if result_text.startswith("```"):
        result_text = re.sub(r'^```(?:json)?\n?', '', result_text)
        result_text = re.sub(r'\n?```$', '', result_text)

    try:
        criteria = json.loads(result_text)
        return criteria
    except json.JSONDecodeError:
        # Fallback: return empty list, let research phase handle it
        return []


async def get_or_discover_criteria(category: str) -> list[dict]:
    """Get criteria from store, or discover and save if not found.

    This is the main entry point for getting category criteria.
    """
    import structlog
    logger = structlog.get_logger()

    store = get_criteria_store()

    # Try to get from store
    criteria = await store.get_criteria(category)

    if criteria:
        logger.info("Loaded criteria from store", category=category, count=len(criteria))
        return criteria

    # Not found - discover new criteria
    await report_progress(
        "🔬 Learning new category",
        f"Discovering criteria for '{category}' (will be saved for future use)"
    )

    criteria = await discover_category_criteria(category)

    if criteria:
        # Save to store for future use
        await store.save_criteria(category, criteria, source="discovered")
        logger.info("Discovered and saved criteria", category=category, count=len(criteria))
    else:
        logger.warning("Could not discover criteria", category=category)

    return criteria


async def translate_query_for_search(query: str, target_language: str) -> str:
    """Translate a query to the target language using LLM.

    This replaces hardcoded translation dictionaries with dynamic translation.
    """
    if target_language.lower() == "english":
        return query

    client = get_openai_client()

    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": f"""Translate the following product search query to {target_language}.
Keep it natural for a product search - use common local terms.
Return ONLY the translated text, nothing else."""},
            {"role": "user", "content": query}
        ],
        temperature=0,
        max_tokens=200,
    )

    return response.choices[0].message.content.strip()


# ============================================================================
# Tool 1: Deep Research - Criteria and Product Discovery
# ============================================================================

async def _research_and_discover_impl(
    requirement: str,
    country: str = "IL",
) -> str:
    """Perform deep research to understand product criteria and find recommendations.

    This tool:
    1. Detects the product category using LLM
    2. Loads criteria from store, or discovers and saves them if new category
    3. Searches in the user's language for buying guides and expert recommendations
    4. Looks for specific product recommendations from reviews, social media, news
    5. Extracts realistic, research-backed criteria + category-specific attributes
    6. Returns both criteria AND specific product model recommendations (5+ different models)

    Args:
        requirement: User's natural language requirement
        country: User's country code for localized search

    Returns:
        JSON with researched criteria and product recommendations
    """
    import structlog
    import httpx

    logger = structlog.get_logger()
    country_info = get_country_info(country)
    language = country_info["language"]
    lang_code = country_info["code"]
    currency = country_info["currency"]

    await report_progress(
        "🔍 Researching",
        f"Searching for expert recommendations in {language}..."
    )

    # Detect product category using LLM (works for any product, any language)
    category_key = await detect_category_with_llm(requirement)

    await report_progress(
        "📋 Category detected",
        f"'{category_key}' - Loading or discovering criteria..."
    )

    # Get criteria from store, or discover and save if new category
    category_criteria = await get_or_discover_criteria(category_key)

    if category_criteria:
        await report_progress(
            "✅ Criteria loaded",
            f"{len(category_criteria)} criteria for {category_key}: {', '.join([c.get('name', '') for c in category_criteria[:5]])}"
        )

    # Collect research from web searches
    research_data = {
        "buying_guides": [],
        "product_recommendations": [],
        "expert_opinions": [],
        "social_mentions": [],
    }

    # Translate query to native language for better search results
    native_query = await translate_query_for_search(requirement, language)

    GOOGLE_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": f"{lang_code}-{country},{lang_code};q=0.9,en-US;q=0.8,en;q=0.7",
    }

    # Generate search queries dynamically
    search_queries = await _generate_research_queries_dynamic(
        requirement, native_query, category_key, language, lang_code
    )

    for query_info in search_queries[:4]:  # Limit to 4 queries
        try:
            await report_progress(
                "🔍 Searching",
                f"{query_info['purpose']}: {query_info['query'][:50]}..."
            )

            params = {
                "q": query_info["query"],
                "gl": country.lower(),
                "hl": lang_code,
                "num": 10,
            }

            async with httpx.AsyncClient(timeout=15.0, headers=GOOGLE_HEADERS) as client:
                response = await client.get("https://www.google.com/search", params=params)
                if response.status_code == 200:
                    html = response.text

                    # Parse search results from Google HTML
                    # Extract titles, snippets, and URLs from search result divs
                    results = _parse_google_search_results(html)

                    for result in results[:5]:
                        title = result.get("title", "")
                        snippet = result.get("snippet", "")
                        link = result.get("url", "")

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

        # Build category criteria section for prompt
        category_criteria_text = ""
        if category_criteria:
            criteria_list = []
            for c in category_criteria:
                if c.get("options"):
                    criteria_list.append(f"- {c['name']}: {c['description']}. Options: {', '.join(c['options'])}")
                else:
                    criteria_list.append(f"- {c['name']}: {c['description']}. Unit: {c.get('unit', 'N/A')}")
            category_criteria_text = f"""
IMPORTANT - CATEGORY-SPECIFIC CRITERIA FOR {category_key.upper()}:
You MUST evaluate and report on ALL of these criteria, not just user-specified ones:
{chr(10).join(criteria_list)}

For each criterion:
1. Determine if the user specified a preference
2. If not specified, research what values are recommended for the user's use case
3. Be explicit about which criteria come from user vs. domain knowledge
"""

        system_prompt = f"""You are a product research expert helping users in {country} find the right products.
Your task is to analyze research data and extract:
1. MARKET-REALISTIC criteria based on what's actually available in {country}
2. At least 5 DIFFERENT product models that experts recommend (NOT the same model)
3. Price expectations in local currency ({currency})

{category_criteria_text}

CRITICAL - FINDING DIFFERENT MODELS:
- Find AT LEAST 5 DIFFERENT product models (different brands or model numbers)
- Do NOT return the same model from different sources
- Each recommended model should be UNIQUE
- If you find "Samsung Model X" mentioned 3 times, list it ONCE and find 4 other models
- Prioritize finding variety: different brands, different price points, different feature sets

CRITICAL - TRANSPARENT CRITERIA GATHERING:
- EXPLICITLY list which criteria came from the user's request
- EXPLICITLY list which criteria you added from domain knowledge
- For each criterion, explain WHY it matters for this product category
- If a criterion is important but the user didn't mention it, ADD it and explain why

CRITICAL - MARKET REALITY:
- Research what products are ACTUALLY AVAILABLE in {country}, not ideal specs
- For noise levels: Find the TYPICAL range in the local market
- Set "ideal_value" as the user's wish and "market_value" as what's realistically available
- Include "market_context" explaining the local reality
- Include specific model numbers when mentioned in research
- Prices must be in {currency} ({country_info['currency_name']})

UNITS - Use {country}'s measurement system:
- Volume: {country_info['volume_unit']} (NOT {('cubic feet' if country_info['volume_unit'] == 'liters' else 'liters')})
- Dimensions: {country_info['dimension_unit']} (NOT {('inches' if country_info['dimension_unit'] == 'cm' else 'cm')})

Respond with valid JSON only."""

        user_prompt = f"""Analyze this research for: "{requirement}"
User country: {country} (currency: {currency})

RESEARCH DATA:
{research_summary}

Based on this research, provide:
{{
  "category": "product category",
  "criteria_transparency": {{
    "user_specified": ["list of criteria the user explicitly asked for"],
    "domain_added": ["list of criteria you added from domain knowledge - explain why each matters"],
    "total_criteria_count": number
  }},
  "criteria": [
    {{
      "attribute": "attribute name",
      "source": "user" or "domain_knowledge",
      "why_important": "explanation of why this criterion matters for this product",
      "ideal_value": "what user ideally wants",
      "market_value": "what's realistically available in {country}",
      "market_context": "explanation of local market reality",
      "is_flexible": true/false,
      "confidence": "high/medium/low"
    }}
  ],
  "recommended_models": [
    {{
      "model": "specific model name/number",
      "brand": "brand name",
      "source": "where recommended (article title, expert, etc.)",
      "why_recommended": "why this model fits the requirement",
      "key_differentiator": "what makes this model unique compared to others"
    }}
  ],
  "search_terms": {{
    "native_language": ["search terms in {language} - ALWAYS include native language terms"],
    "model_searches": ["specific model searches - should have 5+ different models"],
    "category_searches": ["category + feature searches in {language}"]
  }},
  "price_range": {{
    "min": number,
    "max": number,
    "currency": "{currency}",
    "source": "where this estimate comes from"
  }},
  "research_quality": "good/moderate/limited",
  "market_notes": "important notes about the {country} market for this product category",
  "model_diversity_check": "confirmation that you found 5+ DIFFERENT models, not duplicates"
}}

REMEMBER:
- Find AT LEAST 5 different product models
- Include ALL domain-specific criteria even if user didn't ask
- Be transparent about which criteria came from user vs. domain knowledge"""

        response = await client.chat.completions.create(
            model="gpt-4o",  # Using GPT-4o for better research analysis
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=3000,
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
        result["category_template_used"] = category_key

        criteria_count = len(result.get("criteria", []))
        models_count = len(result.get("recommended_models", []))

        # Report on criteria transparency
        transparency = result.get("criteria_transparency", {})
        user_criteria = len(transparency.get("user_specified", []))
        domain_criteria = len(transparency.get("domain_added", []))

        await report_progress(
            "✅ Research complete",
            f"Found {models_count} different models, {criteria_count} criteria ({user_criteria} from user, {domain_criteria} from domain knowledge)"
        )

        logger.info("Research complete",
                   requirement=requirement,
                   criteria_count=criteria_count,
                   models_count=models_count,
                   user_criteria=user_criteria,
                   domain_criteria=domain_criteria,
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


def _parse_google_search_results(html: str) -> list[dict]:
    """Parse Google search results from HTML.

    Extracts titles, snippets, and URLs from Google search result page.
    """
    import re
    from bs4 import BeautifulSoup

    results = []
    soup = BeautifulSoup(html, "lxml")

    # Find search result divs - Google uses various class names
    # Try multiple selectors to find organic results
    selectors = [
        "div.g",  # Classic Google result div
        "div[data-hveid]",  # Alternative data attribute
        "div.tF2Cxc",  # Another common class
    ]

    result_divs = []
    for selector in selectors:
        result_divs = soup.select(selector)
        if result_divs:
            break

    for div in result_divs[:10]:
        try:
            # Extract URL - look for the main link
            link_elem = div.select_one("a[href^='http']")
            if not link_elem:
                link_elem = div.select_one("a[href^='/url']")

            url = ""
            if link_elem:
                href = link_elem.get("href", "")
                if href.startswith("/url?q="):
                    # Extract actual URL from Google redirect
                    url = href.split("/url?q=")[1].split("&")[0]
                else:
                    url = href

            # Skip Google's own pages
            if "google.com" in url or not url:
                continue

            # Extract title - usually in h3
            title_elem = div.select_one("h3")
            title = title_elem.get_text(strip=True) if title_elem else ""

            # Extract snippet - look for common snippet containers
            snippet = ""
            snippet_selectors = [
                "div.VwiC3b",
                "span.aCOpRe",
                "div[data-content-feature]",
                "div.IsZvec",
            ]
            for snippet_sel in snippet_selectors:
                snippet_elem = div.select_one(snippet_sel)
                if snippet_elem:
                    snippet = snippet_elem.get_text(strip=True)
                    break

            if not snippet:
                # Fallback: get text from div excluding title
                all_text = div.get_text(strip=True)
                if title and title in all_text:
                    snippet = all_text.replace(title, "").strip()[:300]

            if title and url:
                results.append({
                    "title": title,
                    "snippet": snippet,
                    "url": url,
                })

        except Exception:
            continue

    return results


async def _generate_research_queries_dynamic(
    requirement: str,
    native_query: str,
    category: str,
    language: str,
    lang_code: str
) -> list:
    """Generate research queries dynamically using LLM.

    This replaces hardcoded query templates with dynamic generation
    that works for any product category and language.
    """
    client = get_openai_client()

    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": f"""Generate 4-5 search queries for product research.
Target language: {language}
Product category: {category}

Generate queries that will find:
1. Buying guides and comparison articles
2. Expert recommendations and reviews
3. Community discussions (forums, Reddit, etc.)
4. Specific product model recommendations

Each query should be in {language} (except one English query for international research).
Keep queries natural and similar to what a local user would search.

Return JSON array:
[{{"query": "search query text", "purpose": "brief description", "category": "buying_guides|product_recommendations|expert_opinions|social_mentions"}}]

Return ONLY valid JSON, no markdown."""},
            {"role": "user", "content": f"User requirement: {requirement}\nTranslated query: {native_query}"}
        ],
        temperature=0.3,
        max_tokens=800,
    )

    result_text = response.choices[0].message.content.strip()

    # Clean up response
    if result_text.startswith("```"):
        result_text = re.sub(r'^```(?:json)?\n?', '', result_text)
        result_text = re.sub(r'\n?```$', '', result_text)

    try:
        queries = json.loads(result_text)
        return queries
    except json.JSONDecodeError:
        # Fallback: return basic queries
        return [
            {
                "query": f"{native_query} recommended 2024",
                "purpose": "Finding recommended models",
                "category": "product_recommendations"
            },
            {
                "query": f"{native_query} reviews buying guide",
                "purpose": "Buying guide",
                "category": "buying_guides"
            },
        ]


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

    for model in model_searches[:10]:  # Search up to 10 models
        await report_progress(
            "🔍 Model search",
            f"Looking for: {model}"
        )

        attempt = {"query": model, "strategy": "specific_model", "results": 0, "scrapers": []}

        for scraper in scrapers:
            try:
                results = await scraper.search(model, max_results=8)
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

    for term in native_terms[:5]:  # Search up to 5 native language terms
        await report_progress(
            "🔍 Local search",
            f"Searching: {term}"
        )

        attempt = {"query": term, "strategy": "local_language", "results": 0, "scrapers": []}

        for scraper in scrapers:
            try:
                results = await scraper.search(term, max_results=max(8, max_results // 2))
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

    for term in category_terms[:4]:  # Search up to 4 category terms
        await report_progress(
            "🔍 Category search",
            f"Searching: {term}"
        )

        attempt = {"query": term, "strategy": "category", "results": 0, "scrapers": []}

        for scraper in scrapers:
            try:
                results = await scraper.search(term, max_results=max(8, max_results // 2))
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
    seen_urls = set()  # Deduplicate by URL, not name

    for result in all_results[:max_results]:
        # Skip if we've already seen this exact URL
        url_key = (result.url or "").lower()[:100]
        if url_key and url_key in seen_urls:
            continue
        if url_key:
            seen_urls.add(url_key)

        name = result.seller.name
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

    # Deduplicate products by model number (keep the one with lowest price)
    seen_models: dict[str, dict] = {}
    deduplicated_products = []
    for product in products:
        model = product.get("model_number") or product.get("model") or ""
        name = product.get("name", "")

        # Create a key from model or product name
        key = model.lower().strip() if model else name.lower().strip()
        if not key:
            deduplicated_products.append(product)
            continue

        if key in seen_models:
            # Keep the one with lower price
            existing_price = seen_models[key].get("price") or float("inf")
            new_price = product.get("price") or float("inf")
            if new_price < existing_price:
                # Replace with cheaper option
                deduplicated_products = [p for p in deduplicated_products if p != seen_models[key]]
                deduplicated_products.append(product)
                seen_models[key] = product
        else:
            seen_models[key] = product
            deduplicated_products.append(product)

    if len(products) != len(deduplicated_products):
        logger.info(
            "Deduplicated products",
            original_count=len(products),
            deduplicated_count=len(deduplicated_products)
        )
        products = deduplicated_products

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
        "criteria_transparency": research.get("criteria_transparency", {}),
        "criteria_used": criteria,
        "recommended_models_searched": [m.get("model") for m in recommended_models],
        "search_attempts": search_results.get("search_attempts", []),
        "total_products_found": len(products),
        "unique_models_found": len(seen_models),
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

        # Get criteria transparency info
        criteria_transparency = research.get("criteria_transparency", {})

        system_prompt = f"""You are a product analyst using ADAPTIVE FILTERING.

Your job is to:
1. FIRST: Validate criteria for logical impossibilities (e.g., "dishwasher without electricity" - all dishwashers require electricity)
2. Score ALL products against VALID criteria
3. If strict criteria eliminate all products, RELAX criteria based on market reality
4. Always return the BEST AVAILABLE products, even if they don't perfectly match

CRITICAL - RETURN DIFFERENT MODELS:
- You MUST return 5 DIFFERENT product models (different brands or model numbers)
- Do NOT return the same model multiple times even if it's available at different stores
- Each product in your output must be a UNIQUE model
- Prioritize variety: different brands, different price points, different feature sets
- If products list has duplicates, SKIP the duplicates and find unique models

CRITERIA VALIDATION:
- If a criterion is physically/logically impossible, IGNORE IT and note why in filtering_notes
- Examples of impossible criteria: "dishwasher without electricity", "silent jackhammer", "waterproof paper"
- Do NOT claim products meet impossible criteria - be honest that the criterion was ignored

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

CRITERIA TRANSPARENCY:
- User specified: {json.dumps(criteria_transparency.get('user_specified', []), ensure_ascii=False)}
- Domain knowledge added: {json.dumps(criteria_transparency.get('domain_added', []), ensure_ascii=False)}

FULL CRITERIA (may include market context):
{json.dumps(criteria, indent=2, ensure_ascii=False)}

MARKET NOTES:
{market_notes}

RECOMMENDED MODELS FROM RESEARCH (use for prioritization only):
{json.dumps(recommended_models, indent=2, ensure_ascii=False)}

PRODUCTS FOUND IN LOCAL STORES ({len(products)} total):
{json.dumps(products[:30], indent=2, ensure_ascii=False)}

CRITICAL - ONLY USE PRODUCTS FROM "PRODUCTS FOUND" LIST:
- You may ONLY return products that appear in the "PRODUCTS FOUND IN LOCAL STORES" list above
- Do NOT include any product that wasn't found in local stores, even if it's in recommended models
- If a recommended model wasn't found in stores, it means it's NOT AVAILABLE in {country} - DO NOT include it
- The recommended models list is ONLY for prioritization - a product must be in "PRODUCTS FOUND" to be returned

Use ADAPTIVE FILTERING - return best available products even if they don't perfectly match criteria.

IMPORTANT: Return exactly 5 DIFFERENT models (unique brand+model combinations).
Do NOT return the same model from different stores.

Output:
{{
  "products": [
    {{
      "id": "prod_<timestamp>_<index>",
      "name": "full product name",
      "brand": "brand",
      "model_number": "model if found - MUST BE UNIQUE",
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
- Return EXACTLY 5 DIFFERENT models (or all available if fewer than 5 unique models exist)
- Each model MUST have a unique model_number - no duplicates
- NEVER return empty products if there are products available - adapt criteria instead
- If a product matches a recommended model, prioritize it
- Be honest about what can't be verified from the product name
- Price should use {country_info['currency']} symbol
- Add market_reality_note when criteria were adapted
- Include model_diversity_note confirming the 5 models are unique"""

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

        # Build set of valid products from search results
        valid_models = set()
        valid_names = set()
        products_with_urls = {}  # model/name -> url mapping
        for p in products:
            model = (p.get("model_number") or "").strip().lower()
            name = (p.get("name") or "").strip().lower()
            if model:
                valid_models.add(model)
                products_with_urls[model] = p.get("url")
            if name:
                valid_names.add(name)
                if name not in products_with_urls:
                    products_with_urls[name] = p.get("url")

        # Filter out products not found in local stores
        filtered_products = []
        for product in result.get("products", []):
            model = (product.get("model_number") or "").strip().lower()
            name = (product.get("name") or "").strip().lower()

            # Check if product was found in local stores
            is_valid = False
            matched_key = None

            # Check by model number
            if model:
                for valid_model in valid_models:
                    if model in valid_model or valid_model in model:
                        is_valid = True
                        matched_key = valid_model
                        break

            # Check by name if model didn't match
            if not is_valid and name:
                for valid_name in valid_names:
                    # Fuzzy match - check if significant overlap
                    if len(name) > 10 and (name in valid_name or valid_name in name):
                        is_valid = True
                        matched_key = valid_name
                        break

            if is_valid:
                # Add URL from original search if not present
                if not product.get("url") and matched_key:
                    product["url"] = products_with_urls.get(matched_key)
                filtered_products.append(product)
            else:
                logger.warning(
                    "Filtered out product not found in local stores",
                    model=model,
                    name=name[:50] if name else None
                )

        if len(filtered_products) < len(result.get("products", [])):
            logger.info(
                "Filtered products not available in local stores",
                original=len(result.get("products", [])),
                filtered=len(filtered_products)
            )

        result["products"] = filtered_products

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

        for i, p in enumerate(products[:10]):
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
# Tool 4: Match Product Sets (for Multi-Product Queries)
# ============================================================================

async def _match_product_sets_impl(
    products_by_type_json: str,
    relationship: str = "matching",
) -> str:
    """Score cross-product matches and highlight best pairs for multi-product queries.

    This tool takes products grouped by type (e.g., coffee_table, side_table) and:
    1. Extracts visual attributes (color, style, material, brand) from each product
    2. Scores all possible pairs across different product types
    3. Returns matched sets with explanations of why they match

    Args:
        products_by_type_json: JSON dict mapping product type to list of products
            Example: {"coffee_table": [...], "side_table": [...]}
        relationship: "matching" (same color/style) or "complementary" (goes well together)

    Returns:
        JSON with matched_sets and products_by_type with match indicators
    """
    import structlog
    logger = structlog.get_logger()

    await report_progress(
        "🔗 Matching",
        "Finding matching product sets..."
    )

    try:
        products_by_type = json.loads(products_by_type_json)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse products_by_type JSON", error=str(e))
        return json.dumps({
            "error": f"Invalid products JSON: {str(e)}",
            "matched_sets": [],
            "products_by_type": {},
        })

    if not products_by_type or len(products_by_type) < 2:
        return json.dumps({
            "matched_sets": [],
            "products_by_type": products_by_type,
            "note": "Need at least 2 product types to find matches",
        })

    # Count total products
    total_products = sum(len(products) for products in products_by_type.values())
    product_types = list(products_by_type.keys())

    await report_progress(
        "🔗 Matching",
        f"Analyzing {total_products} products across {len(product_types)} types..."
    )

    # Use the matching module to find matched sets
    min_score = 0.2 if relationship == "complementary" else 0.3
    matched_sets = find_matched_sets(
        products_by_type,
        min_score=min_score,
        max_sets=10,
    )

    # Build a set of product IDs that have matches
    products_with_matches = set()
    for match_set in matched_sets:
        for product in match_set.get("products", []):
            prod_id = product.get("id")
            if prod_id:
                products_with_matches.add(prod_id)

    # Add match indicators to products
    for product_type, products in products_by_type.items():
        for product in products:
            prod_id = product.get("id")
            product["has_matches"] = prod_id in products_with_matches if prod_id else False
            # Add extracted attributes for frontend display
            attrs = extract_product_attributes(product)
            product["matching_attributes"] = {
                k: v for k, v in attrs.items() if v is not None
            }

    matches_found = len(matched_sets)
    products_matched = len(products_with_matches)

    await report_progress(
        "✅ Matching complete",
        f"Found {matches_found} matched sets ({products_matched} products)"
    )

    logger.info(
        "Product matching complete",
        product_types=product_types,
        total_products=total_products,
        matched_sets=matches_found,
        products_with_matches=products_matched,
        relationship=relationship,
    )

    return json.dumps({
        "matched_sets": matched_sets,
        "products_by_type": products_by_type,
        "summary": {
            "product_types": product_types,
            "total_products": total_products,
            "matched_sets_count": matches_found,
            "products_with_matches": products_matched,
            "relationship": relationship,
        },
    }, indent=2, ensure_ascii=False)


_match_product_sets_cached = cached(
    cache_type="agent", key_prefix="match_sets"
)(_match_product_sets_impl)
match_product_sets = function_tool(
    _match_product_sets_cached, name_override="match_product_sets"
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
    for brand in known_brands:
        # Use word boundary matching to avoid partial matches (e.g., "GE" in "Generic")
        pattern = r'\b' + re.escape(brand) + r'\b'
        if re.search(pattern, product_name, re.IGNORECASE):
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

## HANDLING CONVERSATION REFINEMENTS

If the prompt contains "Previous conversation:" followed by "User's refinement request:", this is a REFINEMENT of an earlier search.

**CRITICAL: DETECT PRODUCT CATEGORY CHANGES**

Before processing a refinement, check if the user is asking for a DIFFERENT product category than the original search:
- Original: "washing machine" → Refinement: "dishwasher" = DIFFERENT CATEGORY → Treat as NEW SEARCH
- Original: "washing machine" → Refinement: "cheaper" = SAME CATEGORY → Apply refinement
- Original: "refrigerator" → Refinement: "air conditioner" = DIFFERENT CATEGORY → Treat as NEW SEARCH
- Original: "refrigerator" → Refinement: "larger capacity" = SAME CATEGORY → Apply refinement

If the refinement mentions a DIFFERENT product category:
1. IGNORE the previous search context entirely
2. Treat this as a completely NEW search for the new product category
3. Run the full workflow (research → search → analyze) for the NEW product
4. Do NOT try to blend criteria from the old and new products

For refinements within the SAME product category:
1. Understand what was searched previously from the conversation history
2. Apply the user's refinement criteria (e.g., "cheaper", "quieter", "different brand", "larger capacity")
3. You may need to:
   - Re-run research with additional constraints
   - Filter the previous results based on new criteria
   - Search for alternative/new products if the refinement is significant

Common refinement patterns (SAME category):
- "cheaper/more affordable" → focus on lower price range
- "quieter/silent" → add noise level as priority criteria
- "prefer [brand]" → filter to specific brand
- "larger/bigger" → increase capacity requirements
- "show more options" → expand the search
- "without [feature]" → exclude products with that feature

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
2. ALWAYS complete all steps (3 for single-product, 4 for multi-product)
3. ALWAYS return valid JSON (no markdown, no explanations outside JSON)
4. NEVER guess criteria - base them on research
5. Use correct currency and units for user's country (IL uses ₪, liters, cm)
6. If no products found, still return the search_summary so user knows what was tried
7. Prioritize finding specific recommended models over generic searches
8. For refinements, incorporate the user's feedback into the search criteria

## MULTI-PRODUCT QUERIES

If the user asks for multiple related products (e.g., "coffee table and side table", "sofa with matching armchair"):

### Detection Patterns
Look for these patterns in the user's query:
- "X and Y" → two products (e.g., "coffee table and side table")
- "X and matching Y" → two products that should match in style/color
- "X with Y" → two complementary products
- "X that matches Y" → products should coordinate
- "matching X and Y" → explicit matching request
- Keywords: "matching", "coordinate", "complement", "go with", "same style", "same color"

### Multi-Product Workflow (4 steps)

**Step 1: DETECT AND PARSE**
Identify if this is a multi-product query. Extract:
- Individual products: ["coffee table", "side table"]
- Relationship: "matching" or "complementary"

**Step 2: SEARCH EACH PRODUCT TYPE**
For EACH product type, run the standard workflow:
1. `research_and_discover` for product type 1
2. `search_products_smart` for product type 1 (aim for 10 results)
3. Repeat for product type 2, 3, etc.

Store results by product type:
```json
{
  "coffee_table": [products...],
  "side_table": [products...]
}
```

**Step 3: MATCH PRODUCT SETS**
Use `match_product_sets` with the products_by_type JSON.
This tool:
- Extracts visual attributes (color, style, material, brand) from each product
- Scores all pairs across different product types
- Returns matched sets with match reasons

**Step 4: FORMAT OUTPUT**
Combine results into multi-product output format:
```json
{
  "is_multi_product": true,
  "products": [...],  // Flat list for backwards compatibility
  "products_by_type": {
    "coffee_table": [...],
    "side_table": [...]
  },
  "matched_sets": [
    {
      "set_id": "set_1",
      "products": [...],
      "match_score": 0.85,
      "match_reasons": ["Same walnut finish", "Both mid-century style"],
      "combined_price": 850
    }
  ],
  "search_summary": {
    "product_types_searched": ["coffee_table", "side_table"],
    "relationship": "matching",
    ...
  }
}
```

### Multi-Product Rules
- Search for 10 products per type (not 3 total)
- Always include both products_by_type AND matched_sets
- Sort matched_sets by match_score (highest first)
- Products in matched_sets should have match_reasons explaining why they match
- For "matching" queries, prioritize color and style matches
- For "complementary" queries, also consider material and brand matches
""",
    tools=[research_and_discover, search_products_smart, analyze_and_format_results, match_product_sets],
)
