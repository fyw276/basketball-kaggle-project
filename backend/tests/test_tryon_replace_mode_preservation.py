"""
Preservation tests for try-on replace mode.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.6**

These tests verify that the replace mode fix does NOT break existing behavior:
- Non-replace modes (strict/balanced) use pipeline A
- Replace mode with Bailian not configured skips Bailian
- Replace mode with Bailian success returns result
- Replace mode falls back to remote VTON when Bailian fails
- Replace mode falls back to local diffusion when all upstream engines fail

Key insight: the replace mode engine priority is [warp, bailian, remote, catvton, diffusion].
Since CatVTON is configured in this test environment, tests mock _catvton_configured()
to False to exercise the Bailian/remote/diffusion paths.
"""

from __future__ import annotations

from io import BytesIO
from unittest.mock import MagicMock

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from PIL import Image


def _jpeg_bytes(
    size: tuple[int, int] = (256, 256), color: tuple[int, int, int] = (255, 255, 255)
) -> bytes:
    """Helper to create JPEG image bytes for testing."""
    im = Image.new("RGB", size=size, color=color)
    buf = BytesIO()
    im.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


# ============================================================================
# Property-Based Test Strategies
# ============================================================================

non_replace_modes = st.sampled_from(["detail_fidelity", "blend"])
# Note: "outfit" is excluded because it requires garment_image_2 (second garment) to succeed.
garment_categories = st.sampled_from(["top", "bottom", "skirt"])
model_genders = st.sampled_from(["male", "female", "neutral"])


# ============================================================================
# Property 1: Strict/Balanced Mode Preservation
# ============================================================================


@settings(
    max_examples=10,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    mode=non_replace_modes,
    garment_category=garment_categories,
    model_gender=model_genders,
)
def test_preservation_non_replace_modes_use_pipeline_a(
    client: TestClient,
    auth_headers: dict,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    garment_category: str,
    model_gender: str,
):
    """
    For any request where mode is NOT "stable_fast" (mode="detail_fidelity" or mode="blend"),
    the code shall use CatVTON hybrid pipeline and preserve all existing
    error handling and success response logic.

    EXPECTED: PASS (baseline behavior, no regression after any changes)
    """
    import app.api.tryon_v2 as tryon_v2_api  # noqa: F401

    async def mock_call_local_catvton(**kwargs):
        return {
            "status": "success",
            "message": "CatVTON success",
            "result_image": Image.new("RGB", (64, 64), color=(200, 200, 200)),
            "metadata": {"pipeline": "CATVTON"},
        }

    class MockMeta:
        engine = "mock"

    def mock_tryon_top_warp_preserve(*args, **kwargs):
        return Image.new("RGB", (64, 64), color=(180, 180, 180)), MockMeta()

    def mock_tryon_pants_warp(*args, **kwargs):
        return Image.new("RGB", (64, 64), color=(180, 180, 180)), MockMeta()

    def mock_tryon_skirt_warp(*args, **kwargs):
        return Image.new("RGB", (64, 64), color=(180, 180, 180)), MockMeta()

    def mock_check_tryon_garment_has_face(_img):
        return False

    def mock_evaluate_input_gate(**kwargs):
        from app.services.tryon_v2.input_gate import GateResult

        return GateResult(
            passed=True,
            error_code=None,
            message="pass",
            action_hint=None,
            retryable=False,
            scores={
                "full_body_score": 0.8,
                "leg_visibility_score": 0.6,
                "front_pose_score": 0.7,
                "garment_front_score": 0.6,
                "garment_bg_clean_score": 0.8,
            },
        )

    def mock_evaluate_qc(**kwargs):
        from app.services.tryon_v2.qc import QCResult

        return QCResult(
            passed=True,
            threshold=0.6,
            scores={
                "identity_preserve_score": 0.8,
                "boundary_artifact_score": 0.9,
                "occlusion_validity_score": 0.85,
            },
            message="pass",
            action_hint="",
        )

    monkeypatch.setattr(
        "app.services.tryon_v2.catvton_engine_client.call_local_catvton", mock_call_local_catvton
    )
    monkeypatch.setattr(
        "app.services.tryon_v2.catvton_engine_client._catvton_configured", lambda: True
    )
    monkeypatch.setattr(
        "app.services.tryon_v2.warp_engine.tryon_top_warp", mock_tryon_top_warp_preserve
    )
    monkeypatch.setattr("app.services.tryon_v2.warp_engine.tryon_pants_warp", mock_tryon_pants_warp)
    monkeypatch.setattr("app.services.tryon_v2.warp_engine.tryon_skirt_warp", mock_tryon_skirt_warp)
    monkeypatch.setattr(
        "app.services.tryon_v2.pipeline_a.tryon_top_warp", mock_tryon_top_warp_preserve
    )
    monkeypatch.setattr("app.services.tryon_v2.pipeline_a.tryon_pants_warp", mock_tryon_pants_warp)
    monkeypatch.setattr("app.services.tryon_v2.pipeline_a.tryon_skirt_warp", mock_tryon_skirt_warp)
    monkeypatch.setattr(
        "app.api.tryon_v2.check_tryon_garment_has_face", mock_check_tryon_garment_has_face
    )
    monkeypatch.setattr(
        "app.services.tryon_v2.input_gate.evaluate_input_gate", mock_evaluate_input_gate
    )
    monkeypatch.setattr("app.api.tryon_v2.evaluate_input_gate", mock_evaluate_input_gate)
    monkeypatch.setattr(
        "app.services.tryon_v2.pipeline_a.evaluate_input_gate", mock_evaluate_input_gate
    )
    monkeypatch.setattr("app.services.tryon_v2.qc.evaluate_qc", mock_evaluate_qc)
    monkeypatch.setattr("app.services.tryon_v2.pipeline_a.evaluate_qc", mock_evaluate_qc)

    garment_bytes = _jpeg_bytes(color=(245, 245, 245))
    person_bytes = _jpeg_bytes(size=(300, 500), color=(220, 220, 220))
    files = {
        "garment_file": ("garment.jpg", garment_bytes, "image/jpeg"),
        "person_file": ("person.jpg", person_bytes, "image/jpeg"),
    }

    res = client.post(
        "/api/v2/tryon/garment",
        headers=auth_headers,
        files=files,
        data={
            "garment_category": garment_category,
            "mode": mode,
            "model_gender": model_gender,
        },
    )

    assert (
        res.status_code == status.HTTP_200_OK
    ), f"REGRESSION: mode={mode} should return HTTP 200, got {res.status_code}. Body: {res.text}"

    body = res.json()
    data = body.get("data", {})
    assert (
        data.get("status") == "success"
    ), f"REGRESSION: mode={mode} should return status='success', got {data.get('status')}"
    assert "result_image_url" in data, f"REGRESSION: mode={mode} should return result_image_url"


# ============================================================================
# Property 2: Bailian Not Configured Preservation
# ============================================================================


def test_preservation_bailian_not_configured_skips_bailian(
    client: TestClient,
    auth_headers: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    """
    For replace mode where Bailian is NOT configured, the code shall skip Bailian
    and attempt remote VTON or local diffusion fallback.

    EXPECTED: PASS (baseline behavior, no regression)
    """
    import app.api.tryon_v2 as tryon_v2_api  # noqa: F401
    import app.services.bailian_tryon_client as bailian_client
    import app.services.tryon_v2.catvton_engine_client as catvton_client
    import app.services.vton_remote_client as vton_client

    # Skip CatVTON to avoid subprocess
    monkeypatch.setattr(catvton_client, "_catvton_configured", lambda: False)

    # Mock Bailian as NOT configured
    monkeypatch.setattr(bailian_client, "_bailian_configured", lambda: False)

    # Mock remote VTON as configured and successful
    monkeypatch.setattr(vton_client, "_remote_url_configured", lambda: True)

    remote_vton_called = {"called": False}

    async def mock_call_remote_vton(**kwargs):
        remote_vton_called["called"] = True
        return {
            "status": "success",
            "message": "远程 VTON 成功",
            "result_image": Image.new("RGB", (64, 64), color=(180, 180, 180)),
            "metadata": {"provider": "remote_vton"},
        }

    monkeypatch.setattr(vton_client, "call_remote_vton", mock_call_remote_vton)

    monkeypatch.setattr(
        tryon_v2_api,
        "check_tryon_garment_has_face",
        lambda _img: False,
    )

    # Fail warp to exercise remote VTON path
    import app.services.tryon_v2.warp_engine as warp_engine

    def mock_warp_fail(*args, **kwargs):
        raise RuntimeError("warp_disabled_for_test")

    monkeypatch.setattr(warp_engine, "tryon_top_warp_preserve", mock_warp_fail)
    monkeypatch.setattr(warp_engine, "tryon_pants_warp", mock_warp_fail)
    monkeypatch.setattr(warp_engine, "tryon_skirt_warp", mock_warp_fail)

    garment_bytes = _jpeg_bytes(color=(245, 245, 245))
    person_bytes = _jpeg_bytes(size=(300, 500), color=(220, 220, 220))
    files = {
        "garment_file": ("garment.jpg", garment_bytes, "image/jpeg"),
        "person_file": ("person.jpg", person_bytes, "image/jpeg"),
    }

    res = client.post(
        "/api/v2/tryon/garment",
        headers=auth_headers,
        files=files,
        data={
            "garment_category": "top",
            "mode": "replace",
            "model_gender": "neutral",
        },
    )

    assert remote_vton_called[
        "called"
    ], "REGRESSION: When Bailian not configured, should call remote VTON"
    assert (
        res.status_code == status.HTTP_200_OK
    ), f"REGRESSION: Should return HTTP 200 when remote VTON succeeds, got {res.status_code}"

    body = res.json()
    data = body.get("data", {})
    assert (
        data.get("status") == "success"
    ), f"REGRESSION: Should return status='success', got {data.get('status')}"
    assert "result_image_url" in data, "REGRESSION: Should return result_image_url"


# ============================================================================
# Property 3: Bailian Success Preservation
# ============================================================================


@settings(
    max_examples=10,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    garment_category=garment_categories,
    model_gender=model_genders,
)
def test_preservation_bailian_success_returns_result(
    client: TestClient,
    auth_headers: dict,
    monkeypatch: pytest.MonkeyPatch,
    garment_category: str,
    model_gender: str,
):
    """
    For replace mode where Bailian API call succeeds, the code shall save
    the result image to storage and return a success response.

    EXPECTED: PASS (baseline behavior, no regression)

    CatVTON must be skipped via mock so Bailian is the first engine tried.
    """
    import app.api.tryon_v2 as tryon_v2_api  # noqa: F401
    import app.services.bailian_tryon_client as bailian_client
    import app.services.tryon_v2.catvton_engine_client as catvton_client

    # Skip CatVTON so Bailian is the first engine in the priority chain
    monkeypatch.setattr(catvton_client, "_catvton_configured", lambda: False)

    # Mock Bailian as configured
    monkeypatch.setattr(bailian_client, "_bailian_configured", lambda: True)

    async def mock_call_bailian_tryon(**kwargs):
        return {
            "status": "success",
            "message": "百炼试衣完成",
            "result_image": Image.new("RGB", (64, 64), color=(150, 150, 150)),
            "metadata": {
                "model": "wanx2.1-imageedit",
                "function": "description_edit_with_mask",
                "provider": "dashscope_bailian",
            },
        }

    monkeypatch.setattr(bailian_client, "call_bailian_tryon", mock_call_bailian_tryon)

    monkeypatch.setattr(
        tryon_v2_api,
        "check_tryon_garment_has_face",
        lambda _img: False,
    )

    # Fail warp to ensure bailian result is used
    import app.services.tryon_v2.warp_engine as warp_engine

    def mock_warp_fail(*args, **kwargs):
        raise RuntimeError("warp_disabled_for_test")

    monkeypatch.setattr(warp_engine, "tryon_top_warp_preserve", mock_warp_fail)
    monkeypatch.setattr(warp_engine, "tryon_pants_warp", mock_warp_fail)
    monkeypatch.setattr(warp_engine, "tryon_skirt_warp", mock_warp_fail)

    garment_bytes = _jpeg_bytes(color=(245, 245, 245))
    person_bytes = _jpeg_bytes(size=(300, 500), color=(220, 220, 220))
    files = {
        "garment_file": ("garment.jpg", garment_bytes, "image/jpeg"),
        "person_file": ("person.jpg", person_bytes, "image/jpeg"),
    }

    res = client.post(
        "/api/v2/tryon/garment",
        headers=auth_headers,
        files=files,
        data={
            "garment_category": garment_category,
            "mode": "replace",
            "model_gender": model_gender,
        },
    )

    assert res.status_code == status.HTTP_200_OK, (
        f"REGRESSION: Bailian success should return HTTP 200, got {res.status_code}. "
        f"Body: {res.text}"
    )

    body = res.json()
    data = body.get("data", {})
    assert (
        data.get("status") == "success"
    ), f"REGRESSION: Should return status='success', got {data.get('status')}"
    assert (
        data.get("pipeline") == "REPLACE"
    ), f"REGRESSION: Should return pipeline='REPLACE', got {data.get('pipeline')}"
    assert "result_image_url" in data, "REGRESSION: Should return result_image_url"

    result_url = data.get("result_image_url", "")
    assert result_url.startswith(
        "/uploads/"
    ), f"REGRESSION: result_image_url should start with '/uploads/', got {result_url}"


# ============================================================================
# Property 4: Fallback Logic Preservation
# ============================================================================


def test_preservation_fallback_to_remote_vton_when_bailian_fails(
    client: TestClient,
    auth_headers: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    """
    When Bailian fails and remote VTON is configured, the code shall invoke
    call_remote_vton and return the remote VTON result.

    EXPECTED: PASS (baseline behavior, no regression)
    """
    import app.api.tryon_v2 as tryon_v2_api  # noqa: F401
    import app.services.bailian_tryon_client as bailian_client
    import app.services.tryon_v2.catvton_engine_client as catvton_client
    import app.services.vton_remote_client as vton_client

    # Skip CatVTON
    monkeypatch.setattr(catvton_client, "_catvton_configured", lambda: False)

    # Mock Bailian as configured but failing
    monkeypatch.setattr(bailian_client, "_bailian_configured", lambda: True)

    async def mock_call_bailian_tryon(**kwargs):
        return {
            "status": "error",
            "message": "百炼失败",
            "result_image": None,
            "metadata": {"reason": "dashscope_error"},
        }

    monkeypatch.setattr(bailian_client, "call_bailian_tryon", mock_call_bailian_tryon)

    # Mock remote VTON as configured and successful
    monkeypatch.setattr(vton_client, "_remote_url_configured", lambda: True)

    remote_vton_called = {"called": False}

    async def mock_call_remote_vton(**kwargs):
        remote_vton_called["called"] = True
        return {
            "status": "success",
            "message": "远程 VTON 成功",
            "result_image": Image.new("RGB", (64, 64), color=(170, 170, 170)),
            "metadata": {"provider": "remote_vton"},
        }

    monkeypatch.setattr(vton_client, "call_remote_vton", mock_call_remote_vton)

    monkeypatch.setattr(
        tryon_v2_api,
        "check_tryon_garment_has_face",
        lambda _img: False,
    )

    # Fail warp
    import app.services.tryon_v2.warp_engine as warp_engine

    def mock_warp_fail(*args, **kwargs):
        raise RuntimeError("warp_disabled_for_test")

    monkeypatch.setattr(warp_engine, "tryon_top_warp_preserve", mock_warp_fail)
    monkeypatch.setattr(warp_engine, "tryon_pants_warp", mock_warp_fail)
    monkeypatch.setattr(warp_engine, "tryon_skirt_warp", mock_warp_fail)

    garment_bytes = _jpeg_bytes(color=(245, 245, 245))
    person_bytes = _jpeg_bytes(size=(300, 500), color=(220, 220, 220))
    files = {
        "garment_file": ("garment.jpg", garment_bytes, "image/jpeg"),
        "person_file": ("person.jpg", person_bytes, "image/jpeg"),
    }

    res = client.post(
        "/api/v2/tryon/garment",
        headers=auth_headers,
        files=files,
        data={
            "garment_category": "top",
            "mode": "replace",
            "model_gender": "neutral",
        },
    )

    assert remote_vton_called[
        "called"
    ], "REGRESSION: When Bailian fails, should fall back to remote VTON, but it was not called"
    assert (
        res.status_code == status.HTTP_200_OK
    ), f"REGRESSION: Should return HTTP 200 when remote VTON succeeds, got {res.status_code}"

    body = res.json()
    data = body.get("data", {})
    assert (
        data.get("status") == "success"
    ), f"REGRESSION: Should return status='success', got {data.get('status')}"


def test_preservation_fallback_to_local_diffusion_when_all_fail(
    client: TestClient,
    auth_headers: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    """
    When both Bailian and remote VTON fail and TRYON_V2_REPLACE_ALLOW_LOCAL_DIFFUSION=true,
    the code shall fall back to local diffusion.

    EXPECTED: PASS (baseline behavior, no regression)
    """
    import app.api.tryon_v2 as tryon_v2_api  # noqa: F401
    import app.services.bailian_tryon_client as bailian_client
    import app.services.tryon_v2.catvton_engine_client as catvton_client
    import app.services.vton_remote_client as vton_client

    # Skip CatVTON
    monkeypatch.setattr(catvton_client, "_catvton_configured", lambda: False)

    # Mock Bailian as configured but failing
    monkeypatch.setattr(bailian_client, "_bailian_configured", lambda: True)

    async def mock_call_bailian_tryon(**kwargs):
        return {
            "status": "error",
            "message": "百炼失败",
            "result_image": None,
            "metadata": {"reason": "dashscope_error"},
        }

    monkeypatch.setattr(bailian_client, "call_bailian_tryon", mock_call_bailian_tryon)

    # Mock remote VTON as configured but failing
    monkeypatch.setattr(vton_client, "_remote_url_configured", lambda: True)

    async def mock_call_remote_vton(**kwargs):
        return {
            "status": "error",
            "message": "远程 VTON 失败",
            "result_image": None,
            "metadata": {"reason": "remote_error"},
        }

    monkeypatch.setattr(vton_client, "call_remote_vton", mock_call_remote_vton)

    # Enable local diffusion fallback
    monkeypatch.setattr(
        tryon_v2_api.settings,
        "TRYON_V2_REPLACE_ALLOW_LOCAL_DIFFUSION",
        True,
    )

    # Mock local diffusion service
    local_diffusion_called = {"called": False}

    def mock_tryon_garment(**kwargs):
        local_diffusion_called["called"] = True
        return {
            "status": "success",
            "message": "本地 diffusion 成功",
            "result_image": Image.new("RGB", (64, 64), color=(160, 160, 160)),
            "metadata": {"provider": "local_diffusion"},
        }

    from app.services.virtual_tryon import VirtualTryOnService

    mock_service = MagicMock(spec=VirtualTryOnService)
    mock_service.tryon_garment = mock_tryon_garment

    def mock_get_tryon_service():
        return mock_service

    import app.services.virtual_tryon as virtual_tryon_module

    monkeypatch.setattr(
        virtual_tryon_module,
        "get_tryon_service",
        mock_get_tryon_service,
    )

    monkeypatch.setattr(
        tryon_v2_api,
        "check_tryon_garment_has_face",
        lambda _img: False,
    )

    # Fail warp
    import app.services.tryon_v2.warp_engine as warp_engine

    def mock_warp_fail(*args, **kwargs):
        raise RuntimeError("warp_disabled_for_test")

    monkeypatch.setattr(warp_engine, "tryon_top_warp_preserve", mock_warp_fail)
    monkeypatch.setattr(warp_engine, "tryon_pants_warp", mock_warp_fail)
    monkeypatch.setattr(warp_engine, "tryon_skirt_warp", mock_warp_fail)

    garment_bytes = _jpeg_bytes(color=(245, 245, 245))
    person_bytes = _jpeg_bytes(size=(300, 500), color=(220, 220, 220))
    files = {
        "garment_file": ("garment.jpg", garment_bytes, "image/jpeg"),
        "person_file": ("person.jpg", person_bytes, "image/jpeg"),
    }

    res = client.post(
        "/api/v2/tryon/garment",
        headers=auth_headers,
        files=files,
        data={
            "garment_category": "top",
            "mode": "replace",
            "model_gender": "neutral",
        },
    )

    assert local_diffusion_called["called"], (
        "REGRESSION: When Bailian and remote VTON fail with local diffusion enabled, "
        "should fall back to local diffusion, but it was not called"
    )
    assert (
        res.status_code == status.HTTP_200_OK
    ), f"REGRESSION: Should return HTTP 200 when local diffusion succeeds, got {res.status_code}"

    body = res.json()
    data = body.get("data", {})
    assert (
        data.get("status") == "success"
    ), f"REGRESSION: Should return status='success', got {data.get('status')}"
