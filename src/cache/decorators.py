"""Cache decorators for transparent caching of async functions."""

from contextvars import ContextVar
from functools import wraps
from typing import Any, Callable, Optional, TypeVar

import structlog

from src.config.settings import settings

from .manager import get_cache_manager
from .versioning import get_component_version, make_cache_key

logger = structlog.get_logger()

F = TypeVar("F", bound=Callable[..., Any])

# Context variable to track cache hit status for observability
# None = not a cached call, True = cache hit, False = cache miss
_cache_hit_status: ContextVar[Optional[bool]] = ContextVar("cache_hit_status", default=None)


def get_cache_hit_status() -> Optional[bool]:
    """Get the cache hit status from the current context.

    Returns:
        True if the last cached call was a cache hit,
        False if it was a cache miss,
        None if no cached call was made.
    """
    return _cache_hit_status.get()


def clear_cache_hit_status() -> None:
    """Clear the cache hit status in the current context."""
    _cache_hit_status.set(None)


def cached(
    cache_type: str = "general",
    ttl_hours: Optional[int] = None,
    key_prefix: Optional[str] = None,
) -> Callable[[F], F]:
    """Decorator to cache async function results.

    Supports version-based invalidation by hashing the source file
    of the decorated function or its class.

    Args:
        cache_type: Category for TTL lookup (scraper, contact, http, agent)
        ttl_hours: Override TTL in hours (uses settings default if None)
        key_prefix: Override component name in key

    Usage:
        @cached(cache_type="scraper", ttl_hours=24)
        async def search(self, query: str) -> list[PriceOption]:
            ...

        # To bypass cache:
        await search(query, no_cache=True)
    """

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, no_cache: bool = False, **kwargs: Any) -> Any:
            # Check if caching is disabled globally or for this call
            if not settings.cache_enabled or no_cache:
                # Remove no_cache from kwargs before calling original function
                return await func(*args, **kwargs)

            # Get version hash from the decorated function's source file
            # For instance methods, use the class; for plain functions, use the function itself
            if args and hasattr(args[0], "__class__"):
                first_arg = args[0]
                # Check if first arg is 'self' (has __dict__ and is not a builtin type)
                if (
                    hasattr(first_arg, "__dict__")
                    and not isinstance(first_arg, type)
                    and first_arg.__class__.__name__
                    not in ("str", "list", "dict", "int", "float", "bool", "tuple")
                ):
                    # It's an instance method, use the class for versioning
                    version = get_component_version(first_arg)
                else:
                    # First arg is a regular argument, use the function for versioning
                    version = get_component_version(func)
            else:
                # No args or first arg doesn't have __class__, use function
                version = get_component_version(func)

            # Build cache key
            if key_prefix:
                name = key_prefix
            elif args and hasattr(args[0], "__class__"):
                first_arg = args[0]
                if (
                    hasattr(first_arg, "__dict__")
                    and not isinstance(first_arg, type)
                    and first_arg.__class__.__name__
                    not in ("str", "list", "dict", "int", "float", "bool", "tuple")
                ):
                    # It's an instance, use class name
                    name = first_arg.__class__.__name__
                else:
                    name = func.__name__
            else:
                name = func.__name__

            # Filter out 'self' from args for key generation, but only for instance methods
            # For plain functions, include all args in the cache key
            if args and hasattr(args[0], "__class__") and args[0].__class__.__name__ not in ("str", "list", "dict", "int", "float", "bool", "tuple"):
                # Check if first arg looks like 'self' (has attributes typical of an instance)
                first_arg = args[0]
                if hasattr(first_arg, "__dict__") and not isinstance(first_arg, type):
                    # It's likely an instance (self), skip it
                    cache_args = args[1:]
                else:
                    cache_args = args
            else:
                cache_args = args
            key = make_cache_key(cache_type, name, version, *cache_args, **kwargs)

            # Check cache
            cache = get_cache_manager()
            cached_value = await cache.get(key)
            if cached_value is not None:
                logger.debug(
                    "Cache hit",
                    func=func.__name__,
                    key=key[:60],
                    type=cache_type,
                )
                # Set cache hit status for observability
                _cache_hit_status.set(True)
                return cached_value

            # Execute original function
            result = await func(*args, **kwargs)

            # Set cache miss status for observability
            _cache_hit_status.set(False)

            # Determine TTL
            ttl = ttl_hours if ttl_hours is not None else _get_default_ttl(cache_type)
            ttl_seconds = ttl * 3600

            # Cache the result
            await cache.set(
                key,
                result,
                ttl_seconds=ttl_seconds,
                cache_type=cache_type,
                version_hash=version,
            )

            logger.debug(
                "Cache miss - stored",
                func=func.__name__,
                key=key[:60],
                type=cache_type,
                ttl_hours=ttl,
            )

            return result

        return wrapper  # type: ignore

    return decorator


def _get_default_ttl(cache_type: str) -> int:
    """Get default TTL in hours from settings.

    Args:
        cache_type: Type of cache entry

    Returns:
        TTL in hours
    """
    ttls = {
        "scraper": settings.cache_ttl_scraper_hours,
        "contact": settings.cache_ttl_contact_days * 24,
        "http": settings.cache_ttl_http_hours,
        "agent": settings.cache_ttl_agent_hours,
    }
    return ttls.get(cache_type, 1)
