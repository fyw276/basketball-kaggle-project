from app.services.look_parsers.base import BaseLookParser, LookParseResult
from app.services.look_parsers.heuristic_parser import HeuristicLookParser


class OmniLookParser(BaseLookParser):
    def __init__(self, fallback_parser: BaseLookParser | None = None):
        self.fallback_parser = fallback_parser or HeuristicLookParser()

    def parse_photo(self, image_bytes: bytes) -> LookParseResult:
        return self.fallback_parser.parse_photo(image_bytes)

    def parse_screenshot(self, image_bytes: bytes) -> LookParseResult:
        return self.fallback_parser.parse_screenshot(image_bytes)
