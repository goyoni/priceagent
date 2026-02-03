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

# Category-specific criteria templates - domain knowledge for each product type
# These ensure the agent considers all important attributes, not just user-specified ones
CATEGORY_CRITERIA_TEMPLATES = {
    "oven": {
        "hebrew": "תנור",
        "criteria": [
            {"name": "volume", "hebrew": "נפח", "unit": "liters", "description": "Internal oven capacity"},
            {"name": "programs", "hebrew": "תכניות", "unit": "count", "description": "Number of cooking programs/modes"},
            {"name": "cleaning_method", "hebrew": "שיטת ניקוי", "options": ["pyrolytic", "catalytic", "steam", "manual"], "description": "Self-cleaning method"},
            {"name": "max_temperature", "hebrew": "טמפרטורה מקסימלית", "unit": "°C", "description": "Maximum temperature"},
            {"name": "energy_rating", "hebrew": "דירוג אנרגיה", "options": ["A+++", "A++", "A+", "A", "B"], "description": "Energy efficiency class"},
            {"name": "type", "hebrew": "סוג", "options": ["built-in", "freestanding", "range"], "description": "Installation type"},
            {"name": "width", "hebrew": "רוחב", "unit": "cm", "description": "Standard widths: 60cm, 90cm"},
            {"name": "convection", "hebrew": "קונבקציה", "options": ["yes", "no"], "description": "Hot air circulation"},
            {"name": "grill", "hebrew": "גריל", "options": ["yes", "no"], "description": "Built-in grill function"},
        ],
    },
    "stove": {
        "hebrew": "תנור",
        "criteria": [
            {"name": "volume", "hebrew": "נפח", "unit": "liters", "description": "Internal oven capacity"},
            {"name": "programs", "hebrew": "תכניות", "unit": "count", "description": "Number of cooking programs/modes"},
            {"name": "cleaning_method", "hebrew": "שיטת ניקוי", "options": ["pyrolytic", "catalytic", "steam", "manual"], "description": "Self-cleaning method"},
            {"name": "max_temperature", "hebrew": "טמפרטורה מקסימלית", "unit": "°C", "description": "Maximum temperature"},
            {"name": "energy_rating", "hebrew": "דירוג אנרגיה", "options": ["A+++", "A++", "A+", "A", "B"], "description": "Energy efficiency class"},
            {"name": "type", "hebrew": "סוג", "options": ["built-in", "freestanding", "range"], "description": "Installation type"},
            {"name": "width", "hebrew": "רוחב", "unit": "cm", "description": "Standard widths: 60cm, 90cm"},
            {"name": "convection", "hebrew": "קונבקציה", "options": ["yes", "no"], "description": "Hot air circulation"},
            {"name": "grill", "hebrew": "גריל", "options": ["yes", "no"], "description": "Built-in grill function"},
        ],
    },
    "refrigerator": {
        "hebrew": "מקרר",
        "criteria": [
            {"name": "total_volume", "hebrew": "נפח כולל", "unit": "liters", "description": "Total storage capacity"},
            {"name": "freezer_volume", "hebrew": "נפח מקפיא", "unit": "liters", "description": "Freezer capacity"},
            {"name": "noise_level", "hebrew": "רמת רעש", "unit": "dB", "description": "Operating noise in decibels"},
            {"name": "energy_rating", "hebrew": "דירוג אנרגיה", "options": ["A+++", "A++", "A+", "A", "B"], "description": "Energy efficiency class"},
            {"name": "type", "hebrew": "סוג", "options": ["top-freezer", "bottom-freezer", "side-by-side", "french-door"], "description": "Configuration type"},
            {"name": "no_frost", "hebrew": "נו פרוסט", "options": ["yes", "no"], "description": "No-frost technology"},
            {"name": "water_dispenser", "hebrew": "מתקן מים", "options": ["yes", "no"], "description": "Built-in water dispenser"},
            {"name": "ice_maker", "hebrew": "מכונת קרח", "options": ["yes", "no"], "description": "Built-in ice maker"},
            {"name": "width", "hebrew": "רוחב", "unit": "cm", "description": "Standard widths: 60cm, 70cm, 90cm"},
        ],
    },
    "fridge": {
        "hebrew": "מקרר",
        "criteria": [
            {"name": "total_volume", "hebrew": "נפח כולל", "unit": "liters", "description": "Total storage capacity"},
            {"name": "freezer_volume", "hebrew": "נפח מקפיא", "unit": "liters", "description": "Freezer capacity"},
            {"name": "noise_level", "hebrew": "רמת רעש", "unit": "dB", "description": "Operating noise in decibels"},
            {"name": "energy_rating", "hebrew": "דירוג אנרגיה", "options": ["A+++", "A++", "A+", "A", "B"], "description": "Energy efficiency class"},
            {"name": "type", "hebrew": "סוג", "options": ["top-freezer", "bottom-freezer", "side-by-side", "french-door"], "description": "Configuration type"},
            {"name": "no_frost", "hebrew": "נו פרוסט", "options": ["yes", "no"], "description": "No-frost technology"},
            {"name": "water_dispenser", "hebrew": "מתקן מים", "options": ["yes", "no"], "description": "Built-in water dispenser"},
            {"name": "ice_maker", "hebrew": "מכונת קרח", "options": ["yes", "no"], "description": "Built-in ice maker"},
            {"name": "width", "hebrew": "רוחב", "unit": "cm", "description": "Standard widths: 60cm, 70cm, 90cm"},
        ],
    },
    "washing_machine": {
        "hebrew": "מכונת כביסה",
        "criteria": [
            {"name": "capacity", "hebrew": "קיבולת", "unit": "kg", "description": "Load capacity in kg"},
            {"name": "spin_speed", "hebrew": "מהירות סחיטה", "unit": "rpm", "description": "Maximum spin speed"},
            {"name": "noise_level", "hebrew": "רמת רעש", "unit": "dB", "description": "Operating noise"},
            {"name": "energy_rating", "hebrew": "דירוג אנרגיה", "options": ["A+++", "A++", "A+", "A", "B"], "description": "Energy efficiency class"},
            {"name": "programs", "hebrew": "תכניות", "unit": "count", "description": "Number of wash programs"},
            {"name": "steam", "hebrew": "קיטור", "options": ["yes", "no"], "description": "Steam washing function"},
            {"name": "inverter", "hebrew": "אינוורטר", "options": ["yes", "no"], "description": "Inverter motor technology"},
            {"name": "quick_wash", "hebrew": "כביסה מהירה", "options": ["yes", "no"], "description": "Quick wash cycle"},
        ],
    },
    "dishwasher": {
        "hebrew": "מדיח כלים",
        "criteria": [
            {"name": "place_settings", "hebrew": "מערכות כלים", "unit": "sets", "description": "Number of place settings"},
            {"name": "noise_level", "hebrew": "רמת רעש", "unit": "dB", "description": "Operating noise in decibels"},
            {"name": "energy_rating", "hebrew": "דירוג אנרגיה", "options": ["A+++", "A++", "A+", "A", "B"], "description": "Energy efficiency class"},
            {"name": "programs", "hebrew": "תכניות", "unit": "count", "description": "Number of wash programs"},
            {"name": "width", "hebrew": "רוחב", "unit": "cm", "description": "Standard widths: 45cm, 60cm"},
            {"name": "half_load", "hebrew": "חצי מילוי", "options": ["yes", "no"], "description": "Half load option"},
            {"name": "quick_wash", "hebrew": "שטיפה מהירה", "options": ["yes", "no"], "description": "Quick wash cycle"},
            {"name": "third_rack", "hebrew": "סל שלישי", "options": ["yes", "no"], "description": "Third rack for cutlery"},
        ],
    },
    "air_conditioner": {
        "hebrew": "מזגן",
        "criteria": [
            {"name": "cooling_capacity", "hebrew": "הספק קירור", "unit": "BTU", "description": "Cooling capacity in BTU"},
            {"name": "noise_level", "hebrew": "רמת רעש", "unit": "dB", "description": "Indoor unit noise level"},
            {"name": "energy_rating", "hebrew": "דירוג אנרגיה", "options": ["A+++", "A++", "A+", "A", "B"], "description": "Energy efficiency class"},
            {"name": "inverter", "hebrew": "אינוורטר", "options": ["yes", "no"], "description": "Inverter technology"},
            {"name": "wifi", "hebrew": "וייפי", "options": ["yes", "no"], "description": "WiFi connectivity"},
            {"name": "heating", "hebrew": "חימום", "options": ["yes", "no"], "description": "Heating function"},
            {"name": "room_size", "hebrew": "גודל חדר", "unit": "sqm", "description": "Recommended room size"},
        ],
    },
    "tv": {
        "hebrew": "טלוויזיה",
        "criteria": [
            {"name": "screen_size", "hebrew": "גודל מסך", "unit": "inches", "description": "Screen diagonal"},
            {"name": "resolution", "hebrew": "רזולוציה", "options": ["4K", "8K", "Full HD", "HD"], "description": "Display resolution"},
            {"name": "panel_type", "hebrew": "סוג פאנל", "options": ["OLED", "QLED", "LED", "Mini-LED"], "description": "Display technology"},
            {"name": "refresh_rate", "hebrew": "קצב רענון", "unit": "Hz", "description": "Refresh rate"},
            {"name": "smart_tv", "hebrew": "סמארט", "options": ["yes", "no"], "description": "Smart TV features"},
            {"name": "hdmi_ports", "hebrew": "יציאות HDMI", "unit": "count", "description": "Number of HDMI ports"},
            {"name": "hdr", "hebrew": "HDR", "options": ["HDR10", "Dolby Vision", "HDR10+", "none"], "description": "HDR support"},
        ],
    },
}


def detect_product_category(requirement: str) -> tuple[str, dict]:
    """Detect the product category from user requirement and return criteria template.

    Returns:
        Tuple of (category_key, criteria_template) or (None, {}) if not detected
    """
    requirement_lower = requirement.lower()

    category_keywords = {
        "oven": ["oven", "תנור אפייה", "תנור בילט אין"],
        "stove": ["stove", "תנור", "כיריים", "range"],
        "refrigerator": ["refrigerator", "fridge", "מקרר"],
        "washing_machine": ["washing machine", "מכונת כביסה", "washer"],
        "dishwasher": ["dishwasher", "מדיח כלים", "מדיח"],
        "air_conditioner": ["air conditioner", "מזגן", "ac", "a/c"],
        "tv": ["tv", "television", "טלוויזיה"],
    }

    for category, keywords in category_keywords.items():
        for keyword in keywords:
            if keyword in requirement_lower:
                return category, CATEGORY_CRITERIA_TEMPLATES.get(category, {})

    return None, {}

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
    1. Detects the product category and loads domain-specific criteria
    2. Searches in the user's language for buying guides and expert recommendations
    3. Looks for specific product recommendations from reviews, social media, news
    4. Extracts realistic, research-backed criteria + category-specific attributes
    5. Returns both criteria AND specific product model recommendations (5+ different models)

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

    # Detect product category and get criteria template
    category_key, category_template = detect_product_category(requirement)
    category_criteria = category_template.get("criteria", []) if category_template else []

    await report_progress(
        "🔍 Researching",
        f"Searching for expert recommendations in {language}..."
    )

    if category_key:
        await report_progress(
            "📋 Category detected",
            f"{category_key} - Loading {len(category_criteria)} domain criteria (volume, programs, cleaning, etc.)"
        )

    # Collect research from web searches
    research_data = {
        "buying_guides": [],
        "product_recommendations": [],
        "expert_opinions": [],
        "social_mentions": [],
    }

    # Use direct Google scraping for research
    import re
    GOOGLE_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": f"{lang_code}-{country},{lang_code};q=0.9,en-US;q=0.8,en;q=0.7",
    }

    # Search queries in user's language
    search_queries = _generate_research_queries(requirement, language, lang_code)

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
                    criteria_list.append(f"- {c['name']} ({c['hebrew']}): {c['description']}. Options: {', '.join(c['options'])}")
                else:
                    criteria_list.append(f"- {c['name']} ({c['hebrew']}): {c['description']}. Unit: {c.get('unit', 'N/A')}")
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

RECOMMENDED MODELS FROM RESEARCH:
{json.dumps(recommended_models, indent=2, ensure_ascii=False)}

PRODUCTS FOUND ({len(products)} total):
{json.dumps(products[:30], indent=2, ensure_ascii=False)}

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
2. ALWAYS complete all 3 steps
3. ALWAYS return valid JSON (no markdown, no explanations outside JSON)
4. NEVER guess criteria - base them on research
5. Use correct currency and units for user's country (IL uses ₪, liters, cm)
6. If no products found, still return the search_summary so user knows what was tried
7. Prioritize finding specific recommended models over generic searches
8. For refinements, incorporate the user's feedback into the search criteria
""",
    tools=[research_and_discover, search_products_smart, analyze_and_format_results],
)
