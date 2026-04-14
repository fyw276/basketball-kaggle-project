from fastapi import status

from app.api.tryon import _normalize_tryon_error


def test_tryon_error_mapping_face_model_image():
    code, err, msg, retryable = _normalize_tryon_error(
        {
            "message": "衣服图检测到人像，请上传无模特的白底商品图，否则会出现重影。",
            "metadata": {"reason": "garment_contains_face"},
        }
    )
    assert code == status.HTTP_400_BAD_REQUEST
    assert err == "TRYON_GARMENT_CONTAINS_MODEL"
    assert retryable is False
    assert "无模特" in msg


def test_tryon_error_mapping_quota_retryable():
    code, err, _msg, retryable = _normalize_tryon_error(
        {
            "message": "Error: 429 quota exceeded",
            "metadata": {},
        }
    )
    assert code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert err == "TRYON_UPSTREAM_QUOTA"
    assert retryable is True
