"""
Bug condition exploration property-based tests for try-on replace mode fix.

**Validates: Requirements 2.2, 2.3, 2.4, 2.5**

This test demonstrates the bug on UNFIXED code:
- When mode="replace" and Bailian is configured but API calls fail
- The error response lacks detailed diagnostics (incomplete bailian_diag, generic error hints)

EXPECTED OUTCOME ON UNFIXED CODE: Test FAILS
- bailian_diag is missing fields like status_code, code, exception_message, model, function
- action_hint contains generic messages like "百炼失败：未知错误" instead of specific hints

This proves the bug exists. After the fix is implemented, this test should PASS.
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
    **Property 1: Bug Condition - Detailed Bailian Error Diagnostics Missing**

    **Validates: Requirements 2.2, 2.3, 2.4, 2.5**

    For any replace mode request where Bailian is configured and the Bailian API call fails,
    the UNFIXED code returns an HTTP 503 error response with INCOMPLETE bailian_diag
    (missing status_code, code, exception_message, model, function) and GENERIC error hints
    (like "百炼失败：未知错误" instead of specific hints like "百炼失败：API key 无效或已过期").

    EXPECTED OUTCOME ON UNFIXED CODE: This test FAILS
    - Assertions fail because bailian_diag is missing diagnostic fields
    - Assertions fail because action_hint is generic instead of specific

    This proves the bug exists. After the fix, this test should PASS.
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

    # Mock Bailian as configured
    monkeypatch.setattr(bailian_client, "_bailian_configured", lambda: True)

    # Mock call_bailian_tryon to return the error response
    async def mock_call_bailian_tryon(**kwargs):
        return error_response

    monkeypatch.setattr(bailian_client, "call_bailian_tryon", mock_call_bailian_tryon)

    # Mock remote VTON as not configured (so we hit the error path)
    monkeypatch.setattr(vton_client, "_remote_url_configured", lambda: False)

    # Mock check_tryon_garment_has_face to return False
    def _stub_check_tryon_garment_has_face(_img):
        return False

    monkeypatch.setattr(
        tryon_v2_api,
        "check_tryon_garment_has_face",
        _stub_check_tryon_garment_has_face,
    )

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
    ), f"Expected HTTP 503, got {res.status_code}"

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

    # ========================================================================
    # BUG ASSERTIONS: These FAIL on unfixed code, proving the bug exists
    # ========================================================================

    # Assert bailian_diag contains ALL available diagnostic fields
    # (UNFIXED code is missing these fields)

    if expected_status_code is not None:
        assert "status_code" in bailian_diag, (
            f"BUG: bailian_diag missing 'status_code' field. "
            f"Expected {expected_status_code}, got bailian_diag={bailian_diag}"
        )
        assert bailian_diag.get("status_code") == expected_status_code, (
            f"BUG: bailian_diag['status_code'] incorrect. "
            f"Expected {expected_status_code}, got {bailian_diag.get('status_code')}"
        )

    if expected_code is not None:
        assert "code" in bailian_diag, (
            f"BUG: bailian_diag missing 'code' field. "
            f"Expected {expected_code}, got bailian_diag={bailian_diag}"
        )
        assert bailian_diag.get("code") == expected_code, (
            f"BUG: bailian_diag['code'] incorrect. "
            f"Expected {expected_code}, got {bailian_diag.get('code')}"
        )

    if expected_exception_message is not None:
        assert "exception_message" in bailian_diag, (
            f"BUG: bailian_diag missing 'exception_message' field. "
            f"Expected {expected_exception_message}, got bailian_diag={bailian_diag}"
        )
        assert bailian_diag.get("exception_message") == expected_exception_message, (
            f"BUG: bailian_diag['exception_message'] incorrect. "
            f"Expected {expected_exception_message}, got {bailian_diag.get('exception_message')}"
        )

    if expected_model is not None:
        assert "model" in bailian_diag, (
            f"BUG: bailian_diag missing 'model' field. "
            f"Expected {expected_model}, got bailian_diag={bailian_diag}"
        )
        assert bailian_diag.get("model") == expected_model, (
            f"BUG: bailian_diag['model'] incorrect. "
            f"Expected {expected_model}, got {bailian_diag.get('model')}"
        )

    if expected_function is not None:
        assert "function" in bailian_diag, (
            f"BUG: bailian_diag missing 'function' field. "
            f"Expected {expected_function}, got bailian_diag={bailian_diag}"
        )
        assert bailian_diag.get("function") == expected_function, (
            f"BUG: bailian_diag['function'] incorrect. "
            f"Expected {expected_function}, got {bailian_diag.get('function')}"
        )

    # Assert action_hint contains specific error message (not generic)
    # (UNFIXED code uses generic hints like "百炼失败：未知错误")

    if expected_specific_hint:
        assert expected_specific_hint in action_hint, (
            f"BUG: action_hint missing specific error hint. "
            f"Expected to contain '{expected_specific_hint}', got action_hint='{action_hint}'"
        )

        # Assert action_hint is NOT generic
        generic_hints = ["未知错误", "查看 detail.replace_debug.bailian 获取详情"]
        for generic in generic_hints:
            if generic in action_hint and expected_specific_hint not in action_hint:
                pytest.fail(
                    f"BUG: action_hint is generic instead of specific. "
                    f"Contains '{generic}' but missing '{expected_specific_hint}'. "
                    f"action_hint='{action_hint}'"
                )


# ============================================================================
# Individual Scenario Tests (for debugging specific cases)
# ============================================================================


def test_bug_invalid_api_key_scenario(
    client: TestClient,
    auth_headers: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    """
    Test invalid API key scenario specifically.

    EXPECTED ON UNFIXED CODE: FAILS
    - bailian_diag missing status_code=401, code="InvalidApiKey", specific_hint
    - action_hint is generic like "百炼失败：未知错误" instead of "百炼失败：API key 无效或已过期"
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

    # Mock Bailian as configured
    monkeypatch.setattr(bailian_client, "_bailian_configured", lambda: True)

    # Mock call_bailian_tryon to return the error response
    async def mock_call_bailian_tryon(**kwargs):
        return error_response

    monkeypatch.setattr(bailian_client, "call_bailian_tryon", mock_call_bailian_tryon)

    # Mock remote VTON as not configured
    monkeypatch.setattr(vton_client, "_remote_url_configured", lambda: False)

    # Mock check_tryon_garment_has_face
    monkeypatch.setattr(
        tryon_v2_api,
        "check_tryon_garment_has_face",
        lambda _img: False,
    )

    # Prepare request
    garment_bytes = _jpeg_bytes(color=(245, 245, 245))
    person_bytes = _jpeg_bytes(size=(300, 500), color=(220, 220, 220))
    files = {
        "garment_file": ("garment.jpg", garment_bytes, "image/jpeg"),
        "person_file": ("person.jpg", person_bytes, "image/jpeg"),
    }

    # Call the endpoint
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

    # Assert HTTP 503
    assert res.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    body = res.json()
    # The error handler wraps the response in error.details
    error = body.get("error", {})
    detail = error.get("details", {})

    # Extract diagnostics
    replace_debug = detail.get("replace_debug", {})
    bailian_diag = replace_debug.get("bailian", {})
    action_hint = detail.get("action_hint", "")

    # BUG ASSERTIONS (FAIL on unfixed code)
    assert (
        "status_code" in bailian_diag
    ), f"BUG: bailian_diag missing 'status_code'. Got: {bailian_diag}"
    assert bailian_diag["status_code"] == 401

    assert "code" in bailian_diag, f"BUG: bailian_diag missing 'code'. Got: {bailian_diag}"
    assert bailian_diag["code"] == "InvalidApiKey"

    assert "model" in bailian_diag, f"BUG: bailian_diag missing 'model'. Got: {bailian_diag}"
    assert bailian_diag["model"] == "wanx2.1-imageedit"

    assert "function" in bailian_diag, f"BUG: bailian_diag missing 'function'. Got: {bailian_diag}"
    assert bailian_diag["function"] == "description_edit_with_mask"

    # Assert specific hint in action_hint
    assert (
        "API key 无效或已过期" in action_hint
    ), f"BUG: action_hint missing specific error. Got: '{action_hint}'"


def test_bug_quota_exceeded_scenario(
    client: TestClient,
    auth_headers: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    """
    Test quota exceeded scenario specifically.

    EXPECTED ON UNFIXED CODE: FAILS
    - bailian_diag missing code="QuotaExceeded", status_code=429
    - action_hint is generic instead of "百炼失败：API 额度不足或超出限制"
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

    # Setup mocks
    monkeypatch.setattr(bailian_client, "_bailian_configured", lambda: True)

    async def mock_call_bailian_tryon(**kwargs):
        return error_response

    monkeypatch.setattr(bailian_client, "call_bailian_tryon", mock_call_bailian_tryon)
    monkeypatch.setattr(vton_client, "_remote_url_configured", lambda: False)
    monkeypatch.setattr(tryon_v2_api, "check_tryon_garment_has_face", lambda _img: False)

    # Prepare request
    garment_bytes = _jpeg_bytes()
    person_bytes = _jpeg_bytes(size=(300, 500))
    files = {
        "garment_file": ("garment.jpg", garment_bytes, "image/jpeg"),
        "person_file": ("person.jpg", person_bytes, "image/jpeg"),
    }

    # Call endpoint
    res = client.post(
        "/api/v2/tryon/garment",
        headers=auth_headers,
        files=files,
        data={"garment_category": "top", "mode": "replace", "model_gender": "neutral"},
    )

    # Assert
    assert res.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    body = res.json()
    error = body.get("error", {})
    detail = error.get("details", {})
    bailian_diag = detail.get("replace_debug", {}).get("bailian", {})
    action_hint = detail.get("action_hint", "")

    # BUG ASSERTIONS
    assert (
        "code" in bailian_diag and bailian_diag["code"] == "QuotaExceeded"
    ), f"BUG: bailian_diag missing or incorrect 'code'. Got: {bailian_diag}"
    assert (
        "status_code" in bailian_diag and bailian_diag["status_code"] == 429
    ), f"BUG: bailian_diag missing or incorrect 'status_code'. Got: {bailian_diag}"
    assert (
        "API 额度不足或超出限制" in action_hint
    ), f"BUG: action_hint missing specific error. Got: '{action_hint}'"


def test_bug_network_timeout_scenario(
    client: TestClient,
    auth_headers: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    """
    Test network timeout scenario specifically.

    EXPECTED ON UNFIXED CODE: FAILS
    - bailian_diag missing exception_message, error_type="TimeoutException"
    - action_hint is generic instead of "百炼失败：网络超时"
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

    # Setup mocks
    monkeypatch.setattr(bailian_client, "_bailian_configured", lambda: True)

    async def mock_call_bailian_tryon(**kwargs):
        return error_response

    monkeypatch.setattr(bailian_client, "call_bailian_tryon", mock_call_bailian_tryon)
    monkeypatch.setattr(vton_client, "_remote_url_configured", lambda: False)
    monkeypatch.setattr(tryon_v2_api, "check_tryon_garment_has_face", lambda _img: False)

    # Prepare request
    garment_bytes = _jpeg_bytes()
    person_bytes = _jpeg_bytes(size=(300, 500))
    files = {
        "garment_file": ("garment.jpg", garment_bytes, "image/jpeg"),
        "person_file": ("person.jpg", person_bytes, "image/jpeg"),
    }

    # Call endpoint
    res = client.post(
        "/api/v2/tryon/garment",
        headers=auth_headers,
        files=files,
        data={"garment_category": "top", "mode": "replace", "model_gender": "neutral"},
    )

    # Assert
    assert res.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    body = res.json()
    error = body.get("error", {})
    detail = error.get("details", {})
    bailian_diag = detail.get("replace_debug", {}).get("bailian", {})
    action_hint = detail.get("action_hint", "")

    # BUG ASSERTIONS
    assert (
        "exception_message" in bailian_diag
    ), f"BUG: bailian_diag missing 'exception_message'. Got: {bailian_diag}"
    assert bailian_diag["exception_message"] == "Request timed out"

    assert (
        "error_type" in bailian_diag
    ), f"BUG: bailian_diag missing 'error_type'. Got: {bailian_diag}"
    assert bailian_diag["error_type"] == "TimeoutException"

    assert (
        "网络超时" in action_hint
    ), f"BUG: action_hint missing specific error. Got: '{action_hint}'"


def test_bug_success_no_image_scenario(
    client: TestClient,
    auth_headers: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    """
    Test success but no result_image scenario specifically.

    EXPECTED ON UNFIXED CODE: FAILS
    - bailian_diag missing model, function fields
    - action_hint doesn't mention "百炼返回成功但缺少结果图"
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

    # Setup mocks
    monkeypatch.setattr(bailian_client, "_bailian_configured", lambda: True)

    async def mock_call_bailian_tryon(**kwargs):
        return error_response

    monkeypatch.setattr(bailian_client, "call_bailian_tryon", mock_call_bailian_tryon)
    monkeypatch.setattr(vton_client, "_remote_url_configured", lambda: False)
    monkeypatch.setattr(tryon_v2_api, "check_tryon_garment_has_face", lambda _img: False)

    # Prepare request
    garment_bytes = _jpeg_bytes()
    person_bytes = _jpeg_bytes(size=(300, 500))
    files = {
        "garment_file": ("garment.jpg", garment_bytes, "image/jpeg"),
        "person_file": ("person.jpg", person_bytes, "image/jpeg"),
    }

    # Call endpoint
    res = client.post(
        "/api/v2/tryon/garment",
        headers=auth_headers,
        files=files,
        data={"garment_category": "top", "mode": "replace", "model_gender": "neutral"},
    )

    # Assert
    assert res.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    body = res.json()
    error = body.get("error", {})
    detail = error.get("details", {})
    bailian_diag = detail.get("replace_debug", {}).get("bailian", {})

    # BUG ASSERTIONS
    assert "model" in bailian_diag, f"BUG: bailian_diag missing 'model'. Got: {bailian_diag}"
    assert bailian_diag["model"] == "wanx2.1-imageedit"

    assert "function" in bailian_diag, f"BUG: bailian_diag missing 'function'. Got: {bailian_diag}"
    assert bailian_diag["function"] == "description_edit_with_mask"

    # Assert action_hint mentions the specific scenario
    action_hint = detail.get("action_hint", "")
    assert "百炼返回成功但缺少结果图" in action_hint, (
        f"BUG: action_hint missing specific success-no-image hint. " f"Got: '{action_hint}'"
    )
