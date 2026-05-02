"""
Bug condition exploration property-based tests for try-on replace mode.

**Validates: Requirements 2.2, 2.3, 2.4, 2.5**

This test validates that when mode="replace" and Bailian is configured but API calls fail,
the error response includes complete bailian_diag and specific action_hints.

Key insight: the replace mode engine priority is [catvton, bailian, remote, warp, diffusion].
Since CatVTON is configured in this test environment, CatVTON runs first.
To test the Bailian diagnostics path, we mock _catvton_configured() to False so CatVTON
is skipped, letting Bailian be the first attempted engine.
"""

from __future__ import annotations

from io import BytesIO
from typing import Any

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
# Property-Based Test Strategies for Bailian Error Responses
# ============================================================================


@st.composite
def bailian_error_invalid_api_key(draw):
    """Generate Bailian error response for invalid API key scenario."""
    return {
        "status": "error",
        "message": "InvalidApiKey",
        "result_image": None,
        "metadata": {
            "reason": "dashscope_http",
            "error_type": "api_error",
            "code": "InvalidApiKey",
            "status_code": 401,
            "specific_hint": "API key 无效或已过期",
            "model": "wanx2.1-imageedit",
            "function": "description_edit_with_mask",
        },
    }


@st.composite
def bailian_error_quota_exceeded(draw):
    """Generate Bailian error response for quota exceeded scenario."""
    return {
        "status": "error",
        "message": "QuotaExceeded",
        "result_image": None,
        "metadata": {
            "reason": "dashscope_http",
            "error_type": "api_error",
            "code": "QuotaExceeded",
            "status_code": 429,
            "specific_hint": "API 额度不足或超出限制",
            "model": "wanx2.1-imageedit",
            "function": "description_edit_with_mask",
        },
    }


@st.composite
def bailian_error_network_timeout(draw):
    """Generate Bailian error response for network timeout scenario."""
    return {
        "status": "error",
        "message": "网络超时",
        "result_image": None,
        "metadata": {
            "reason": "dashscope_exception",
            "error_type": "TimeoutException",
            "exception_message": "Request timed out",
            "specific_hint": "网络超时",
            "model": "wanx2.1-imageedit",
            "function": "description_edit_with_mask",
        },
    }


@st.composite
def bailian_error_success_no_image(draw):
    """Generate Bailian response for success but no result_image scenario."""
    return {
        "status": "success",
        "message": "百炼试衣完成",
        "result_image": None,
        "metadata": {
            "reason": "dashscope_no_url",
            "model": "wanx2.1-imageedit",
            "function": "description_edit_with_mask",
        },
    }


# Combined strategy that generates all error scenarios
bailian_error_responses = st.one_of(
    bailian_error_invalid_api_key(),
    bailian_error_quota_exceeded(),
    bailian_error_network_timeout(),
    bailian_error_success_no_image(),
)


# ============================================================================
# Bug Condition Exploration Property Test
# ============================================================================


@settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(error_response=bailian_error_responses)
def test_bug_condition_bailian_error_diagnostics_missing(
    client: TestClient,
    auth_headers: dict,
    monkeypatch: pytest.MonkeyPatch,
    error_response: dict[str, Any],
):
    """
    **Property: Bailian Error Diagnostics Completeness**

    For any replace mode request where CatVTON is skipped (not configured) and
    Bailian API call fails, the error response should include complete bailian_diag
    with all available fields and specific action_hints (not generic ones).

    We skip CatVTON by mocking _catvton_configured() to False so Bailian is the
    first attempted engine.
    """
    import app.api.tryon_v2 as tryon_v2_api
    import app.services.bailian_tryon_client as bailian_client
    import app.services.tryon_v2.catvton_engine_client as catvton_client
    import app.services.vton_remote_client as vton_client

    # Skip CatVTON so Bailian is the first attempted engine in priority.
    # This lets us test Bailian error diagnostics without CatVTON subprocess.
    monkeypatch.setattr(catvton_client, "_catvton_configured", lambda: False)

    # Mock Bailian as configured
    monkeypatch.setattr(bailian_client, "_bailian_configured", lambda: True)

    # Mock call_bailian_tryon to return the error response
    async def mock_call_bailian_tryon(**kwargs):
        return error_response

    monkeypatch.setattr(bailian_client, "call_bailian_tryon", mock_call_bailian_tryon)

    # Mock remote VTON as not configured (so we move to warp fallback)
    monkeypatch.setattr(vton_client, "_remote_url_configured", lambda: False)

    # Mock check_tryon_garment_has_face to return False
    monkeypatch.setattr(
        tryon_v2_api,
        "check_tryon_garment_has_face",
        lambda _img: False,
    )

    # Mock warp to fail (so we get the 503 "all engines failed" response)
    import app.services.tryon_v2.warp_engine as warp_engine

    def mock_warp_fail(*args, **kwargs):
        raise RuntimeError("warp_disabled_for_test")

    monkeypatch.setattr(warp_engine, "tryon_top_warp_preserve", mock_warp_fail)
    monkeypatch.setattr(warp_engine, "tryon_pants_warp", mock_warp_fail)
    monkeypatch.setattr(warp_engine, "tryon_skirt_warp", mock_warp_fail)

    # Prepare request
    garment_bytes = _jpeg_bytes(color=(245, 245, 245))
    person_bytes = _jpeg_bytes(size=(300, 500), color=(220, 220, 220))
    files = {
        "garment_file": ("garment.jpg", garment_bytes, "image/jpeg"),
        "person_file": ("person.jpg", person_bytes, "image/jpeg"),
    }

    # Call the endpoint with mode="replace"
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

    # Assert HTTP 503 error
    assert (
        res.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    ), f"Expected HTTP 503, got {res.status_code}. Body: {res.text}"

    body = res.json()
    error = body.get("error", {})
    detail = error.get("details", {})

    # Extract replace_debug.bailian
    replace_debug = detail.get("replace_debug", {})
    bailian_diag = replace_debug.get("bailian", {})
    action_hint = detail.get("action_hint", "")

    # Get expected fields from error_response metadata
    metadata = error_response.get("metadata", {})
    expected_status_code = metadata.get("status_code")
    expected_code = metadata.get("code")
    expected_exception_message = metadata.get("exception_message")
    expected_model = metadata.get("model")
    expected_function = metadata.get("function")
    expected_specific_hint = metadata.get("specific_hint", "")

    # Assert bailian_diag contains ALL available diagnostic fields
    if expected_status_code is not None:
        assert "status_code" in bailian_diag, (
            f"bailian_diag missing 'status_code'. Expected {expected_status_code}, "
            f"got bailian_diag={bailian_diag}"
        )
        assert bailian_diag.get("status_code") == expected_status_code

    if expected_code is not None:
        assert (
            "code" in bailian_diag
        ), f"bailian_diag missing 'code'. Expected {expected_code}, got bailian_diag={bailian_diag}"
        assert bailian_diag.get("code") == expected_code

    if expected_exception_message is not None:
        assert "exception_message" in bailian_diag, (
            f"bailian_diag missing 'exception_message'. Expected {expected_exception_message}, "
            f"got bailian_diag={bailian_diag}"
        )
        assert bailian_diag.get("exception_message") == expected_exception_message

    if expected_model is not None:
        assert "model" in bailian_diag, (
            f"bailian_diag missing 'model'. "
            f"Expected {expected_model}, got bailian_diag={bailian_diag}"
        )
        assert bailian_diag.get("model") == expected_model

    if expected_function is not None:
        assert "function" in bailian_diag, (
            f"bailian_diag missing 'function'. Expected {expected_function}, "
            f"got bailian_diag={bailian_diag}"
        )
        assert bailian_diag.get("function") == expected_function

    # Assert action_hint contains specific error message (not generic)
    if expected_specific_hint:
        assert expected_specific_hint in action_hint, (
            f"action_hint missing specific error hint. "
            f"Expected '{expected_specific_hint}', got action_hint='{action_hint}'"
        )


# ============================================================================
# Individual Scenario Tests (for debugging specific cases)
# ============================================================================


def _setup_replace_mode_mocks(monkeypatch, bailian_response, warp_fails=True):
    """Common mock setup for replace mode bailian tests."""
    import app.api.tryon_v2 as tryon_v2_api
    import app.services.bailian_tryon_client as bailian_client
    import app.services.tryon_v2.catvton_engine_client as catvton_client
    import app.services.tryon_v2.warp_engine as warp_engine
    import app.services.vton_remote_client as vton_client

    # Skip CatVTON so Bailian is first engine
    monkeypatch.setattr(catvton_client, "_catvton_configured", lambda: False)

    # Configure Bailian
    monkeypatch.setattr(bailian_client, "_bailian_configured", lambda: True)

    async def mock_call_bailian_tryon(**kwargs):
        return bailian_response

    monkeypatch.setattr(bailian_client, "call_bailian_tryon", mock_call_bailian_tryon)

    # Remote VTON not configured
    monkeypatch.setattr(vton_client, "_remote_url_configured", lambda: False)

    # Skip face check
    monkeypatch.setattr(
        tryon_v2_api,
        "check_tryon_garment_has_face",
        lambda _img: False,
    )

    # Fail warp so we get the "all engines failed" 503
    if warp_fails:

        def mock_warp_fail(*args, **kwargs):
            raise RuntimeError("warp_disabled_for_test")

        monkeypatch.setattr(warp_engine, "tryon_top_warp_preserve", mock_warp_fail)
        monkeypatch.setattr(warp_engine, "tryon_pants_warp", mock_warp_fail)
        monkeypatch.setattr(warp_engine, "tryon_skirt_warp", mock_warp_fail)


def test_bug_invalid_api_key_scenario(
    client: TestClient,
    auth_headers: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    """Test invalid API key scenario. Skips CatVTON so Bailian is the first engine."""
    error_response = {
        "status": "error",
        "message": "InvalidApiKey",
        "result_image": None,
        "metadata": {
            "reason": "dashscope_http",
            "error_type": "api_error",
            "code": "InvalidApiKey",
            "status_code": 401,
            "specific_hint": "API key 无效或已过期",
            "model": "wanx2.1-imageedit",
            "function": "description_edit_with_mask",
        },
    }
    _setup_replace_mode_mocks(monkeypatch, error_response)

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

    assert res.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    body = res.json()
    error = body.get("error", {})
    detail = error.get("details", {})
    bailian_diag = detail.get("replace_debug", {}).get("bailian", {})
    action_hint = detail.get("action_hint", "")

    assert bailian_diag.get("status_code") == 401
    assert bailian_diag.get("code") == "InvalidApiKey"
    assert bailian_diag.get("model") == "wanx2.1-imageedit"
    assert bailian_diag.get("function") == "description_edit_with_mask"
    assert "API key 无效或已过期" in action_hint


def test_bug_quota_exceeded_scenario(
    client: TestClient,
    auth_headers: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    """Test quota exceeded scenario."""
    error_response = {
        "status": "error",
        "message": "QuotaExceeded",
        "result_image": None,
        "metadata": {
            "reason": "dashscope_http",
            "error_type": "api_error",
            "code": "QuotaExceeded",
            "status_code": 429,
            "specific_hint": "API 额度不足或超出限制",
            "model": "wanx2.1-imageedit",
            "function": "description_edit_with_mask",
        },
    }
    _setup_replace_mode_mocks(monkeypatch, error_response)

    garment_bytes = _jpeg_bytes()
    person_bytes = _jpeg_bytes(size=(300, 500))
    files = {
        "garment_file": ("garment.jpg", garment_bytes, "image/jpeg"),
        "person_file": ("person.jpg", person_bytes, "image/jpeg"),
    }

    res = client.post(
        "/api/v2/tryon/garment",
        headers=auth_headers,
        files=files,
        data={"garment_category": "top", "mode": "replace", "model_gender": "neutral"},
    )

    assert res.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    body = res.json()
    error = body.get("error", {})
    detail = error.get("details", {})
    bailian_diag = detail.get("replace_debug", {}).get("bailian", {})
    action_hint = detail.get("action_hint", "")

    assert bailian_diag.get("code") == "QuotaExceeded"
    assert bailian_diag.get("status_code") == 429
    assert "API 额度不足或超出限制" in action_hint


def test_bug_network_timeout_scenario(
    client: TestClient,
    auth_headers: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    """Test network timeout scenario."""
    error_response = {
        "status": "error",
        "message": "网络超时",
        "result_image": None,
        "metadata": {
            "reason": "dashscope_exception",
            "error_type": "TimeoutException",
            "exception_message": "Request timed out",
            "specific_hint": "网络超时",
            "model": "wanx2.1-imageedit",
            "function": "description_edit_with_mask",
        },
    }
    _setup_replace_mode_mocks(monkeypatch, error_response)

    garment_bytes = _jpeg_bytes()
    person_bytes = _jpeg_bytes(size=(300, 500))
    files = {
        "garment_file": ("garment.jpg", garment_bytes, "image/jpeg"),
        "person_file": ("person.jpg", person_bytes, "image/jpeg"),
    }

    res = client.post(
        "/api/v2/tryon/garment",
        headers=auth_headers,
        files=files,
        data={"garment_category": "top", "mode": "replace", "model_gender": "neutral"},
    )

    assert res.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    body = res.json()
    error = body.get("error", {})
    detail = error.get("details", {})
    bailian_diag = detail.get("replace_debug", {}).get("bailian", {})
    action_hint = detail.get("action_hint", "")

    assert bailian_diag.get("exception_message") == "Request timed out"
    assert bailian_diag.get("error_type") == "TimeoutException"
    assert "网络超时" in action_hint


def test_bug_success_no_image_scenario(
    client: TestClient,
    auth_headers: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    """Test success but no result_image scenario."""
    error_response = {
        "status": "success",
        "message": "百炼试衣完成",
        "result_image": None,
        "metadata": {
            "reason": "dashscope_no_url",
            "model": "wanx2.1-imageedit",
            "function": "description_edit_with_mask",
        },
    }
    _setup_replace_mode_mocks(monkeypatch, error_response)

    garment_bytes = _jpeg_bytes()
    person_bytes = _jpeg_bytes(size=(300, 500))
    files = {
        "garment_file": ("garment.jpg", garment_bytes, "image/jpeg"),
        "person_file": ("person.jpg", person_bytes, "image/jpeg"),
    }

    res = client.post(
        "/api/v2/tryon/garment",
        headers=auth_headers,
        files=files,
        data={"garment_category": "top", "mode": "replace", "model_gender": "neutral"},
    )

    assert res.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    body = res.json()
    error = body.get("error", {})
    detail = error.get("details", {})
    bailian_diag = detail.get("replace_debug", {}).get("bailian", {})
    action_hint = detail.get("action_hint", "")

    assert bailian_diag.get("model") == "wanx2.1-imageedit"
    assert bailian_diag.get("function") == "description_edit_with_mask"
    assert "百炼返回成功但缺少结果图" in action_hint
