"""Product matching module for cross-product attribute extraction and scoring.

This module provides utilities to:
1. Parse multi-product queries (e.g., "coffee table and matching side table")
2. Extract visual attributes (color, style, material) from product names
3. Score how well products match each other for creating sets
"""

import re
from typing import Optional


# ============================================================================
# Color Extraction
# ============================================================================

# Color synonyms grouped by canonical color name
COLORS = {
    "walnut": ["walnut", "dark brown", "espresso", "chocolate", "mahogany"],
    "oak": ["oak", "light wood", "natural wood", "light oak", "white oak"],
    "black": ["black", "noir", "ebony", "charcoal black", "jet black"],
    "white": ["white", "ivory", "cream", "off-white", "snow white"],
    "gray": ["gray", "grey", "charcoal", "slate", "graphite", "silver"],
    "brown": ["brown", "tan", "caramel", "cognac", "chestnut"],
    "natural": ["natural", "raw wood", "unfinished", "bare wood"],
    "beige": ["beige", "sand", "taupe", "khaki", "linen"],
    "blue": ["blue", "navy", "teal", "turquoise", "azure"],
    "green": ["green", "olive", "sage", "forest", "emerald", "mint"],
    # Hebrew colors for IL market
    "אגוז": ["אגוז", "חום כהה"],
    "לבן": ["לבן", "שנהב", "קרם"],
    "שחור": ["שחור", "עץ שחור"],
    "אלון": ["אלון", "עץ טבעי", "אלון לבן"],
}


def extract_color(text: str) -> Optional[str]:
    """Extract color/finish from product text.

    Args:
        text: Product name or description (lowercase)

    Returns:
        Canonical color name or None if not found
    """
    text_lower = text.lower()

    for canonical_color, synonyms in COLORS.items():
        for synonym in synonyms:
            # Use word boundary for longer terms, exact match for Hebrew
            if len(synonym) >= 3:
                if re.search(r'\b' + re.escape(synonym) + r'\b', text_lower):
                    return canonical_color
            else:
                # Short terms or Hebrew - just check presence
                if synonym in text_lower:
                    return canonical_color

    return None


# ============================================================================
# Style Extraction
# ============================================================================

STYLES = {
    "mid-century": ["mid-century", "midcentury", "mid century", "50s", "60s", "eames"],
    "modern": ["modern", "contemporary", "minimalist", "sleek"],
    "rustic": ["rustic", "farmhouse", "country", "cottage", "reclaimed"],
    "industrial": ["industrial", "loft", "urban", "factory", "pipe"],
    "scandinavian": ["scandinavian", "nordic", "hygge", "danish", "swedish"],
    "traditional": ["traditional", "classic", "antique", "vintage", "heritage"],
    "boho": ["boho", "bohemian", "eclectic", "rattan", "wicker"],
    "coastal": ["coastal", "beach", "nautical", "seaside"],
    "glam": ["glam", "glamour", "luxury", "velvet", "gold accent"],
}


def extract_style(text: str) -> Optional[str]:
    """Extract design style from product text.

    Args:
        text: Product name or description (lowercase)

    Returns:
        Canonical style name or None if not found
    """
    text_lower = text.lower()

    for canonical_style, keywords in STYLES.items():
        for keyword in keywords:
            if re.search(r'\b' + re.escape(keyword) + r'\b', text_lower):
                return canonical_style

    return None


# ============================================================================
# Material Extraction
# ============================================================================

MATERIALS = {
    "wood": ["wood", "wooden", "timber", "עץ"],
    "metal": ["metal", "steel", "iron", "aluminum", "brass", "מתכת"],
    "glass": ["glass", "tempered glass", "זכוכית"],
    "marble": ["marble", "stone", "granite", "שיש"],
    "fabric": ["fabric", "upholstered", "linen", "cotton", "velvet", "בד"],
    "leather": ["leather", "faux leather", "pu leather", "עור"],
    "plastic": ["plastic", "acrylic", "polycarbonate", "פלסטיק"],
    "rattan": ["rattan", "wicker", "bamboo", "cane"],
}


def extract_material(text: str) -> Optional[str]:
    """Extract primary material from product text.

    Args:
        text: Product name or description (lowercase)

    Returns:
        Canonical material name or None if not found
    """
    text_lower = text.lower()

    for canonical_material, keywords in MATERIALS.items():
        for keyword in keywords:
            if keyword in text_lower:
                return canonical_material

    return None


# ============================================================================
# Product Attribute Extraction
# ============================================================================

def extract_product_attributes(product: dict) -> dict:
    """Extract visual attributes from a product.

    Args:
        product: Product dict with 'name', 'brand', optionally 'description'

    Returns:
        Dict with color, style, material, brand
    """
    # Combine name and description for text analysis
    name = product.get("name", "") or ""
    description = product.get("description", "") or ""
    text = f"{name} {description}".strip()

    return {
        "color": extract_color(text),
        "style": extract_style(text),
        "material": extract_material(text),
        "brand": product.get("brand"),
    }


# ============================================================================
# Cross-Product Matching
# ============================================================================

def score_product_match(product_a: dict, product_b: dict) -> tuple[float, list[str]]:
    """Score how well two products match visually.

    Args:
        product_a: First product dict
        product_b: Second product dict

    Returns:
        Tuple of (score 0-1, list of match reasons)
    """
    attrs_a = extract_product_attributes(product_a)
    attrs_b = extract_product_attributes(product_b)

    score = 0.0
    reasons = []

    # Color match (highest weight - most visible)
    if attrs_a["color"] and attrs_b["color"]:
        if attrs_a["color"] == attrs_b["color"]:
            score += 0.4
            reasons.append(f"Same color: {attrs_a['color']}")

    # Style match (important for cohesive look)
    if attrs_a["style"] and attrs_b["style"]:
        if attrs_a["style"] == attrs_b["style"]:
            score += 0.3
            reasons.append(f"Same style: {attrs_a['style']}")

    # Brand match (often means same collection)
    if attrs_a["brand"] and attrs_b["brand"]:
        if attrs_a["brand"].lower() == attrs_b["brand"].lower():
            score += 0.2
            reasons.append(f"Same brand: {attrs_a['brand']}")

    # Material match (complementary materials)
    if attrs_a["material"] and attrs_b["material"]:
        if attrs_a["material"] == attrs_b["material"]:
            score += 0.1
            reasons.append(f"Same material: {attrs_a['material']}")

    return score, reasons


def find_matched_sets(
    products_by_type: dict[str, list[dict]],
    min_score: float = 0.3,
    max_sets: int = 10,
) -> list[dict]:
    """Find matching product sets across different product types.

    Args:
        products_by_type: Dict mapping product type to list of products
        min_score: Minimum match score to include (0-1)
        max_sets: Maximum number of matched sets to return

    Returns:
        List of matched sets, each with products, score, and reasons
    """
    if len(products_by_type) < 2:
        return []

    product_types = list(products_by_type.keys())
    matched_sets = []

    # For now, handle 2-product matching (can extend to 3+ later)
    if len(product_types) >= 2:
        type_a, type_b = product_types[0], product_types[1]
        products_a = products_by_type[type_a]
        products_b = products_by_type[type_b]

        for prod_a in products_a:
            for prod_b in products_b:
                score, reasons = score_product_match(prod_a, prod_b)

                if score >= min_score:
                    # Calculate combined price if available
                    combined_price = None
                    price_a = prod_a.get("price")
                    price_b = prod_b.get("price")
                    if price_a and price_b:
                        combined_price = price_a + price_b

                    matched_sets.append({
                        "set_id": f"set_{prod_a.get('id', '')}_{prod_b.get('id', '')}",
                        "products": [prod_a, prod_b],
                        "product_types": [type_a, type_b],
                        "match_score": round(score, 2),
                        "match_reasons": reasons,
                        "combined_price": combined_price,
                        "currency": prod_a.get("currency") or prod_b.get("currency"),
                    })

    # Sort by score descending
    matched_sets.sort(key=lambda x: x["match_score"], reverse=True)

    return matched_sets[:max_sets]


# ============================================================================
# Multi-Product Query Parsing
# ============================================================================

# Patterns for detecting multi-product queries
MULTI_PRODUCT_PATTERNS = [
    # "X and matching Y"
    (r"(.+?)\s+(?:and|with)\s+matching\s+(.+)", "matching"),
    # "X that matches Y"
    (r"(.+?)\s+that\s+match(?:es)?\s+(.+)", "matching"),
    # "X to match Y"
    (r"(.+?)\s+to\s+match\s+(.+)", "matching"),
    # "matching X and Y"
    (r"matching\s+(.+?)\s+and\s+(.+)", "matching"),
    # "X and Y" (simple conjunction - complementary)
    (r"(.+?)\s+and\s+(.+)", "complementary"),
    # "X with Y"
    (r"(.+?)\s+with\s+(.+)", "complementary"),
    # "X, Y, and Z" (three products)
    (r"(.+?),\s*(.+?),?\s+and\s+(.+)", "complementary"),
]

# Words that indicate the user wants products to coordinate
MATCHING_KEYWORDS = [
    "matching", "match", "coordinate", "coordinating", "complement",
    "complementary", "go with", "goes with", "pairs with", "same style",
    "same color", "תואם", "מתאים", "באותו סגנון",
]


def parse_multi_product_query(query: str) -> dict:
    """Parse a query to detect multiple products and their relationship.

    Args:
        query: User's search query

    Returns:
        {
            "is_multi_product": bool,
            "products": list of product names,
            "relationship": "matching" | "complementary" | None,
            "original_query": the input query
        }
    """
    query_lower = query.lower().strip()

    # Check if any matching keywords present
    has_matching_intent = any(kw in query_lower for kw in MATCHING_KEYWORDS)

    # Try each pattern
    for pattern, default_relationship in MULTI_PRODUCT_PATTERNS:
        match = re.search(pattern, query_lower, re.IGNORECASE)
        if match:
            groups = match.groups()
            products = [g.strip() for g in groups if g and g.strip()]

            # Filter out empty or very short products
            products = [p for p in products if len(p) > 2]

            if len(products) >= 2:
                # Override to "matching" if matching keywords present
                relationship = "matching" if has_matching_intent else default_relationship

                return {
                    "is_multi_product": True,
                    "products": products,
                    "relationship": relationship,
                    "original_query": query,
                }

    # No multi-product pattern found
    return {
        "is_multi_product": False,
        "products": [query.strip()],
        "relationship": None,
        "original_query": query,
    }


def normalize_product_type(product_name: str) -> str:
    """Convert product name to a normalized type key.

    Args:
        product_name: e.g., "coffee table", "side table"

    Returns:
        Normalized key: e.g., "coffee_table", "side_table"
    """
    return re.sub(r'\s+', '_', product_name.lower().strip())
