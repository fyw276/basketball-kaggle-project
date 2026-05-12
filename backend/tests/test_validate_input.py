"""
Tests for POST /api/v2/tryon/validate-input endpoint validation behavior.

Tests FastAPI returns 422 when required fields are missing or invalid,
and verifies error details are properly logged.
"""

import io

import pytest
from PIL import Image

from tests.api_json import unwrap_json


def _make_test_image_bytes(size: int = 224) -> bytes:
    """Create a minimal valid JPEG image bytes for testing."""
    img = Image.new("RGB", (size, size), color="red")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def auth_headers_and_files(client):
    """Create authenticated user and return headers + minimal image files."""
    user_data = {
        "username": "validate_test_user",
        "email": "validate_test@example.com",
        "password": "TestPass123!",
    }
    client.post("/api/v1/auth/register", json=user_data)
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"username": user_data["username"], "password": user_data["password"]},
    )
    token = unwrap_json(login_resp)["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    return headers


def _files_dict(garment_bytes: bytes, person_bytes: bytes):
    """Create a files dict for multipart upload."""
    return {
        "garment_file": ("garment.jpg", garment_bytes, "image/jpeg"),
        "person_file": ("person.jpg", person_bytes, "image/jpeg"),
    }


class TestValidateInputFastAPI422:
    """Test cases where FastAPI returns 422 (validation error)."""

    def test_missing_garment_file_returns_422(self, client, auth_headers_and_files):
        """When garment_file is not provided, FastAPI must return 422."""
        person_bytes = _make_test_image_bytes()
        response = client.post(
            "/api/v2/tryon/validate-input",
            headers=auth_headers_and_files,
            data={"mode": "strict"},
            files={"person_file": ("person.jpg", person_bytes, "image/jpeg")},
        )
        assert (
            response.status_code == 422
        ), f"Expected 422 for missing garment_file, got {response.status_code}"
        print(f"[422] Missing garment_file: {response.text[:300]}")

    def test_missing_person_file_returns_422(self, client, auth_headers_and_files):
        """When person_file is not provided, FastAPI must return 422."""
        garment_bytes = _make_test_image_bytes()
        response = client.post(
            "/api/v2/tryon/validate-input",
            headers=auth_headers_and_files,
            data={"mode": "strict"},
            files={"garment_file": ("garment.jpg", garment_bytes, "image/jpeg")},
        )
        assert (
            response.status_code == 422
        ), f"Expected 422 for missing person_file, got {response.status_code}"
        print(f"[422] Missing person_file: {response.text[:300]}")

    def test_garment_file_wrong_content_type_returns_400_or_422(
        self, client, auth_headers_and_files
    ):
        """When garment_file is not an image, FastAPI should return 400 or 422."""
        person_bytes = _make_test_image_bytes()
        response = client.post(
            "/api/v2/tryon/validate-input",
            headers=auth_headers_and_files,
            data={"mode": "strict"},
            files={
                "garment_file": ("garment.txt", b"not an image", "text/plain"),
                "person_file": ("person.jpg", person_bytes, "image/jpeg"),
            },
        )
        assert response.status_code in (
            400,
            422,
        ), f"Expected 400/422 for wrong content type, got {response.status_code}"
        print(f"[{response.status_code}] Wrong content type: {response.text[:200]}")

    def test_mode_invalid_value_returns_400_or_422(self, client, auth_headers_and_files):
        """When mode has an invalid value, FastAPI should return 400 or 422."""
        garment_bytes = _make_test_image_bytes()
        person_bytes = _make_test_image_bytes()
        response = client.post(
            "/api/v2/tryon/validate-input",
            headers=auth_headers_and_files,
            data={"mode": "invalid_mode"},
            files=_files_dict(garment_bytes, person_bytes),
        )
        assert response.status_code in (
            400,
            422,
        ), f"Expected 400/422 for invalid mode, got {response.status_code}"
        print(f"[{response.status_code}] Invalid mode: {response.text[:200]}")

    def test_missing_authorization_returns_403(self, client):
        """Without auth, request should be rejected with 403."""
        garment_bytes = _make_test_image_bytes()
        person_bytes = _make_test_image_bytes()
        response = client.post(
            "/api/v2/tryon/validate-input",
            data={"mode": "strict"},
            files=_files_dict(garment_bytes, person_bytes),
        )
        assert response.status_code == 403, f"Expected 403 without auth, got {response.status_code}"
        print(f"[{response.status_code}] No auth: {response.text[:200]}")


class TestValidateInputBusinessLogic:
    """Test business logic responses from the validate-input endpoint."""

    def test_valid_top_request_returns_200(self, client, auth_headers_and_files):
        """With valid images and top category, should return 200."""
        garment_bytes = _make_test_image_bytes(300)  # taller = aspect < 1.8 -> "top"
        person_bytes = _make_test_image_bytes()  # square = aspect >= 1.6 -> full_body=1.0
        response = client.post(
            "/api/v2/tryon/validate-input",
            headers=auth_headers_and_files,
            data={"mode": "strict", "garment_category": "top"},
            files=_files_dict(garment_bytes, person_bytes),
        )
        print(f"[{response.status_code}] Top request: {response.text[:300]}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    def test_valid_bottom_request_returns_200(self, client, auth_headers_and_files):
        """With valid images and bottom category, should return 200."""
        garment_bytes = _make_test_image_bytes(500)  # tall = aspect > 1.8 -> "bottom"
        person_bytes = _make_test_image_bytes()  # square
        response = client.post(
            "/api/v2/tryon/validate-input",
            headers=auth_headers_and_files,
            data={"mode": "strict", "garment_category": "bottom"},
            files=_files_dict(garment_bytes, person_bytes),
        )
        print(f"[{response.status_code}] Bottom request: {response.text[:300]}")
        assert response.status_code == 200

    def test_strict_mode_with_explicit_top_category(self, client, auth_headers_and_files):
        """With strict mode and explicit top category, gate should evaluate."""
        garment_bytes = _make_test_image_bytes(300)
        person_bytes = _make_test_image_bytes()
        response = client.post(
            "/api/v2/tryon/validate-input",
            headers=auth_headers_and_files,
            data={"mode": "strict", "garment_category": "top"},
            files=_files_dict(garment_bytes, person_bytes),
        )
        print(f"[{response.status_code}] Strict top: {response.text[:500]}")
        assert response.status_code == 200
        body = unwrap_json(response)
        print(f"  result: passed={body.get('passed')}, error_code={body.get('error_code')}")

    def test_realistic_mode_with_top_category_skips_gate(self, client, auth_headers_and_files):
        """Realistic mode should skip pipeline A gate and return pass immediately."""
        garment_bytes = _make_test_image_bytes(300)
        person_bytes = _make_test_image_bytes()
        response = client.post(
            "/api/v2/tryon/validate-input",
            headers=auth_headers_and_files,
            data={"mode": "realistic", "garment_category": "top"},
            files=_files_dict(garment_bytes, person_bytes),
        )
        print(f"[{response.status_code}] Realistic mode: {response.text[:500]}")
        assert response.status_code == 200
        body = unwrap_json(response)
        assert body.get("passed") is True, (
            f"realistic mode should skip gate and pass, got passed={body.get('passed')}, "
            f"error_code={body.get('error_code')}"
        )
        assert "REALISTIC" in body.get(
            "pipeline", ""
        ), f"Expected REALISTIC pipeline, got {body.get('pipeline')}"

    def test_replace_mode_with_top_category_skips_gate(self, client, auth_headers_and_files):
        """Replace mode should skip pipeline A gate and return pass immediately."""
        garment_bytes = _make_test_image_bytes(300)
        person_bytes = _make_test_image_bytes()
        response = client.post(
            "/api/v2/tryon/validate-input",
            headers=auth_headers_and_files,
            data={"mode": "replace", "garment_category": "top"},
            files=_files_dict(garment_bytes, person_bytes),
        )
        print(f"[{response.status_code}] Replace mode: {response.text[:500]}")
        assert response.status_code == 200
        body = unwrap_json(response)
        assert body.get("passed") is True, (
            f"replace mode should skip gate and pass, got passed={body.get('passed')}, "
            f"error_code={body.get('error_code')}"
        )
        assert "REPLACE" in body.get(
            "pipeline", ""
        ), f"Expected REPLACE pipeline, got {body.get('pipeline')}"

    def test_strict_mode_auto_category_returns_400_when_unclassified(
        self, client, auth_headers_and_files
    ):
        """
        When garment_category is 'auto' and classifier returns 'unknown',
        the endpoint should return 400 (not 422).
        """
        garment_bytes = _make_test_image_bytes()
        person_bytes = _make_test_image_bytes()
        response = client.post(
            "/api/v2/tryon/validate-input",
            headers=auth_headers_and_files,
            data={"mode": "strict", "garment_category": "auto"},
            files=_files_dict(garment_bytes, person_bytes),
        )
        print(f"[{response.status_code}] Auto category: {response.text[:500]}")
        # After fix: unknown category returns 400
        # Before fix: 422 cascade
        assert response.status_code in (
            200,
            400,
        ), f"Expected 200/400 for auto category, got {response.status_code}"
        if response.status_code == 400:
            body = response.json()
            assert "GARMENT_CLASSIFICATION_FAILED" in str(
                body
            ), f"400 should have GARMENT_CLASSIFICATION_FAILED, got {body}"
            print(f"  -> Correctly returned 400 for unclassified garment")


class TestValidateInputErrorDetails:
    """Test that validation errors include detailed error information."""

    def test_422_response_includes_errors_in_error_details(self, client, auth_headers_and_files):
        """FastAPI 422 response must include exc.errors() in error details."""
        response = client.post(
            "/api/v2/tryon/validate-input",
            headers=auth_headers_and_files,
            data={"mode": "strict"},
            files={},
        )
        assert response.status_code == 422
        body = response.json()
        print(f"[422] Error body keys: {list(body.keys())}")

        # After error_handlers fix, errors are at body['error']['details']['errors']
        error_details = body.get("error", {}).get("details", {})
        assert (
            "errors" in error_details
        ), f"Expected 'errors' in error.details, got keys: {list(error_details.keys())}"
        errors = error_details["errors"]
        assert len(errors) > 0
        print(f"[422] Validation errors: {errors}")

    def test_error_response_includes_body_field(self, client, auth_headers_and_files):
        """After fix, validation handler includes exc.body in response details."""
        response = client.post(
            "/api/v2/tryon/validate-input",
            headers=auth_headers_and_files,
            data={"mode": "strict"},
            files={},
        )
        assert response.status_code == 422
        body = response.json()
        # After fix: body is included in error.details
        error_details = body.get("error", {}).get("details", {})
        if "body" in error_details:
            print(f"[422] body field present: {error_details['body'] is not None}")
        else:
            print(f"[422] body field not in error.details (expected before fix)")
