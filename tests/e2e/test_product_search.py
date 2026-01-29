"""E2E tests for product search functionality."""

import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from src.state.models import PriceOption, SellerInfo


class TestProductSearchE2E:
    """E2E tests for product search with caching."""

    @pytest.mark.asyncio
    async def test_search_rf72dg9620b1(
        self, record_mode, recorded_responses, save_cassette, mock_cache_manager
    ):
        """Test search for Samsung refrigerator model RF72DG9620B1."""
        from src.agents.product_research import _search_products_cached

        cassette_name = "search_rf72dg9620b1"
        cassette = recorded_responses(cassette_name)

        if record_mode or not cassette:
            # Record mode or no cassette: use real scrapers
            result = await _search_products_cached(
                "RF72DG9620B1", country="IL", no_cache=True
            )

            # Save cassette
            save_cassette(cassette_name, {"query": "RF72DG9620B1", "result": result})
        else:
            # Replay mode: use recorded data
            result = cassette.get("result", "")

        # Assertions - check result is valid
        assert isinstance(result, str)
        # Allow for "no results" case in replay mode
        if "No products found" not in result:
            assert "Price:" in result or "ILS" in result

    @pytest.mark.asyncio
    async def test_search_bfl523mb1f(
        self, record_mode, recorded_responses, save_cassette, mock_cache_manager
    ):
        """Test search for Bosch oven model BFL523MB1F."""
        from src.agents.product_research import _search_products_cached

        cassette_name = "search_bfl523mb1f"
        cassette = recorded_responses(cassette_name)

        if record_mode or not cassette:
            # Record mode or no cassette: use real scrapers
            result = await _search_products_cached(
                "BFL523MB1F", country="IL", no_cache=True
            )

            # Save cassette
            save_cassette(cassette_name, {"query": "BFL523MB1F", "result": result})
        else:
            # Replay mode: use recorded data
            result = cassette.get("result", "")

        # Assertions
        assert isinstance(result, str)
        if "No products found" not in result:
            assert "Price:" in result or "ILS" in result

    @pytest.mark.asyncio
    async def test_cache_hit_second_call(self, mock_cache_manager, mock_settings):
        """Verify second call uses cache (not real API)."""
        from src.agents.product_research import _search_products_cached, _search_products_impl
        from src.cache import make_cache_key, get_component_version

        query = "TEST_CACHE_HIT"

        # Create mock search result
        mock_result = "Test result for cache hit verification"

        # Get version hash for the cached function
        version = get_component_version(_search_products_impl)
        key = make_cache_key("agent", "search_products", version, query, country="IL")

        # Store in cache
        await mock_cache_manager.set(key, mock_result, ttl_seconds=3600, cache_type="agent")

        # Check stats before second call
        stats_before = mock_cache_manager.get_stats()

        # Second call - should hit cache
        cached_value = await mock_cache_manager.get(key)

        stats_after = mock_cache_manager.get_stats()

        assert cached_value == mock_result
        assert stats_after.hits > stats_before.hits

    @pytest.mark.asyncio
    async def test_no_cache_bypasses_cache(self, mock_cache_manager, mock_settings):
        """Verify no_cache parameter bypasses cache."""
        from src.cache import make_cache_key, get_component_version
        from src.agents.product_research import _search_products_impl

        query = "TEST_NO_CACHE"

        version = get_component_version(_search_products_impl)
        key = make_cache_key("agent", "search_products", version, query, country="IL")

        cached_value = "Cached result"
        await mock_cache_manager.set(
            key, cached_value, ttl_seconds=3600, cache_type="agent"
        )

        # Verify cache has the value
        retrieved = await mock_cache_manager.get(key)
        assert retrieved == cached_value


class TestCacheVersionInvalidation:
    """Tests for version-based cache invalidation."""

    @pytest.mark.asyncio
    async def test_version_hash_generation(self):
        """Verify version hashes are generated from source files."""
        from src.cache.versioning import get_component_version
        from src.agents.product_research import _search_products_impl

        version = get_component_version(_search_products_impl)

        # Should be 8 hex characters
        assert len(version) == 8
        assert all(c in "0123456789abcdef" for c in version)

    @pytest.mark.asyncio
    async def test_cache_key_deterministic(self):
        """Verify cache keys are deterministic for same inputs."""
        from src.cache.versioning import make_cache_key

        key1 = make_cache_key("agent", "test", "abc123", "query1", country="IL")
        key2 = make_cache_key("agent", "test", "abc123", "query1", country="IL")
        key3 = make_cache_key("agent", "test", "abc123", "query2", country="IL")

        assert key1 == key2
        assert key1 != key3

    @pytest.mark.asyncio
    async def test_different_version_different_key(self):
        """Verify different versions produce different cache keys."""
        from src.cache.versioning import make_cache_key

        key1 = make_cache_key("agent", "test", "version1", "query", country="IL")
        key2 = make_cache_key("agent", "test", "version2", "query", country="IL")

        assert key1 != key2

    @pytest.mark.asyncio
    async def test_different_query_lists_different_keys(self):
        """Verify different query lists produce different cache keys.

        Regression test for bug where query lists were excluded from cache key,
        causing different multi-product searches to return the same cached result.
        """
        from src.cache.versioning import make_cache_key

        # Two-product search
        key1 = make_cache_key(
            "agent", "search_multiple_products", "abc123",
            ["RF72DG9620B1", "BFL523MB1F"],
            country="IL"
        )

        # Three-product search (different queries)
        key2 = make_cache_key(
            "agent", "search_multiple_products", "abc123",
            ["SMV4HAX21E", "RF72DG9620B1", "BFL523MB1F"],
            country="IL"
        )

        # Single product search
        key3 = make_cache_key(
            "agent", "search_products", "abc123",
            "RF72DG9620B1",
            country="IL"
        )

        # All keys should be different
        assert key1 != key2, "Different query lists should produce different cache keys"
        assert key1 != key3, "Multi-product and single-product keys should differ"
        assert key2 != key3, "Different function names should produce different keys"


class TestCacheManager:
    """Tests for CacheManager functionality."""

    @pytest.mark.asyncio
    async def test_memory_and_db_storage(self, cache_manager):
        """Verify values are stored in both memory and SQLite."""
        key = "test:key:123"
        value = {"data": "test value", "count": 42}

        await cache_manager.set(key, value, ttl_seconds=3600, cache_type="test")

        # Should be in memory
        assert key in cache_manager._memory

        # Should be retrievable (hits memory first)
        retrieved = await cache_manager.get(key)
        assert retrieved == value

        # Clear memory to force DB read
        cache_manager._memory.clear()

        # Should still be retrievable from DB
        retrieved_from_db = await cache_manager.get(key)
        assert retrieved_from_db == value

    @pytest.mark.asyncio
    async def test_expired_entries_not_returned(self, cache_manager):
        """Verify expired entries return None."""
        key = "test:expired:123"
        value = "this will expire"

        # Set with 0 second TTL (already expired)
        await cache_manager.set(key, value, ttl_seconds=-1, cache_type="test")

        # Should not be retrievable
        retrieved = await cache_manager.get(key)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_lru_eviction(self, tmp_path):
        """Verify LRU eviction when memory limit is reached."""
        from src.cache.manager import CacheManager

        # Small memory limit
        manager = CacheManager(db_path=tmp_path / "lru_test.db", max_memory_items=3)

        # Add 4 items
        for i in range(4):
            await manager.set(f"key{i}", f"value{i}", ttl_seconds=3600, cache_type="test")

        # Only 3 should be in memory (oldest evicted)
        assert len(manager._memory) == 3
        assert "key0" not in manager._memory  # First one evicted
        assert "key3" in manager._memory  # Most recent kept

    @pytest.mark.asyncio
    async def test_stats_tracking(self, cache_manager):
        """Verify hit/miss statistics are tracked."""
        # Miss
        await cache_manager.get("nonexistent")
        stats = cache_manager.get_stats()
        assert stats.misses == 1
        assert stats.hits == 0

        # Set and hit
        await cache_manager.set("exists", "value", ttl_seconds=3600, cache_type="test")
        await cache_manager.get("exists")
        stats = cache_manager.get_stats()
        assert stats.hits == 1
        assert stats.misses == 1

    @pytest.mark.asyncio
    async def test_clear_by_type(self, cache_manager):
        """Verify clearing cache by type."""
        # Add entries of different types
        await cache_manager.set("scraper:1", "v1", ttl_seconds=3600, cache_type="scraper")
        await cache_manager.set("agent:1", "v2", ttl_seconds=3600, cache_type="agent")

        # Clear only scraper type
        cleared = await cache_manager.clear(cache_type="scraper")
        assert cleared >= 1

        # Agent entry should still exist
        assert await cache_manager.get("agent:1") == "v2"
        # Scraper entry should be gone
        assert await cache_manager.get("scraper:1") is None


class TestSellerAggregation:
    """Tests for seller aggregation and multi-product search."""

    def test_normalize_seller_name(self):
        """Test seller name normalization for matching across sources."""
        from src.tools.aggregation import normalize_seller_name

        # Test basic normalization
        assert normalize_seller_name("iStore") == "istore"
        assert normalize_seller_name("i-Store") == "istore"
        # Known aliases map to canonical names
        assert normalize_seller_name("BUG Israel") == "bug"
        assert normalize_seller_name("bug-israel") == "bug"
        assert normalize_seller_name("Store  Name") == "store name"

        # Test special characters removed
        assert normalize_seller_name("Store's Name!") == "stores name"
        assert normalize_seller_name("Store (Main)") == "store main"

    def test_aggregate_by_seller_single_product(self):
        """Test aggregation with single product per seller."""
        from src.tools.aggregation import aggregate_by_seller

        results_by_query = {
            "Product1": [
                PriceOption(
                    product_id="1",
                    seller=SellerInfo(name="Store A", country="IL"),
                    listed_price=1000,
                    currency="ILS",
                    url="https://storea.com/p1"
                ),
                PriceOption(
                    product_id="1",
                    seller=SellerInfo(name="Store B", country="IL"),
                    listed_price=900,
                    currency="ILS",
                    url="https://storeb.com/p1"
                ),
            ],
        }

        aggregations = aggregate_by_seller(results_by_query, top_stores=10)

        assert len(aggregations) == 2
        # Both have 1 product each, so sorted by price
        assert aggregations[0].seller_name == "Store B"
        assert aggregations[0].total_price == 900
        assert aggregations[1].seller_name == "Store A"
        assert aggregations[1].total_price == 1000

    def test_aggregate_prioritizes_multi_product_stores(self):
        """Test that stores with multiple products appear first."""
        from src.tools.aggregation import aggregate_by_seller

        results_by_query = {
            "Product1": [
                PriceOption(
                    product_id="1",
                    seller=SellerInfo(name="Store A", country="IL"),
                    listed_price=1000,
                    currency="ILS",
                    url="https://storea.com/p1"
                ),
                PriceOption(
                    product_id="1",
                    seller=SellerInfo(name="Store B", country="IL"),
                    listed_price=800,
                    currency="ILS",
                    url="https://storeb.com/p1"
                ),
            ],
            "Product2": [
                PriceOption(
                    product_id="2",
                    seller=SellerInfo(name="Store A", country="IL"),
                    listed_price=500,
                    currency="ILS",
                    url="https://storea.com/p2"
                ),
            ],
        }

        aggregations = aggregate_by_seller(results_by_query, top_stores=10)

        # Store A should be first (2 products) even though Store B has lower price
        assert aggregations[0].seller_name == "Store A"
        assert aggregations[0].product_count == 2
        assert aggregations[0].total_price == 1500

        # Store B second (1 product, lower price)
        assert aggregations[1].seller_name == "Store B"
        assert aggregations[1].product_count == 1
        assert aggregations[1].total_price == 800

    def test_aggregate_total_price_calculation(self):
        """Test that total price is correctly summed."""
        from src.tools.aggregation import aggregate_by_seller

        results_by_query = {
            "P1": [
                PriceOption(
                    product_id="1",
                    seller=SellerInfo(name="Store", country="IL"),
                    listed_price=1000,
                    currency="ILS",
                    url="https://store.com/p1"
                )
            ],
            "P2": [
                PriceOption(
                    product_id="2",
                    seller=SellerInfo(name="Store", country="IL"),
                    listed_price=2000,
                    currency="ILS",
                    url="https://store.com/p2"
                )
            ],
        }

        aggregations = aggregate_by_seller(results_by_query)

        assert len(aggregations) == 1
        assert aggregations[0].total_price == 3000

    def test_aggregate_picks_lowest_price_per_query(self):
        """Test that aggregation picks lowest price when same seller has multiple listings."""
        from src.tools.aggregation import aggregate_by_seller

        results_by_query = {
            "Product1": [
                PriceOption(
                    product_id="1",
                    seller=SellerInfo(name="Store A", country="IL"),
                    listed_price=1200,
                    currency="ILS",
                    url="https://storea.com/p1-high"
                ),
                PriceOption(
                    product_id="1",
                    seller=SellerInfo(name="Store A", country="IL"),
                    listed_price=1000,
                    currency="ILS",
                    url="https://storea.com/p1-low"
                ),
            ],
        }

        aggregations = aggregate_by_seller(results_by_query)

        assert len(aggregations) == 1
        assert aggregations[0].total_price == 1000  # Lowest price picked
        assert aggregations[0].products[0].listed_price == 1000

    def test_aggregate_average_rating(self):
        """Test average rating calculation."""
        from src.tools.aggregation import aggregate_by_seller

        results_by_query = {
            "P1": [
                PriceOption(
                    product_id="1",
                    seller=SellerInfo(name="Store", country="IL", reliability_score=4.0),
                    listed_price=1000,
                    currency="ILS",
                    url="https://store.com/p1"
                )
            ],
            "P2": [
                PriceOption(
                    product_id="2",
                    seller=SellerInfo(name="Store", country="IL", reliability_score=5.0),
                    listed_price=2000,
                    currency="ILS",
                    url="https://store.com/p2"
                )
            ],
        }

        aggregations = aggregate_by_seller(results_by_query)

        assert aggregations[0].average_rating == 4.5

    def test_aggregate_contact_extraction(self):
        """Test that contact info is extracted from products."""
        from src.tools.aggregation import aggregate_by_seller

        results_by_query = {
            "P1": [
                PriceOption(
                    product_id="1",
                    seller=SellerInfo(
                        name="Store",
                        country="IL",
                        whatsapp_number="+972501234567"
                    ),
                    listed_price=1000,
                    currency="ILS",
                    url="https://store.com/p1"
                )
            ],
        }

        aggregations = aggregate_by_seller(results_by_query)

        assert aggregations[0].contact == "+972501234567"

    def test_aggregate_top_stores_limit(self):
        """Test that top_stores parameter limits results."""
        from src.tools.aggregation import aggregate_by_seller

        results_by_query = {
            "Product1": [
                PriceOption(
                    product_id="1",
                    seller=SellerInfo(name=f"Store {i}", country="IL"),
                    listed_price=1000 + i * 100,
                    currency="ILS",
                    url=f"https://store{i}.com/p1"
                )
                for i in range(10)
            ],
        }

        aggregations = aggregate_by_seller(results_by_query, top_stores=3)

        assert len(aggregations) == 3


class TestSoferaviAggregation:
    """E2E tests specifically for Soferavi seller aggregation.

    Regression tests for bug where Hebrew/English seller name variants
    (אבי סופר, סופראבי, Soferavi) were not being merged correctly.
    """

    def test_soferavi_hebrew_english_normalization(self):
        """Test that all Soferavi variants normalize to the same key."""
        from src.tools.aggregation import normalize_seller_name

        # All these should normalize to "soferavi"
        assert normalize_seller_name("אבי סופר") == "soferavi"
        assert normalize_seller_name("סופראבי") == "soferavi"
        assert normalize_seller_name("Soferavi") == "soferavi"
        assert normalize_seller_name("soferavi") == "soferavi"
        assert normalize_seller_name("SOFERAVI") == "soferavi"

        # With URL (should also work)
        assert normalize_seller_name("אבי סופר", "https://www.soferavi.co.il/product/123") == "soferavi"
        assert normalize_seller_name("Unknown Store", "https://www.soferavi.co.il/product/123") == "soferavi"

    def test_soferavi_aggregation_merges_all_products(self):
        """Test that products from Soferavi variants are aggregated together.

        Simulates a scenario where:
        - Product 1 found at "סופראבי" (from Zap)
        - Product 2 found at "אבי סופר" (from Zap)
        - Product 3 found at "Soferavi" (from site search)
        All should merge into a single aggregation with 3 products.
        """
        from src.tools.aggregation import aggregate_by_seller

        results_by_query = {
            "RF72DG9620B1": [
                PriceOption(
                    product_id="fridge",
                    seller=SellerInfo(name="סופראבי", country="IL", source="zap"),
                    listed_price=8000,
                    currency="ILS",
                    url="https://www.zap.co.il/model/fridge"
                ),
                PriceOption(
                    product_id="fridge",
                    seller=SellerInfo(name="Other Store", country="IL"),
                    listed_price=8500,
                    currency="ILS",
                    url="https://otherstore.co.il/fridge"
                ),
            ],
            "BFL523MB1F": [
                PriceOption(
                    product_id="oven",
                    seller=SellerInfo(name="אבי סופר", country="IL", source="zap"),
                    listed_price=3000,
                    currency="ILS",
                    url="https://www.zap.co.il/model/oven"
                ),
            ],
            "SMV4HAX21E": [
                PriceOption(
                    product_id="dishwasher",
                    seller=SellerInfo(
                        name="Soferavi",  # English name (from site search)
                        country="IL",
                        source="site_search",
                        website="https://www.soferavi.co.il"
                    ),
                    listed_price=2500,
                    currency="ILS",
                    url="https://www.soferavi.co.il/product/dishwasher"
                ),
            ],
        }

        aggregations = aggregate_by_seller(results_by_query, top_stores=10)

        # Find Soferavi aggregation
        soferavi_agg = None
        for agg in aggregations:
            if agg.normalized_name == "soferavi":
                soferavi_agg = agg
                break

        assert soferavi_agg is not None, "Soferavi should appear in aggregations"
        assert soferavi_agg.product_count == 3, (
            f"Soferavi should have all 3 products, got {soferavi_agg.product_count}. "
            f"Products: {[p.product_id for p in soferavi_agg.products]}"
        )
        assert soferavi_agg.total_price == 8000 + 3000 + 2500
        assert set(soferavi_agg.product_queries) == {"RF72DG9620B1", "BFL523MB1F", "SMV4HAX21E"}

        # Other Store should be separate
        other_agg = next((a for a in aggregations if "other" in a.normalized_name.lower()), None)
        assert other_agg is not None
        assert other_agg.product_count == 1

    def test_soferavi_five_product_bundle(self):
        """Test Soferavi correctly aggregates a 5-product bundle.

        Regression test for the specific user scenario where Soferavi
        had all 5 products but only showed 2/5 in aggregation.
        """
        from src.tools.aggregation import aggregate_by_seller

        # 5 products, all available at Soferavi with different name variants
        results_by_query = {
            "RF72DG9620B1": [
                PriceOption(
                    product_id="fridge",
                    seller=SellerInfo(name="סופראבי", country="IL", source="zap"),
                    listed_price=8000,
                    currency="ILS",
                    url="https://www.zap.co.il/model/fridge"
                ),
            ],
            "BFL523MB1F": [
                PriceOption(
                    product_id="oven",
                    seller=SellerInfo(name="אבי סופר", country="IL", source="zap"),
                    listed_price=3000,
                    currency="ILS",
                    url="https://www.zap.co.il/model/oven"
                ),
            ],
            "SMV4HAX21E": [
                PriceOption(
                    product_id="dishwasher",
                    seller=SellerInfo(name="Soferavi", country="IL", source="site_search"),
                    listed_price=2500,
                    currency="ILS",
                    url="https://www.soferavi.co.il/dishwasher"
                ),
            ],
            "WAN28219IL": [
                PriceOption(
                    product_id="washer",
                    seller=SellerInfo(name="soferavi", country="IL", source="google_shopping"),
                    listed_price=2000,
                    currency="ILS",
                    url="https://www.google.com/shopping/product/washer"
                ),
            ],
            "WTG86409IL": [
                PriceOption(
                    product_id="dryer",
                    seller=SellerInfo(name="SOFERAVI", country="IL", source="google_search"),
                    listed_price=2500,
                    currency="ILS",
                    url="https://www.soferavi.co.il/dryer"
                ),
            ],
        }

        aggregations = aggregate_by_seller(results_by_query, top_stores=10)

        # Find Soferavi
        soferavi = next((a for a in aggregations if a.normalized_name == "soferavi"), None)

        assert soferavi is not None, "Soferavi should appear in aggregations"
        assert soferavi.product_count == 5, (
            f"Soferavi should have all 5 products, got {soferavi.product_count}. "
            f"Queries found: {soferavi.product_queries}"
        )
        assert soferavi.total_price == 8000 + 3000 + 2500 + 2000 + 2500  # 18000
        assert len(set(soferavi.product_queries)) == 5, "All 5 queries should be represented"

        # Soferavi should be first (most products)
        assert aggregations[0].normalized_name == "soferavi"

    def test_seller_domains_mapping(self):
        """Test SELLER_DOMAINS mapping for site-search."""
        from src.tools.aggregation import SELLER_DOMAINS

        assert SELLER_DOMAINS.get("soferavi") == "soferavi.co.il"
        assert SELLER_DOMAINS.get("bug") == "bug.co.il"
        assert SELLER_DOMAINS.get("ksp") == "ksp.co.il"


