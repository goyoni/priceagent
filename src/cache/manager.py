"""Cache manager with memory and SQLite layers."""

import json
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import aiosqlite
import structlog
from pydantic import BaseModel

logger = structlog.get_logger()


class CacheStats(BaseModel):
    """Cache statistics."""

    hits: int = 0
    misses: int = 0
    memory_items: int = 0
    db_items: int = 0

    @property
    def hit_rate(self) -> float:
        """Calculate hit rate percentage."""
        total = self.hits + self.misses
        return (self.hits / total * 100) if total > 0 else 0.0


class CacheEntry(BaseModel):
    """A single cache entry."""

    key: str
    value: str  # JSON serialized
    cache_type: str
    version_hash: str
    created_at: datetime
    expires_at: datetime
    hit_count: int = 0


class CacheManager:
    """Two-tier cache: LRU memory + SQLite persistence."""

    def __init__(self, db_path: Path, max_memory_items: int = 1000):
        """Initialize cache manager.

        Args:
            db_path: Path to SQLite database
            max_memory_items: Maximum items in memory cache (LRU eviction)
        """
        self._memory: OrderedDict[str, CacheEntry] = OrderedDict()
        self._max_memory = max_memory_items
        self._db_path = db_path
        self._initialized = False
        self._stats = CacheStats()

    async def _ensure_initialized(self) -> None:
        """Ensure database is initialized."""
        if self._initialized:
            return

        # Ensure directory exists
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS cache_entries (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    cache_type TEXT NOT NULL,
                    version_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    hit_count INTEGER DEFAULT 0
                )
            """)
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_cache_type ON cache_entries(cache_type)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_expires ON cache_entries(expires_at)"
            )
            await db.commit()

        self._initialized = True
        logger.debug("Cache database initialized", path=str(self._db_path))

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache.

        Checks memory first, then SQLite.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        await self._ensure_initialized()

        # Check memory first
        if key in self._memory:
            entry = self._memory[key]
            if datetime.now() < entry.expires_at:
                # Move to end (most recently used)
                self._memory.move_to_end(key)
                entry.hit_count += 1
                self._stats.hits += 1
                logger.debug("Cache hit (memory)", key=key[:50])
                return self._deserialize(entry.value)
            else:
                # Expired, remove from memory
                del self._memory[key]

        # Check SQLite
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT value, expires_at, hit_count FROM cache_entries WHERE key = ?",
                (key,),
            )
            row = await cursor.fetchone()

            if row:
                value, expires_at_str, hit_count = row
                expires_at = datetime.fromisoformat(expires_at_str)

                if datetime.now() < expires_at:
                    # Update hit count
                    await db.execute(
                        "UPDATE cache_entries SET hit_count = ? WHERE key = ?",
                        (hit_count + 1, key),
                    )
                    await db.commit()
                    self._stats.hits += 1
                    logger.debug("Cache hit (db)", key=key[:50])
                    return self._deserialize(value)
                else:
                    # Expired, delete from db
                    await db.execute("DELETE FROM cache_entries WHERE key = ?", (key,))
                    await db.commit()

        self._stats.misses += 1
        logger.debug("Cache miss", key=key[:50])
        return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: int,
        cache_type: str,
        version_hash: str = "",
    ) -> None:
        """Store value in cache.

        Stores in both memory and SQLite.

        Args:
            key: Cache key
            value: Value to cache (will be JSON serialized)
            ttl_seconds: Time to live in seconds
            cache_type: Category of cached item (scraper, contact, etc.)
            version_hash: Version hash for invalidation tracking
        """
        await self._ensure_initialized()

        now = datetime.now()
        expires_at = now + timedelta(seconds=ttl_seconds)
        serialized = self._serialize(value)

        entry = CacheEntry(
            key=key,
            value=serialized,
            cache_type=cache_type,
            version_hash=version_hash,
            created_at=now,
            expires_at=expires_at,
        )

        # Store in memory (LRU)
        self._memory[key] = entry
        self._memory.move_to_end(key)

        # Evict oldest if over limit
        while len(self._memory) > self._max_memory:
            self._memory.popitem(last=False)

        # Store in SQLite
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO cache_entries
                (key, value, cache_type, version_hash, created_at, expires_at, hit_count)
                VALUES (?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    key,
                    serialized,
                    cache_type,
                    version_hash,
                    now.isoformat(),
                    expires_at.isoformat(),
                ),
            )
            await db.commit()

        logger.debug("Cache set", key=key[:50], ttl=ttl_seconds, type=cache_type)

    async def invalidate(self, pattern: str) -> int:
        """Invalidate cache entries matching pattern.

        Args:
            pattern: Pattern to match (uses SQL LIKE syntax with % wildcards)

        Returns:
            Number of entries invalidated
        """
        await self._ensure_initialized()

        # Remove from memory
        keys_to_remove = [k for k in self._memory if self._matches_pattern(k, pattern)]
        for key in keys_to_remove:
            del self._memory[key]

        # Remove from SQLite
        async with aiosqlite.connect(self._db_path) as db:
            # Convert pattern to SQL LIKE pattern
            sql_pattern = pattern.replace("*", "%")
            cursor = await db.execute(
                "DELETE FROM cache_entries WHERE key LIKE ?", (sql_pattern,)
            )
            await db.commit()
            return cursor.rowcount + len(keys_to_remove)

    async def clear(self, cache_type: Optional[str] = None) -> int:
        """Clear cache entries.

        Args:
            cache_type: If specified, only clear entries of this type

        Returns:
            Number of entries cleared
        """
        await self._ensure_initialized()

        count = 0

        if cache_type:
            # Clear specific type from memory
            keys_to_remove = [
                k for k, v in self._memory.items() if v.cache_type == cache_type
            ]
            for key in keys_to_remove:
                del self._memory[key]
            count += len(keys_to_remove)

            # Clear from SQLite
            async with aiosqlite.connect(self._db_path) as db:
                cursor = await db.execute(
                    "DELETE FROM cache_entries WHERE cache_type = ?", (cache_type,)
                )
                await db.commit()
                count += cursor.rowcount
        else:
            # Clear all
            count = len(self._memory)
            self._memory.clear()

            async with aiosqlite.connect(self._db_path) as db:
                cursor = await db.execute("DELETE FROM cache_entries")
                await db.commit()
                count += cursor.rowcount

        logger.info("Cache cleared", type=cache_type, count=count)
        return count

    async def cleanup_expired(self) -> int:
        """Remove expired entries from cache.

        Returns:
            Number of entries removed
        """
        await self._ensure_initialized()

        now = datetime.now()

        # Clean memory
        expired_keys = [k for k, v in self._memory.items() if v.expires_at < now]
        for key in expired_keys:
            del self._memory[key]

        # Clean SQLite
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "DELETE FROM cache_entries WHERE expires_at < ?", (now.isoformat(),)
            )
            await db.commit()
            return cursor.rowcount + len(expired_keys)

    def get_stats(self) -> CacheStats:
        """Get cache statistics.

        Returns:
            CacheStats with hit/miss counts and item counts
        """
        self._stats.memory_items = len(self._memory)
        return self._stats.model_copy()

    async def get_db_item_count(self) -> int:
        """Get count of items in SQLite database."""
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM cache_entries")
            row = await cursor.fetchone()
            return row[0] if row else 0

    def _serialize(self, value: Any) -> str:
        """Serialize value to JSON string."""
        return json.dumps(value, default=self._json_default)

    def _deserialize(self, value: str) -> Any:
        """Deserialize JSON string to value."""
        return json.loads(value)

    def _json_default(self, obj: Any) -> Any:
        """Default JSON serializer for complex types."""
        if isinstance(obj, datetime):
            return {"__datetime__": obj.isoformat()}
        elif hasattr(obj, "model_dump"):
            return {"__pydantic__": obj.__class__.__name__, "data": obj.model_dump()}
        elif hasattr(obj, "__dict__"):
            return {"__object__": obj.__class__.__name__, "data": obj.__dict__}
        return str(obj)

    def _matches_pattern(self, key: str, pattern: str) -> bool:
        """Check if key matches pattern (simple glob matching)."""
        import fnmatch

        # Convert SQL-like pattern to glob
        glob_pattern = pattern.replace("%", "*")
        return fnmatch.fnmatch(key, glob_pattern)


# Global cache manager instance
_cache_manager: Optional[CacheManager] = None


def get_cache_manager() -> CacheManager:
    """Get the global cache manager instance.

    Returns:
        CacheManager instance (creates if needed)
    """
    global _cache_manager
    if _cache_manager is None:
        from src.config.settings import settings

        _cache_manager = CacheManager(
            db_path=settings.cache_path,
            max_memory_items=settings.cache_memory_max_items,
        )
    return _cache_manager


def reset_cache_manager() -> None:
    """Reset the global cache manager (for testing)."""
    global _cache_manager
    _cache_manager = None
