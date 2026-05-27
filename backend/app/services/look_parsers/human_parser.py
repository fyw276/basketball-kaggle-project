from io import BytesIO
from typing import Callable

import numpy as np
from PIL import Image

from app.services.look_parsers.base import BaseLookParser, LookBlock, LookParseResult, LookPart
from app.services.look_parsers.heuristic_parser import HeuristicLookParser


class _ProportionalParsing:
    def __init__(self, image: Image.Image):
        width, height = image.size
        labels = np.zeros((height, width), dtype=np.int32)

        margin_x = int(width * 0.08)
        y1 = int(height * 0.04)
        y2 = int(height * 0.96)
        x1 = margin_x
        x2 = width - margin_x

        top_y2 = y1 + int((y2 - y1) * 0.52)
        bottom_y1 = y1 + int((y2 - y1) * 0.45)
        labels[y1:top_y2, x1:x2] = 5
        labels[bottom_y1:y2, x1:x2] = 9
        self.parsing_map = labels


class HumanLookParser(BaseLookParser):
    def __init__(
        self,
        fallback_parser: BaseLookParser | None = None,
        parsing_func: Callable[[Image.Image], object] | None = None,
        min_mask_pixels: int = 64,
    ):
        self.fallback_parser = fallback_parser or HeuristicLookParser()
        self.parsing_func = parsing_func
        self.min_mask_pixels = min_mask_pixels

    @classmethod
    def from_schp(
        cls,
        fallback_parser: BaseLookParser | None = None,
        min_mask_pixels: int = 64,
    ) -> "HumanLookParser":
        from app.services.human_parsing import schp_parse

        return cls(
            fallback_parser=fallback_parser,
            parsing_func=schp_parse,
            min_mask_pixels=min_mask_pixels,
        )

    def parse_photo(self, image_bytes: bytes) -> LookParseResult:
        try:
            with Image.open(BytesIO(image_bytes)) as img:
                image = img.convert("RGB")
                parsing = self._parse_human(image)
                blocks, parts = self._parts_from_parsing(image, parsing)
            if not parts:
                return self.fallback_parser.parse_photo(image_bytes)
            return LookParseResult(source_type="photo", blocks=blocks, parts=parts)
        except Exception:
            return self.fallback_parser.parse_photo(image_bytes)

    def parse_screenshot(self, image_bytes: bytes) -> LookParseResult:
        result = self.parse_photo(image_bytes)
        return LookParseResult(
            source_type="screenshot",
            blocks=result.blocks,
            parts=result.parts,
        )

    def _parse_human(self, image: Image.Image):
        if self.parsing_func is not None:
            return self.parsing_func(image)
        return _ProportionalParsing(image)

    def _parts_from_parsing(
        self, image: Image.Image, parsing
    ) -> tuple[list[LookBlock], list[LookPart]]:
        parsing_map = getattr(parsing, "parsing_map", None)
        if parsing_map is None:
            return [], []

        labels = np.asarray(parsing_map)
        full_mask = labels > 0
        full_bbox = self._mask_bbox(full_mask, image.size)
        if full_bbox is None:
            return [], []

        blocks = [
            LookBlock(
                block_id="look_0",
                block_type="person_look",
                bbox=full_bbox,
                confidence=0.75,
            )
        ]

        specs = [
            ("full-look", full_mask),
            ("top", np.isin(labels, [5])),
            ("bottom", np.isin(labels, [9, 12])),
            ("dress", np.isin(labels, [6, 10])),
            ("outerwear", np.isin(labels, [7])),
        ]

        parts: list[LookPart] = []
        for role, mask in specs:
            bbox = self._mask_bbox(mask, image.size)
            if bbox is None:
                continue
            parts.append(
                LookPart(
                    part_role=role,
                    bbox=bbox,
                    image_bytes=self._crop_bytes(image, bbox),
                )
            )
        return blocks, parts

    def _mask_bbox(self, mask: np.ndarray, image_size: tuple[int, int]) -> list[int] | None:
        if int(mask.sum()) < self.min_mask_pixels:
            return None

        width, height = image_size
        ys, xs = np.where(mask)
        if xs.size == 0 or ys.size == 0:
            return None

        pad_x = max(2, int(width * 0.02))
        pad_y = max(2, int(height * 0.02))
        x1 = max(0, int(xs.min()) - pad_x)
        y1 = max(0, int(ys.min()) - pad_y)
        x2 = min(width, int(xs.max()) + pad_x + 1)
        y2 = min(height, int(ys.max()) + pad_y + 1)
        if x2 <= x1 or y2 <= y1:
            return None
        return [x1, y1, x2, y2]

    def _crop_bytes(self, image: Image.Image, bbox: list[int]) -> bytes:
        buf = BytesIO()
        image.crop(tuple(bbox)).save(buf, format="JPEG", quality=90)
        return buf.getvalue()
