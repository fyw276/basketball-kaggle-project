from collections.abc import Callable
from io import BytesIO
from typing import Any

from PIL import Image

from app.services.look_parsers.base import (
    BaseLookParser,
    LookBlock,
    LookParseResult,
    LookPart,
    ParserUnavailable,
)
from app.services.look_parsers.heuristic_parser import HeuristicLookParser


class OmniLookParser(BaseLookParser):
    SUPPORTED_BLOCK_TYPES = {"person_look", "product_card", "garment_image"}
    PART_ROLE_BY_BLOCK_TYPE = {
        "person_look": "full-look",
        "product_card": "product-card",
        "garment_image": "garment-image",
    }

    def __init__(
        self,
        adapter: Callable[[bytes], Any] | None = None,
        fallback_parser: BaseLookParser | None = None,
    ):
        self.adapter = adapter
        self.fallback_parser = fallback_parser or HeuristicLookParser()

    def parse_photo(self, image_bytes: bytes) -> LookParseResult:
        return self.fallback_parser.parse_photo(image_bytes)

    def parse_screenshot(self, image_bytes: bytes) -> LookParseResult:
        try:
            result = self._parse_with_adapter(image_bytes)
        except ParserUnavailable:
            return self.fallback_parser.parse_screenshot(image_bytes)
        except Exception:
            return self.fallback_parser.parse_screenshot(image_bytes)

        if not result.blocks and not result.parts:
            return self.fallback_parser.parse_screenshot(image_bytes)
        return result

    def _parse_with_adapter(self, image_bytes: bytes) -> LookParseResult:
        if self.adapter is None:
            raise ParserUnavailable("OmniParser adapter is not configured")

        raw_result = self.adapter(image_bytes)
        blocks = self._normalize_blocks(raw_result)
        parts = self._parts_from_blocks(image_bytes, blocks)
        return LookParseResult(source_type="screenshot", blocks=blocks, parts=parts)

    def _normalize_blocks(self, raw_result: Any) -> list[LookBlock]:
        raw_blocks = (
            raw_result.get("blocks", raw_result) if isinstance(raw_result, dict) else raw_result
        )
        if raw_blocks is None:
            raise ParserUnavailable("OmniParser returned no blocks")
        if not isinstance(raw_blocks, list):
            raise ParserUnavailable("OmniParser returned unsupported block payload")

        blocks: list[LookBlock] = []
        for idx, item in enumerate(raw_blocks):
            if not isinstance(item, dict):
                continue
            block_type = str(item.get("block_type") or item.get("type") or "")
            if block_type not in self.SUPPORTED_BLOCK_TYPES:
                continue
            bbox = self._normalize_bbox(item.get("bbox"))
            if bbox is None:
                continue
            blocks.append(
                LookBlock(
                    block_id=str(item.get("block_id") or item.get("id") or f"{block_type}_{idx}"),
                    block_type=block_type,
                    bbox=bbox,
                    confidence=float(item.get("confidence", 0.5) or 0.0),
                )
            )
        return blocks

    def _parts_from_blocks(self, image_bytes: bytes, blocks: list[LookBlock]) -> list[LookPart]:
        if not blocks:
            return []

        parts: list[LookPart] = []
        with Image.open(BytesIO(image_bytes)) as img:
            image = img.convert("RGB")
            for block in blocks:
                role = self.PART_ROLE_BY_BLOCK_TYPE.get(block.block_type)
                if role is None:
                    continue
                bbox = self._clamp_bbox(block.bbox, image.width, image.height)
                parts.append(
                    LookPart(
                        part_role=role,
                        bbox=bbox,
                        image_bytes=self._crop_bytes(image, bbox),
                    )
                )
        return parts

    def _normalize_bbox(self, bbox: Any) -> list[int] | None:
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            return None
        try:
            x1, y1, x2, y2 = [int(round(float(value))) for value in bbox]
        except (TypeError, ValueError):
            return None
        if x2 <= x1 or y2 <= y1:
            return None
        return [x1, y1, x2, y2]

    def _clamp_bbox(self, bbox: list[int], width: int, height: int) -> list[int]:
        x1, y1, x2, y2 = bbox
        x1 = max(0, min(x1, width - 1))
        y1 = max(0, min(y1, height - 1))
        x2 = max(x1 + 1, min(x2, width))
        y2 = max(y1 + 1, min(y2, height))
        return [x1, y1, x2, y2]

    def _crop_bytes(self, image: Image.Image, bbox: list[int]) -> bytes:
        buf = BytesIO()
        image.crop(tuple(bbox)).save(buf, format="JPEG", quality=90)
        return buf.getvalue()
