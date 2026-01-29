"""Version hashing for cache invalidation."""

import hashlib
import inspect
import json
from pathlib import Path
from typing import Any


def get_component_version(obj: Any) -> str:
    """Get hash of the source file containing the object.

    This enables automatic cache invalidation when code changes.

    Args:
        obj: Class instance, function, or any object with source file

    Returns:
        8-character hash of the source file content
    """
    try:
        # Get the class if it's an instance
        if hasattr(obj, "__class__") and not inspect.isclass(obj) and not inspect.isfunction(obj):
            obj = obj.__class__

        source_file = Path(inspect.getfile(obj))
        content = source_file.read_text()
        return hashlib.sha256(content.encode()).hexdigest()[:8]
    except (TypeError, OSError):
        # Fallback for built-in types or inaccessible files
        return "00000000"


def make_cache_key(
    component_type: str,
    component_name: str,
    version_hash: str,
    *args: Any,
    **kwargs: Any,
) -> str:
    """Generate deterministic cache key.

    Format: {component_type}:{component_name}:{version_hash}:{args_hash}

    Args:
        component_type: Type of component (scraper, contact, agent, etc.)
        component_name: Name of the component (class name, function name)
        version_hash: Hash of the source file
        *args: Positional arguments to hash
        **kwargs: Keyword arguments to hash

    Returns:
        Deterministic cache key string
    """
    # Create a hashable representation of args and kwargs
    args_data = {
        "args": [_serialize_arg(a) for a in args],
        "kwargs": {k: _serialize_arg(v) for k, v in sorted(kwargs.items())},
    }
    args_json = json.dumps(args_data, sort_keys=True, default=str)
    args_hash = hashlib.sha256(args_json.encode()).hexdigest()[:12]

    return f"{component_type}:{component_name}:{version_hash}:{args_hash}"


def _serialize_arg(arg: Any) -> Any:
    """Serialize an argument for hashing."""
    if isinstance(arg, (str, int, float, bool, type(None))):
        return arg
    elif isinstance(arg, (list, tuple)):
        return [_serialize_arg(a) for a in arg]
    elif isinstance(arg, dict):
        return {k: _serialize_arg(v) for k, v in sorted(arg.items())}
    else:
        # For complex objects, use string representation
        return str(arg)
