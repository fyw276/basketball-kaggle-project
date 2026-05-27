from io import BytesIO

import numpy as np
from PIL import Image

from app.services.look_parsers.base import BaseLookParser, LookParseResult
from app.services.look_parsers.heuristic_parser import HeuristicLookParser
from app.services.look_parsers.human_parser import HumanLookParser
from app.services.look_parsers.omni_parser import OmniLookParser


class HybridLookParser(BaseLookParser):
    def __init__(
        self,
        human_parser: BaseLookParser | None = None,
        omni_parser: BaseLookParser | None = None,
        fallback_parser: BaseLookParser | None = None,
    ):
        self.fallback_parser = fallback_parser or HeuristicLookParser()
        self.human_parser = human_parser or HumanLookParser(fallback_parser=self.fallback_parser)
        self.omni_parser = omni_parser or OmniLookParser(fallback_parser=self.fallback_parser)

    def parse(self, image_bytes: bytes, source_type: str = "photo") -> LookParseResult:
        if source_type == "photo":
            return self.parse_photo(image_bytes)
        if source_type == "screenshot":
            return self.parse_screenshot(image_bytes)
        if source_type == "auto":
            return self.parse_auto(image_bytes)
        return self.parse_photo(image_bytes)

    def parse_photo(self, image_bytes: bytes) -> LookParseResult:
        try:
            return self.human_parser.parse_photo(image_bytes)
        except Exception:
            return self.fallback_parser.parse_photo(image_bytes)

    def parse_screenshot(self, image_bytes: bytes) -> LookParseResult:
        try:
            return self.omni_parser.parse_screenshot(image_bytes)
        except Exception:
            return self.fallback_parser.parse_screenshot(image_bytes)

    def parse_auto(self, image_bytes: bytes) -> LookParseResult:
        guessed_type = self._guess_source_type(image_bytes)
        if guessed_type == "screenshot":
            return self.parse_screenshot(image_bytes)
        return self.parse_photo(image_bytes)

    def _guess_source_type(self, image_bytes: bytes) -> str:
        try:
            with Image.open(BytesIO(image_bytes)) as img:
                image = img.convert("RGB")
                width, height = image.size
                aspect = width / max(height, 1)
                if aspect <= 0.62 or aspect >= 1.65:
                    return "screenshot"
                if width >= 900 and height >= 900 and self._has_screenshot_bands(image):
                    return "screenshot"
                if self._has_screenshot_edges(image):
                    return "screenshot"
        except Exception:
            return "photo"
        return "photo"

    def _has_screenshot_bands(self, image: Image.Image) -> bool:
        arr = np.asarray(image, dtype=np.float32)
        height = arr.shape[0]
        band_h = max(8, int(height * 0.06))
        top_std = float(arr[:band_h].std())
        bottom_std = float(arr[-band_h:].std())
        return top_std < 10.0 or bottom_std < 10.0

    def _has_screenshot_edges(self, image: Image.Image) -> bool:
        gray = np.asarray(image.convert("L").resize((160, 160)), dtype=np.float32)
        dx = np.abs(np.diff(gray, axis=1))
        dy = np.abs(np.diff(gray, axis=0))
        strong_vertical = float((dx > 48).mean())
        strong_horizontal = float((dy > 48).mean())
        return strong_vertical > 0.10 or strong_horizontal > 0.10
