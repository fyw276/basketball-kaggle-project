"""In-memory TTL cache for LLM call results.

Avoids redundant API calls when the same prompt is sent within a short window
(e.g. repeated outfit recommendations for the same scenario).
"""

from __future__ import annotations

import hashlib
import threading
import time
from collections import OrderedDict
from typing import Any, Optional


class LLMResultCache:
    """Thread-safe LRU cache with per-entry TTL.

    Keys are SHA-256 hashes of the prompt content.
    Values are the raw response dicts/strings returned by the LLM.
    """

    def __init__(self, max_size: int = 256, default_ttl: int = 600) -> None:
        self._max_size = max(1, max_size)
        self._default_ttl = max(1, default_ttl)
        self._store: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()

    @staticmethod
    def make_key(*parts: str) -> str:
        """Build a cache key by hashing the concatenation of all parts."""
        h = hashlib.sha256()
        for p in parts:
            h.update(p.encode("utf-8", errors="replace"))
        return h.hexdigest()

    def get(self, key: str) -> Optional[Any]:
        """Return cached value if present and not expired, else None."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if time.monotonic() > expires_at:
                del self._store[key]
                return None
            # Move to end (most recently used)
            self._store.move_to_end(key)
            return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Store a value with TTL seconds from now."""
        effective_ttl = ttl if ttl is not None else self._default_ttl
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
            self._store[key] = (time.monotonic() + effective_ttl, value)
            # Evict oldest if over capacity
            while len(self._store) > self._max_size:
                self._store.popitem(last=False)

    def get_or_set(self, key: str, factory, ttl: Optional[int] = None) -> Any:
        """Return cached value or call ``factory()``, cache and return the result."""
        cached = self.get(key)
        if cached is not None:
            return cached
        value = factory()
        self.set(key, value, ttl=ttl)
        return value

    def invalidate(self, key: str) -> bool:
        """Remove a specific key. Returns True if it existed."""
        with self._lock:
            return self._store.pop(key, None) is not None

    def clear(self) -> int:
        """Remove all entries. Returns number of entries removed."""
        with self._lock:
            count = len(self._store)
            self._store.clear()
            return count


# Module-level singleton — 256 entries, 10-minute TTL by default.
_llm_cache: Optional[LLMResultCache] = None


def get_llm_cache(max_size: int = 256, default_ttl: int = 600) -> LLMResultCache:
    """Return the module-level LLM cache singleton."""
    global _llm_cache
    if _llm_cache is None:
        _llm_cache = LLMResultCache(max_size=max_size, default_ttl=default_ttl)
    return _llm_cache
