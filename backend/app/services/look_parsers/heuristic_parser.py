from io import BytesIO

from PIL import Image

from app.services.look_parsers.base import BaseLookParser, LookBlock, LookParseResult, LookPart


class HeuristicLookParser(BaseLookParser):
    def parse_photo(self, image_bytes: bytes) -> LookParseResult:
        blocks = self._extract_full_look_block(image_bytes)
        parts: list[LookPart] = []
        for block in blocks:
            parts.extend(self._split_person_look_into_parts(image_bytes, block.bbox))
        return LookParseResult(source_type="photo", blocks=blocks, parts=parts)

    def parse_screenshot(self, image_bytes: bytes) -> LookParseResult:
        blocks = self._extract_full_look_block(image_bytes)
        parts: list[LookPart] = []
        for block in blocks:
            parts.extend(self._split_person_look_into_parts(image_bytes, block.bbox))
        return LookParseResult(source_type="screenshot", blocks=blocks, parts=parts)

    def _extract_full_look_block(self, image_bytes: bytes) -> list[LookBlock]:
        width, height = self._image_size(image_bytes)
        margin_x = int(width * 0.08)
        margin_y = int(height * 0.04)
        return [
            LookBlock(
                block_id="look_0",
                block_type="person_look",
                bbox=[margin_x, margin_y, width - margin_x, height - margin_y],
                confidence=0.5,
            )
        ]

    def _split_person_look_into_parts(self, image_bytes: bytes, bbox: list[int]) -> list[LookPart]:
        with Image.open(BytesIO(image_bytes)) as img:
            img = img.convert("RGB")
            x1, y1, x2, y2 = self._clamp_bbox(bbox, img.width, img.height)
            look_height = y2 - y1
            top_y2 = y1 + int(look_height * 0.52)
            bottom_y1 = y1 + int(look_height * 0.45)

            parts = [
                ("full-look", [x1, y1, x2, y2]),
                ("top", [x1, y1, x2, top_y2]),
                ("bottom", [x1, bottom_y1, x2, y2]),
            ]
            return [
                LookPart(
                    part_role=role,
                    bbox=part_bbox,
                    image_bytes=self._crop_bytes(img, part_bbox),
                )
                for role, part_bbox in parts
            ]

    def _image_size(self, image_bytes: bytes) -> tuple[int, int]:
        with Image.open(BytesIO(image_bytes)) as img:
            return img.width, img.height

    def _clamp_bbox(self, bbox: list[int], width: int, height: int) -> list[int]:
        x1, y1, x2, y2 = bbox
        x1 = max(0, min(x1, width - 1))
        y1 = max(0, min(y1, height - 1))
        x2 = max(x1 + 1, min(x2, width))
        y2 = max(y1 + 1, min(y2, height))
        return [x1, y1, x2, y2]

    def _crop_bytes(self, img: Image.Image, bbox: list[int]) -> bytes:
        buf = BytesIO()
        img.crop(tuple(bbox)).save(buf, format="JPEG", quality=90)
        return buf.getvalue()
