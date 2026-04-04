"""Tests for Hugging Face env sync from Settings."""

import os
from types import SimpleNamespace

from app.core.hf_hub_env import apply_hf_hub_env_defaults, sync_hf_env_from_settings

_KEYS = ("HF_ENDPOINT", "HF_HUB_DOWNLOAD_TIMEOUT")


def _snapshot(keys):
    return {k: os.environ.get(k) for k in keys}


def _restore(snapshot):
    for k, v in snapshot.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def test_sync_hf_env_from_settings_writes_non_empty_values():
    snap = _snapshot(_KEYS)
    try:
        for k in _KEYS:
            os.environ.pop(k, None)
        sync_hf_env_from_settings(
            SimpleNamespace(
                HF_ENDPOINT="https://hf-mirror.com",
                HF_HOME="",
                HF_TOKEN=None,
                TRANSFORMERS_CACHE="   ",
                HF_HUB_DOWNLOAD_TIMEOUT="300",
            )
        )
        assert os.environ["HF_ENDPOINT"] == "https://hf-mirror.com"
        assert os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] == "300"
    finally:
        _restore(snap)


def test_apply_hf_hub_env_defaults_does_not_override_existing_timeout():
    snap = _snapshot(("HF_HUB_DOWNLOAD_TIMEOUT",))
    try:
        os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] = "999"
        apply_hf_hub_env_defaults()
        assert os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] == "999"
    finally:
        _restore(snap)
