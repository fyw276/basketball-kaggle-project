"""Lite tests for rule-based agent intent router."""

from app.api.agent_intent import route_intent_rules


def test_intent_weather_keywords():
    r = route_intent_rules("上海今天天气冷不冷")
    assert "get_weather_by_city" in r.suggested_mcp_tools
    assert r.intent_label == "weather"


def test_intent_fallback():
    r = route_intent_rules("随便看看")
    assert r.intent_label == "general"
    assert "list_wardrobe" in r.suggested_mcp_tools
