"""API contract tests for try-on v2 pipeline A endpoint."""

from __future__ import annotations

from io import BytesIO

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from PIL import Image


def _jpeg_bytes(
    size: tuple[int, int] = (256, 256), color: tuple[int, int, int] = (255, 255, 255)
) -> bytes:
    im = Image.new("RGB", size=size, color=color)
    buf = BytesIO()
    im.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def test_tryon_v2_requires_auth(client: TestClient):
    res = client.post("/api/v2/tryon/pants")
    assert res.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)


def test_tryon_v2_returns_structured_gate_error(
    client: TestClient, auth_headers: dict, monkeypatch: pytest.MonkeyPatch
):
    import app.api.tryon_v2 as tryon_v2_api

    def _stub_run_pipeline_a(**kwargs):
        return {
            "status": "error",
            "message": "人物图未满足全身要求，请上传完整站立照片。",
            "error_code": "TRYON_V2_PERSON_NOT_FULL_BODY",
            "retryable": False,
            "action_hint": "请确保头顶到脚部完整入镜。",
            "qc_scores": {
                "full_body_score": 0.2,
                "leg_visibility_score": 0.8,
                "front_pose_score": 0.9,
                "garment_front_score": 0.95,
            },
        }

    monkeypatch.setattr(tryon_v2_api, "run_pipeline_a", _stub_run_pipeline_a)

    garment_bytes = _jpeg_bytes(color=(245, 245, 245))
    person_bytes = _jpeg_bytes(size=(220, 220), color=(220, 220, 220))
    files = {
        "garment_file": ("garment.jpg", garment_bytes, "image/jpeg"),
        "person_file": ("person.jpg", person_bytes, "image/jpeg"),
    }

    res = client.post(
        "/api/v2/tryon/pants",
        headers=auth_headers,
        files=files,
        data={"garment_category": "bottom", "mode": "blend"},
    )

    assert res.status_code == status.HTTP_400_BAD_REQUEST
    body = res.json()
    err = body.get("error") if isinstance(body, dict) else None
    assert isinstance(err, dict)
    assert err.get("error_code") == "TRYON_V2_PERSON_NOT_FULL_BODY"
    assert err.get("retryable") is False
    qc_scores = err.get("qc_scores")
    if qc_scores is None and isinstance(err.get("details"), dict):
        qc_scores = err["details"].get("qc_scores")
    assert isinstance(qc_scores, dict)


def test_tryon_v2_returns_structured_qc_error(
    client: TestClient, auth_headers: dict, monkeypatch: pytest.MonkeyPatch
):
    import app.api.tryon_v2 as tryon_v2_api

    def _stub_run_pipeline_a(**kwargs):
        return {
            "status": "error",
            "message": "输出未通过方案A质量评估",
            "error_code": "TRYON_V2_QC_NOT_PASSED",
            "retryable": False,
            "action_hint": "请更换清晰的人像与商品图。",
            "qc_scores": {
                "full_body_score": 0.95,
                "identity_preserve_score": 0.2,
                "boundary_artifact_score": 0.3,
                "occlusion_validity_score": 0.25,
                "qc_aggregate_score": 0.25,
            },
        }

    monkeypatch.setattr(tryon_v2_api, "run_pipeline_a", _stub_run_pipeline_a)

    garment_bytes = _jpeg_bytes(color=(245, 245, 245))
    person_bytes = _jpeg_bytes(size=(300, 500), color=(220, 220, 220))
    files = {
        "garment_file": ("garment.jpg", garment_bytes, "image/jpeg"),
        "person_file": ("person.jpg", person_bytes, "image/jpeg"),
    }

    res = client.post(
        "/api/v2/tryon/pants",
        headers=auth_headers,
        files=files,
        data={"garment_category": "bottom", "mode": "blend"},
    )

    assert res.status_code == status.HTTP_400_BAD_REQUEST
    body = res.json()
    err = body.get("error") if isinstance(body, dict) else None
    assert isinstance(err, dict)
    assert err.get("error_code") == "TRYON_V2_QC_NOT_PASSED"
    assert err.get("retryable") is False


def test_tryon_v2_passes_qc_threshold_to_pipeline(
    client: TestClient, auth_headers: dict, monkeypatch: pytest.MonkeyPatch
):
    import app.api.tryon_v2 as tryon_v2_api

    captured: dict[str, float] = {}

    def _stub_run_pipeline_a(**kwargs):
        captured["qc_threshold"] = float(kwargs.get("qc_threshold", 0))
        return {
            "status": "success",
            "message": "方案A试衣成功",
            "result_image": Image.new("RGB", (64, 64), color=(200, 200, 200)),
            "qc_scores": {"qc_aggregate_score": 0.9},
            "metadata": {"pipeline": "A"},
        }

    monkeypatch.setattr(tryon_v2_api, "run_pipeline_a", _stub_run_pipeline_a)
    monkeypatch.setattr(tryon_v2_api.settings, "TRYON_V2_QC_THRESHOLD", 0.73)

    garment_bytes = _jpeg_bytes(color=(245, 245, 245))
    person_bytes = _jpeg_bytes(size=(300, 500), color=(220, 220, 220))
    files = {
        "garment_file": ("garment.jpg", garment_bytes, "image/jpeg"),
        "person_file": ("person.jpg", person_bytes, "image/jpeg"),
    }

    res = client.post(
        "/api/v2/tryon/pants",
        headers=auth_headers,
        files=files,
        data={"garment_category": "bottom", "mode": "blend"},
    )
    assert res.status_code == status.HTTP_200_OK
    assert captured["qc_threshold"] == 0.73


def test_tryon_v2_success_returns_pipeline_a_result(
    client: TestClient, auth_headers: dict, monkeypatch: pytest.MonkeyPatch
):
    import app.api.tryon_v2 as tryon_v2_api

    def _stub_run_pipeline_a(**kwargs):
        return {
            "status": "success",
            "message": "方案A试衣成功",
            "result_image": Image.new("RGB", (80, 80), color=(200, 200, 200)),
            "qc_scores": {
                "full_body_score": 0.95,
                "leg_visibility_score": 0.92,
                "front_pose_score": 0.88,
                "garment_front_score": 0.9,
            },
            "metadata": {"pipeline": "A", "strict_identity": True},
        }

    monkeypatch.setattr(tryon_v2_api, "run_pipeline_a", _stub_run_pipeline_a)

    garment_bytes = _jpeg_bytes(color=(245, 245, 245))
    person_bytes = _jpeg_bytes(size=(300, 500), color=(220, 220, 220))
    files = {
        "garment_file": ("garment.jpg", garment_bytes, "image/jpeg"),
        "person_file": ("person.jpg", person_bytes, "image/jpeg"),
    }

    res = client.post(
        "/api/v2/tryon/pants",
        headers=auth_headers,
        files=files,
        data={"garment_category": "bottom", "mode": "blend"},
    )

    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    data = body.get("data") if isinstance(body, dict) else None
    assert isinstance(data, dict)
    assert data.get("pipeline") == "A"
    url = data.get("result_image_url")
    assert isinstance(url, str) and url.startswith("/uploads/")
    assert "\\" not in url


def test_tryon_v2_validate_input_returns_fail_with_scores(
    client: TestClient, auth_headers: dict, monkeypatch: pytest.MonkeyPatch
):
    import app.api.tryon_v2 as tryon_v2_api

    def _stub_check_tryon_garment_has_face(_img):
        return False

    monkeypatch.setattr(
        tryon_v2_api,
        "check_tryon_garment_has_face",
        _stub_check_tryon_garment_has_face,
    )

    garment_bytes = _jpeg_bytes(color=(245, 245, 245))
    person_bytes = _jpeg_bytes(size=(180, 180), color=(220, 220, 220))
    files = {
        "garment_file": ("garment.jpg", garment_bytes, "image/jpeg"),
        "person_file": ("person.jpg", person_bytes, "image/jpeg"),
    }

    res = client.post(
        "/api/v2/tryon/validate-input",
        headers=auth_headers,
        files=files,
        data={"garment_category": "bottom", "mode": "strict"},
    )

    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    data = body.get("data") if isinstance(body, dict) else None
    assert isinstance(data, dict)
    assert data.get("status") in {"pass", "fail"}
    assert isinstance(data.get("qc_scores"), dict)
    assert isinstance(data.get("thresholds"), dict)


def test_tryon_v2_capabilities_exposes_thresholds(client: TestClient, auth_headers: dict):
    res = client.get("/api/v2/tryon/capabilities", headers=auth_headers)
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    data = body.get("data") if isinstance(body, dict) else None
    assert isinstance(data, dict)
    assert data.get("pipeline_default") == "A"
    assert isinstance(data.get("modes"), list)
    assert isinstance(data.get("thresholds"), dict)


def test_tryon_v2_capabilities_reads_configured_thresholds(
    client: TestClient, auth_headers: dict, monkeypatch: pytest.MonkeyPatch
):
    import app.api.tryon_v2 as tryon_v2_api

    monkeypatch.setattr(tryon_v2_api.settings, "TRYON_V2_MIN_FULL_BODY_SCORE", 0.77)
    monkeypatch.setattr(tryon_v2_api.settings, "TRYON_V2_MIN_LEG_VISIBILITY_SCORE", 0.66)
    monkeypatch.setattr(tryon_v2_api.settings, "TRYON_V2_MIN_FRONT_POSE_SCORE", 0.55)
    monkeypatch.setattr(tryon_v2_api.settings, "TRYON_V2_MIN_GARMENT_FRONT_SCORE", 0.44)
    monkeypatch.setattr(tryon_v2_api.settings, "TRYON_V2_QC_THRESHOLD", 0.69)

    res = client.get("/api/v2/tryon/capabilities", headers=auth_headers)
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    data = body.get("data") if isinstance(body, dict) else None
    assert isinstance(data, dict)
    thresholds = data.get("thresholds")
    assert isinstance(thresholds, dict)
    assert thresholds.get("full_body") == 0.77
    assert thresholds.get("leg_visibility") == 0.66
    assert thresholds.get("front_pose") == 0.55
    assert thresholds.get("garment_front") == 0.44
    assert thresholds.get("qc_threshold") == 0.69
