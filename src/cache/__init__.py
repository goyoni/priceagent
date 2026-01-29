"""Cache module for transparent caching with version-based invalidation."""

from .decorators import cached, clear_cache_hit_status, get_cache_hit_status
from .manager import CacheManager, CacheStats, get_cache_manager, reset_cache_manager
from .versioning import get_component_version, make_cache_key

__all__ = [
    "cached",
    "CacheManager",
    "CacheStats",
    "get_cache_manager",
    "reset_cache_manager",
    "get_component_version",
    "make_cache_key",
    "get_cache_hit_status",
    "clear_cache_hit_status",
]
