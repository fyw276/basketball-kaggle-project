import io

from PIL import Image

from app.services.look_parsers import HeuristicLookParser, HybridLookParser, OmniLookParser


def _image_bytes(width=320, height=480):
    buf = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(buf, format="JPEG")
    return buf.getvalue()


class _FailingParser:
    def parse_photo(self, image_bytes):
        raise RuntimeError("boom")

    def parse_screenshot(self, image_bytes):
        raise RuntimeError("boom")


def test_photo_human_failure_falls_back_to_heuristic_parts():
    parser = HybridLookParser(
        human_parser=_FailingParser(),
        fallback_parser=HeuristicLookParser(),
    )

    result = parser.parse(_image_bytes(), source_type="photo")
    roles = {part.part_role for part in result.parts}

    assert result.source_type == "photo"
    assert {"full-look", "top", "bottom"}.issubset(roles)


def test_screenshot_omni_failure_falls_back_to_heuristic_parts():
    parser = HybridLookParser(
        omni_parser=_FailingParser(),
        fallback_parser=HeuristicLookParser(),
    )

    result = parser.parse(_image_bytes(), source_type="screenshot")
    roles = {part.part_role for part in result.parts}

    assert result.source_type == "screenshot"
    assert {"full-look", "top", "bottom"}.issubset(roles)


def test_omni_unavailable_returns_heuristic_parts():
    result = OmniLookParser().parse_screenshot(_image_bytes())
    roles = {part.part_role for part in result.parts}

    assert result.source_type == "screenshot"
    assert {"full-look", "top", "bottom"}.issubset(roles)
