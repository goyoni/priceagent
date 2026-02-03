"""Unit tests for product matching module."""

import pytest
from src.agents.product_matching import (
    extract_color,
    extract_style,
    extract_material,
    extract_product_attributes,
    score_product_match,
    find_matched_sets,
    parse_multi_product_query,
    normalize_product_type,
)


class TestColorExtraction:
    """Tests for color extraction from product text."""

    def test_extract_walnut(self):
        assert extract_color("Walnut Coffee Table") == "walnut"
        assert extract_color("Dark Brown Espresso Table") == "walnut"

    def test_extract_white(self):
        assert extract_color("Modern White Side Table") == "white"
        assert extract_color("Ivory Cream Cabinet") == "white"

    def test_extract_black(self):
        assert extract_color("Jet Black Console") == "black"
        assert extract_color("Charcoal Black Shelf") == "black"

    def test_extract_gray(self):
        assert extract_color("Gray Charcoal Dresser") == "gray"
        assert extract_color("Slate Grey Desk") == "gray"

    def test_extract_oak(self):
        assert extract_color("Light Oak Bookshelf") == "oak"
        assert extract_color("Natural Wood Table") == "oak"

    def test_extract_hebrew_colors(self):
        assert extract_color("שולחן אגוז") == "אגוז"
        assert extract_color("ארון לבן") == "לבן"
        assert extract_color("מדף שחור") == "שחור"
        assert extract_color("שולחן אלון טבעי") == "אלון"

    def test_no_color_found(self):
        assert extract_color("Simple Table") is None
        assert extract_color("Product XYZ") is None

    def test_case_insensitive(self):
        assert extract_color("WALNUT TABLE") == "walnut"
        assert extract_color("WHITE shelf") == "white"


class TestStyleExtraction:
    """Tests for style extraction from product text."""

    def test_extract_mid_century(self):
        assert extract_style("Mid-Century Modern Coffee Table") == "mid-century"
        assert extract_style("Midcentury Style Sofa") == "mid-century"

    def test_extract_modern(self):
        assert extract_style("Modern Minimalist Desk") == "modern"
        assert extract_style("Contemporary Sleek Chair") == "modern"

    def test_extract_rustic(self):
        assert extract_style("Rustic Farmhouse Table") == "rustic"
        assert extract_style("Country Cottage Bench") == "rustic"

    def test_extract_industrial(self):
        assert extract_style("Industrial Loft Shelf") == "industrial"
        assert extract_style("Factory Style Desk") == "industrial"

    def test_extract_scandinavian(self):
        assert extract_style("Scandinavian Nordic Chair") == "scandinavian"
        assert extract_style("Danish Hygge Lamp") == "scandinavian"

    def test_no_style_found(self):
        assert extract_style("Simple Table") is None
        assert extract_style("Product XYZ") is None


class TestMaterialExtraction:
    """Tests for material extraction from product text."""

    def test_extract_wood(self):
        assert extract_material("Wooden Coffee Table") == "wood"
        assert extract_material("Solid Timber Desk") == "wood"

    def test_extract_metal(self):
        assert extract_material("Metal Steel Frame") == "metal"
        assert extract_material("Iron Base Table") == "metal"

    def test_extract_glass(self):
        assert extract_material("Tempered Glass Top") == "glass"

    def test_extract_marble(self):
        assert extract_material("Marble Stone Counter") == "marble"
        assert extract_material("Granite Top Table") == "marble"

    def test_extract_fabric(self):
        assert extract_material("Upholstered Linen Chair") == "fabric"
        assert extract_material("Velvet Sofa") == "fabric"

    def test_extract_leather(self):
        assert extract_material("Leather Armchair") == "leather"
        assert extract_material("Faux Leather Ottoman") == "leather"

    def test_extract_hebrew_materials(self):
        assert extract_material("שולחן עץ") == "wood"
        assert extract_material("כיסא מתכת") == "metal"

    def test_no_material_found(self):
        assert extract_material("Simple Table") is None


class TestProductAttributes:
    """Tests for extracting all product attributes."""

    def test_full_attribute_extraction(self):
        product = {
            "name": "Walnut Mid-Century Modern Coffee Table",
            "brand": "West Elm",
            "description": "Beautiful wooden construction",
        }
        attrs = extract_product_attributes(product)
        assert attrs["color"] == "walnut"
        assert attrs["style"] == "mid-century"
        assert attrs["material"] == "wood"
        assert attrs["brand"] == "West Elm"

    def test_missing_fields(self):
        product = {"name": "Simple Table"}
        attrs = extract_product_attributes(product)
        assert attrs["color"] is None
        assert attrs["style"] is None
        assert attrs["material"] is None
        assert attrs["brand"] is None

    def test_empty_product(self):
        product = {}
        attrs = extract_product_attributes(product)
        assert attrs["color"] is None
        assert attrs["brand"] is None


class TestProductMatching:
    """Tests for cross-product matching."""

    def test_perfect_match(self):
        """Products with same color, style, and brand should score high."""
        product_a = {
            "id": "1",
            "name": "Walnut Mid-Century Coffee Table",
            "brand": "West Elm",
        }
        product_b = {
            "id": "2",
            "name": "Walnut Mid-Century Side Table",
            "brand": "West Elm",
        }
        score, reasons = score_product_match(product_a, product_b)
        assert score >= 0.8
        assert "Same color: walnut" in reasons
        assert "Same style: mid-century" in reasons
        assert "Same brand: West Elm" in reasons

    def test_color_only_match(self):
        """Products with only color match should score lower."""
        product_a = {"id": "1", "name": "White Coffee Table"}
        product_b = {"id": "2", "name": "White Side Table"}
        score, reasons = score_product_match(product_a, product_b)
        assert 0.3 <= score < 0.5
        assert "Same color: white" in reasons

    def test_no_match(self):
        """Products with nothing in common should score zero."""
        product_a = {"id": "1", "name": "Walnut Mid-Century Table", "brand": "West Elm"}
        product_b = {"id": "2", "name": "White Modern Chair", "brand": "IKEA"}
        score, reasons = score_product_match(product_a, product_b)
        assert score == 0.0
        assert len(reasons) == 0

    def test_brand_case_insensitive(self):
        """Brand matching should be case insensitive."""
        product_a = {"id": "1", "name": "Table", "brand": "WEST ELM"}
        product_b = {"id": "2", "name": "Chair", "brand": "west elm"}
        score, reasons = score_product_match(product_a, product_b)
        assert "Same brand: WEST ELM" in reasons


class TestFindMatchedSets:
    """Tests for finding matched product sets."""

    def test_find_matching_sets(self):
        """Should find sets of matching products."""
        products_by_type = {
            "coffee_table": [
                {"id": "1", "name": "Walnut Mid-Century Coffee Table", "brand": "West Elm"},
            ],
            "side_table": [
                {"id": "2", "name": "Walnut Mid-Century Side Table", "brand": "West Elm"},
                {"id": "3", "name": "White Modern Side Table", "brand": "IKEA"},
            ],
        }
        sets = find_matched_sets(products_by_type, min_score=0.3)
        assert len(sets) == 1
        assert sets[0]["match_score"] >= 0.8
        assert len(sets[0]["products"]) == 2

    def test_no_matches_below_threshold(self):
        """Should not return sets below min_score."""
        products_by_type = {
            "coffee_table": [{"id": "1", "name": "White Modern Table"}],
            "side_table": [{"id": "2", "name": "Black Rustic Table"}],
        }
        sets = find_matched_sets(products_by_type, min_score=0.5)
        assert len(sets) == 0

    def test_single_product_type(self):
        """Should return empty for single product type."""
        products_by_type = {
            "coffee_table": [{"id": "1", "name": "Table"}],
        }
        sets = find_matched_sets(products_by_type)
        assert len(sets) == 0

    def test_empty_products(self):
        """Should handle empty product lists."""
        sets = find_matched_sets({})
        assert len(sets) == 0

    def test_max_sets_limit(self):
        """Should respect max_sets limit."""
        # Create many matching products
        products_by_type = {
            "type_a": [{"id": f"a{i}", "name": "Walnut Table"} for i in range(5)],
            "type_b": [{"id": f"b{i}", "name": "Walnut Chair"} for i in range(5)],
        }
        sets = find_matched_sets(products_by_type, max_sets=3)
        assert len(sets) <= 3

    def test_combined_price_calculation(self):
        """Should calculate combined price for sets."""
        products_by_type = {
            "coffee_table": [
                {"id": "1", "name": "Walnut Table", "price": 500, "currency": "ILS"},
            ],
            "side_table": [
                {"id": "2", "name": "Walnut Table", "price": 300, "currency": "ILS"},
            ],
        }
        sets = find_matched_sets(products_by_type, min_score=0.3)
        assert len(sets) == 1
        assert sets[0]["combined_price"] == 800


class TestMultiProductQueryParsing:
    """Tests for parsing multi-product queries."""

    def test_simple_and_query(self):
        """Simple 'X and Y' query."""
        result = parse_multi_product_query("coffee table and side table")
        assert result["is_multi_product"] is True
        assert "coffee table" in result["products"]
        assert "side table" in result["products"]
        assert result["relationship"] == "complementary"

    def test_matching_query(self):
        """'X and matching Y' query."""
        result = parse_multi_product_query("coffee table and matching side table")
        assert result["is_multi_product"] is True
        assert result["relationship"] == "matching"

    def test_that_matches_query(self):
        """'X that matches Y' query."""
        result = parse_multi_product_query("side table that matches my coffee table")
        assert result["is_multi_product"] is True
        assert result["relationship"] == "matching"

    def test_matching_keyword_query(self):
        """Query with matching keywords."""
        result = parse_multi_product_query("sofa and chair, same style")
        assert result["is_multi_product"] is True
        assert result["relationship"] == "matching"

    def test_single_product_query(self):
        """Single product query."""
        result = parse_multi_product_query("quiet refrigerator")
        assert result["is_multi_product"] is False
        assert result["products"] == ["quiet refrigerator"]
        assert result["relationship"] is None

    def test_with_query(self):
        """'X with Y' query."""
        result = parse_multi_product_query("dining table with chairs")
        assert result["is_multi_product"] is True
        assert result["relationship"] == "complementary"


class TestNormalizeProductType:
    """Tests for product type normalization."""

    def test_simple_normalization(self):
        assert normalize_product_type("coffee table") == "coffee_table"
        assert normalize_product_type("side table") == "side_table"

    def test_multiple_spaces(self):
        assert normalize_product_type("dining  room  table") == "dining_room_table"

    def test_case_normalization(self):
        assert normalize_product_type("Coffee Table") == "coffee_table"
        assert normalize_product_type("SIDE TABLE") == "side_table"

    def test_trim_whitespace(self):
        assert normalize_product_type("  coffee table  ") == "coffee_table"
