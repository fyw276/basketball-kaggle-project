"""
Core application modules
"""

from app.core.config import settings

try:
    from app.core.cache import cache, get_cache
except Exception:  # pragma: no cover - optional runtime dependency for lite environments
    cache = None

    def get_cache():
        raise RuntimeError("Cache backend is unavailable in current environment")


__all__ = ["settings", "cache", "get_cache"]
