import io
from types import SimpleNamespace

from PIL import Image

from app.services.look_parsers import HybridLookParser


def _image_bytes(width=320, height=480):
    buf = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(buf, format="JPEG")
    return buf.getvalue()


class _TaggedParser:
    def __init__(self, role):
        self.role = role

    def parse_photo(self, image_bytes):
        return self._result("photo")

    def parse_screenshot(self, image_bytes):
        return self._result("screenshot")

    def _result(self, source_type):
        return SimpleNamespace(
            source_type=source_type,
            blocks=[],
            parts=[SimpleNamespace(part_role=self.role, bbox=[0, 0, 1, 1], image_bytes=b"x")],
        )


def test_photo_prefers_human_parser():
    parser = HybridLookParser(
        human_parser=_TaggedParser("human"),
        omni_parser=_TaggedParser("omni"),
    )

    result = parser.parse(_image_bytes(), source_type="photo")

    assert result.source_type == "photo"
    assert result.parts[0].part_role == "human"


def test_screenshot_prefers_omni_parser():
    parser = HybridLookParser(
        human_parser=_TaggedParser("human"),
        omni_parser=_TaggedParser("omni"),
    )

    result = parser.parse(_image_bytes(), source_type="screenshot")

    assert result.source_type == "screenshot"
    assert result.parts[0].part_role == "omni"
