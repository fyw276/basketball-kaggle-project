"""Test configuration and fixtures for tests_lite."""

from unittest.mock import MagicMock, Mock

import pytest

from app.core.config import Settings


@pytest.fixture
def mock_settings():
    """Create a mock Settings object for testing.

    使用 Mock 而不是直接修改 Pydantic Settings 对象的属性，
    因为 Pydantic v2 Settings 对象在初始化后不允许修改属性。
    """
    settings = Mock(spec=Settings)
    settings.FINETUNED_INFER_ENABLED = False
    settings.FINETUNED_INFER_API_BASE_URL = ""
    settings.FINETUNED_INFER_API_PATH = "/infer/fashion"
    settings.FINETUNED_INFER_API_KEY = ""
    settings.FINETUNED_INFER_TIMEOUT_MS = 3000
    return settings


@pytest.fixture
def monkeypatch_settings(monkeypatch, mock_settings):
    """Fixture to patch settings in any module.

    Usage:
      def test_something(monkeypatch_settings):
          monkeypatch_settings(some_module, mock_settings)
    """

    def patcher(module, settings_obj=None):
        if settings_obj is None:
            settings_obj = mock_settings
        monkeypatch.setattr(module, "settings", settings_obj)
        return settings_obj

    return patcher
