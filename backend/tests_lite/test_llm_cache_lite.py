"""Lite gate tests for LLM result cache."""

from app.services.llm_cache import LLMResultCache


def test_set_and_get():
    c = LLMResultCache(max_size=10, default_ttl=60)
    c.set("k", "v")
    assert c.get("k") == "v"


def test_miss_returns_none():
    c = LLMResultCache()
    assert c.get("missing") is None


def test_eviction_on_overflow():
    c = LLMResultCache(max_size=2, default_ttl=60)
    c.set("a", 1)
    c.set("b", 2)
    c.set("c", 3)  # evicts "a"
    assert c.get("a") is None
    assert c.get("c") == 3


def test_make_key_is_deterministic():
    k1 = LLMResultCache.make_key("x", "y")
    k2 = LLMResultCache.make_key("x", "y")
    assert k1 == k2
