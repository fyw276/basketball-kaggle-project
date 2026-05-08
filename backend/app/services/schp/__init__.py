"""Local SCHP implementation (pirocheto/schp-lip-20).

Provides SCHPForSemanticSegmentation, SCHPConfig, and SCHPImageProcessor
without requiring the missing `schp` pip package.
"""

from .configuration_schp import SCHPConfig
from .image_processing_schp import SCHPImageProcessor
from .modeling_schp import InPlaceABNSync, SCHPForSemanticSegmentation, SCHPSemanticSegmenterOutput

__all__ = [
    "SCHPConfig",
    "SCHPImageProcessor",
    "SCHPForSemanticSegmentation",
    "SCHPSemanticSegmenterOutput",
    "InPlaceABNSync",
]
