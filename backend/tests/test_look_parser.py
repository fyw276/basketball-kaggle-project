import io
from types import SimpleNamespace

import numpy as np
from PIL import Image

from app.services.look_parser import LookParser
from app.services.look_parsers import HeuristicLookParser, HumanLookParser, HybridLookParser


def _image_bytes(width=320, height=480):
    buf = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(buf, format="JPEG")
    return buf.getvalue()


def test_parse_photo_returns_full_look_and_parts():
    result = LookParser().parse_photo(_image_bytes())

    assert result.source_type == "photo"
    assert result.blocks
    assert result.blocks[0].block_type == "person_look"
    assert result.parts


def test_parse_photo_returns_top_and_bottom_roles():
    result = LookParser().parse_photo(_image_bytes())
    roles = {part.part_role for part in result.parts}

    assert "top" in roles
    assert "bottom" in roles


def test_parse_screenshot_fallback_returns_blocks():
    result = LookParser().parse_screenshot(_image_bytes())

    assert result.source_type == "screenshot"
    assert result.blocks
    assert result.blocks[0].block_type == "person_look"


def test_part_bboxes_are_non_empty_and_in_bounds():
    width, height = 320, 480
    result = LookParser().parse_photo(_image_bytes(width, height))

    for part in result.parts:
        x1, y1, x2, y2 = part.bbox
        assert 0 <= x1 < x2 <= width
        assert 0 <= y1 < y2 <= height
        assert part.image_bytes


class _FailingParser:
    def parse_photo(self, image_bytes):
        raise RuntimeError("boom")

    def parse_screenshot(self, image_bytes):
        raise RuntimeError("boom")


class _TaggedParser:
    def __init__(self, source_type, role):
        self.source_type = source_type
        self.role = role

    def parse_photo(self, image_bytes):
        return self._result("photo")

    def parse_screenshot(self, image_bytes):
        return self._result("screenshot")

    def _result(self, source_type):
        return SimpleNamespace(
            source_type=self.source_type or source_type,
            blocks=[],
            parts=[SimpleNamespace(part_role=self.role, bbox=[0, 0, 1, 1], image_bytes=b"x")],
        )


def test_hybrid_photo_prefers_human_parser():
    parser = HybridLookParser(
        human_parser=_TaggedParser("photo", "human"),
        omni_parser=_TaggedParser("screenshot", "omni"),
    )

    result = parser.parse(_image_bytes(), source_type="photo")

    assert result.source_type == "photo"
    assert result.parts[0].part_role == "human"


def test_hybrid_screenshot_prefers_omni_parser():
    parser = HybridLookParser(
        human_parser=_TaggedParser("photo", "human"),
        omni_parser=_TaggedParser("screenshot", "omni"),
    )

    result = parser.parse(_image_bytes(), source_type="screenshot")

    assert result.source_type == "screenshot"
    assert result.parts[0].part_role == "omni"


def test_hybrid_falls_back_to_heuristic_when_primary_fails():
    parser = HybridLookParser(
        human_parser=_FailingParser(),
        fallback_parser=HeuristicLookParser(),
    )

    result = parser.parse(_image_bytes(), source_type="photo")
    roles = {part.part_role for part in result.parts}

    assert result.source_type == "photo"
    assert {"full-look", "top", "bottom"}.issubset(roles)


def test_hybrid_auto_detects_tall_screenshot_shape():
    parser = HybridLookParser(
        human_parser=_TaggedParser("photo", "human"),
        omni_parser=_TaggedParser("screenshot", "omni"),
    )

    result = parser.parse(_image_bytes(width=360, height=800), source_type="auto")

    assert result.source_type == "screenshot"
    assert result.parts[0].part_role == "omni"


def test_human_parser_uses_parsing_map_for_garment_parts():
    labels = np.zeros((100, 80), dtype=np.int32)
    labels[10:45, 20:60] = 5
    labels[45:90, 25:55] = 9
    labels[20:80, 30:50] = 6
    labels[8:42, 15:65] = 7

    parser = HumanLookParser(
        parsing_func=lambda image: SimpleNamespace(parsing_map=labels),
        min_mask_pixels=4,
    )

    result = parser.parse_photo(_image_bytes(width=80, height=100))
    roles = {part.part_role for part in result.parts}

    assert {"full-look", "top", "bottom", "dress", "outerwear"}.issubset(roles)
