from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.look_parser import LookPart
from app.services.look_similarity import LookSimilarityService


class FakeParser:
    def __init__(self, parts):
        self.parts = parts

    def parse(self, image_bytes, source_type="photo"):
        return SimpleNamespace(
            source_type=source_type,
            blocks=[],
            parts=self.parts,
        )


class FakeClipAdapter:
    def enrich_part(self, part):
        return {
            "category": part.category or "top",
            "style_tags": part.style_tags or [],
            "main_color": part.main_color or {"name": "black", "hex_code": "#000000"},
            "feature_vector": part.feature_vector or [1.0, 0.0, 0.0],
        }


def _part(role="top", vector=None, tags=None):
    return LookPart(
        part_role=role,
        bbox=[0, 0, 10, 10],
        image_bytes=b"part",
        category=role,
        style_tags=tags or ["minimal"],
        main_color={"name": "black", "hex_code": "#000000"},
        feature_vector=vector or [1.0, 0.0, 0.0],
    )


def _garment(category="top", vector=None, tags=None):
    return SimpleNamespace(
        garment_id=uuid4(),
        name="item",
        category=category,
        image_url="/uploads/item.jpg",
        style_tags=tags or ["minimal"],
        main_color={"name": "black", "hex_code": "#000000"},
        feature_vector=vector or [1.0, 0.0, 0.0],
    )


def _service(parts=None):
    return LookSimilarityService(
        parser=FakeParser(parts or [_part()]),
        clip_adapter=FakeClipAdapter(),
    )


def test_analyze_look_with_empty_wardrobe_returns_zero_matches():
    result = _service().analyze_look(b"img", [], include_accessories=False)

    assert result["overall_similarity"] == 0.0
    assert result["parts"][0]["matched_garments"] == []


def test_match_part_to_wardrobe_returns_top_k_sorted():
    service = _service()
    part = _part(vector=[1.0, 0.0, 0.0])
    wardrobe = [
        _garment(vector=[0.6, 0.8, 0.0]),
        _garment(vector=[1.0, 0.0, 0.0]),
        _garment(vector=[0.0, 1.0, 0.0]),
    ]

    result = service.match_part_to_wardrobe(part, wardrobe, top_k=2)

    scores = [m["similarity_score"] for m in result["matched_garments"]]
    assert len(scores) == 2
    assert scores == sorted(scores, reverse=True)


def test_score_overall_combines_part_scores():
    service = _service()
    scores = service.score_overall(
        [
            {
                "part_role": "top",
                "similarity": 1.0,
                "style_tags": ["minimal"],
                "main_color": {"hex_code": "#000000"},
                "matched_garments": [{"similarity_score": 1.0}],
            }
        ]
    )

    assert scores["part_match_score"] == pytest.approx(1.0)
    assert 0.0 <= scores["overall_similarity"] <= 1.0


def test_build_tryon_candidates_prefers_top_and_bottom_matches():
    service = _service()
    top_id = str(uuid4())
    bottom_id = str(uuid4())
    candidates = service.build_tryon_candidates(
        [
            {
                "part_role": "shoes",
                "matched_garments": [{"garment_id": str(uuid4()), "similarity_score": 1.0}],
            },
            {
                "part_role": "top",
                "matched_garments": [{"garment_id": top_id, "similarity_score": 0.9}],
            },
            {
                "part_role": "bottom",
                "matched_garments": [{"garment_id": bottom_id, "similarity_score": 0.8}],
            },
        ]
    )

    assert [c["part_role"] for c in candidates] == ["top", "bottom"]
    assert candidates[0]["garment_id"] == top_id


def test_missing_categories_detects_missing_shoes():
    result = _service(parts=[_part("top"), _part("bottom")]).analyze_look(
        b"img",
        [_garment("top")],
        include_accessories=False,
    )

    assert "shoes" in result["missing_categories"]


def test_include_accessories_false_skips_accessory_gap():
    result = _service(parts=[_part("top"), _part("bottom")]).analyze_look(
        b"img",
        [_garment("top")],
        include_accessories=False,
    )

    assert "accessory" not in result["missing_categories"]
