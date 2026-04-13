import io

from PIL import Image

from tests.api_json import unwrap_json


def _png_bytes(color=(50, 120, 180)):
    img = Image.new("RGB", (224, 224), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_suitability_api_returns_dimension_reasons(client, auth_headers, monkeypatch):
    # Ensure profile exists
    profile = {
        "height": 170,
        "body_type": "梨形",
        "skin_tone": "黄皮",
        "budget_range": "中等",
        "style_preference": ["通勤", "简约"],
        "avoid_body_parts": ["臀", "大腿"],
        "gender_expression": 0.5,
    }
    r = client.get("/api/v1/profile", headers=auth_headers)
    if r.status_code == 404:
        client.post("/api/v1/profile", json=profile, headers=auth_headers)
    else:
        client.put("/api/v1/profile", json=profile, headers=auth_headers)

    # Patch CLIP recognizer to be deterministic (avoid model/network)
    from app.ml import clip_recognizer as clip_mod

    class _DummyRec:
        def recognize(self, _bytes):
            return {
                "category": "上衣",
                "category_confidence": 0.9,
                "style_tags": ["通勤", "简约"],
                "fit_type": "修身",
                "occasions": ["通勤上班"],
                "feature_dim": 768,
                "feature_vector": [0.0] * 10,
                "category_scores": {"上衣": 0.9},
            }

    monkeypatch.setattr(clip_mod, "get_clip_recognizer", lambda: _DummyRec())

    files = {"file": ("t.png", _png_bytes(), "image/png")}
    res = client.post("/api/v1/analysis/suitability", headers=auth_headers, files=files)
    assert res.status_code == 200
    body = unwrap_json(res)

    assert "scene_match_reason" in body
    assert "body_fit_reason" in body
    assert "style_coordination_reason" in body

    assert body["scene_match_reason"].strip()
    assert body["body_fit_reason"].strip()
    assert body["style_coordination_reason"].strip()

    # Reasons should tie to user/profile and garment tags (not pure boilerplate)
    assert "梨形" in body["body_fit_reason"] or "修身" in body["body_fit_reason"]
    assert (
        "通勤" in body["style_coordination_reason"] or "简约" in body["style_coordination_reason"]
    )
