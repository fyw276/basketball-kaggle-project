"""Lightweight config and environment behavior tests."""

import os

from app.core.config import Settings
from app.core.hf_hub_env import apply_hf_hub_env_defaults, sync_hf_env_from_settings


def test_cors_origins_list_parsing():
    settings = Settings(CORS_ORIGINS="http://localhost:3000, http://127.0.0.1:5173")
    assert settings.cors_origins_list == ["http://localhost:3000", "http://127.0.0.1:5173"]


def test_settings_default_port_is_8010():
    settings = Settings()
    assert settings.PORT == 8010


def test_sync_hf_env_from_settings_sets_non_empty_values():
    previous_endpoint = os.environ.get("HF_ENDPOINT")
    previous_timeout = os.environ.get("HF_HUB_DOWNLOAD_TIMEOUT")

    try:
        os.environ.pop("HF_ENDPOINT", None)
        os.environ.pop("HF_HUB_DOWNLOAD_TIMEOUT", None)

        sync_hf_env_from_settings(
            Settings(
                HF_ENDPOINT="https://hf-mirror.com",
                HF_HUB_DOWNLOAD_TIMEOUT="300",
                HF_HOME="",
                HF_TOKEN="",
                TRANSFORMERS_CACHE="",
            )
        )

        assert os.environ.get("HF_ENDPOINT") == "https://hf-mirror.com"
        assert os.environ.get("HF_HUB_DOWNLOAD_TIMEOUT") == "300"
    finally:
        if previous_endpoint is None:
            os.environ.pop("HF_ENDPOINT", None)
        else:
            os.environ["HF_ENDPOINT"] = previous_endpoint

        if previous_timeout is None:
            os.environ.pop("HF_HUB_DOWNLOAD_TIMEOUT", None)
        else:
            os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] = previous_timeout


def test_apply_hf_hub_env_defaults_keeps_existing_timeout():
    previous_timeout = os.environ.get("HF_HUB_DOWNLOAD_TIMEOUT")

    try:
        os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] = "999"
        apply_hf_hub_env_defaults()
        assert os.environ.get("HF_HUB_DOWNLOAD_TIMEOUT") == "999"
    finally:
        if previous_timeout is None:
            os.environ.pop("HF_HUB_DOWNLOAD_TIMEOUT", None)
        else:
            os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] = previous_timeout
