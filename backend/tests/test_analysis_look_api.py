import io

from PIL import Image

from tests.api_json import unwrap_json


def _image_upload():
    buf = io.BytesIO()
    Image.new("RGB", (240, 360), "white").save(buf, format="JPEG")
    buf.seek(0)
    return {"file": ("look.jpg", buf.getvalue(), "image/jpeg")}


class FakeLookSimilarityService:
    def __init__(self, *args, **kwargs):
        self.parser = kwargs.get("parser")

    def analyze_look(
        self,
        image_bytes,
        wardrobe_garments,
        source_type="photo",
        scene_hint=None,
        include_tryon_candidates=True,
        include_accessories=True,
    ):
        missing = ["shoes"]
        if include_accessories:
            missing.append("accessory")
        return {
            "source_type": source_type,
            "overall_similarity": 0.5,
            "coverage_score": 0.0,
            "style_consistency": 1.0,
            "color_harmony": 1.0,
            "missing_categories": missing,
            "look_summary": {
                "dominant_style_tags": ["minimal"],
                "dominant_colors": ["black"],
                "scene": scene_hint,
            },
            "parts": [
                {
                    "part_role": "top",
                    "detected_category": "top",
                    "bbox": [0, 0, 10, 10],
                    "style_tags": ["minimal"],
                    "main_color": {"name": "black"},
                    "similarity": 0.0,
                    "matched_garments": [],
                }
            ],
            "recommended_tryon_candidates": [],
        }


def test_look_similarity_requires_file(client, auth_headers):
    response = client.post("/api/v1/analysis/look-similarity", headers=auth_headers)

    assert response.status_code == 400


def test_look_similarity_returns_expected_shape(client, auth_headers, monkeypatch):
    monkeypatch.setattr("app.api.analysis.LookSimilarityService", FakeLookSimilarityService)

    response = client.post(
        "/api/v1/analysis/look-similarity",
        headers=auth_headers,
        files=_image_upload(),
        data={
            "source_type": "photo",
            "parser_strategy": "auto",
            "include_accessories": "false",
        },
    )
    data = unwrap_json(response)

    assert response.status_code == 200
    assert data["source_type"] == "photo"
    assert data["parser_strategy_used"] == "hybrid"
    assert data["matched_parts_count"] == 0
    assert "overall_similarity" in data
    assert data["parts"][0]["part_role"] == "top"


def test_look_parse_returns_blocks_and_parts(client, auth_headers):
    response = client.post(
        "/api/v1/analysis/look-parse",
        headers=auth_headers,
        files=_image_upload(),
        data={"source_type": "screenshot", "parser_strategy": "auto"},
    )
    data = unwrap_json(response)

    assert response.status_code == 200
    assert data["source_type"] == "screenshot"
    assert data["blocks"]
    assert data["parts"]


def test_look_parse_omni_unavailable_does_not_500(client, auth_headers):
    response = client.post(
        "/api/v1/analysis/look-parse",
        headers=auth_headers,
        files=_image_upload(),
        data={"source_type": "screenshot", "parser_strategy": "omni"},
    )
    data = unwrap_json(response)

    assert response.status_code == 200
    assert data["source_type"] == "screenshot"
    assert data["parts"]


def test_look_complement_returns_missing_categories(client, auth_headers, monkeypatch):
    monkeypatch.setattr("app.api.analysis.LookSimilarityService", FakeLookSimilarityService)

    response = client.post(
        "/api/v1/analysis/look-complement",
        headers=auth_headers,
        files=_image_upload(),
        data={
            "source_type": "auto",
            "parser_strategy": "auto",
            "include_accessories": "false",
        },
    )
    data = unwrap_json(response)

    assert response.status_code == 200
    assert data["missing_categories"] == ["shoes"]
    assert "recommendations" in data
