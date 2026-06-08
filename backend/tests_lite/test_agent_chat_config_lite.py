"""Lite tests for Agent LLM configuration diagnostics."""

from app.api.agent_chat import _agent_llm_config_error


def test_agent_llm_config_requires_api_base():
    error = _agent_llm_config_error("", "")
    assert error is not None
    assert "AI_RECOMMENDER_API_BASE_URL" in error


def test_agent_llm_config_requires_http_url():
    error = _agent_llm_config_error("localhost:11434/v1", "key")
    assert error is not None
    assert "http://" in error


def test_agent_llm_config_requires_api_key():
    error = _agent_llm_config_error("http://localhost:11434/v1", "")
    assert error is not None
    assert "AI_RECOMMENDER_API_KEY" in error


def test_agent_llm_config_accepts_complete_configuration():
    assert _agent_llm_config_error("https://example.com/v1", "key") is None
