"""Tests for LLM result cache."""

from app.services.llm_cache import LLMResultCache


class TestLLMResultCache:
    def test_set_and_get(self):
        c = LLMResultCache(max_size=10, default_ttl=60)
        c.set("k1", "value1")
        assert c.get("k1") == "value1"

    def test_returns_none_for_missing_key(self):
        c = LLMResultCache()
        assert c.get("nonexistent") is None

    def test_expired_entry_returns_none(self):
        c = LLMResultCache(max_size=10, default_ttl=1)
        # Use negative TTL so expires_at is in the past (avoids monotonic race)
        c.set("k1", "value1", ttl=-1)
        assert c.get("k1") is None

    def test_lru_eviction(self):
        c = LLMResultCache(max_size=3, default_ttl=60)
        c.set("a", 1)
        c.set("b", 2)
        c.set("c", 3)
        c.set("d", 4)  # should evict "a"
        assert c.get("a") is None
        assert c.get("d") == 4

    def test_get_promotes_entry(self):
        c = LLMResultCache(max_size=3, default_ttl=60)
        c.set("a", 1)
        c.set("b", 2)
        c.set("c", 3)
        c.get("a")  # promote "a"
        c.set("d", 4)  # should evict "b" (oldest unused)
        assert c.get("a") == 1
        assert c.get("b") is None

    def test_invalidate(self):
        c = LLMResultCache()
        c.set("k1", "v1")
        assert c.invalidate("k1") is True
        assert c.get("k1") is None
        assert c.invalidate("k1") is False

    def test_clear(self):
        c = LLMResultCache()
        c.set("a", 1)
        c.set("b", 2)
        count = c.clear()
        assert count == 2
        assert c.get("a") is None

    def test_make_key_deterministic(self):
        k1 = LLMResultCache.make_key("a", "b", "c")
        k2 = LLMResultCache.make_key("a", "b", "c")
        assert k1 == k2

    def test_make_key_different_inputs(self):
        k1 = LLMResultCache.make_key("a", "b")
        k2 = LLMResultCache.make_key("a", "c")
        assert k1 != k2

    def test_get_or_set(self):
        c = LLMResultCache(max_size=10, default_ttl=60)
        calls = []

        def factory():
            calls.append(1)
            return "computed"

        result1 = c.get_or_set("k", factory)
        result2 = c.get_or_set("k", factory)
        assert result1 == "computed"
        assert result2 == "computed"
        assert len(calls) == 1  # factory called only once
