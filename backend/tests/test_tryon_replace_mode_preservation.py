"""
Preservation property-based tests for try-on replace mode fix.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.6**

These tests verify that the fix does NOT break existing behavior for non-buggy inputs:
- mode="strict" or mode="balanced" requests use pipeline A (run_pipeline_a)
- mode="replace" with Bailian not configured skips Bailian and tries remote VTON or local diffusion
- mode="replace" + Bailian success saves result image and returns success response
- Fallback logic to remote VTON when Bailian fails is invoked
- Fallback logic to local diffusion when all fail and
  TRYON_V2_REPLACE_ALLOW_LOCAL_DIFFUSION=true is invoked

EXPECTED OUTCOME ON UNFIXED CODE: Tests PASS
This confirms baseline behavior to preserve. After the fix, these tests should STILL PASS.
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

# Strategy for non-replace modes (strict, balanced)
non_replace_modes = st.sampled_from(["strict", "balanced"])

# Strategy for garment categories
garment_categories = st.sampled_from(["top", "bottom", "skirt", "outfit"])

# Strategy for model genders
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
    **Property 2.1: Preservation - Non-Replace Mode Behavior**

    **Validates: Requirements 3.1**

    For any request where mode is NOT "replace" (mode="strict" or mode="balanced"),
    the fixed code SHALL produce exactly the same behavior as the original code,
    using pipeline A (run_pipeline_a) and preserving all existing error handling
    and success response logic.

    EXPECTED OUTCOME: Test PASSES on unfixed code (baseline behavior)
    After fix: Test STILL PASSES (no regression)
    """
    import app.api.tryon_v2 as tryon_v2_api

    # Track that run_pipeline_a was called
    pipeline_a_called = {"called": False, "kwargs": {}}

    def mock_run_pipeline_a(**kwargs):
        pipeline_a_called["called"] = True
        pipeline_a_called["kwargs"] = kwargs
        return {
            "status": "success",
            "message": "方案A试衣成功",
            "result_image": Image.new("RGB", (64, 64), color=(200, 200, 200)),
            "qc_scores": {"qc_aggregate_score": 0.9},
            "metadata": {"pipeline": "A"},
        }

    def mock_check_tryon_garment_has_face(_img):
        return False

    monkeypatch.setattr(tryon_v2_api, "run_pipeline_a", mock_run_pipeline_a)
    monkeypatch.setattr(
        tryon_v2_api,
        "check_tryon_garment_has_face",
        mock_check_tryon_garment_has_face,
    )

    # Prepare request
    garment_bytes = _jpeg_bytes(color=(245, 245, 245))
    person_bytes = _jpeg_bytes(size=(300, 500), color=(220, 220, 220))
    files = {
        "garment_file": ("garment.jpg", garment_bytes, "image/jpeg"),
        "person_file": ("person.jpg", person_bytes, "image/jpeg"),
    }

    # Call endpoint with non-replace mode
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

    # Assert pipeline A was called (preservation of existing behavior)
    assert pipeline_a_called[
        "called"
    ], f"REGRESSION: mode={mode} should call run_pipeline_a, but it was not called"

    # Assert success response structure is preserved
    assert (
        res.status_code == status.HTTP_200_OK
    ), f"REGRESSION: mode={mode} should return HTTP 200, got {res.status_code}"

    body = res.json()
    data = body.get("data", {})

    # Assert response structure matches expected format
    assert (
        data.get("pipeline") == "A"
    ), f"REGRESSION: mode={mode} should return pipeline='A', got {data.get('pipeline')}"
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
    **Property 2.2: Preservation - Bailian Not Configured Behavior**

    **Validates: Requirements 3.2**

    For any replace mode request where Bailian is NOT configured,
    the fixed code SHALL produce exactly the same behavior as the original code,
    skipping Bailian and attempting remote VTON or local diffusion fallback.

    EXPECTED OUTCOME: Test PASSES on unfixed code (baseline behavior)
    After fix: Test STILL PASSES (no regression)
    """
    import app.api.tryon_v2 as tryon_v2_api
    import app.services.bailian_tryon_client as bailian_client
    import app.services.tryon_v2.warp_engine as warp_engine
    import app.services.vton_remote_client as vton_client

    # Mock composition engine to fail so we exercise the Bailian fallback path
    def mock_warp_fail(*args, **kwargs):
        raise RuntimeError("composition_test_stub")

    monkeypatch.setattr(warp_engine, "tryon_top_warp", mock_warp_fail)
    monkeypatch.setattr(warp_engine, "tryon_pants_warp", mock_warp_fail)
    monkeypatch.setattr(warp_engine, "tryon_skirt_warp", mock_warp_fail)

    # Mock Bailian as NOT configured
    monkeypatch.setattr(bailian_client, "_bailian_configured", lambda: False)

    # Track that call_bailian_tryon returns None (not configured)
    async def mock_call_bailian_tryon(**kwargs):
        return None

    monkeypatch.setattr(bailian_client, "call_bailian_tryon", mock_call_bailian_tryon)

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

    def mock_check_tryon_garment_has_face(_img):
        return False

    monkeypatch.setattr(
        tryon_v2_api,
        "check_tryon_garment_has_face",
        mock_check_tryon_garment_has_face,
    )

    # Prepare request
    garment_bytes = _jpeg_bytes(color=(245, 245, 245))
    person_bytes = _jpeg_bytes(size=(300, 500), color=(220, 220, 220))
    files = {
        "garment_file": ("garment.jpg", garment_bytes, "image/jpeg"),
        "person_file": ("person.jpg", person_bytes, "image/jpeg"),
    }

    # Call endpoint with mode="replace"
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

    # Assert remote VTON was called (preservation of fallback logic)
    assert remote_vton_called[
        "called"
    ], "REGRESSION: When Bailian not configured, should call remote VTON, but it was not called"

    # Assert success response
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
    **Property 2.3: Preservation - Bailian Success Behavior**

    **Validates: Requirements 3.6**

    For any replace mode request where Bailian API call succeeds,
    the fixed code SHALL produce exactly the same behavior as the original code,
    saving the result image to storage and returning a success response with result_image_url.

    EXPECTED OUTCOME: Test PASSES on unfixed code (baseline behavior)
    After fix: Test STILL PASSES (no regression)
    """
    import app.api.tryon_v2 as tryon_v2_api
    import app.services.bailian_tryon_client as bailian_client

    # Mock Bailian as configured
    monkeypatch.setattr(bailian_client, "_bailian_configured", lambda: True)

    # Mock successful Bailian response
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

    def mock_check_tryon_garment_has_face(_img):
        return False

    monkeypatch.setattr(
        tryon_v2_api,
        "check_tryon_garment_has_face",
        mock_check_tryon_garment_has_face,
    )

    # Prepare request
    garment_bytes = _jpeg_bytes(color=(245, 245, 245))
    person_bytes = _jpeg_bytes(size=(300, 500), color=(220, 220, 220))
    files = {
        "garment_file": ("garment.jpg", garment_bytes, "image/jpeg"),
        "person_file": ("person.jpg", person_bytes, "image/jpeg"),
    }

    # Call endpoint with mode="replace"
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

    # Assert success response (preservation of success path)
    assert (
        res.status_code == status.HTTP_200_OK
    ), f"REGRESSION: Bailian success should return HTTP 200, got {res.status_code}"

    body = res.json()
    data = body.get("data", {})

    # Assert response structure is preserved
    assert (
        data.get("status") == "success"
    ), f"REGRESSION: Should return status='success', got {data.get('status')}"
    assert (
        data.get("pipeline") == "REPLACE"
    ), f"REGRESSION: Should return pipeline='REPLACE', got {data.get('pipeline')}"
    assert "result_image_url" in data, "REGRESSION: Should return result_image_url"

    # Assert result_image_url is a valid path
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
    **Property 2.4: Preservation - Fallback to Remote VTON**

    **Validates: Requirements 3.3**

    For any replace mode request where Bailian fails and remote VTON is configured,
    the fixed code SHALL continue to invoke call_remote_vton and check remote_ok
    exactly as before.

    EXPECTED OUTCOME: Test PASSES on unfixed code (baseline behavior)
    After fix: Test STILL PASSES (no regression)
    """
    import app.api.tryon_v2 as tryon_v2_api
    import app.services.bailian_tryon_client as bailian_client
    import app.services.tryon_v2.warp_engine as warp_engine
    import app.services.vton_remote_client as vton_client

    # Mock composition engine to fail so we exercise the Bailian fallback path
    def mock_warp_fail(*args, **kwargs):
        raise RuntimeError("composition_test_stub")

    monkeypatch.setattr(warp_engine, "tryon_top_warp", mock_warp_fail)
    monkeypatch.setattr(warp_engine, "tryon_pants_warp", mock_warp_fail)
    monkeypatch.setattr(warp_engine, "tryon_skirt_warp", mock_warp_fail)

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

    def mock_check_tryon_garment_has_face(_img):
        return False

    monkeypatch.setattr(
        tryon_v2_api,
        "check_tryon_garment_has_face",
        mock_check_tryon_garment_has_face,
    )

    # Prepare request
    garment_bytes = _jpeg_bytes(color=(245, 245, 245))
    person_bytes = _jpeg_bytes(size=(300, 500), color=(220, 220, 220))
    files = {
        "garment_file": ("garment.jpg", garment_bytes, "image/jpeg"),
        "person_file": ("person.jpg", person_bytes, "image/jpeg"),
    }

    # Call endpoint with mode="replace"
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

    # Assert remote VTON was called (preservation of fallback logic)
    assert remote_vton_called[
        "called"
    ], "REGRESSION: When Bailian fails, should fall back to remote VTON, but it was not called"

    # Assert success response from remote VTON
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
    **Property 2.5: Preservation - Fallback to Local Diffusion**

    **Validates: Requirements 3.4**

    When both Bailian and remote VTON fail and TRYON_V2_REPLACE_ALLOW_LOCAL_DIFFUSION=true,
    the fixed code SHALL continue to fall back to local diffusion.

    EXPECTED OUTCOME: Test PASSES on unfixed code (baseline behavior)
    After fix: Test STILL PASSES (no regression)
    """
    import app.api.tryon_v2 as tryon_v2_api
    import app.services.bailian_tryon_client as bailian_client
    import app.services.tryon_v2.warp_engine as warp_engine
    import app.services.vton_remote_client as vton_client

    # Mock composition engine to fail so we exercise the Bailian fallback path
    def mock_warp_fail(*args, **kwargs):
        raise RuntimeError("composition_test_stub")

    monkeypatch.setattr(warp_engine, "tryon_top_warp", mock_warp_fail)
    monkeypatch.setattr(warp_engine, "tryon_pants_warp", mock_warp_fail)
    monkeypatch.setattr(warp_engine, "tryon_skirt_warp", mock_warp_fail)
    from app.services.virtual_tryon import VirtualTryOnService

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

    mock_service = MagicMock(spec=VirtualTryOnService)
    mock_service.tryon_garment = mock_tryon_garment

    def mock_get_tryon_service():
        return mock_service

    # Patch get_tryon_service in the virtual_tryon module
    import app.services.virtual_tryon as virtual_tryon_module

    monkeypatch.setattr(
        virtual_tryon_module,
        "get_tryon_service",
        mock_get_tryon_service,
    )

    def mock_check_tryon_garment_has_face(_img):
        return False

    monkeypatch.setattr(
        tryon_v2_api,
        "check_tryon_garment_has_face",
        mock_check_tryon_garment_has_face,
    )

    # Prepare request
    garment_bytes = _jpeg_bytes(color=(245, 245, 245))
    person_bytes = _jpeg_bytes(size=(300, 500), color=(220, 220, 220))
    files = {
        "garment_file": ("garment.jpg", garment_bytes, "image/jpeg"),
        "person_file": ("person.jpg", person_bytes, "image/jpeg"),
    }

    # Call endpoint with mode="replace"
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

    # Assert local diffusion was called (preservation of fallback logic)
    assert local_diffusion_called["called"], (
        "REGRESSION: When Bailian and remote VTON fail with local diffusion enabled, "
        "should fall back to local diffusion, but it was not called"
    )

    # Assert success response from local diffusion
    assert (
        res.status_code == status.HTTP_200_OK
    ), f"REGRESSION: Should return HTTP 200 when local diffusion succeeds, got {res.status_code}"

    body = res.json()
    data = body.get("data", {})

    assert (
        data.get("status") == "success"
    ), f"REGRESSION: Should return status='success', got {data.get('status')}"
