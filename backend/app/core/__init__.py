"""
Core application modules
"""

from app.core.cache import cache, get_cache
from app.core.config import settings

__all__ = ["settings", "cache", "get_cache"]
