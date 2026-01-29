"""Tests for cache module - manager, decorators, and versioning."""

import asyncio
import pytest
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

from src.cache.manager import CacheManager, CacheStats, reset_cache_manager, get_cache_manager
from src.cache.decorators import cached, get_cache_hit_status, clear_cache_hit_status
from src.cache.versioning import get_component_version, make_cache_key


class TestCacheManager:
    """Tests for CacheManager class."""

    @pytest.fixture
    def temp_cache_db(self):
        """Create a temporary cache database."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            yield Path(f.name)

    @pytest.fixture
    def cache_manager(self, temp_cache_db):
        """Create a cache manager with temp database."""
        return CacheManager(db_path=temp_cache_db, max_memory_items=100)

    @pytest.mark.asyncio
    async def test_set_and_get(self, cache_manager):
        """Test basic set and get operations."""
        await cache_manager.set(
            key="test:key1",
            value={"name": "test", "price": 100},
            ttl_seconds=3600,
            cache_type="test",
            version_hash="abc123",
        )

        result = await cache_manager.get("test:key1")
        assert result is not None
        assert result["name"] == "test"
        assert result["price"] == 100

    @pytest.mark.asyncio
    async def test_get_missing_key(self, cache_manager):
        """Test get returns None for missing keys."""
        result = await cache_manager.get("nonexistent:key")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_hit_increments_stats(self, cache_manager):
        """Test that cache hits increment statistics."""
        await cache_manager.set("test:stats", "value", 3600, "test", "v1")

        # First get - cache hit
        await cache_manager.get("test:stats")
        stats = cache_manager.get_stats()
        assert stats.hits == 1
        assert stats.misses == 0

        # Second get - another hit
        await cache_manager.get("test:stats")
        stats = cache_manager.get_stats()
        assert stats.hits == 2

    @pytest.mark.asyncio
    async def test_cache_miss_increments_stats(self, cache_manager):
        """Test that cache misses increment statistics."""
        await cache_manager.get("nonexistent:key")
        stats = cache_manager.get_stats()
        assert stats.misses == 1
        assert stats.hits == 0

    @pytest.mark.asyncio
    async def test_expired_entry_returns_none(self, cache_manager):
        """Test that expired entries return None."""
        # Set with 0 TTL (immediately expired)
        await cache_manager.set("test:expired", "value", 0, "test", "v1")

        # Small delay to ensure expiration
        await asyncio.sleep(0.01)

        result = await cache_manager.get("test:expired")
        assert result is None

    @pytest.mark.asyncio
    async def test_memory_lru_eviction(self, temp_cache_db):
        """Test that memory cache evicts LRU items when full."""
        cache = CacheManager(db_path=temp_cache_db, max_memory_items=3)

        # Fill cache to max
        for i in range(3):
            await cache.set(f"key{i}", f"value{i}", 3600, "test", "v1")

        # Add one more - should evict key0 (oldest)
        await cache.set("key3", "value3", 3600, "test", "v1")

        # Check memory cache has 3 items (not key0)
        assert len(cache._memory) == 3
        assert "key0" not in cache._memory
        assert "key3" in cache._memory

        # But key0 should still be in SQLite
        result = await cache.get("key0")
        assert result == "value0"

    @pytest.mark.asyncio
    async def test_clear_all(self, cache_manager):
        """Test clearing all cache entries."""
        await cache_manager.set("key1", "value1", 3600, "type1", "v1")
        await cache_manager.set("key2", "value2", 3600, "type2", "v1")

        count = await cache_manager.clear()
        assert count >= 2

        assert await cache_manager.get("key1") is None
        assert await cache_manager.get("key2") is None

    @pytest.mark.asyncio
    async def test_clear_by_type(self, cache_manager):
        """Test clearing cache entries by type."""
        await cache_manager.set("key1", "value1", 3600, "scraper", "v1")
        await cache_manager.set("key2", "value2", 3600, "contact", "v1")

        count = await cache_manager.clear(cache_type="scraper")
        assert count >= 1

        # Scraper entry should be gone
        assert await cache_manager.get("key1") is None
        # Contact entry should remain
        assert await cache_manager.get("key2") == "value2"

    @pytest.mark.asyncio
    async def test_invalidate_pattern(self, cache_manager):
        """Test invalidating cache entries by pattern."""
        await cache_manager.set("scraper:zap:v1:abc", "value1", 3600, "scraper", "v1")
        await cache_manager.set("scraper:wisebuy:v1:def", "value2", 3600, "scraper", "v1")
        await cache_manager.set("contact:store1:v1:ghi", "value3", 3600, "contact", "v1")

        # Invalidate all scraper entries
        count = await cache_manager.invalidate("scraper:*")
        assert count >= 2

        assert await cache_manager.get("scraper:zap:v1:abc") is None
        assert await cache_manager.get("scraper:wisebuy:v1:def") is None
        assert await cache_manager.get("contact:store1:v1:ghi") == "value3"

    @pytest.mark.asyncio
    async def test_cleanup_expired(self, cache_manager):
        """Test cleanup of expired entries."""
        # Set one expired and one valid
        await cache_manager.set("expired", "value", 0, "test", "v1")
        await cache_manager.set("valid", "value", 3600, "test", "v1")

        await asyncio.sleep(0.01)

        count = await cache_manager.cleanup_expired()
        assert count >= 1

        assert await cache_manager.get("expired") is None
        assert await cache_manager.get("valid") == "value"

    @pytest.mark.asyncio
    async def test_complex_value_serialization(self, cache_manager):
        """Test that complex values are serialized correctly."""
        complex_value = {
            "list": [1, 2, 3],
            "nested": {"a": 1, "b": [4, 5]},
            "string": "hello",
            "number": 42.5,
        }

        await cache_manager.set("complex", complex_value, 3600, "test", "v1")
        result = await cache_manager.get("complex")

        assert result == complex_value

    @pytest.mark.asyncio
    async def test_get_db_item_count(self, cache_manager):
        """Test getting database item count."""
        await cache_manager.set("key1", "value1", 3600, "test", "v1")
        await cache_manager.set("key2", "value2", 3600, "test", "v1")

        count = await cache_manager.get_db_item_count()
        assert count == 2


class TestCacheDecorator:
    """Tests for the @cached decorator."""

    @pytest.fixture(autouse=True)
    def reset_cache(self):
        """Reset cache manager before each test."""
        reset_cache_manager()
        clear_cache_hit_status()
        yield
        reset_cache_manager()

    @pytest.fixture
    def mock_cache_manager(self):
        """Create a mock cache manager."""
        manager = MagicMock()
        manager.get = AsyncMock(return_value=None)
        manager.set = AsyncMock()
        return manager

    @pytest.mark.asyncio
    async def test_cache_miss_calls_function(self, mock_cache_manager):
        """Test that cache miss calls the original function."""
        call_count = 0

        @cached(cache_type="test")
        async def my_func(arg1: str) -> str:
            nonlocal call_count
            call_count += 1
            return f"result:{arg1}"

        with patch("src.cache.decorators.get_cache_manager", return_value=mock_cache_manager):
            with patch("src.cache.decorators.settings") as mock_settings:
                mock_settings.cache_enabled = True

                result = await my_func("hello")

                assert result == "result:hello"
                assert call_count == 1
                mock_cache_manager.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_hit_skips_function(self, mock_cache_manager):
        """Test that cache hit returns cached value without calling function."""
        mock_cache_manager.get = AsyncMock(return_value="cached_result")
        call_count = 0

        @cached(cache_type="test")
        async def my_func(arg1: str) -> str:
            nonlocal call_count
            call_count += 1
            return f"result:{arg1}"

        with patch("src.cache.decorators.get_cache_manager", return_value=mock_cache_manager):
            with patch("src.cache.decorators.settings") as mock_settings:
                mock_settings.cache_enabled = True

                result = await my_func("hello")

                assert result == "cached_result"
                assert call_count == 0
                mock_cache_manager.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_cache_bypasses_cache(self, mock_cache_manager):
        """Test that no_cache=True bypasses the cache."""
        call_count = 0

        @cached(cache_type="test")
        async def my_func(arg1: str) -> str:
            nonlocal call_count
            call_count += 1
            return f"result:{arg1}"

        with patch("src.cache.decorators.get_cache_manager", return_value=mock_cache_manager):
            with patch("src.cache.decorators.settings") as mock_settings:
                mock_settings.cache_enabled = True

                result = await my_func("hello", no_cache=True)

                assert result == "result:hello"
                assert call_count == 1
                mock_cache_manager.get.assert_not_called()
                mock_cache_manager.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_disabled_bypasses_cache(self, mock_cache_manager):
        """Test that disabled cache bypasses caching."""
        call_count = 0

        @cached(cache_type="test")
        async def my_func(arg1: str) -> str:
            nonlocal call_count
            call_count += 1
            return f"result:{arg1}"

        with patch("src.cache.decorators.get_cache_manager", return_value=mock_cache_manager):
            with patch("src.cache.decorators.settings") as mock_settings:
                mock_settings.cache_enabled = False

                result = await my_func("hello")

                assert result == "result:hello"
                assert call_count == 1
                mock_cache_manager.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_hit_status_context_var(self, mock_cache_manager):
        """Test that cache hit status is set correctly."""
        @cached(cache_type="test")
        async def my_func(arg1: str) -> str:
            return f"result:{arg1}"

        with patch("src.cache.decorators.get_cache_manager", return_value=mock_cache_manager):
            with patch("src.cache.decorators.settings") as mock_settings:
                mock_settings.cache_enabled = True

                # Cache miss
                mock_cache_manager.get = AsyncMock(return_value=None)
                await my_func("hello")
                assert get_cache_hit_status() is False

                # Cache hit
                mock_cache_manager.get = AsyncMock(return_value="cached")
                await my_func("hello")
                assert get_cache_hit_status() is True

    @pytest.mark.asyncio
    async def test_custom_key_prefix(self, mock_cache_manager):
        """Test that custom key prefix is used."""
        @cached(cache_type="test", key_prefix="custom_prefix")
        async def my_func(arg1: str) -> str:
            return f"result:{arg1}"

        with patch("src.cache.decorators.get_cache_manager", return_value=mock_cache_manager):
            with patch("src.cache.decorators.settings") as mock_settings:
                mock_settings.cache_enabled = True

                await my_func("hello")

                # Check that the key contains custom_prefix
                call_args = mock_cache_manager.set.call_args
                key = call_args[1]["key"] if "key" in call_args[1] else call_args[0][0]
                assert "custom_prefix" in key


class TestCacheVersioning:
    """Tests for cache versioning functions."""

    def test_make_cache_key_deterministic(self):
        """Test that cache keys are deterministic."""
        key1 = make_cache_key("scraper", "ZapScraper", "abc123", "query1", max_results=10)
        key2 = make_cache_key("scraper", "ZapScraper", "abc123", "query1", max_results=10)

        assert key1 == key2

    def test_make_cache_key_different_args(self):
        """Test that different args produce different keys."""
        key1 = make_cache_key("scraper", "ZapScraper", "abc123", "query1")
        key2 = make_cache_key("scraper", "ZapScraper", "abc123", "query2")

        assert key1 != key2

    def test_make_cache_key_different_version(self):
        """Test that different versions produce different keys."""
        key1 = make_cache_key("scraper", "ZapScraper", "abc123", "query1")
        key2 = make_cache_key("scraper", "ZapScraper", "def456", "query1")

        assert key1 != key2

    def test_make_cache_key_format(self):
        """Test cache key format."""
        key = make_cache_key("scraper", "ZapScraper", "abc12345", "query")

        parts = key.split(":")
        assert len(parts) == 4
        assert parts[0] == "scraper"
        assert parts[1] == "ZapScraper"
        assert parts[2] == "abc12345"
        assert len(parts[3]) == 12  # args hash length

    def test_get_component_version_function(self):
        """Test getting version hash for a function."""
        def sample_func():
            pass

        version = get_component_version(sample_func)
        assert len(version) == 8
        assert all(c in "0123456789abcdef" for c in version)

    def test_get_component_version_class(self):
        """Test getting version hash for a class."""
        class SampleClass:
            pass

        version = get_component_version(SampleClass)
        assert len(version) == 8

    def test_get_component_version_instance(self):
        """Test getting version hash for an instance."""
        class SampleClass:
            pass

        instance = SampleClass()
        version = get_component_version(instance)
        assert len(version) == 8


class TestCacheIntegration:
    """Integration tests for the full cache flow."""

    @pytest.fixture
    def temp_cache_path(self):
        """Create a temporary cache database path."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            yield Path(f.name)

    @pytest.fixture(autouse=True)
    def reset_global_cache(self, temp_cache_path):
        """Reset global cache manager."""
        reset_cache_manager()
        yield
        reset_cache_manager()

    @pytest.mark.asyncio
    async def test_full_cache_cycle(self, temp_cache_path):
        """Test complete cache cycle with actual storage."""
        call_count = 0

        @cached(cache_type="agent", key_prefix="test_func")
        async def expensive_operation(query: str) -> dict:
            nonlocal call_count
            call_count += 1
            return {"query": query, "result": f"computed:{query}"}

        with patch("src.cache.decorators.settings") as mock_settings:
            mock_settings.cache_enabled = True
            mock_settings.cache_ttl_agent_hours = 1

            with patch("src.cache.decorators.get_cache_manager") as mock_get_manager:
                cache = CacheManager(db_path=temp_cache_path)
                mock_get_manager.return_value = cache

                # First call - cache miss
                result1 = await expensive_operation("test")
                assert call_count == 1
                assert result1 == {"query": "test", "result": "computed:test"}

                # Second call - cache hit
                result2 = await expensive_operation("test")
                assert call_count == 1  # Not incremented
                assert result2 == {"query": "test", "result": "computed:test"}

                # Different query - cache miss
                result3 = await expensive_operation("other")
                assert call_count == 2
                assert result3 == {"query": "other", "result": "computed:other"}

    @pytest.mark.asyncio
    async def test_cache_survives_manager_reset(self, temp_cache_path):
        """Test that cached data survives when using same DB path."""
        with patch("src.cache.decorators.settings") as mock_settings:
            mock_settings.cache_enabled = True
            mock_settings.cache_ttl_agent_hours = 1

            # First cache manager
            cache1 = CacheManager(db_path=temp_cache_path)
            await cache1.set("persist:key", {"data": "value"}, 3600, "test", "v1")

            # Create new cache manager with same path (simulates app restart)
            cache2 = CacheManager(db_path=temp_cache_path)
            result = await cache2.get("persist:key")

            assert result == {"data": "value"}

    @pytest.mark.asyncio
    async def test_version_hash_for_plain_functions(self, temp_cache_path):
        """Test that plain functions (not methods) get proper version hashes."""
        from src.cache.versioning import get_component_version

        @cached(cache_type="agent", key_prefix="versioned_func")
        async def my_versioned_func(query: str) -> str:
            return f"result:{query}"

        # The underlying function should have a proper version hash
        version = get_component_version(my_versioned_func.__wrapped__)
        assert version != "00000000", "Plain functions should have valid version hashes"
        assert len(version) == 8

    @pytest.mark.asyncio
    async def test_repeated_calls_are_cached(self, temp_cache_path):
        """Test that repeated identical calls use cache."""
        execution_times = []

        @cached(cache_type="agent", key_prefix="timing_test")
        async def slow_operation(query: str, max_results: int = 10) -> str:
            import asyncio
            await asyncio.sleep(0.1)  # Simulate slow operation
            execution_times.append(query)
            return f"result:{query}"

        with patch("src.cache.decorators.settings") as mock_settings:
            mock_settings.cache_enabled = True
            mock_settings.cache_ttl_agent_hours = 1

            with patch("src.cache.decorators.get_cache_manager") as mock_get_manager:
                cache = CacheManager(db_path=temp_cache_path)
                mock_get_manager.return_value = cache

                import time

                # First call - slow
                start1 = time.time()
                result1 = await slow_operation("test", max_results=5)
                duration1 = time.time() - start1

                # Second call - should be fast (cached)
                start2 = time.time()
                result2 = await slow_operation("test", max_results=5)
                duration2 = time.time() - start2

                assert result1 == result2 == "result:test"
                assert len(execution_times) == 1, "Function should only be called once"
                assert duration2 < duration1 * 0.5, f"Second call should be faster: {duration2:.3f}s vs {duration1:.3f}s"
