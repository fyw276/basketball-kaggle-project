"""LRU cache service for recognition results with TTL support.

Caches image recognition results by content hash to avoid redundant processing.
Uses SHA256 hash and supports TTL-based expiration.
"""

import hashlib
import logging
import time
from typing import Dict, Optional

from app.ml.image_recognizer import RecognitionResult

logger = logging.getLogger(__name__)

# Default cache size and TTL
DEFAULT_CACHE_SIZE = 1000
DEFAULT_TTL_SECONDS = 3600  # 1 hour


class CacheEntry:
    """Entry in the recognition result cache."""

    def __init__(self, result: RecognitionResult, ttl_sec: float):
        """Initialize cache entry.

        Args:
            result: Recognition result to cache
            ttl_sec: Time to live in seconds
        """
        self.result = result
        self.expires_at = time.time() + ttl_sec


class RecognitionCache:
    """LRU cache for image recognition results."""

    def __init__(self, max_size: int = DEFAULT_CACHE_SIZE, ttl_sec: float = DEFAULT_TTL_SECONDS):
        """Initialize recognition cache.

        Args:
            max_size: Maximum number of cached entries
            ttl_sec: Time to live for each entry in seconds
        """
        self.max_size = max_size
        self.ttl_sec = ttl_sec
        self.cache: Dict[str, CacheEntry] = {}
        self.access_order = []  # Track access order for LRU eviction

    @staticmethod
    def compute_hash(image_bytes: bytes) -> str:
        """Compute SHA256 hash of image bytes.

        Args:
            image_bytes: Raw image data

        Returns:
            Hex string hash
        """
        return hashlib.sha256(image_bytes).hexdigest()

    def get(self, image_bytes: bytes) -> Optional[RecognitionResult]:
        """Get cached recognition result.

        Args:
            image_bytes: Image to look up

        Returns:
            Cached RecognitionResult or None if not found/expired
        """
        key = self.compute_hash(image_bytes)

        if key not in self.cache:
            return None

        entry = self.cache[key]

        # Check expiration
        if time.time() > entry.expires_at:
            del self.cache[key]
            self.access_order.remove(key)
            return None

        # Update access order (move to end for LRU)
        if key in self.access_order:
            self.access_order.remove(key)
        self.access_order.append(key)

        return entry.result

    def set(self, image_bytes: bytes, result: RecognitionResult) -> None:
        """Cache a recognition result.

        Args:
            image_bytes: Original image
            result: Recognition result to cache
        """
        key = self.compute_hash(image_bytes)

        # Evict oldest entry if at capacity
        if len(self.cache) >= self.max_size and key not in self.cache:
            oldest_key = self.access_order.pop(0)
            del self.cache[oldest_key]
            logger.debug(f"Evicted cache entry: {oldest_key}")

        # Add or update entry
        self.cache[key] = CacheEntry(result, self.ttl_sec)
        if key in self.access_order:
            self.access_order.remove(key)
        self.access_order.append(key)

    def clear(self) -> None:
        """Clear all cache entries."""
        self.cache.clear()
        self.access_order.clear()

    def stats(self) -> Dict:
        """Get cache statistics.

        Returns:
            Dict with size, max_size, and hit_rate info
        """
        return {"size": len(self.cache), "max_size": self.max_size}


# Singleton instance
_cache: Optional[RecognitionCache] = None


def get_cache(
    max_size: int = DEFAULT_CACHE_SIZE, ttl_sec: float = DEFAULT_TTL_SECONDS
) -> RecognitionCache:
    """Get or create singleton cache.

    Args:
        max_size: Max cache size (only used on first call)
        ttl_sec: TTL in seconds (only used on first call)

    Returns:
        RecognitionCache instance
    """
    global _cache
    if _cache is None:
        _cache = RecognitionCache(max_size=max_size, ttl_sec=ttl_sec)
    return _cache
