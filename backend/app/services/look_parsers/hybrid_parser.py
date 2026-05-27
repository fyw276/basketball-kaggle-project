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

    def parse_photo(self, image_bytes: bytes) -> LookParseResult:
        return self.human_parser.parse_photo(image_bytes)

    def parse_screenshot(self, image_bytes: bytes) -> LookParseResult:
        return self.omni_parser.parse_screenshot(image_bytes)
