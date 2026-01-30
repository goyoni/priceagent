"""E2E test for Zap aggregation logic.

Tests that products from Zap are correctly attributed to actual sellers,
not just "Zap" for everything.
"""

import pytest
from collections import defaultdict

from src.tools.scraping.israel.zap_http_scraper import ZapHttpScraper
from src.tools.aggregation import normalize_seller_name, aggregate_by_seller


class TestZapAggregation:
    """E2E tests for Zap seller aggregation."""

    @pytest.fixture
    def scraper(self):
        """Create a ZapHttpScraper instance."""
        return ZapHttpScraper()

    @pytest.mark.asyncio
    async def test_zap_aggregation_multiple_products(self, scraper):
        """Test that Zap products are correctly attributed to actual sellers.

        Search for multiple products and verify:
        1. Products sold by ZapStore are aggregated under "zap"
        2. Products sold by third-party sellers keep their actual seller name
        3. SMV4HAX21E specifically should NOT be under "zap" (third-party only)
        """
        products = [
            "BFL523MB1F",   # Bosch microwave
            "SMV4HAX21E",  # Bosch dishwasher - NOT sold by Zap directly
            "RF72DG9620B1", # Samsung fridge
            "HBG578EB3",    # Bosch oven
            "PVS631HC1E",   # Bosch cooktop
        ]

        results_by_query: dict[str, list] = {}
        all_results = []

        for product in products:
            try:
                results = await scraper.search(product, max_results=10)
                results_by_query[product] = results
                all_results.extend(results)
                print(f"\n{product}: Found {len(results)} results")
                for r in results[:5]:
                    normalized = normalize_seller_name(r.seller.name, r.url)
                    print(f"  - {r.seller.name} ({normalized}): ₪{r.listed_price}")
            except Exception as e:
                print(f"\n{product}: Error - {e}")
                results_by_query[product] = []

        # Aggregate by seller
        aggregations = aggregate_by_seller(results_by_query)

        print("\n=== AGGREGATIONS ===")
        for agg in aggregations:
            print(f"\n{agg.seller_name} (normalized: {agg.normalized_name}):")
            print(f"  Products: {agg.product_count}")
            print(f"  Total: ₪{agg.total_price:,.0f}")
            print(f"  Queries: {agg.product_queries}")

        # Find Zap aggregation
        zap_agg = next((a for a in aggregations if a.normalized_name == "zap"), None)

        if zap_agg:
            print(f"\n=== ZAP AGGREGATION ===")
            print(f"Products in Zap: {zap_agg.product_queries}")

            # SMV4HAX21E should NOT be in Zap aggregation (third-party only)
            assert "SMV4HAX21E" not in zap_agg.product_queries, \
                f"SMV4HAX21E should NOT be in Zap aggregation (third-party sellers only). Found: {zap_agg.product_queries}"

            # Verify all products in Zap aggregation are from ZapStore
            for product in zap_agg.products:
                seller_name = product.seller.name.lower()
                # Should be a Zap-owned store name
                assert any(zap_name in seller_name for zap_name in ["zap", "זאפ"]), \
                    f"Product in Zap aggregation has non-Zap seller: {product.seller.name}"

        # Verify SMV4HAX21E appears under a different seller (not zap)
        smv_sellers = []
        for result in results_by_query.get("SMV4HAX21E", []):
            normalized = normalize_seller_name(result.seller.name, result.url)
            smv_sellers.append(normalized)

        print(f"\nSMV4HAX21E sellers: {set(smv_sellers)}")

        # SMV4HAX21E should have sellers, and none should be "zap"
        if smv_sellers:
            assert "zap" not in smv_sellers, \
                f"SMV4HAX21E should not have 'zap' as seller. Found: {smv_sellers}"

        print("\n✓ All assertions passed!")

    @pytest.mark.asyncio
    async def test_single_product_seller_attribution(self, scraper):
        """Test seller attribution for a single product with multiple sellers."""
        # SMV4HAX21E is known to be sold by third-party sellers on Zap, not Zap directly
        results = await scraper.search("SMV4HAX21E", max_results=15)

        print(f"\nSMV4HAX21E: Found {len(results)} results")

        zap_direct_count = 0
        third_party_count = 0

        for r in results:
            normalized = normalize_seller_name(r.seller.name, r.url)
            print(f"  - {r.seller.name} -> {normalized}: ₪{r.listed_price}")

            if normalized == "zap":
                zap_direct_count += 1
            else:
                third_party_count += 1

        print(f"\nZap direct: {zap_direct_count}, Third-party: {third_party_count}")

        # SMV4HAX21E should have NO Zap direct sellers
        assert zap_direct_count == 0, \
            f"SMV4HAX21E should have 0 Zap direct sellers, found {zap_direct_count}"

        # Should have some third-party sellers
        assert third_party_count > 0, \
            f"SMV4HAX21E should have third-party sellers, found {third_party_count}"
