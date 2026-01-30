"""Tests for seller aggregation logic."""

import pytest

from src.tools.aggregation import normalize_seller_name, ZAP_STORE_NAMES


class TestNormalizeSellerName:
    """Tests for seller name normalization."""

    # Zap-owned store tests
    def test_zapstore_normalizes_to_zap(self):
        """ZapStore (Zap's own store) should normalize to 'zap'."""
        assert normalize_seller_name("ZapStore") == "zap"
        assert normalize_seller_name("zapstore") == "zap"

    def test_zap_direct_normalizes_to_zap(self):
        """Zap Direct should normalize to 'zap'."""
        assert normalize_seller_name("Zap Direct") == "zap"

    def test_hebrew_zap_normalizes_to_zap(self):
        """Hebrew Zap store names should normalize to 'zap'."""
        # Only actual Zap-owned stores, not the marketplace section
        assert normalize_seller_name("זאפ") == "zap"
        assert normalize_seller_name("Zap ישיר") == "zap"

    def test_marketplace_section_not_zap(self):
        """רכישה בזאפ is a marketplace, sellers there are third-party."""
        # When seller is listed under רכישה בזאפ, use actual seller name
        result = normalize_seller_name(
            "x-press",  # Actual seller shown under רכישה בזאפ
            url="https://shop.zap.co.il/product-model?offerid=123"
        )
        assert result == "xpress"
        assert result != "zap"

    def test_zap_co_il_normalizes_to_zap(self):
        """Zap.co.il as seller name should normalize to 'zap'."""
        assert normalize_seller_name("Zap.co.il") == "zap"

    # Third-party sellers on Zap should NOT normalize to zap
    def test_superelectric_on_zap_stays_superelectric(self):
        """Superelectric sold on Zap should NOT become 'zap'."""
        result = normalize_seller_name(
            "superelectric",
            url="https://www.zap.co.il/model.aspx?modelid=1229103"
        )
        assert result == "superelectric"
        assert result != "zap"

    def test_xpress_on_zap_stays_xpress(self):
        """X-Press sold on Zap should normalize to 'xpress', not 'zap'."""
        result = normalize_seller_name(
            "x-press",
            url="https://shop.zap.co.il/product-model?offerid=123"
        )
        assert result == "xpress"
        assert result != "zap"

    def test_third_party_on_zap_not_attributed_to_zap(self):
        """Any third-party seller on Zap URL should not become 'zap'."""
        # Simulate a product listed on Zap but sold by a third party
        result = normalize_seller_name(
            "שוק החשמל",
            url="https://www.zap.co.il/model.aspx?modelid=1217383"
        )
        assert result == "shuk-hashmal"
        assert result != "zap"

    # Known aliases
    def test_known_aliases_normalize_correctly(self):
        """Known seller aliases should normalize to canonical names."""
        assert normalize_seller_name("אבי סופר") == "soferavi"
        assert normalize_seller_name("באג") == "bug"
        assert normalize_seller_name("KSP") == "ksp"
        assert normalize_seller_name("סיטי דיל") == "citydeal"

    def test_domain_based_normalization(self):
        """Sellers with non-aggregator domains should use domain."""
        result = normalize_seller_name(
            "Some Store",
            url="https://www.bug.co.il/product/123"
        )
        # Should match "bug" from domain
        assert result == "bug"

    def test_aggregator_domain_uses_seller_name(self):
        """For aggregator URLs, should use seller name not domain."""
        # Even with a Zap URL, if seller is not Zap-owned, use seller name
        result = normalize_seller_name(
            "חשמל נטו",
            url="https://www.zap.co.il/model.aspx?modelid=123"
        )
        assert result == "chashmal-neto"

    # Edge cases
    def test_generic_name_normalization(self):
        """Unknown sellers should be normalized generically."""
        result = normalize_seller_name("מוצרי חשמל בע\"מ")
        # Should keep Hebrew chars, remove special chars
        assert "מוצרי חשמל בעמ" in result or "מוצרי חשמל" in result

    def test_empty_name(self):
        """Empty name should return empty string."""
        assert normalize_seller_name("") == ""
        assert normalize_seller_name("   ") == ""


class TestZapStoreNames:
    """Tests for ZAP_STORE_NAMES constant."""

    def test_contains_common_zap_names(self):
        """Should contain all common Zap store name variants."""
        assert "zap" in ZAP_STORE_NAMES
        assert "zapstore" in ZAP_STORE_NAMES
        assert "zap direct" in ZAP_STORE_NAMES

    def test_does_not_contain_third_parties(self):
        """Should NOT contain third-party seller names."""
        assert "superelectric" not in ZAP_STORE_NAMES
        assert "x-press" not in ZAP_STORE_NAMES
        assert "bug" not in ZAP_STORE_NAMES

    def test_does_not_contain_marketplace_section(self):
        """רכישה בזאפ is a marketplace section, not Zap's own store."""
        # Third-party sellers list under רכישה בזאפ, so it's not a Zap store name
        assert "רכישה בזאפ" not in ZAP_STORE_NAMES
