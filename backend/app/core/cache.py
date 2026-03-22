"""
Redis cache configuration and utilities
"""

import json
from typing import Any, Optional

import redis
from redis.connection import ConnectionPool

from app.core.config import settings


class RedisCache:
    """Redis cache manager"""

    def __init__(self):
        """Initialize Redis connection pool"""
        self.pool = ConnectionPool.from_url(
            settings.REDIS_URL,
            max_connections=settings.REDIS_MAX_CONNECTIONS,
            decode_responses=True,
        )
        self.client = redis.Redis(connection_pool=self.pool)

    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found
        """
        try:
            value = self.client.get(key)
            if value is None:
                return None
            return json.loads(value)
        except (redis.RedisError, json.JSONDecodeError):
            return None

    def set(self, key: str, value: Any, expire: Optional[int] = None) -> bool:
        """
        Set value in cache

        Args:
            key: Cache key
            value: Value to cache (will be JSON serialized)
            expire: Expiration time in seconds (optional)

        Returns:
            True if successful, False otherwise
        """
        try:
            serialized = json.dumps(value)
            if expire:
                return self.client.setex(key, expire, serialized)
            else:
                return self.client.set(key, serialized)
        except (redis.RedisError, TypeError):
            return False

    def delete(self, key: str) -> bool:
        """
        Delete value from cache

        Args:
            key: Cache key

        Returns:
            True if key was deleted, False otherwise
        """
        try:
            return bool(self.client.delete(key))
        except redis.RedisError:
            return False

    def exists(self, key: str) -> bool:
        """
        Check if key exists in cache

        Args:
            key: Cache key

        Returns:
            True if key exists, False otherwise
        """
        try:
            return bool(self.client.exists(key))
        except redis.RedisError:
            return False

    def expire(self, key: str, seconds: int) -> bool:
        """
        Set expiration time for a key

        Args:
            key: Cache key
            seconds: Expiration time in seconds

        Returns:
            True if successful, False otherwise
        """
        try:
            return bool(self.client.expire(key, seconds))
        except redis.RedisError:
            return False

    def ttl(self, key: str) -> int:
        """
        Get time to live for a key

        Args:
            key: Cache key

        Returns:
            TTL in seconds, -1 if key has no expiration, -2 if key doesn't exist
        """
        try:
            return self.client.ttl(key)
        except redis.RedisError:
            return -2

    def flush_all(self) -> bool:
        """
        Clear all cache

        WARNING: This will delete all keys in the Redis database!

        Returns:
            True if successful, False otherwise
        """
        try:
            return bool(self.client.flushdb())
        except redis.RedisError:
            return False

    def ping(self) -> bool:
        """
        Test Redis connection

        Returns:
            True if connection is working, False otherwise
        """
        try:
            return self.client.ping()
        except redis.RedisError:
            return False

    def close(self):
        """Close Redis connection"""
        try:
            self.client.close()
        except redis.RedisError:
            pass


# Global cache instance
cache = RedisCache()


def get_cache() -> RedisCache:
    """
    Dependency function to get cache instance

    Returns:
        RedisCache: Global cache instance
    """
    return cache


# Cache key generators
def make_cache_key(*parts: str) -> str:
    """
    Generate cache key from parts

    Args:
        *parts: Key parts to join

    Returns:
        Cache key string
    """
    return ":".join(str(p) for p in parts)


def user_cache_key(user_id: str) -> str:
    """Generate cache key for user data"""
    return make_cache_key("user", user_id)


def profile_cache_key(user_id: str) -> str:
    """Generate cache key for user profile"""
    return make_cache_key("profile", user_id)


def garment_cache_key(garment_id: str) -> str:
    """Generate cache key for garment data"""
    return make_cache_key("garment", garment_id)


def feature_cache_key(image_hash: str) -> str:
    """Generate cache key for image features"""
    return make_cache_key("feature", image_hash)


def recognition_cache_key(image_hash: str) -> str:
    """Generate cache key for recognition results"""
    return make_cache_key("recognition", image_hash)
