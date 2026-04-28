"""
Lightweight unit tests for tryon_v2/catvton_engine_client.py.
Tests the logic that does NOT require a GPU or CatVTON installation.

Covers:
- _catvton_category_hint: garment category string mapping
- _catvton_configured: configuration checking
- _get_catvton_path: path resolution
- get_catvton_status: status reporting
"""

from __future__ import annotations

from unittest.mock import patch

import pytest


class TestCatvtonCategoryHint:
    """Tests for _catvton_category_hint."""

    def test_upper_categories(self):
        from app.services.tryon_v2.catvton_engine_client import _catvton_category_hint

        assert _catvton_category_hint("上装") == "upper"
        assert _catvton_category_hint("上衣") == "upper"
        assert _catvton_category_hint("外套") == "upper"
        assert _catvton_category_hint("top") == "upper"
        assert _catvton_category_hint("T恤") == "upper"
        assert _catvton_category_hint("毛衣") == "upper"

    def test_lower_categories(self):
        from app.services.tryon_v2.catvton_engine_client import _catvton_category_hint

        assert _catvton_category_hint("下装") == "lower"
        assert _catvton_category_hint("裤") == "lower"
        assert _catvton_category_hint("裤装") == "lower"
        assert _catvton_category_hint("bottom") == "lower"
        assert _catvton_category_hint("短裤") == "lower"

    def test_overall_categories(self):
        from app.services.tryon_v2.catvton_engine_client import _catvton_category_hint

        assert _catvton_category_hint("裙") == "overall"
        assert _catvton_category_hint("连衣裙") == "overall"
        assert _catvton_category_hint("dress") == "overall"

    def test_none_and_empty(self):
        from app.services.tryon_v2.catvton_engine_client import _catvton_category_hint

        assert _catvton_category_hint(None) == "upper"
        assert _catvton_category_hint("") == "upper"
        assert _catvton_category_hint("   ") == "upper"


class TestCatvtonConfigured:
    """Tests for _catvton_configured."""

    def test_disabled_when_flag_false(self):
        with patch("app.services.tryon_v2.catvton_engine_client.settings") as mock_settings:
            mock_settings.CATVTON_ENABLED = False
            from app.services.tryon_v2.catvton_engine_client import _catvton_configured

            assert _catvton_configured() is False

    def test_false_when_path_empty(self):
        with patch("app.services.tryon_v2.catvton_engine_client.settings") as mock_settings:
            mock_settings.CATVTON_ENABLED = True
            mock_settings.CATVTON_PATH = ""
            from app.services.tryon_v2.catvton_engine_client import _catvton_configured

            assert _catvton_configured() is False

    def test_false_when_path_not_exist(self, tmp_path: pytest.TempPathFactory):
        with patch("app.services.tryon_v2.catvton_engine_client.settings") as mock_settings:
            mock_settings.CATVTON_ENABLED = True
            mock_settings.CATVTON_PATH = str(tmp_path / "nonexistent_catvton")
            from app.services.tryon_v2.catvton_engine_client import _catvton_configured

            assert _catvton_configured() is False


class TestCatvtonStatus:
    """Tests for get_catvton_status and log_catvton_status."""

    def test_get_catvton_status_returns_dict(self):
        with patch("app.services.tryon_v2.catvton_engine_client.settings") as mock_settings:
            mock_settings.CATVTON_ENABLED = False
            mock_settings.CATVTON_PATH = ""
            mock_settings.CATVTON_WIDTH = 768
            mock_settings.CATVTON_HEIGHT = 1024
            mock_settings.CATVTON_STEPS = 50
            mock_settings.CATVTON_GUIDANCE = 2.5
            mock_settings.CATVTON_REPAINT = True
            mock_settings.CATVTON_TIMEOUT_SECONDS = 2400
            mock_settings.CATVTON_MIXED_PRECISION = "bf16"
            mock_settings.CATVTON_FORCE_FP16 = False
            mock_settings.CATVTON_ENABLE_VAE_SLICING = True
            mock_settings.CATVTON_ENABLE_XFORMERS = True
            mock_settings.CATVTON_CPU_OFFLOAD = False
            mock_settings.CATVTON_LOW_VRAM_MODE = False
            mock_settings.CATVTON_ENABLE_GC_AFTER_INFER = True
            mock_settings.CATVTON_DEBUG_DIR = ""

            from app.services.tryon_v2.catvton_engine_client import get_catvton_status

            status = get_catvton_status()
            assert isinstance(status, dict)
            assert "enabled" in status
            assert "configured" in status
            assert "path" in status
            assert "width" in status
            assert "height" in status
            assert "steps" in status
            assert "precision" in status
            assert status["enabled"] is False
            assert status["width"] == 768
            assert status["height"] == 1024

    def test_log_catvton_status_returns_string(self):
        with patch("app.services.tryon_v2.catvton_engine_client.settings") as mock_settings:
            mock_settings.CATVTON_ENABLED = False
            mock_settings.CATVTON_PATH = ""
            mock_settings.CATVTON_WIDTH = 768
            mock_settings.CATVTON_HEIGHT = 1024
            mock_settings.CATVTON_STEPS = 50
            mock_settings.CATVTON_GUIDANCE = 2.5
            mock_settings.CATVTON_REPAINT = True
            mock_settings.CATVTON_TIMEOUT_SECONDS = 2400
            mock_settings.CATVTON_MIXED_PRECISION = "bf16"
            mock_settings.CATVTON_FORCE_FP16 = False
            mock_settings.CATVTON_ENABLE_VAE_SLICING = True
            mock_settings.CATVTON_ENABLE_XFORMERS = True
            mock_settings.CATVTON_CPU_OFFLOAD = False
            mock_settings.CATVTON_LOW_VRAM_MODE = False
            mock_settings.CATVTON_ENABLE_GC_AFTER_INFER = True
            mock_settings.CATVTON_DEBUG_DIR = ""

            from app.services.tryon_v2.catvton_engine_client import log_catvton_status

            summary = log_catvton_status("[TEST]")
            assert isinstance(summary, str)
            assert "CatVTON" in summary
