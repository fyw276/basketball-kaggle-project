from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LookBlock:
    block_id: str
    block_type: str
    bbox: list[int]
    confidence: float


@dataclass
class LookPart:
    part_role: str
    bbox: list[int]
    image_bytes: bytes
    category: Optional[str] = None
    style_tags: list[str] = field(default_factory=list)
    main_color: Optional[dict] = None
    feature_vector: list[float] = field(default_factory=list)


@dataclass
class LookParseResult:
    source_type: str
    blocks: list[LookBlock]
    parts: list[LookPart]


class BaseLookParser(ABC):
    def parse(self, image_bytes: bytes, source_type: str = "photo") -> LookParseResult:
        if source_type == "screenshot":
            return self.parse_screenshot(image_bytes)
        if source_type == "auto":
            return self.parse_auto(image_bytes)
        return self.parse_photo(image_bytes)

    def parse_auto(self, image_bytes: bytes) -> LookParseResult:
        return self.parse_photo(image_bytes)

    @abstractmethod
    def parse_photo(self, image_bytes: bytes) -> LookParseResult:
        raise NotImplementedError

    @abstractmethod
    def parse_screenshot(self, image_bytes: bytes) -> LookParseResult:
        raise NotImplementedError
