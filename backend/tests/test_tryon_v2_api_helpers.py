from __future__ import annotations

from PIL import Image

from app.api.tryon_v2_helpers import (
    _load_uploads_url,
    _make_tryon_error_detail,
    _normalize_tryon_mode,
)


def test_normalize_tryon_mode_maps_legacy_aliases():
    assert _normalize_tryon_mode("detail") == "detail_fidelity"
    assert _normalize_tryon_mode("mixed") == "hybrid"
    assert _normalize_tryon_mode("fast") == "stable_fast"
    assert _normalize_tryon_mode("strict") == "detail_fidelity"
    assert _normalize_tryon_mode("balanced") == "hybrid"
    assert _normalize_tryon_mode("detail_fidelity") == "detail_fidelity"


def test_make_tryon_error_detail_returns_structured_payload():
    detail = _make_tryon_error_detail(
        "TRYON_GARMENT_CONTAINS_MODEL",
        "Please use a product photo",
        "Use a clean garment image without a model face.",
    )

    assert detail["message"] == "Please use a product photo"
    assert detail["error_code"] == "TRYON_GARMENT_CONTAINS_MODEL"
    assert detail["retryable"] is False
    assert detail["action_hint"] == "Use a clean garment image without a model face."


def test_load_uploads_url_reads_local_uploads_file(tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads" / "demo"
    upload_dir.mkdir(parents=True)
    target = upload_dir / "test.jpg"
    Image.new("RGB", (12, 16), "red").save(target)

    monkeypatch.setattr("app.api.tryon_v2_helpers.settings.UPLOAD_DIR", str(tmp_path))

    img = _load_uploads_url("/uploads/demo/test.jpg")
    assert img is not None
    assert img.size == (12, 16)
